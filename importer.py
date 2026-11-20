"""Bank statement import: parse (bsi package) -> clean narration -> categorise -> store."""
import hashlib
import os
import tempfile

import categorizer
import database
import risk
from bsi.extractor import extract_statement
from bsi.narration_intelligence import enrich_transactions


def fingerprint(date, withdrawal, deposit, closing_balance):
    """Stable id for a bank row. The running balance after the row is included so two
    genuinely identical same-day purchases (which have different balances) are kept,
    while the same row appearing in two overlapping statements is detected."""
    raw = f"{date}|{withdrawal:.2f}|{deposit:.2f}|{closing_balance:.2f}"
    return hashlib.sha1(raw.encode()).hexdigest()


def import_statement(user_id, file_storage):
    suffix = os.path.splitext(file_storage.filename or "")[1].lower()
    if suffix not in (".csv", ".json", ".xls", ".xlsx", ".txt", ".pdf"):
        raise ValueError("Unsupported file type. Upload a .csv, .xls, .xlsx, .txt, .json or .pdf statement.")
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        file_storage.save(tmp)
        valid, rejected, file_type = extract_statement(tmp)
    finally:
        os.remove(tmp)

    rejected = list(rejected)
    ml = categorizer.train_for_user(database.get_labeled_records(user_id))
    masters = database.get_masters(user_id) or {"categories": []}
    existing_cats = list(masters["categories"])

    rows, counts = [], {"ml": 0, "rule": 0, "default": 0}
    for t in enrich_transactions(valid):
        w, d = t["withdrawal"], t["deposit"]
        if (w > 0) == (d > 0):   # both zero or both set -> can't tell expense from income
            rejected.append({**t, "reason": "withdrawal and deposit are both zero or both set"})
            continue
        typ, amount = ("expense", w) if w > 0 else ("earning", d)
        text = categorizer.record_text({"raw_narration": t["narration"],
                                        "receiver_payer": t["counterparty"]})
        cat, src, conf = categorizer.categorize(ml if ml.info["trained"] else None, text, typ)
        cat = categorizer.match_existing_name(cat, existing_cats)
        counts[src] += 1
        rows.append({"type": typ, "amount": amount, "category": cat,
                     "receiver_payer": t["counterparty"][:80], "date": t["date"],
                     "raw_narration": t["narration"], "bank_ref": t["reference_number"],
                     "balance_after": t["closing_balance"],
                     "dedupe_key": fingerprint(t["date"], w, d, t["closing_balance"]),
                     "category_source": src, "category_confidence": conf})

    database.ensure_master_categories(user_id, sorted({r["category"] for r in rows}))
    inserted, dup = database.insert_imported_records(user_id, rows)
    dates = sorted(r["date"] for r in rows)
    risk_counts = {}
    for r in rows:
        for f in risk.detect_flags(r["raw_narration"], r["balance_after"]):
            risk_counts[f["type"]] = risk_counts.get(f["type"], 0) + 1
    return {"risk_flags_found": risk_counts, "file_type": file_type, "rows_found": len(valid) + len(rejected),
            "inserted": inserted, "duplicates_skipped": dup, "rejected": len(rejected),
            "rejected_sample": [{"reason": r.get("reason"), "narration": r.get("narration", "")}
                                for r in rejected[:5]],
            "date_from": dates[0] if dates else None, "date_to": dates[-1] if dates else None,
            "categorized_by": counts, "ml_status": ml.info}


def recategorize_user(user_id):
    """Re-run categorisation on rows that were auto-categorised (never touches user labels)."""
    ml = categorizer.train_for_user(database.get_labeled_records(user_id))
    masters = database.get_masters(user_id) or {"categories": []}
    cats = list(masters["categories"])
    changed = 0
    new_cats = set()
    for r in database.get_auto_categorized_records(user_id):
        cat, src, conf = categorizer.categorize(ml if ml.info["trained"] else None,
                                                categorizer.record_text(r), r["type"])
        cat = categorizer.match_existing_name(cat, cats)
        if (cat, src) != (r["category"], r["category_source"]):
            changed += 1
        new_cats.add(cat)
        database.set_auto_category(r["id"], user_id, cat, src, conf)
    database.ensure_master_categories(user_id, sorted(new_cats))
    return {"changed": changed, "ml_status": ml.info}
