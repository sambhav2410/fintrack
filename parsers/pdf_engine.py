import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
import pytz

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pikepdf
    HAS_PIKEPDF = True
except ImportError:
    HAS_PIKEPDF = False

IST = pytz.timezone("Asia/Kolkata")

BANK_DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
    "%d %b %Y", "%d-%b-%Y", "%d/%b/%Y", "%d %b %y",
]


def parse_date_str(date_str):
    date_str = date_str.strip()
    for fmt in BANK_DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return IST.localize(dt)
        except ValueError:
            continue
    return None


def clean_amount(amount_str):
    if not amount_str:
        return None
    cleaned = re.sub(r"[^\d\.]", "", str(amount_str).strip())
    if not cleaned:
        return None
    try:
        val = Decimal(cleaned)
        return val if val > 0 else None
    except InvalidOperation:
        return None


def decrypt_pdf(pdf_bytes, password=None):
    if not HAS_PIKEPDF:
        return pdf_bytes
    if not password:
        return pdf_bytes
    try:
        pdf_in = pikepdf.open(io.BytesIO(pdf_bytes), password=password)
        output = io.BytesIO()
        pdf_in.save(output)
        return output.getvalue()
    except Exception:
        return pdf_bytes


def parse_hdfc_statement(pdf_bytes, password=None):
    pdf_bytes = decrypt_pdf(pdf_bytes, password)
    transactions = []
    if not HAS_PDFPLUMBER:
        return transactions
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 5:
                            continue
                        date_str = str(row[0]).strip() if row[0] else ""
                        narration = str(row[1]).strip() if row[1] else ""
                        withdrawal = clean_amount(row[3]) if len(row) > 3 else None
                        deposit = clean_amount(row[4]) if len(row) > 4 else None
                        date = parse_date_str(date_str)
                        if not date or (not withdrawal and not deposit):
                            continue
                        if withdrawal:
                            transactions.append({
                                "amount": float(withdrawal),
                                "transaction_type": "debit",
                                "narration": narration,
                                "date": date.isoformat(),
                                "bank_name": "HDFC Bank",
                                "merchant_name": extract_merchant_from_narration(narration),
                            })
                        if deposit:
                            transactions.append({
                                "amount": float(deposit),
                                "transaction_type": "credit",
                                "narration": narration,
                                "date": date.isoformat(),
                                "bank_name": "HDFC Bank",
                                "merchant_name": extract_merchant_from_narration(narration),
                            })
    except Exception as e:
        print(f"HDFC parse error: {e}")
    return transactions


def parse_icici_statement(pdf_bytes, password=None):
    pdf_bytes = decrypt_pdf(pdf_bytes, password)
    transactions = []
    if not HAS_PDFPLUMBER:
        return transactions
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 4:
                            continue
                        date_str = str(row[0]).strip() if row[0] else ""
                        narration = str(row[1]).strip() if row[1] else ""
                        amount_str = str(row[2]).strip() if row[2] else ""
                        dr_cr = str(row[3]).strip().upper() if len(row) > 3 and row[3] else ""
                        amount = clean_amount(amount_str)
                        date = parse_date_str(date_str)
                        if not date or not amount:
                            continue
                        txn_type = "debit" if "DR" in dr_cr or "DEBIT" in dr_cr else "credit"
                        transactions.append({
                            "amount": float(amount),
                            "transaction_type": txn_type,
                            "narration": narration,
                            "date": date.isoformat(),
                            "bank_name": "ICICI Bank",
                            "merchant_name": extract_merchant_from_narration(narration),
                        })
    except Exception as e:
        print(f"ICICI parse error: {e}")
    return transactions


def parse_sbi_statement(pdf_bytes, password=None):
    pdf_bytes = decrypt_pdf(pdf_bytes, password)
    transactions = []
    if not HAS_PDFPLUMBER:
        return transactions
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += (page.extract_text() or "") + "\n"
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 5:
                            continue
                        date_str = str(row[0]).strip() if row[0] else ""
                        narration = str(row[1]).strip() if len(row) > 1 and row[1] else ""
                        debit = clean_amount(row[3]) if len(row) > 3 else None
                        credit = clean_amount(row[4]) if len(row) > 4 else None
                        date = parse_date_str(date_str)
                        if not date or (not debit and not credit):
                            continue
                        if debit:
                            transactions.append({
                                "amount": float(debit),
                                "transaction_type": "debit",
                                "narration": narration,
                                "date": date.isoformat(),
                                "bank_name": "SBI",
                                "merchant_name": extract_merchant_from_narration(narration),
                            })
                        if credit:
                            transactions.append({
                                "amount": float(credit),
                                "transaction_type": "credit",
                                "narration": narration,
                                "date": date.isoformat(),
                                "bank_name": "SBI",
                                "merchant_name": extract_merchant_from_narration(narration),
                            })
    except Exception as e:
        print(f"SBI parse error: {e}")
    return transactions


