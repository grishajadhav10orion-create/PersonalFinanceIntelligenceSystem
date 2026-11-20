"""Counterparty classification tests. Run: python -m unittest tests.test_counterparty"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_fd, _db = tempfile.mkstemp(suffix=".db"); os.close(_fd)
os.environ["DB_PATH"] = _db
import counterparty as C, app as A                      # noqa: E402
SD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sample_data")

class Rules(unittest.TestCase):
    CASES = [("Ramesh Kumar Sharma Rent Aug", "UPI-RAMESH", "expense", "Rent", "individual"),
             ("Swaranjali Music Academy Singing Class Fee", "UPI", "expense", "", "merchant"),
             ("Ach D Bajaj Finance Ltd EMI", "ACH D", "expense", "", "institution"),
             ("Neft Cr Acme Technologies Pvt Ltd Salary", "NEFT CR SALARY", "earning", "", "employer"),
             ("Sharma Chai Corner", "UPI", "expense", "", "merchant"),
             ("Ananya Deshpande Split", "UPI", "expense", "", "individual"),
             ("Spotify India", "UPI", "expense", "", "merchant"),
             ("Brightpixel Studio Llp Freelance Inv", "IMPS", "earning", "", "merchant"),
             ("HDFC Mutual Fund", "", "expense", "Investments", "institution"),
             ("Zzz", "", "expense", "", "unknown")]
    def test_cases(self):
        for name, nar, t, cat, want in self.CASES:
            self.assertEqual(C.classify_counterparty(name, nar, t, cat)["type"], want, name)
    def test_reason_is_always_given(self):
        for name, nar, t, cat, _ in self.CASES: self.assertTrue(C.classify_counterparty(name, nar, t, cat)["reason"])

class Integration(unittest.TestCase):
    def test_statement_and_manual_spellings_merge(self):
        c = A.app.test_client()
        tok = c.post("/api/signup", json={"username": "cpuser", "password": "secret1"}).get_json()["token"]; H = {"Authorization": "Bearer " + tok}
        c.post("/api/masters", json={"categories": [], "subcategories": [], "receivers": [], "payers": [], "opening_balance": 0}, headers=H)
        for t, a, cat, sub, who, note, d in json.load(open(os.path.join(SD, "manual_entries_mar_jun_2026.json"))):
            c.post("/api/records", json={"type": t, "amount": a, "category": cat, "subcategory": sub, "receiver_payer": who, "notes": note, "date": d}, headers=H)
        c.post("/api/import", data={"file": (open(os.path.join(SD, "statement_1_jul_aug_2026.csv"), "rb"), "s.csv")}, headers=H, content_type="multipart/form-data")
        d = c.get("/api/counterparties", headers=H).get_json(); by = {x["name"].lower()[:12]: x for x in d["counterparties"]}
        names = [x["name"].lower() for x in d["counterparties"]]
        self.assertEqual(sum("acme" in n for n in names), 1); self.assertEqual(sum("ramesh" in n for n in names), 1)   # merged, not duplicated
        self.assertEqual(next(x for x in d["counterparties"] if "acme" in x["name"].lower())["type"], "employer")
        self.assertEqual(next(x for x in d["counterparties"] if "ramesh" in x["name"].lower())["type"], "individual")
        self.assertEqual(next(x for x in d["counterparties"] if "bajaj" in x["name"].lower())["type"], "institution")

if __name__ == "__main__":
    unittest.main()
