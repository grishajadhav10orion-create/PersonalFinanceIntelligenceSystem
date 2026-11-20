"""Persona tests. Run: python -m unittest tests.test_persona"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_fd, _db = tempfile.mkstemp(suffix=".db"); os.close(_fd)
os.environ["DB_PATH"] = _db
import persona as P, app as A                           # noqa: E402
SD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sample_data")

def rec(date, typ, amt, cat, who="", raw="", bal=None):
    return {"id": None, "date": date, "type": typ, "amount": amt, "category": cat, "receiver_payer": who,
            "raw_narration": raw, "balance_after": bal, "source": "manual"}

def months(n, salary=60000, rent=20000, emi=0, food=3000, shop=0, start=1):
    out = []
    for m in range(start, start + n):
        d = lambda x: f"2026-{m:02d}-{x:02d}"
        out += [rec(d(1), "earning", salary, "Salary", "Acme Pvt Ltd", "SALARY"), rec(d(3), "expense", rent, "Rent", "Landlord Person"),
                rec(d(10), "expense", food, "Food", "Swiggy")]
        if emi: out.append(rec(d(8), "expense", emi, "EMI & Loans", "Bajaj Finance Ltd"))
        if shop: out.append(rec(d(15), "expense", shop, "Shopping", "Amazon"))
    return out

class Personas(unittest.TestCase):
    def label(self, recs): return P.compute_persona(recs)["persona"]["label"]
    def test_insufficient_data(self):
        self.assertEqual(self.label([]), "Insufficient data"); self.assertEqual(self.label(months(1)), "Insufficient data")
    def test_disciplined_saver(self):
        self.assertEqual(self.label(months(4, salary=80000, rent=20000, food=4000)), "Salaried Disciplined Saver")
    def test_over_leveraged(self):
        self.assertEqual(self.label(months(4, salary=60000, rent=15000, emi=26000, food=8000, shop=8000)), "Over-Leveraged Spender")
    def test_cash_flow_stressed_from_risk_flags(self):
        recs = months(3) + [rec("2026-02-09", "expense", 590, "Fees", "", "ECS RETURN CHARGES-EMI BOUNCE")]
        self.assertEqual(self.label(recs), "Cash-Flow Stressed")
    def test_gig_freelancer(self):
        recs = []
        for m, a in ((1, 30000), (2, 8000), (3, 45000), (4, 12000)):
            recs += [rec(f"2026-{m:02d}-05", "earning", a, "Freelance", "Pixel Studio Llp", "FREELANCE INV"), rec(f"2026-{m:02d}-09", "expense", 9000, "Rent", "Owner Person")]
        self.assertEqual(self.label(recs), "Gig-Economy Freelancer")
    def test_json_schema_and_explanations(self):
        d = P.compute_persona(months(4, salary=80000))
        for k in ("schema_version", "data_coverage", "persona", "features", "income_streams", "spending_distribution", "recurring_commitments",
                  "risk", "counterparties", "persona_checks", "thresholds", "definitions", "limitations"): self.assertIn(k, d)
        self.assertTrue(d["persona"]["explanations"]); json.dumps(d)       # serialisable

class Integration(unittest.TestCase):
    def test_api_on_sample_data(self):
        c = A.app.test_client()
        def user(u):
            t = c.post("/api/signup", json={"username": u, "password": "secret1"}).get_json()["token"]; H = {"Authorization": "Bearer " + t}
            c.post("/api/masters", json={"categories": [], "subcategories": [], "receivers": [], "payers": [], "opening_balance": 0}, headers=H); return H
        H = user("persmain")
        for t, a, cat, sub, who, note, d in json.load(open(os.path.join(SD, "manual_entries_mar_jun_2026.json"))):
            c.post("/api/records", json={"type": t, "amount": a, "category": cat, "subcategory": sub, "receiver_payer": who, "notes": note, "date": d}, headers=H)
        for f in ("statement_1_jul_aug_2026.csv", "statement_2_15aug_30sep_2026.csv"):
            c.post("/api/import", data={"file": (open(os.path.join(SD, f), "rb"), f)}, headers=H, content_type="multipart/form-data")
        self.assertEqual(c.get("/api/persona", headers=H).get_json()["persona"]["label"], "Salaried Disciplined Saver")
        H2 = user("persrisk")
        c.post("/api/import", data={"file": (open(os.path.join(SD, "statement_risk_demo_jan_feb_2026.csv"), "rb"), "r.csv")}, headers=H2, content_type="multipart/form-data")
        d = c.get("/api/persona", headers=H2).get_json()
        self.assertEqual(d["persona"]["label"], "Cash-Flow Stressed"); self.assertEqual(d["risk"]["counts"]["bounced_payment"], 3)
        self.assertEqual(c.get("/api/persona").status_code, 401)

if __name__ == "__main__":
    unittest.main()
