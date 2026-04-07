import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.utils import timezone
import pytz

IST = pytz.timezone("Asia/Kolkata")

BANK_SENDER_IDS = {
    "HDFCBK": "HDFC Bank", "HDFC": "HDFC Bank",
    "ICICIB": "ICICI Bank", "ICICI": "ICICI Bank",
    "SBISMS": "SBI", "SBIBNK": "SBI", "SBI": "SBI",
    "AXISBK": "Axis Bank", "AXIS": "Axis Bank",
    "KOTAKB": "Kotak Bank", "KOTAK": "Kotak Bank",
    "YESBKG": "Yes Bank", "YESBNK": "Yes Bank",
    "INDBNK": "IndusInd Bank", "INDUS": "IndusInd Bank",
    "FEDBK": "Federal Bank", "IDFCFB": "IDFC First Bank",
    "PAYTMB": "Paytm Bank", "PAYTM": "Paytm Bank",
    "AUSFBL": "AU Small Finance Bank",
    "PNBSMS": "PNB", "BOBIBN": "Bank of Baroda",
    "CANBNK": "Canara Bank", "UNIONB": "Union Bank",
}

MERCHANT_CATEGORIES = {
    "zomato": "Food & Dining", "swiggy": "Food & Dining",
    "dominos": "Food & Dining", "mcdonalds": "Food & Dining",
    "kfc": "Food & Dining", "pizzahut": "Food & Dining",
    "subway": "Food & Dining", "starbucks": "Food & Dining",
    "restaurant": "Food & Dining", "hotel": "Food & Dining",
    "uber": "Transport", "ola": "Transport",
    "rapido": "Transport", "irctc": "Transport",
    "makemytrip": "Transport", "redbus": "Transport",
    "petrol": "Transport", "fuel": "Transport",
    "fasttag": "Transport", "toll": "Transport",
    "indigo": "Transport", "spicejet": "Transport",
    "amazon": "Shopping", "flipkart": "Shopping",
    "myntra": "Shopping", "ajio": "Shopping",
    "nykaa": "Shopping", "meesho": "Shopping",
    "dmart": "Shopping", "big bazaar": "Shopping",
    "croma": "Shopping", "lifestyle": "Shopping",
    "electricity": "Bills & Utilities", "bescom": "Bills & Utilities",
    "airtel": "Bills & Utilities", "jio": "Bills & Utilities",
    "vodafone": "Bills & Utilities", "bsnl": "Bills & Utilities",
    "broadband": "Bills & Utilities", "internet": "Bills & Utilities",
    "netflix": "Entertainment", "hotstar": "Entertainment",
    "disney": "Entertainment", "spotify": "Entertainment",
    "bookmyshow": "Entertainment", "pvr": "Entertainment",
    "inox": "Entertainment",
    "apollo": "Health", "medplus": "Health",
    "netmeds": "Health", "1mg": "Health",
    "pharmeasy": "Health", "practo": "Health",
    "hospital": "Health", "pharmacy": "Health", "gym": "Health",
    "byjus": "Education", "unacademy": "Education",
    "coursera": "Education", "udemy": "Education",
    "zerodha": "Investments", "groww": "Investments",
    "upstox": "Investments", "mutual fund": "Investments",
    "sip": "Investments", "insurance": "Insurance", "lic": "Insurance",
    "bigbasket": "Groceries", "blinkit": "Groceries",
    "zepto": "Groceries", "jiomart": "Groceries",
    "instamart": "Groceries", "supermarket": "Groceries",
}

DEFAULT_CATEGORY = "Other"


def categorize_merchant(merchant_name, narration):
    text = (merchant_name + " " + narration).lower()
    for keyword, category in MERCHANT_CATEGORIES.items():
        if keyword in text:
            return category
    return DEFAULT_CATEGORY


