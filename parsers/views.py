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


GEMINI_PROMPT = """Extract ALL individual financial transactions from this bank/UPI statement text.

Return ONLY a valid JSON array, no other text. Each object must have exactly:
{"date":"YYYY-MM-DD","amount":123.45,"transaction_type":"debit","narration":"description","merchant_name":"name or empty","reference_number":"UPI ID or empty"}

Rules:
- debit = money OUT (Paid to, Sent to, purchase, withdrawal, Dr)
- credit = money IN (Received from, salary, refund, cashback, Cr)
- Each transaction must have its own DATE — lines like "01Feb,2026 Paid to ARATI 2000" are individual transactions
- SKIP: page headers, statement period summary (e.g. "Total Sent: 81420"), column headers
- A summary line like "01February2026-28February2026 81,420.86 48,392.35" is NOT a transaction — skip it
- Extract EVERY individual transaction line — do not skip any real transaction
- Return [] if no transactions found"""


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
            model="gemini-2.5-flash-lite",
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


def _call_gemini_text_batch(client, prompt, bank_name, page_info):
    """Call Gemini with a text prompt and return parsed transaction list."""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        items = json.loads(text)
        result = items if isinstance(items, list) else []
        print(f"[Gemini] {page_info}: {len(result)} transactions")
        return result
    except Exception as e:
        print(f"[Gemini] {page_info} error: {e}")
        return []


def parse_with_gemini(pdf_bytes, bank_name):
    """
    Extract all text from PDF with pdfplumber, then send to Gemini.
    - Under 8000 chars: single call (fastest)
    - Over 8000 chars: parallel batches of 10 pages
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    try:
        import pdfplumber
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Extract all text at once
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_pages = len(pdf.pages)
            for page in pdf.pages:
                pages_text.append(page.extract_text() or "")

        full_text = "\n\n--- PAGE BREAK ---\n\n".join(pages_text)
        print(f"[Gemini] {bank_name}: {total_pages} pages, {len(full_text)} chars")

        def parse_text_chunk(text_chunk, page_info):
            prompt = GEMINI_PROMPT + f"\n\nBank: {bank_name}\n\n" + text_chunk
            return _call_gemini_text_batch(client, prompt, bank_name, page_info)

        # Always use parallel batches of 3 pages — avoids Gemini response truncation
        if False:
            all_items = []  # never used
        else:
            batch_size = 3
            batches = []
            for batch_start in range(0, total_pages, batch_size):
                batch_end = min(batch_start + batch_size, total_pages)
                batch_text = "\n\n--- PAGE BREAK ---\n\n".join(pages_text[batch_start:batch_end])
                page_info = f"pages {batch_start+1}-{batch_end}"
                batches.append((batch_text, page_info, batch_start))

            print(f"[Gemini] {len(batches)} parallel batches of {batch_size} pages each")
            batch_results = {}
            with ThreadPoolExecutor(max_workers=min(len(batches), 5)) as executor:
                futures = {
                    executor.submit(parse_text_chunk, text, page_info): batch_start
                    for text, page_info, batch_start in batches
                }
                for future in as_completed(futures):
                    batch_start = futures[future]
                    try:
                        batch_results[batch_start] = future.result()
                    except Exception as e:
                        print(f"[Gemini] batch {batch_start} failed: {e}")
                        batch_results[batch_start] = []

            all_items = []
            for _, _, batch_start in batches:
                all_items.extend(batch_results.get(batch_start, []))

        # Normalize
        all_results = []
        for item in all_items:
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


SMS_GEMINI_PROMPT = """You are a bank SMS parser. Extract financial transactions from the SMS messages below.

Return ONLY a valid JSON array, no other text. Each object must have exactly these fields:
{"date":"YYYY-MM-DD","amount":123.45,"transaction_type":"debit","narration":"full sms body","merchant_name":"merchant or empty string","reference_number":"UPI ref/txn ID or empty string","bank_name":"bank name or empty string","account_last4":"last 4 digits or empty string"}

