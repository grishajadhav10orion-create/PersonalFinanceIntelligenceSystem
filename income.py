"""
Income stream identification for credits (rule-based): salary | business_revenue | investment_returns | p2p | other.
Signals: narration/payee/notes/category words, whether the payer looks like a person or a business, and whether the
credit is part of a recurring monthly pattern (analytics.recurring_signals).
"""
import re
from collections import defaultdict

import analytics
import counterparty

STREAMS = ("salary", "business_revenue", "investment_returns", "p2p", "other")
_INVEST = re.compile(r"\b(?:INTEREST|INT\s?PD|INT\s?CR|DIVIDEND|MATURITY|REDEMPTION|COUPON)\b")
_REFUND = re.compile(r"\b(?:REFUND|REVERSAL|CASHBACK|RETURN|RETURNED|RET)\b")
_SALARY = re.compile(r"\b(?:SALARY|PAYROLL|STIPEND|WAGES|SAL\s?CR)\b")
_BUSINESS = re.compile(r"\b(?:INVOICE|INV|FREELANCE|CLIENT|SALES|SETTLEMENT|PAYOUT|RAZORPAY|CASHFREE|CONSULTING|"
                       r"PROFESSIONAL\s+FEE|COMMISSION|PROJECT)\b")
SALARY_MIN_FRACTION_OF_LARGEST = 0.5     # recurring non-person credit counts as salary only if >= 50% of the largest credit


def _text(r):
    t = " ".join(str(r.get(k) or "") for k in ("raw_narration", "receiver_payer", "notes", "subcategory", "category"))
    return " " + re.sub(r"[^A-Z0-9\s]", " ", t.upper()) + " "


def _payer_kind(r):
    """'business' | 'person' | 'unknown' from the counterparty classifier."""
    t = counterparty.classify_counterparty(r.get("receiver_payer") or "", r.get("raw_narration") or "",
                                           "earning", r.get("category") or "")["type"]
    return "person" if t == "individual" else "unknown" if t == "unknown" else "business"


def classify_credits(records, recurring=None):
    """Returns {id(record): {'stream', 'reason'}} for every earning record."""
    recurring = analytics.recurring_signals(records) if recurring is None else recurring
    rec_tokens = [analytics._tokens(s["name"]) for s in recurring if s["type"] == "earning" and s["frequency"] == "monthly"]
    credits = [r for r in records if r.get("type") == "earning"]
    largest = max((r["amount"] for r in credits), default=0)
    out = {}
    for r in credits:
        t, cat, name = _text(r), (r.get("category") or "").lower(), r.get("receiver_payer") or ""
        tk = analytics._tokens(name)
        recurring_monthly = bool(tk) and any(len(tk & x) / len(tk | x) >= 0.5 for x in rec_tokens)
        kind = _payer_kind(r)
        if _INVEST.search(t) or cat in ("interest", "investment income"):
            stream, why = "investment_returns", "interest / dividend / maturity wording"
        elif _REFUND.search(t) and not _SALARY.search(t):
            stream, why = "other", "refund / reversal / cashback / returned payment"
        elif _SALARY.search(t) or cat == "salary":
            stream, why = "salary", "salary / payroll wording or Salary category"
        elif recurring_monthly and kind != "person" and r["amount"] >= SALARY_MIN_FRACTION_OF_LARGEST * largest:
            stream, why = "salary", "large regular monthly credit from the same non-person payer"
        elif _BUSINESS.search(t) or cat in ("freelance", "business"):
            stream, why = "business_revenue", "invoice / freelance / client / settlement wording"
        elif kind == "business":
            stream, why = "business_revenue", "credit from a company-like payer (not salary)"
        elif kind == "person":
            stream, why = "p2p", "credit from a person-like payer"
        else:
            stream, why = "other", "no rule matched"
        out[id(r)] = {"stream": stream, "reason": why + (" (recurring monthly)" if recurring_monthly else "")}
    return out


def summarize(records, recurring=None, recent=25):
    cls = classify_credits(records, recurring)
    tot, cnt, months = defaultdict(float), defaultdict(int), defaultdict(set)
    rows = []
    for r in records:
        c = cls.get(id(r))
        if not c:
            continue
        tot[c["stream"]] += r["amount"]; cnt[c["stream"]] += 1; months[c["stream"]].add((r.get("date") or "")[:7])
        rows.append({"id": r.get("id"), "date": r.get("date"), "amount": r["amount"],
                     "payer": (r.get("receiver_payer") or "")[:60], "stream": c["stream"], "reason": c["reason"]})
    total = sum(tot.values())
    rows.sort(key=lambda x: x["date"] or "", reverse=True)
    return {"total_income": round(total, 2),
            "by_stream": {s: {"total": round(tot[s], 2), "count": cnt[s], "months_present": len(months[s]),
                              "share_pct": round(tot[s] / total * 100, 1) if total else 0.0} for s in STREAMS},
            "primary_stream": max(STREAMS, key=lambda s: tot[s]) if total else None,
            "recent_credits": rows[:recent]}
