from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.utils import timezone
from django.conf import settings
import dateutil.parser as dateparser
import json
import base64
import io

from transactions.models import Transaction, Category, BankAccount
from .sms_engine import parse_sms_batch, categorize_merchant
from .pdf_engine import parse_pdf_statement, debug_extract_pdf_text


GEMINI_PROMPT = """Extract ALL financial transactions from these pages of a bank/UPI statement PDF.

Return ONLY a valid JSON array, no other text. Each object must have exactly:
{"date":"YYYY-MM-DD","amount":123.45,"transaction_type":"debit","narration":"description","merchant_name":"name or empty","reference_number":"UPI ID or empty"}

Rules:
- debit = money OUT (Paid to, Sent to, purchase, withdrawal)
- credit = money IN (Received from, salary, refund, cashback)
- Extract EVERY transaction — do not skip any
- Skip only page headers, column headers, balance summary lines
- Return [] if no transactions on these pages"""


def _call_gemini_on_file(client, tmp_path, bank_name, page_info=""):
    """Upload one PDF chunk to Gemini and return parsed list."""
    from google.genai import types
    uploaded = None
    try:
        uploaded = client.files.upload(
            file=tmp_path,
            config=types.UploadFileConfig(mime_type="application/pdf"),
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded, GEMINI_PROMPT],
        )
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except Exception as e:
        print(f"[Gemini] chunk error {page_info}: {e}")
        return []
    finally:
        if uploaded:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass


def parse_with_gemini(pdf_bytes, bank_name):
    """
    Split PDF into batches of 5 pages, send each to Gemini separately.
    Combines all results. Fast and avoids timeout on large PDFs.
    """
    import tempfile, os
    try:
        import pikepdf
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Split PDF into 5-page chunks using pikepdf
        src = pikepdf.open(io.BytesIO(pdf_bytes))
        total_pages = len(src.pages)
        batch_size = 5
        chunks = []
        for start in range(0, total_pages, batch_size):
            end = min(start + batch_size, total_pages)
            dst = pikepdf.Pdf.new()
            for i in range(start, end):
                dst.pages.append(src.pages[i])
            buf = io.BytesIO()
            dst.save(buf)
            chunks.append((start + 1, end, buf.getvalue()))
        src.close()

        print(f"[Gemini] Processing {bank_name} PDF: {total_pages} pages in {len(chunks)} batches")

        all_results = []
        for page_from, page_to, chunk_bytes in chunks:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(chunk_bytes)
                tmp_path = tmp.name
            try:
                items = _call_gemini_on_file(client, tmp_path, bank_name, f"pages {page_from}-{page_to}")
                print(f"[Gemini] pages {page_from}-{page_to}: {len(items)} transactions")
            finally:
                os.unlink(tmp_path)

            for item in items:
                try:
                    amount = float(item.get("amount", 0))
                    if amount <= 0:
                        continue
                    all_results.append({
                        "amount": amount,
                        "transaction_type": item.get("transaction_type", "debit"),
                        "narration": str(item.get("narration", ""))[:300],
                        "date": item.get("date", timezone.now().strftime("%Y-%m-%d")),
                        "bank_name": bank_name,
                        "merchant_name": str(item.get("merchant_name", ""))[:100],
                        "reference_number": str(item.get("reference_number", ""))[:100],
                    })
                except Exception:
                    continue

        print(f"[Gemini] Total extracted: {len(all_results)} transactions from {bank_name}")
        return all_results

    except Exception as e:
        print(f"[Gemini] Fatal error: {e}")
        return []


def get_or_create_category(name):
    cat, _ = Category.objects.get_or_create(
        name=name,
        is_default=True,
        user=None,
        defaults={"icon": "receipt", "color": "#6B7280"},
    )
    return cat


def build_dedup_key(txn_dict, user_id):
    ref = txn_dict.get("reference_number", "")
    if ref:
        return f"{user_id}:{ref}"
    return f"{user_id}:{txn_dict['amount']}:{txn_dict['date'][:10]}:{txn_dict.get('account_last4','')}"


