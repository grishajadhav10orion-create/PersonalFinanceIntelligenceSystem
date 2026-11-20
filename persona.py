"""
Persona profiling: features -> rule-based persona -> structured JSON with explanations.
All values are computed from the stored records. Thresholds are assumptions (listed in THRESHOLDS and returned
in the JSON); the persona is rule-based, not a trained model.
"""
import datetime
import statistics

import analytics
import counterparty
import income
import risk

THRESHOLDS = {
    "salary_share_salaried_pct": 60, "stability_high_score": 75, "stability_medium_score": 50,
    "dti_low_pct": 30, "dti_high_pct": 40, "total_saving_rate_saver_pct": 20, "saving_rate_low_pct": 10,
    "business_share_gig_pct": 40, "salary_share_gig_max_pct": 30, "discretionary_heavy_pct": 50, "min_months": 2,
}
DISCRETIONARY = {"food", "shopping", "entertainment", "travel"}
EXCLUDED_FROM_SPEND_BASE = {"transfers", "investments"}
DEFINITIONS = {
    "income_stability": "score = (1 - coefficient of variation of monthly income) x 100, floored at 0; needs >= 2 months",
    "debt_to_income_pct": "expenses in EMI & Loans categories / total income x 100 over the stored period",
    "savings_rate_pct": "(income - expenses) / income x 100 (investments such as SIPs count as expenses here)",
    "investment_rate_pct": "expenses in the Investments category / income x 100",
    "total_saving_rate_pct": "savings rate + investment rate",
    "discretionary_share_pct": "Food + Shopping + Entertainment + Travel spend / total expenses excluding Transfers and Investments",
}
LIMITATIONS = [
    "Rule-based persona using the thresholds above; not a trained model and not validated on real accounts.",
    "Computed from the transactions stored in this app (statements + manual entries) for one user; other accounts are not visible.",
    "Partial first/last months can distort income stability; own-account transfers and credit-card payments are not excluded.",
    "Debt and discretionary measures depend on transaction categories being correct.",
]


def _pct(a, b):
    return round(a / b * 100, 1) if b else None


def _features(records):
    summary = analytics.compute_summary(records)
    trend = analytics.monthly_trend(records)
    cats = analytics.spending_by_category(records)
    recurring = analytics.recurring_signals(records)
    inc = income.summarize(records, recurring)
    rk = risk.summarize(records)
    months, inc_total, exp_total = len(trend), summary["total_income"], summary["total_expenses"]
    by_cat = {c["category"].lower(): c["total"] for c in cats}
    emi = sum(v for k, v in by_cat.items() if "emi" in k or "loan" in k)
    invest = sum(v for k, v in by_cat.items() if "invest" in k)
    base = sum(v for k, v in by_cat.items() if k not in EXCLUDED_FROM_SPEND_BASE)
    disc = sum(v for k, v in by_cat.items() if k in DISCRETIONARY)
    monthly_inc = [m["income"] for m in trend]
    stab = {"months_used": months, "cv": None, "score": None, "level": "Insufficient data",
            "salary_months": inc["by_stream"]["salary"]["months_present"]}
    if months >= THRESHOLDS["min_months"] and statistics.mean(monthly_inc) > 0:
        cv = statistics.pstdev(monthly_inc) / statistics.mean(monthly_inc)
        score = round(max(0.0, 1 - cv) * 100)
        stab.update(cv=round(cv, 3), score=score, level="High" if score >= THRESHOLDS["stability_high_score"]
                    else "Medium" if score >= THRESHOLDS["stability_medium_score"] else "Low")
    sav, inv = summary["savings_rate"], _pct(invest, inc_total)
    f = {"income_stability": stab, "debt_to_income_pct": _pct(emi, inc_total), "savings_rate_pct": sav,
         "investment_rate_pct": inv,
         "total_saving_rate_pct": round(sav + inv, 1) if sav is not None and inv is not None else None,
         "discretionary_share_pct": _pct(disc, base),
         "avg_monthly_income": round(inc_total / months, 2) if months else None,
         "avg_monthly_expenses": round(exp_total / months, 2) if months else None,
         "salary_share_pct": inc["by_stream"]["salary"]["share_pct"],
         "business_share_pct": inc["by_stream"]["business_revenue"]["share_pct"]}
    return summary, trend, cats, recurring, inc, rk, f


