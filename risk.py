"""
Rule-based risk / negative-event detection on transaction text (no ML).

Flags: bounced_payment, payment_return, min_balance_penalty, overdraft, late_fee.
Works on the narration (statement rows) plus payee/notes (manual rows). A negative running
balance also raises an overdraft flag. Every flag carries the phrase that triggered it.
"""
import re

FLAGS = {
    "bounced_payment": ("Bounced / failed EMI, ECS, NACH or cheque payment", "high"),
    "payment_return": ("Payment returned (NEFT / IMPS / UPI)", "medium"),
    "min_balance_penalty": ("Minimum balance penalty", "medium"),
    "overdraft": ("Overdraft", "high"),
    "late_fee": ("Late payment fee or penalty", "medium"),
}

_R = re.compile
_BOUNCE = _R(r"\b(?:BOUNCE|BOUNCED|BNCE|DISHONOU?R(?:ED)?|NSF)\b")
_INSUFF = _R(r"\bINSUFF(?:ICIENT)?\s+(?:FUNDS?|BAL(?:ANCE)?)\b|\bFUNDS?\s+INSUFF(?:ICIENT)?\b"
             r"|\bNO\s+(?:SUFFICIENT\s+)?FUNDS\b|\bNOT\s+SUFFICIENT\s+FUNDS\b")
_FAIL = _R(r"\b(?:RET|RETD|RETURN|RETURNED|RTN|RTND|REJ|REJECT|REJECTED|UNPAID|UNPD|FAILED|"
           r"UNSUCCESSFUL|NOT\s+HONOU?RED)\b")
_MANDATE = _R(r"\b(?:EMI|ECS|NACH|ENACH|ACH|MANDATE|AUTO\s?DEBIT|CHQ|CHEQUE|CHEQ|CHECK|LOAN|"
              r"INSTALMENT|INSTALLMENT)\b")
_TRANSFER = _R(r"\b(?:NEFT|IMPS|RTGS|IFT|TRANSFER|BENEFICIARY|BENE|REMITTANCE|UPI)\b")
_ACCT_BAD = _R(r"\b(?:ACCOUNT|ACCT|A C)\s+(?:CLOSED|FROZEN|INVALID|DORMANT|BLOCKED|NOT\s+FOUND)\b"
               r"|\bINVALID\s+(?:ACCOUNT|ACCT|BENEFICIARY)\b")
_REFUND = _R(r"\b(?:REFUND|REFUNDED|CASHBACK)\b")
_MINBAL = _R(r"\bMIN(?:IMUM)?\s*(?:AVG\s+|AVERAGE\s+)?(?:MONTHLY\s+|QTRLY\s+|QUARTERLY\s+)?BAL(?:ANCE)?\b"
             r"|\bMINBAL\b|\bNON\s*MAINT(?:ENANCE)?\b|\bBAL(?:ANCE)?\s+NOT\s+MAINT(?:AINED)?\b")
_MINBAL_ABBR = _R(r"\b(?:AMB|MAB|AQB|NMC)\b")
_CHARGE = _R(r"\b(?:CHG|CHGS|CHARGE|CHARGES|CHRG|CHRGS|INT|INTEREST|PENALTY|FEE|FEES)\b")
_OVERDRAFT = _R(r"\bOVER\s?DRAFT\b|\bOVERDRAWN\b|\bOVER\s?DRAWN\b|\bOVER\s?LIMIT\b")
_OD = _R(r"\bO\s?D\b")
_LATE = _R(r"\bLATE\s+(?:PAYMENT|PMT|FEE|FEES|CHARGE|CHARGES|CHRG)\b|\bLPC\b|"
           r"\bDELAY(?:ED)?\s+(?:PAYMENT|PMT|CHARGE|CHARGES)\b|\bOVERDUE\b|"
           r"\bPENAL\s+(?:INTEREST|INT|CHARGE|CHARGES|CHRG)\b|\bDEFAULT\s+(?:CHARGE|CHARGES|FEE)\b")
_PENALTY = _R(r"\bPENALTY\b")