def parse_axis_statement(pdf_bytes, password=None):
    return _parse_generic_statement(pdf_bytes, "Axis Bank", password)


def parse_kotak_statement(pdf_bytes, password=None):
    return _parse_generic_statement(pdf_bytes, "Kotak Bank", password)


def _parse_generic_statement(pdf_bytes, bank_name, password=None):
    pdf_bytes = decrypt_pdf(pdf_bytes, password)
    transactions = []
    if not HAS_PDFPLUMBER:
        return transactions
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 4:
                            continue
                        date_str = str(row[0]).strip() if row[0] else ""
                        narration = str(row[1]).strip() if len(row) > 1 and row[1] else ""
                        withdrawal = clean_amount(row[-3]) if len(row) >= 3 else None
                        deposit = clean_amount(row[-2]) if len(row) >= 2 else None
                        date = parse_date_str(date_str)
                        if not date or (not withdrawal and not deposit):
                            continue
                        if withdrawal:
                            transactions.append({
                                "amount": float(withdrawal),
                                "transaction_type": "debit",
                                "narration": narration,
                                "date": date.isoformat(),
                                "bank_name": bank_name,
                                "merchant_name": extract_merchant_from_narration(narration),
                            })
                        if deposit:
                            transactions.append({
                                "amount": float(deposit),
                                "transaction_type": "credit",
                                "narration": narration,
                                "date": date.isoformat(),
                                "bank_name": bank_name,
                                "merchant_name": extract_merchant_from_narration(narration),
                            })
    except Exception as e:
        print(f"{bank_name} parse error: {e}")
    return transactions


def extract_merchant_from_narration(narration):
    if not narration:
        return ""
    upi_match = re.search(r"UPI[/-]([^/\-]+)[/-]", narration, re.IGNORECASE)
    if upi_match:
        return upi_match.group(1).strip()[:100]
    parts = narration.split("/")
    if len(parts) >= 2:
        candidate = parts[1].strip()
        if len(candidate) > 2 and not candidate.isdigit():
            return candidate[:100]
    return narration[:50]


def parse_gpay_statement(pdf_bytes, password=None):
    """
    Parse Google Pay transaction history PDF.

    GPay PDF table format (3 columns per row):
      Col 0: "01 Feb, 2026\n09:30 AM"
      Col 1: "Paid to ARATI\nUPI Transaction ID: 639896373956\nPaid by AU Small Finance Bank 6439"
      Col 2: "₹2,000"
    """
    pdf_bytes = decrypt_pdf(pdf_bytes, password)
    transactions = []
    if not HAS_PDFPLUMBER:
        return transactions
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 3:
                            continue

                        date_cell = str(row[0] or "").strip()
                        detail_cell = str(row[1] or "").strip()
                        amount_cell = str(row[2] or "").strip()

                        # Skip header rows
                        if not amount_cell or "amount" in amount_cell.lower():
                            continue

                        amount = extract_amount_from_text(amount_cell)
                        if not amount:
                            continue

                        # Parse date from first cell: "01 Feb, 2026\n09:30 AM" or "01 Feb, 2026"
                        date_line = date_cell.replace("\n", " ").strip()
                        date = parse_date_from_text(date_line)

                        # Parse transaction type and merchant from detail cell
                        detail_lower = detail_cell.lower()
                        is_debit = any(k in detail_lower for k in ["paid to", "sent to", "payment to", "transferred to"])
                        is_credit = any(k in detail_lower for k in ["received from", "refund", "cashback"])

                        # Extract merchant name (first line of detail cell)
                        lines = detail_cell.split("\n")
                        first_line = lines[0].strip() if lines else detail_cell

                        merchant = ""
                        for prefix in ["Paid to ", "Sent to ", "Payment to ", "Received from ", "Transferred to "]:
                            if first_line.startswith(prefix):
                                merchant = first_line[len(prefix):].strip()[:100]
                                break

                        # Extract UPI reference
                        upi_match = re.search(r"UPI Transaction ID:\s*(\d+)", detail_cell)
                        reference = upi_match.group(1) if upi_match else ""

                        transactions.append({
                            "amount": float(amount),
                            "transaction_type": "debit" if is_debit else "credit",
                            "narration": first_line[:300],
                            "date": date.isoformat(),
                            "bank_name": "Google Pay",
                            "merchant_name": merchant,
                            "reference_number": reference,
                        })

        print(f"[GPay] Extracted {len(transactions)} transactions from table parser")

        # Fallback: text-based parsing if table extraction got nothing
        if not transactions:
            transactions = _parse_gpay_text_fallback(pdf_bytes)

    except Exception as e:
        print(f"GPay parse error: {e}")
    return transactions


