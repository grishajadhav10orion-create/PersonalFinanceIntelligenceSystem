"""
Financial analytics + deterministic insights. Pure functions over a list of record dicts
(as returned by database.get_records), so everything is computed from stored data.
"""
import datetime
import re
import statistics
from collections import defaultdict


def _valid_month(d):
    return isinstance(d, str) and len(d) >= 7 and d[4] == "-" and d[:4].isdigit() and d[5:7].isdigit()


def compute_summary(records):
    income = sum(r["amount"] for r in records if r["type"] == "earning")
    expenses = sum(r["amount"] for r in records if r["type"] == "expense")
    net = income - expenses
    return {"total_income": round(income, 2), "total_expenses": round(expenses, 2),
            "net_cash_flow": round(net, 2),
            "savings_rate": round(net / income * 100, 1) if income > 0 else None,
            "transaction_count": len(records)}


def spending_by_category(records):
    tot = defaultdict(float)
    for r in records:
        if r["type"] == "expense":
            tot[r["category"]] += r["amount"]
    total = sum(tot.values())
    return [{"category": c, "total": round(v, 2), "pct": round(v / total * 100, 1) if total else 0}
            for c, v in sorted(tot.items(), key=lambda kv: -kv[1])]


def monthly_trend(records):
    m = defaultdict(lambda: {"income": 0.0, "expenses": 0.0})
    for r in records:
        if not _valid_month(r["date"]):
            continue
        k = r["date"][:7]
        m[k]["income" if r["type"] == "earning" else "expenses"] += r["amount"]
    out, prev = [], None
    for k in sorted(m):
        inc, exp = m[k]["income"], m[k]["expenses"]
        out.append({"month": k, "income": round(inc, 2), "expenses": round(exp, 2),
                    "net": round(inc - exp, 2),
                    "savings_rate": round((inc - exp) / inc * 100, 1) if inc > 0 else None,
                    "expense_change_pct": round((exp - prev) / prev * 100, 1) if prev else None})
        prev = exp
    return out


def month_over_month(trend):
    """Latest month vs the month before it (None if fewer than 2 months of data)."""
    if len(trend) < 2:
        return None
    cur, prev = trend[-1], trend[-2]
    today = datetime.date.today()
    partial = cur["month"] == today.strftime("%Y-%m")
    chg = lambda a, b: round((a - b) / b * 100, 1) if b else None
    return {"current_month": cur["month"], "previous_month": prev["month"],
            "current_expenses": cur["expenses"], "previous_expenses": prev["expenses"],
            "expense_change_pct": chg(cur["expenses"], prev["expenses"]),
            "current_income": cur["income"], "previous_income": prev["income"],
            "income_change_pct": chg(cur["income"], prev["income"]),
            "current_month_partial": partial}


def _label(r):
    return (r.get("receiver_payer") or "").strip() or (r.get("category") or "")


_MONTHS = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
_NOISE = {"upi", "neft", "imps", "rtgs", "ach", "nach", "cr", "dr", "ref", "txn", "to", "from",
          "via", "payment", "transfer"}
_HINTS = ("rent", "emi", "loan", "insurance", "premium", "sip", "subscription")


def _tokens(label):
    """Payee words with months, digits, punctuation and channel words removed."""
    t = re.sub(r"\b(?:" + _MONTHS + r")\b", " ", (label or "").lower())
    t = re.sub(r"[^a-z\s]", " ", t)
    return frozenset(w for w in t.split() if len(w) > 1 and w not in _NOISE)


def _cluster_by_payee(records):
    """Group records whose payee text is similar (Jaccard >= 0.5), so 'Ramesh Kumar Sharma Rent Aug',
    'Ramesh Kumar Sharma Rent Sep' and 'Ramesh Sharma Rent' end up together."""
    clusters = []
    for r in sorted(records, key=lambda r: r["date"]):
        tk = _tokens(_label(r)) or frozenset([(r.get("category") or "").lower()])
        best, score = None, 0.0
        for c in clusters:
            j = len(tk & c[0]) / len(tk | c[0])
            if j > score:
                best, score = c, j
        if best is not None and score >= 0.5:
            best[0] |= tk
            best[1].append(r)
        else:
            clusters.append([set(tk), [r]])
    return [c[1] for c in clusters]