def _norm(text):
    t = re.sub(r"[^A-Z0-9\s]", " ", (text or "").upper())
    return " " + re.sub(r"\s+", " ", t).strip() + " "


def detect_flags(text, closing_balance=None):
    """Returns a list of {type, label, severity, reason}. One flag per type."""
    t = _norm(text)
    out = {}

    def add(kind, reason):
        if kind not in out:
            out[kind] = {"type": kind, "label": FLAGS[kind][0], "severity": FLAGS[kind][1], "reason": reason}

    m = _BOUNCE.search(t) or _INSUFF.search(t)
    if m:
        add("bounced_payment", m.group(0).strip().title())
    elif _FAIL.search(t) and _MANDATE.search(t):
        add("bounced_payment", f"{_FAIL.search(t).group(0).title()} + {_MANDATE.search(t).group(0).title()}")
    if "bounced_payment" not in out and not _REFUND.search(t):
        if _FAIL.search(t) and _TRANSFER.search(t):
            add("payment_return", f"{_FAIL.search(t).group(0).title()} + {_TRANSFER.search(t).group(0).title()}")
        elif _ACCT_BAD.search(t):
            add("payment_return", _ACCT_BAD.search(t).group(0).strip().title())
    if _MINBAL.search(t):
        add("min_balance_penalty", _MINBAL.search(t).group(0).strip().title())
    elif _MINBAL_ABBR.search(t) and _CHARGE.search(t):
        add("min_balance_penalty", _MINBAL_ABBR.search(t).group(0).title() + " charges")
    if _OVERDRAFT.search(t):
        add("overdraft", _OVERDRAFT.search(t).group(0).strip().title())
    elif _OD.search(t) and _CHARGE.search(t):
        add("overdraft", "OD charges")
    if closing_balance is not None and closing_balance < 0:
        add("overdraft", "Negative running balance")
    if _LATE.search(t):
        add("late_fee", _LATE.search(t).group(0).strip().title())
    elif _PENALTY.search(t) and not ({"min_balance_penalty", "bounced_payment"} & set(out)):
        add("late_fee", "Penalty")
    return list(out.values())


def flags_for_record(r):
    text = " ".join(str(r.get(k) or "") for k in ("raw_narration", "receiver_payer", "notes", "subcategory"))
    return detect_flags(text, r.get("balance_after"))


def summarize(records, limit=100):
    counts = {k: 0 for k in FLAGS}
    events = []
    for r in records:
        fl = flags_for_record(r)
        if not fl:
            continue
        for f in fl:
            counts[f["type"]] += 1
        events.append({"id": r.get("id"), "date": r.get("date"), "amount": r.get("amount"), "direction": r.get("type"),
                       "narration": (r.get("raw_narration") or r.get("receiver_payer") or "")[:120],
                       "flags": [{"type": f["type"], "severity": f["severity"], "reason": f["reason"]} for f in fl]})
    events.sort(key=lambda e: e["date"] or "", reverse=True)
    distress = counts["bounced_payment"] + counts["overdraft"] + counts["late_fee"] + counts["min_balance_penalty"]
    return {"counts": counts, "total_flags": sum(counts.values()), "distress_events": distress,
            "flagged_transactions": len(events), "events": events[:limit]}


def risk_insights(summary):
    c, out = summary["counts"], []
    if c["bounced_payment"]:
        out.append({"level": "risk", "title": f"{c['bounced_payment']} bounced/failed payment event(s)",
                    "detail": "EMI/ECS/NACH or cheque failures found. Keep enough balance before due dates."})
    if c["overdraft"]:
        out.append({"level": "risk", "title": f"{c['overdraft']} overdraft event(s)",
                    "detail": "The account balance went negative or overdraft charges were applied."})
    other = c["late_fee"] + c["min_balance_penalty"]
    if other:
        out.append({"level": "warn", "title": f"{other} penalty/late-fee charge(s)",
                    "detail": "Late fees or minimum-balance penalties were charged."})
    if c["payment_return"]:
        out.append({"level": "info", "title": f"{c['payment_return']} returned payment(s)",
                    "detail": "Some NEFT/IMPS/UPI payments came back."})
    return out