def _rules(f, rk):
    T, c, stab = THRESHOLDS, rk["counts"], f["income_stability"]
    n = lambda v: v if v is not None else float("nan")
    cond = lambda text, ok, actual: {"text": text, "passed": bool(ok), "actual": actual}
    pen = c["late_fee"] + c["min_balance_penalty"]
    return [
        ("Cash-Flow Stressed", "any", [
            cond("bounced payment events >= 1", c["bounced_payment"] >= 1, c["bounced_payment"]),
            cond("overdraft events >= 1", c["overdraft"] >= 1, c["overdraft"]),
            cond("penalty / late-fee / min-balance events >= 2", pen >= 2, pen)]),
        ("Over-Leveraged Spender", "all", [
            cond(f"debt-to-income >= {T['dti_high_pct']}%", n(f["debt_to_income_pct"]) >= T["dti_high_pct"], f["debt_to_income_pct"]),
            cond(f"savings rate < {T['saving_rate_low_pct']}%", n(f["savings_rate_pct"]) < T["saving_rate_low_pct"], f["savings_rate_pct"])]),
        ("Gig-Economy Freelancer", "all", [
            cond(f"salary share < {T['salary_share_gig_max_pct']}%", f["salary_share_pct"] < T["salary_share_gig_max_pct"], f["salary_share_pct"]),
            cond(f"business revenue share >= {T['business_share_gig_pct']}%", f["business_share_pct"] >= T["business_share_gig_pct"], f["business_share_pct"])]),
        ("Salaried Disciplined Saver", "all", [
            cond(f"salary share >= {T['salary_share_salaried_pct']}%", f["salary_share_pct"] >= T["salary_share_salaried_pct"], f["salary_share_pct"]),
            cond("income stability is High", stab["level"] == "High", stab["level"]),
            cond(f"debt-to-income < {T['dti_low_pct']}%", n(f["debt_to_income_pct"]) < T["dti_low_pct"], f["debt_to_income_pct"]),
            cond(f"total saving rate >= {T['total_saving_rate_saver_pct']}%", n(f["total_saving_rate_pct"]) >= T["total_saving_rate_saver_pct"], f["total_saving_rate_pct"])]),
        ("Discretionary-Heavy Spender", "all", [
            cond(f"discretionary share >= {T['discretionary_heavy_pct']}%", n(f["discretionary_share_pct"]) >= T["discretionary_heavy_pct"], f["discretionary_share_pct"]),
            cond(f"savings rate < {T['saving_rate_low_pct']}%", n(f["savings_rate_pct"]) < T["saving_rate_low_pct"], f["savings_rate_pct"])]),
        ("Balanced Salaried Earner", "all", [
            cond(f"salary share >= {T['salary_share_salaried_pct']}%", f["salary_share_pct"] >= T["salary_share_salaried_pct"], f["salary_share_pct"]),
            cond("total saving rate >= 5%", n(f["total_saving_rate_pct"]) >= 5, f["total_saving_rate_pct"]),
            cond(f"debt-to-income < {T['dti_high_pct']}%", n(f["debt_to_income_pct"]) < T["dti_high_pct"], f["debt_to_income_pct"])]),
    ]


def compute_persona(records):
    summary, trend, cats, recurring, inc, rk, f = _features(records)
    T = THRESHOLDS
    checks = [{"persona": p, "mode": m, "matched": (any if m == "any" else all)(c["passed"] for c in conds),
               "conditions": conds} for p, m, conds in _rules(f, rk)]
    if len(trend) < T["min_months"] or summary["total_income"] <= 0:
        label = "Insufficient data"
        expl = [f"Needs at least {T['min_months']} months of data and some income; found {len(trend)} month(s) and "
                f"total income of Rs.{summary['total_income']:,.0f}."]
    else:
        hit = next((c for c in checks if c["matched"]), None)
        if hit:
            label, expl = hit["persona"], [f"{c['text']} (actual: {c['actual']})" for c in hit["conditions"] if c["passed"]]
        else:
            label, expl = "Mixed / Unclassified", ["No persona rule was fully satisfied; see persona_checks for the closest rules."]
        s = inc["by_stream"]
        expl += [f"Income mix: salary {s['salary']['share_pct']}%, business {s['business_revenue']['share_pct']}%, "
                 f"investment returns {s['investment_returns']['share_pct']}%, P2P {s['p2p']['share_pct']}%.",
                 f"Savings rate {f['savings_rate_pct']}%, debt-to-income {f['debt_to_income_pct']}%, discretionary share "
                 f"{f['discretionary_share_pct']}%, income stability {f['income_stability']['level']}."]
    dates = sorted(r["date"] for r in records if r.get("date"))
    return {
        "schema_version": "1.0", "generated_on": datetime.date.today().isoformat(),
        "data_coverage": {"transactions": len(records), "months": len(trend),
                          "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
                          "statement_rows": sum(1 for r in records if r.get("source") == "statement"),
                          "manual_rows": sum(1 for r in records if r.get("source", "manual") != "statement")},
        "persona": {"label": label, "explanations": expl},
        "features": f,
        "income_streams": {k: v for k, v in inc.items() if k != "recent_credits"},
        "spending_distribution": cats[:8],
        "recurring_commitments": recurring[:10],
        "risk": {"counts": rk["counts"], "total_flags": rk["total_flags"], "distress_events": rk["distress_events"],
                 "events": rk["events"][:10]},
        "counterparties": counterparty.summarize(records, limit=10)["counterparties"],
        "persona_checks": checks, "thresholds": THRESHOLDS, "definitions": DEFINITIONS, "limitations": LIMITATIONS,
    }