def extract_amount(text):
    patterns = [
        r"(?:rs\.?|inr|\u20b9)\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"([0-9,]+(?:\.[0-9]{1,2})?)\s*(?:rs\.?|inr|\u20b9)",
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


def extract_account_last4(text):
    patterns = [
        r"(?:a/c|ac|account|acct)[\s\*\-]*(?:no\.?\s*)?[xX\*]*(\d{4})",
        r"[xX\*]{2,}(\d{4})",
        r"ending\s+(?:with\s+)?(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def extract_reference(text):
    patterns = [
        r"(?:upi\s*ref\.?|ref\.?\s*no\.?|ref\s*id|txn\s*id)\s*[:\-]?\s*(\w+)",
        r"(?:imps|neft|rtgs)\s*[:\-]?\s*(\w+)",
        r"/(\d{12})/",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def extract_merchant(text):
    patterns = [
        r"/([^/]+)/\d{9,}/",
        r"(?:to|at)\s+([A-Za-z][A-Za-z0-9\s&\.]{2,40}?)(?:\s+on|\s+via|\s+ref|\s+upi|\.)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            merchant = match.group(1).strip()
            if len(merchant) > 2 and not merchant.isdigit():
                return merchant[:100]
    return ""


def parse_date(text):
    date_patterns = [
        (r"\d{2}-[A-Za-z]{3}-\d{2,4}", "%d-%b-%Y"),
        (r"\d{2}/[A-Za-z]{3}/\d{2,4}", "%d/%b/%Y"),
        (r"\d{2}/\d{2}/\d{2,4}", "%d/%m/%Y"),
        (r"\d{2}-\d{2}-\d{2,4}", "%d-%m-%Y"),
        (r"\d{2}[A-Za-z]{3}\d{2,4}", "%d%b%Y"),
    ]
    for pattern, fmt in date_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(0)
            try:
                if len(date_str) <= 8 or date_str[-2:].isdigit() and len(date_str[-2:]) == 2:
                    fmt = fmt.replace("%Y", "%y")
                dt = datetime.strptime(date_str, fmt)
                if dt.year < 100:
                    dt = dt.replace(year=dt.year + 2000)
                return IST.localize(dt)
            except ValueError:
                continue
    return timezone.now()


def is_debit(text):
    debit_kw = ["debited", "debit", "withdrawn", "spent", "paid", "purchase", "dr "]
    credit_kw = ["credited", "credit", "received", "deposited", "refund", "cashback", "cr ", "salary"]
    tl = text.lower()
    d = sum(1 for k in debit_kw if k in tl)
    c = sum(1 for k in credit_kw if k in tl)
    return d >= c


def parse_sms(sender, body):
    sender_upper = sender.upper().strip()
    bank_name = ""
    for key, name in BANK_SENDER_IDS.items():
        if key in sender_upper:
            bank_name = name
            break

    if not bank_name:
        bank_kw = ["debited", "credited", "upi", "neft", "imps", "a/c", "avl bal"]
        if not any(k in body.lower() for k in bank_kw):
            return None

    amount = extract_amount(body)
    if not amount or amount <= 0:
        return None

    txn_type = "debit" if is_debit(body) else "credit"
    account_last4 = extract_account_last4(body)
    reference = extract_reference(body)
    merchant = extract_merchant(body)
    date = parse_date(body)
    category = categorize_merchant(merchant, body)

    balance = None
    bal_match = re.search(
        r"(?:avl\.?\s*bal\.?|available\s+balance|balance)\s*[:\-]?\s*(?:rs\.?|inr|\u20b9)?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        body, re.IGNORECASE
    )
    if bal_match:
        try:
            balance = float(Decimal(bal_match.group(1).replace(",", "")))
        except InvalidOperation:
            pass

    return {
        "amount": float(amount),
        "transaction_type": txn_type,
        "bank_name": bank_name,
        "account_last4": account_last4,
        "reference_number": reference,
        "merchant_name": merchant,
        "date": date.isoformat(),
        "narration": body[:500],
        "raw_text": body[:1000],
        "category_name": category,
        "balance": balance,
    }


def parse_sms_batch(sms_list):
    results = []
    for sms in sms_list:
        sender = sms.get("sender", "")
        body = sms.get("body", "")
        if not body:
            continue
        parsed = parse_sms(sender, body)
        if parsed:
            results.append(parsed)
    return results