class SMSParseView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        sms_list = request.data.get("sms_list", [])
        if not isinstance(sms_list, list):
            return Response({"error": "sms_list must be an array"}, status=400)
        if len(sms_list) > 500:
            return Response({"error": "Max 500 SMS per request"}, status=400)

        parsed = parse_sms_batch(sms_list)
        imported = 0
        duplicates = 0
        errors = 0

        for txn_data in parsed:
            try:
                dedup_key = build_dedup_key(txn_data, request.user.id)
                ref = txn_data.get("reference_number", "")

                # Check duplicate by reference number
                if ref and Transaction.objects.filter(
                    user=request.user, reference_number=ref
                ).exists():
                    duplicates += 1
                    continue

                # Check duplicate by amount+date+account
                try:
                    txn_date = dateparser.parse(txn_data["date"])
                except Exception:
                    txn_date = timezone.now()

                if Transaction.objects.filter(
                    user=request.user,
                    amount=txn_data["amount"],
                    date__date=txn_date.date() if txn_date else None,
                    account_last4=txn_data.get("account_last4", ""),
                    bank_name=txn_data.get("bank_name", ""),
                ).exists():
                    duplicates += 1
                    continue

                category = get_or_create_category(txn_data.get("category_name", "Other"))

                Transaction.objects.create(
                    user=request.user,
                    amount=txn_data["amount"],
                    transaction_type=txn_data["transaction_type"],
                    category=category,
                    date=txn_date or timezone.now(),
                    narration=txn_data.get("narration", ""),
                    merchant_name=txn_data.get("merchant_name", ""),
                    reference_number=ref,
                    account_last4=txn_data.get("account_last4", ""),
                    bank_name=txn_data.get("bank_name", ""),
                    source=Transaction.SOURCE_SMS,
                    raw_text=txn_data.get("raw_text", ""),
                )
                imported += 1
            except Exception as e:
                errors += 1
                print(f"SMS import error: {e}")

        return Response({
            "imported": imported,
            "duplicates": duplicates,
            "errors": errors,
            "total_parsed": len(parsed),
        })


class PDFParseView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        pdf_file = request.FILES.get("file")
        bank_name = request.data.get("bank_name", "")
        password = request.data.get("password", None)

        if not pdf_file:
            return Response({"error": "No PDF file provided"}, status=400)
        if not bank_name:
            return Response({"error": "bank_name is required"}, status=400)
        if pdf_file.size > 10 * 1024 * 1024:
            return Response({"error": "File too large (max 10MB)"}, status=400)

        pdf_bytes = pdf_file.read()
        parsed_transactions = []
        try:
            # Step 1: Gemini (primary) — batched by 5 pages, handles any PDF format
            if settings.GEMINI_API_KEY:
                parsed_transactions = parse_with_gemini(pdf_bytes, bank_name)

            # Step 2: pdfplumber fallback if Gemini got nothing
            if not parsed_transactions:
                print(f"[PDF] Gemini empty, trying pdfplumber for {bank_name}")
                parsed_transactions = parse_pdf_statement(pdf_bytes, bank_name, password)
                print(f"[PDF] pdfplumber found {len(parsed_transactions)} transactions")

        except Exception as e:
            print(f"[PDF] Error: {e}")
            try:
                parsed_transactions = parse_pdf_statement(pdf_bytes, bank_name, password)
            except Exception:
                pass
        finally:
            password = None

        if not parsed_transactions:
            return Response({
                "error": "No transactions found. Try selecting a different bank or upload a bank statement (not UPI app export).",
                "imported": 0,
                "hint": "GPay/PhonePe exports may not contain full transaction data. Try your bank's official statement PDF instead.",
            }, status=400)

        imported = 0
        duplicates = 0
        errors = 0

        for txn_data in parsed_transactions:
            try:
                try:
                    txn_date = dateparser.parse(txn_data["date"])
                except Exception:
                    txn_date = timezone.now()

                ref = txn_data.get("reference_number", "")
                if ref and Transaction.objects.filter(user=request.user, reference_number=ref).exists():
                    duplicates += 1
                    continue
                if Transaction.objects.filter(
                    user=request.user,
                    amount=txn_data["amount"],
                    date__date=txn_date.date() if txn_date else None,
                    bank_name__icontains=bank_name[:10],
                ).exists():
                    duplicates += 1
                    continue

                from .sms_engine import categorize_merchant
                category_name = categorize_merchant(
                    txn_data.get("merchant_name", ""),
                    txn_data.get("narration", ""),
                )
                category = get_or_create_category(category_name)

                Transaction.objects.create(
                    user=request.user,
                    amount=txn_data["amount"],
                    transaction_type=txn_data["transaction_type"],
                    category=category,
                    date=txn_date or timezone.now(),
                    narration=txn_data.get("narration", ""),
                    merchant_name=txn_data.get("merchant_name", ""),
                    reference_number=txn_data.get("reference_number", ""),
                    bank_name=txn_data.get("bank_name", bank_name),
                    source=Transaction.SOURCE_PDF,
                )
                imported += 1
            except Exception as e:
                errors += 1
                print(f"PDF import error: {e}")

        return Response({
            "imported": imported,
            "duplicates": duplicates,
            "errors": errors,
            "total_parsed": len(parsed_transactions),
        })


class PDFDebugView(APIView):
    """Debug endpoint — shows raw extracted text from PDF. Beta only."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        pdf_file = request.FILES.get("file")
        if not pdf_file:
            return Response({"error": "No file"}, status=400)
        pdf_bytes = pdf_file.read()
        result = debug_extract_pdf_text(pdf_bytes)
        return Response(result)


class RecategorizeMerchantView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        transaction_id = request.data.get("transaction_id")
        category_id = request.data.get("category_id")
        try:
            txn = Transaction.objects.get(id=transaction_id, user=request.user)
            category = Category.objects.get(id=category_id)
            txn.category = category
            txn.save(update_fields=["category"])
            return Response({"message": "Category updated"})
        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found"}, status=404)
        except Category.DoesNotExist:
            return Response({"error": "Category not found"}, status=404)
