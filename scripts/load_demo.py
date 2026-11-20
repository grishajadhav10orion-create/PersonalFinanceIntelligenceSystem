"""Create ready-to-explore demo accounts.   Usage (from the project folder):  python scripts/load_demo.py
  demo       / demo1234   salaried user: 36 manual entries + two imported bank statements (Mar-Sep 2026)
  demo_risk  / demo1234   account with bounced EMI, overdraft, penalty and late-fee events (Jan-Feb 2026)
All data is made-up sample data. Existing demo accounts are left untouched."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A                                                              # noqa: E402
SD = os.path.join(ROOT, "sample_data")
PASSWORD = "demo1234"


def create(c, username):
    r = c.post("/api/signup", json={"username": username, "password": PASSWORD})
    if r.status_code != 201 and r.status_code != 200:
        return None
    return {"Authorization": "Bearer " + r.get_json()["token"]}


def import_file(c, H, name):
    with open(os.path.join(SD, name), "rb") as f:
        r = c.post("/api/import", data={"file": (f, name)}, headers=H, content_type="multipart/form-data")
    j = r.get_json()
    print(f"    imported {name}: {j.get('inserted')} new, {j.get('duplicates_skipped')} duplicates skipped")


def main():
    c = A.app.test_client()
    H = create(c, "demo")
    if H is None:
        print("Demo account 'demo' already exists: nothing to do (delete finance.db to start fresh).")
    else:
        print("Creating account 'demo' ...")
        manual = json.load(open(os.path.join(SD, "manual_entries_mar_jun_2026.json")))
        cats = sorted({m[2] for m in manual})
        c.post("/api/masters", json={"categories": cats, "subcategories": [], "opening_balance": 0,
                                     "receivers": sorted({m[4] for m in manual if m[0] == "expense"}),
                                     "payers": sorted({m[4] for m in manual if m[0] == "earning"})}, headers=H)
        for t, a, cat, sub, who, note, d in manual:      # manual entries first: they become the ML model's training labels
            c.post("/api/records", json={"type": t, "amount": a, "category": cat, "subcategory": sub,
                                         "receiver_payer": who, "notes": note, "date": d}, headers=H)
        print(f"    added {len(manual)} manual entries")
        for f in ("statement_1_jul_aug_2026.csv", "statement_2_15aug_30sep_2026.csv"):
            import_file(c, H, f)
    H2 = create(c, "demo_risk")
    if H2 is not None:
        print("Creating account 'demo_risk' ...")
        c.post("/api/masters", json={"categories": [], "subcategories": [], "receivers": [], "payers": [], "opening_balance": 0}, headers=H2)
        import_file(c, H2, "statement_risk_demo_jan_feb_2026.csv")
    print("\nDone. Log in with:  demo / demo1234   (or demo_risk / demo1234)")


if __name__ == "__main__":
    main()