def _amount_segments(rs):
    """Split into amount levels (a >15% jump starts a new level) so a rent increase doesn't hide the rent."""
    by_amt = sorted(rs, key=lambda r: r["amount"])
    segs, cur = [], [by_amt[0]]
    for r in by_amt[1:]:
        prev = cur[-1]["amount"]
        if prev > 0 and r["amount"] / prev > 1.15:
            segs.append(cur); cur = []
        cur.append(r)
    segs.append(cur)
    return segs


def _segment_signal(seg, hint):
    seg = sorted(seg, key=lambda r: r["date"])
    dates = [datetime.date.fromisoformat(r["date"][:10]) for r in seg]
    amounts = [r["amount"] for r in seg]
    # weekly: 4+ payments, at least 75% of them 5-9 days apart
    if len(seg) >= 4:
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        med = statistics.median(amounts)
        regular = sum(1 for g in gaps if 5 <= g <= 9) >= 0.75 * len(gaps)
        if regular and med > 0 and max(abs(a - med) for a in amounts) / med <= 0.15:
            return {"frequency": "weekly", "typical_amount": round(med, 2), "occurrences": len(seg),
                    "_rec": seg[-1], "_recs": seg, "_first": seg[0]["date"]}
    # monthly: one payment per calendar month (duplicates in a month count once)
    by_month = {}
    for d, r in zip(dates, seg):
        by_month.setdefault(d.year * 12 + d.month, (d, r))
    months = sorted(by_month)
    if len(months) < 2:
        return None
    mgaps = [b - a for a, b in zip(months, months[1:])]
    if sum(1 for g in mgaps if g == 1) < max(1, 0.6 * len(mgaps)):
        return None                                     # not mostly consecutive months
    days = [by_month[m][0].day for m in months]
    mdn = statistics.median(days)
    near = sum(1 for d in days if min(abs(d - mdn), 31 - abs(d - mdn)) <= 7)
    if near < 0.75 * len(days):
        return None                                     # day of month too scattered
    amts = [by_month[m][1]["amount"] for m in months]
    med = statistics.median(amts)
    if med <= 0:
        return None
    spread = max(abs(a - med) for a in amts) / med
    limit = 0.15 if len(months) >= 3 else (0.10 if hint else 0.02)
    if spread > limit:
        return None
    return {"frequency": "monthly", "typical_amount": round(med, 2), "occurrences": len(months),
            "_rec": by_month[months[-1]][1], "_recs": seg, "_first": seg[0]["date"]}


def _detect(rs, typ, hint=False):
    sigs = []
    for seg in _amount_segments(rs):
        s = _segment_signal(seg, hint)
        if s:
            r = s["_rec"]
            s.update(name=r.get("receiver_payer") or r["category"], type=typ, category=r["category"],
                     last_date=max(x["date"] for x in s["_recs"]))
            sigs.append(s)
    # an older amount level that ended before a newer one began is superseded (e.g. rent increase)
    return [s for s in sigs if not any(t is not s and t["_first"] > s["last_date"] for t in sigs)]


def recurring_signals(records):
    """Recurring payments/income: same payee (similar text), roughly one per month (or per week) at
    a similar amount and day of month. Tolerates narration/counterparty variations, month names in
    the text, small date drift, duplicated rows, and amount changes (each amount level is checked).
    Rent-like categories (rent, EMI, loan, insurance, SIP, subscription) are also detected by
    category when the payee text differs."""
    valid = [r for r in records if _valid_month(r["date"]) and r["amount"] > 0]
    found, covered = [], set()
    for typ in ("expense", "earning"):
        of_type = [r for r in valid if r["type"] == typ]
        if not of_type:
            continue
        for cluster in _cluster_by_payee(of_type):
            for s in _detect(cluster, typ):
                found.append(s); covered.update(id(r) for r in s["_recs"])
        by_cat = defaultdict(list)
        for r in of_type:
            cat = (r.get("category") or "").lower()
            if id(r) not in covered and any(h in cat for h in _HINTS):
                by_cat[cat].append(r)
        for cat, rs in by_cat.items():
            found.extend(_detect(rs, typ, hint=True))
    out = [{"name": s["name"], "type": s["type"], "category": s["category"],
            "typical_amount": s["typical_amount"], "frequency": s["frequency"],
            "occurrences": s["occurrences"], "last_date": s["last_date"]} for s in found]
    return sorted(out, key=lambda x: -x["typical_amount"])