Rules:
- debit = money OUT (debited, paid, sent, purchase, withdrawn, dr)
- credit = money IN (credited, received, salary, refund, cashback, cr)
- amount must be positive number only
- Skip OTP, promotional, balance alerts with no transaction
- Return [] if no transactions found

SMS messages:
"""


def parse_sms_with_gemini(sms_list):
    """Use Gemini to parse SMS list. Falls back to regex on error."""
    try:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        all_results = []
        batch_size = 50
        for i in range(0, len(sms_list), batch_size):
            batch = sms_list[i:i + batch_size]
            sms_text = "\n\n".join([
                f"[{idx+1}] From: {s.get('sender','')}\n{s.get('body','')}"
                for idx, s in enumerate(batch)
            ])
            prompt = SMS_GEMINI_PROMPT + sms_text
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents=prompt,
                )
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    all_results.extend(parsed)
                    print(f"[SMS Gemini] batch {i//batch_size+1}: {len(parsed)} transactions")
            except Exception as e:
                print(f"[SMS Gemini] batch error: {e}, using regex fallback")
                all_results.extend(parse_sms_batch(batch))

        return all_results
    except Exception as e:
        print(f"[SMS Gemini] Fatal: {e}, using regex fallback")
        return parse_sms_batch(sms_list)


class SMSParseView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        sms_list = request.data.get("sms_list", [])
        if not isinstance(sms_list, list):
            return Response({"error": "sms_list must be an array"}, status=400)
        if len(sms_list) > 500:
            return Response({"error": "Max 500 SMS per request"}, status=400)

        # Use Gemini if available, else regex
        if settings.GEMINI_API_KEY:
            parsed = parse_sms_with_gemini(sms_list)
        else:
            parsed = parse_sms_batch(sms_list)

        imported = 0
        duplicates = 0
        errors = 0

        for txn_data in parsed:
            try:
                amount = float(txn_data.get("amount", 0))
                if amount <= 0:
                    continue

                ref = str(txn_data.get("reference_number", "")).strip()

                # Dedup by reference number (most reliable)
                if ref and Transaction.objects.filter(
                    user=request.user, reference_number=ref
                ).exists():
                    print(f"[SMS dedup] skipped by ref={ref}")
                    duplicates += 1
                    continue

                try:
                    txn_date = dateparser.parse(str(txn_data.get("date", "")))
                    if txn_date and txn_date.tzinfo is None:
                        import pytz
                        txn_date = pytz.timezone("Asia/Kolkata").localize(txn_date)
                except Exception:
                    txn_date = timezone.now()

                # Fuzzy dedup only when we have enough identifying info
                account_last4 = str(txn_data.get("account_last4", "")).strip()
                bank_name = str(txn_data.get("bank_name", "")).strip()
                narration = str(txn_data.get("narration", "")).strip()

                if account_last4 and bank_name and Transaction.objects.filter(
                    user=request.user,
                    amount=amount,
                    date__date=txn_date.date() if txn_date else None,
                    account_last4=account_last4,
                    bank_name=bank_name,
                ).exists():
                    print(f"[SMS dedup] skipped by amount+date+account: {amount} {account_last4} {bank_name}")
                    duplicates += 1
                    continue

                category_name = categorize_merchant(
                    txn_data.get("merchant_name", ""),
                    txn_data.get("narration", ""),
                )
                category = get_or_create_category(category_name)

                Transaction.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type=txn_data.get("transaction_type", "debit"),
                    category=category,
                    date=txn_date or timezone.now(),
                    narration=str(txn_data.get("narration", ""))[:500],
                    merchant_name=str(txn_data.get("merchant_name", ""))[:100],
                    reference_number=ref[:100],
                    account_last4=str(txn_data.get("account_last4", ""))[:4],
                    bank_name=str(txn_data.get("bank_name", ""))[:100],
                    source=Transaction.SOURCE_SMS,
                    raw_text=str(txn_data.get("narration", ""))[:1000],
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