def _parse_gpay_text_fallback(pdf_bytes):
    """Text-based fallback for GPay PDFs where table extraction fails."""
    transactions = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += (page.extract_text() or "") + "\n"

        # Each transaction block looks like:
        # "01 Feb, 2026"
        # "09:30 AM"
        # "Paid to ARATI"
        # "UPI Transaction ID: 639896373956"
        # "Paid by AU Small Finance Bank 6439"
        # "₹2,000"
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]

        i = 0
        while i < len(lines):
            line = lines[i]

            # Detect transaction title line
            is_debit = any(k in line for k in ["Paid to ", "Sent to ", "Payment to "])
            is_credit = any(k in line for k in ["Received from ", "Refund", "Cashback"])

            if not (is_debit or is_credit):
                i += 1
                continue

            # Look back for date
            date_str = ""
            for j in range(max(0, i - 3), i):
                if re.search(r'\d{1,2}\s+[A-Za-z]{3},?\s+\d{4}', lines[j]):
                    date_str = lines[j]
                    break

            date = parse_date_from_text(date_str) if date_str else datetime.now(IST)

            # Extract merchant from current line
            merchant = ""
            for prefix in ["Paid to ", "Sent to ", "Payment to ", "Received from "]:
                if prefix in line:
                    merchant = line.split(prefix, 1)[1].strip()[:100]
                    break

            # Look forward for amount (₹ sign)
            amount = None
            upi_ref = ""
            for j in range(i + 1, min(i + 6, len(lines))):
                if not amount:
                    amount = extract_amount_from_text(lines[j])
                if not upi_ref:
                    m = re.search(r"UPI Transaction ID:\s*(\d+)", lines[j])
                    if m:
                        upi_ref = m.group(1)

            if amount:
                transactions.append({
                    "amount": float(amount),
                    "transaction_type": "debit" if is_debit else "credit",
                    "narration": line[:300],
                    "date": date.isoformat(),
                    "bank_name": "Google Pay",
                    "merchant_name": merchant,
                    "reference_number": upi_ref,
                })
            i += 1

        print(f"[GPay fallback] Extracted {len(transactions)} transactions")
    except Exception as e:
        print(f"GPay text fallback error: {e}")
    return transactions