def monthly_equivalent(sig):
    return sig["typical_amount"] * (4.33 if sig["frequency"] == "weekly" else 1)


def generate_insights(summary, categories, trend, mom, recurring):
    """Deterministic insights; every number comes from the arguments."""
    ins = []
    if summary["transaction_count"] == 0:
        return [{"level": "info", "title": "No transactions yet",
                 "detail": "Add transactions or import a bank statement to see insights."}]
    fmt = lambda v: f"Rs.{v:,.0f}"

    if categories:
        top = categories[0]
        ins.append({"level": "info", "title": f"Highest spending category: {top['category']}",
                    "detail": f"{fmt(top['total'])} — {top['pct']}% of total expenses."})
    sr = summary["savings_rate"]
    if sr is None:
        ins.append({"level": "warn", "title": "No income recorded",
                    "detail": "Savings rate can't be computed without income transactions."})
    elif sr < 0:
        ins.append({"level": "risk", "title": f"Spending exceeds income (savings rate {sr}%)",
                    "detail": f"Expenses {fmt(summary['total_expenses'])} vs income "
                              f"{fmt(summary['total_income'])}."})
    elif sr < 20:
        ins.append({"level": "warn", "title": f"Savings rate is {sr}%",
                    "detail": f"You kept {fmt(summary['net_cash_flow'])} of "
                              f"{fmt(summary['total_income'])} income. 20% or more is a common target."})
    else:
        ins.append({"level": "good", "title": f"Savings rate is {sr}%",
                    "detail": f"You kept {fmt(summary['net_cash_flow'])} of {fmt(summary['total_income'])} income."})
    if mom and mom["expense_change_pct"] is not None:
        c = mom["expense_change_pct"]
        note = " (current month is still in progress)" if mom["current_month_partial"] else ""
        if abs(c) >= 10:
            ins.append({"level": "warn" if c > 0 else "good",
                        "title": f"Spending {'increased' if c > 0 else 'decreased'} {abs(c)}% vs {mom['previous_month']}",
                        "detail": f"{mom['current_month']}: {fmt(mom['current_expenses'])} vs "
                                  f"{mom['previous_month']}: {fmt(mom['previous_expenses'])}{note}."})
        else:
            ins.append({"level": "info", "title": f"Spending is steady ({c:+}% vs {mom['previous_month']})",
                        "detail": f"{fmt(mom['current_expenses'])} this month vs {fmt(mom['previous_expenses'])}{note}."})
    rec_exp = [r for r in recurring if r["type"] == "expense"]
    if rec_exp:
        monthly = sum(monthly_equivalent(r) for r in rec_exp)
        names = ", ".join(r["name"] for r in rec_exp[:3])
        ins.append({"level": "info", "title": f"{len(rec_exp)} recurring expense(s) detected",
                    "detail": f"About {fmt(monthly)} per month ({names}{'…' if len(rec_exp) > 3 else ''})."})
    other = next((c for c in categories if c["category"] == "Other"), None)
    if other and other["pct"] >= 30:
        ins.append({"level": "warn", "title": f"{other['pct']}% of spending is uncategorised ('Other')",
                    "detail": "Correct some categories on the Records page — your edits train the model."})
    return ins


def compute_all(records):
    summary = compute_summary(records)
    categories = spending_by_category(records)
    trend = monthly_trend(records)
    mom = month_over_month(trend)
    recurring = recurring_signals(records)
    return {"summary": summary, "spending_by_category": categories,
            "top_categories": categories[:5], "monthly_trend": trend,
            "month_over_month": mom, "recurring": recurring,
            "insights": generate_insights(summary, categories, trend, mom, recurring)}


def get_analytics(user_id, date_from=None, date_to=None):
    import database
    import risk
    recs = database.get_records(user_id, {"date_from": date_from, "date_to": date_to})
    out = compute_all(recs)
    out["insights"] = risk.risk_insights(risk.summarize(recs)) + out["insights"]   # risk events first
    return out
