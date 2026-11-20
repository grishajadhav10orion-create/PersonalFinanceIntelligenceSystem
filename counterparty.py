"""
Rule-based counterparty classification: merchant | employer | individual | institution | unknown.
Uses the counterparty name, narration context (salary words, UPI/IMPS/NEFT), direction and category.
Simplification: a business that pays you for non-salary work (e.g. a freelance client) is 'merchant'.
"""
import re
from collections import Counter

_MONTHS = r"JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUNE?|JULY?|AUG(?:UST)?|SEP(?:T(?:EMBER)?)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?"
_NOTE_WORDS = {"RENT", "SPLIT", "PAYMENT", "PAID", "REPAID", "REPAY", "SHARE", "REFUND", "TRANSFER", "UPI", "NEFT",
               "IMPS", "RTGS", "CR", "DR", "SALARY", "FEE", "FEES", "SIP", "EMI", "INV", "INVOICE"}
INSTITUTION = {"BANK", "FINANCE", "FINSERV", "NBFC", "INSURANCE", "ASSURANCE", "LIC", "MUTUAL", "FUND", "AMC", "CAPITAL",
               "CREDIT", "GOVERNMENT", "GOVT", "MUNICIPAL", "TAX", "GST", "NPCI", "RBI", "EPFO", "NSDL", "CDSL",
               "UNIVERSITY", "TREASURY", "SEBI", "NPS", "CLEARING", "ELECTRICITY", "MSEDCL", "BESCOM", "BSES", "BOARD",
               "AUTHORITY", "CORPORATION", "HDFC", "ICICI", "SBI", "AXIS", "KOTAK"}
BUSINESS = {"PVT", "LTD", "LIMITED", "LLP", "INC", "CORP", "TECHNOLOGIES", "SOLUTIONS", "SYSTEMS", "SERVICES",
            "ENTERPRISES", "TRADERS", "TRADING", "STORE", "STORES", "MART", "MARKET", "SUPERMARKET", "RESTAURANT",
            "CAFE", "COFFEE", "CHAI", "TEA", "BAKERY", "FOODS", "KITCHEN", "PHARMACY", "MEDICAL", "CLINIC", "HOSPITAL",
            "PETROL", "PUMP", "FUEL", "ELECTRONICS", "RETAIL", "FASHION", "STUDIO", "ACADEMY", "CLASSES", "FITNESS",
            "GYM", "SALON", "TRAVELS", "TOURS", "CABS", "TAXI", "HOTEL", "RESORT", "SHOP", "PAYMENTS", "ONLINE",
            "DIGITAL", "MEDIA", "ENTERTAINMENT", "NETWORK", "FIBERNET", "BROADBAND", "SPORTS", "CORNER", "STALL",
            "CENTRE", "CENTER", "AGENCY", "CONSULTING", "LABS", "DESIGN", "MUSIC", "PHARMA", "SUPPLIES"}
BRANDS = {"SWIGGY", "ZOMATO", "AMAZON", "FLIPKART", "MYNTRA", "UBER", "OLA", "RAPIDO", "NETFLIX", "SPOTIFY", "BLINKIT",
          "BIGBASKET", "DMART", "BOOKMYSHOW", "STARBUCKS", "APOLLO", "AIRTEL", "JIO", "CROMA", "HPCL", "BPCL", "IRCTC",
          "CULTFIT", "BILLDESK", "RAZORPAY", "PAYTM", "PHONEPE", "GPAY", "MEESHO", "NYKAA", "AJIO", "ZEPTO", "INSTAMART",
          "DOMINOS", "MCDONALDS", "KFC", "REDBUS", "MAKEMYTRIP", "HOTSTAR", "YOUTUBE", "ZERODHA", "GROWW", "UPSTOX"}
_SALARY_WORDS = re.compile(r"\b(?:SALARY|PAYROLL|STIPEND|WAGES|SAL\s+CR|BONUS|REIMBURSEMENT)\b")
MERCHANT_CATEGORIES = {"food", "shopping", "travel", "entertainment", "bills & utilities", "health"}


def _words(text):
    t = re.sub(r"\b(?:" + _MONTHS + r")\b", " ", (text or "").upper())
    return [w for w in re.sub(r"[^A-Z\s]", " ", t).split() if len(w) > 1]


def classify_counterparty(name, narration="", txn_type="expense", category="", income_stream=None):
    """Returns {'type': ..., 'reason': ...}."""
    core = [w for w in _words(name) if w not in _NOTE_WORDS]
    nar = (narration or "").upper()
    if txn_type == "earning" and (income_stream == "salary" or _SALARY_WORDS.search(nar + " " + (name or "").upper())):
        return {"type": "employer", "reason": "credit with salary/payroll wording or salary income stream"}
    hit = next((w for w in core if w in INSTITUTION), None)
    if hit:
        return {"type": "institution", "reason": f"name contains '{hit.title()}'"}
    hit = next((w for w in core if w in BUSINESS or w in BRANDS), None)
    if hit:
        return {"type": "merchant", "reason": f"business/brand word '{hit.title()}'"}
    if 2 <= len(core) <= 4 and ("UPI" in nar or "IMPS" in nar or "NEFT" in nar or not nar):
        return {"type": "individual", "reason": "personal-name pattern (2-4 plain words, no business wording)"}
    if (category or "").lower() in MERCHANT_CATEGORIES:
        return {"type": "merchant", "reason": f"spending category '{category}'"}
    return {"type": "unknown", "reason": "no rule matched"}


def summarize(records, limit=20):
    """Group records by similar payee text and classify each group (statement + manual spellings merge)."""
    import analytics, income
    streams = income.classify_credits(records)
    out = []
    for rs in analytics._cluster_by_payee([r for r in records if r.get("date")]):
        exp = sum(r["amount"] for r in rs if r["type"] == "expense")
        crd = sum(r["amount"] for r in rs if r["type"] == "earning")
        direction = "expense" if exp >= crd else "earning"
        rep = max(rs, key=lambda r: r["amount"])
        stream = next((streams[id(r)]["stream"] for r in rs if id(r) in streams), None)
        cp = classify_counterparty(analytics._label(rep), rep.get("raw_narration") or "", direction,
                                   rep.get("category") or "", stream if direction == "earning" else None)
        out.append({"name": analytics._label(rep), "type": cp["type"], "reason": cp["reason"], "direction": direction,
                    "total": round(exp + crd, 2), "transactions": len(rs)})
    out.sort(key=lambda x: -x["total"])
    return {"by_type": dict(Counter(x["type"] for x in out)), "counterparties": out[:limit]}