def extract_amount_from_text(text):
    """Extract rupee amount from any text."""
    patterns = [
        r"[\u20b9₹]\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"(?:rs\.?|inr)\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"([0-9,]+(?:\.[0-9]{1,2})?)\s*(?:[\u20b9₹]|rs\.?|inr)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = Decimal(match.group(1).replace(",", ""))
                if val > 0:
                    return val
            except InvalidOperation:
                continue
    return None


def parse_date_from_text(text):
    """Try to extract a date from any text line."""
    patterns = [
        (r"\d{2}[-/]\d{2}[-/]\d{2,4}", ["%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"]),
        (r"\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}", ["%d %b %Y", "%d %b %y"]),
        (r"[A-Za-z]{3}\s+\d{1,2},?\s+\d{2,4}", ["%b %d %Y", "%b %d, %Y"]),
    ]
    for pattern, fmts in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(0).replace(",", "")
            for fmt in fmts:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    if dt.year < 100:
                        dt = dt.replace(year=dt.year + 2000)
                    return IST.localize(dt)
                except ValueError:
                    continue
    return datetime.now(IST)


def parse_text_universal(pdf_bytes, bank_name, password=None):
    """
    Universal text-based parser — extracts ALL text from PDF and finds
    transaction patterns using regex. Works as fallback for any bank.
    """
    pdf_bytes = decrypt_pdf(pdf_bytes, password)
    transactions = []
    if not HAS_PDFPLUMBER:
        return transactions
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            # First try tables on all pages
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        row_text = " ".join(str(c) for c in row if c)
                        amount = extract_amount_from_text(row_text)
                        if not amount:
                            continue
                        date = parse_date_from_text(row_text)
                        is_debit = any(k in row_text.lower() for k in ["dr", "debit", "withdrawal", "paid", "purchase"])
                        is_credit = any(k in row_text.lower() for k in ["cr", "credit", "deposit", "received", "salary"])

                        # Check debit/credit columns separately
                        # Usually last 3-4 columns are: withdrawal, deposit, balance
                        withdrawal = None
                        deposit = None
                        for i in range(len(row) - 1, max(len(row) - 5, -1), -1):
                            if row[i] and str(row[i]).strip():
                                val = clean_amount(str(row[i]))
                                if val and val != amount:
                                    if deposit is None and not withdrawal:
                                        deposit = val
                                    elif withdrawal is None:
                                        withdrawal = val
                                    break

                        narration = " ".join(str(c) for c in row[:3] if c).strip()
                        merchant = extract_merchant_from_narration(narration)

                        if withdrawal:
                            transactions.append({
                                "amount": float(withdrawal),
                                "transaction_type": "debit",
                                "narration": narration[:300],
                                "date": date.isoformat(),
                                "bank_name": bank_name,
                                "merchant_name": merchant,
                            })
                        elif deposit:
                            transactions.append({
                                "amount": float(deposit),
                                "transaction_type": "credit",
                                "narration": narration[:300],
                                "date": date.isoformat(),
                                "bank_name": bank_name,
                                "merchant_name": merchant,
                            })
                        elif amount:
                            transactions.append({
                                "amount": float(amount),
                                "transaction_type": "debit" if is_debit else "credit",
                                "narration": narration[:300],
                                "date": date.isoformat(),
                                "bank_name": bank_name,
                                "merchant_name": merchant,
                            })

            # If no table transactions found, try raw text parsing
            if not transactions:
                full_text = ""
                for page in pdf.pages:
                    full_text += (page.extract_text() or "") + "\n"

                for line in full_text.split("\n"):
                    line = line.strip()
                    if len(line) < 10:
                        continue
                    amount = extract_amount_from_text(line)
                    if not amount:
                        continue
                    date = parse_date_from_text(line)
                    is_debit = any(k in line.lower() for k in ["dr", "debit", "paid", "purchase", "withdrawal"])
                    transactions.append({
                        "amount": float(amount),
                        "transaction_type": "debit" if is_debit else "credit",
                        "narration": line[:300],
                        "date": date.isoformat(),
                        "bank_name": bank_name,
                        "merchant_name": extract_merchant_from_narration(line),
                    })

    except Exception as e:
        print(f"Universal parse error for {bank_name}: {e}")
    return transactions


BANK_PARSERS = {
    "hdfc": parse_hdfc_statement,
    "icici": parse_icici_statement,
    "sbi": parse_sbi_statement,
    "axis": parse_axis_statement,
    "kotak": parse_kotak_statement,
    "gpay": parse_gpay_statement,
    "google pay": parse_gpay_statement,
    "google": parse_gpay_statement,
    "phonepe": parse_text_universal,
    "paytm": parse_text_universal,
    "yes": parse_text_universal,
    "indusind": parse_text_universal,
    "federal": parse_text_universal,
    "idfc": parse_text_universal,
    "au ": parse_text_universal,
    "pnb": parse_text_universal,
    "canara": parse_text_universal,
    "union": parse_text_universal,
    "bob": parse_text_universal,
}


def parse_pdf_statement(pdf_bytes, bank_name, password=None):
    bank_key = bank_name.lower().strip()
    for key, parser_fn in BANK_PARSERS.items():
        if key in bank_key:
            result = parser_fn(pdf_bytes, password)
            if result:
                return result
    # Final fallback: universal parser
    return parse_text_universal(pdf_bytes, bank_name, password)


def debug_extract_pdf_text(pdf_bytes, password=None):
    """Returns raw extracted text and tables for debugging."""
    pdf_bytes = decrypt_pdf(pdf_bytes, password)
    output = {"pages": [], "tables": []}
    if not HAS_PDFPLUMBER:
        return output
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                output["pages"].append({"page": i + 1, "text": text[:2000]})
                tables = page.extract_tables()
                for j, table in enumerate(tables):
                    output["tables"].append({"page": i + 1, "table": j, "rows": table[:20]})
    except Exception as e:
        output["error"] = str(e)
    return output
