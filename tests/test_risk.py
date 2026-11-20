"""Risk detection tests. Run: python -m unittest tests.test_risk"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_fd, _db = tempfile.mkstemp(suffix=".db"); os.close(_fd)
os.environ["DB_PATH"] = _db
import risk, app as A                                   # noqa: E402
from scripts.eval_risk import evaluate                  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))

class Rules(unittest.TestCase):
    def test_variants_recall_and_no_false_positives(self):
        r = evaluate()
        self.assertEqual(r["per_type"]["bounced_payment"]["recall"], 1.0)   # self-test on author-written variants
        for k, v in r["per_type"].items(): self.assertEqual(v["recall"], 1.0, k)
        self.assertEqual(r["false_positives_on_clean"], 0); self.assertEqual(r["issues"], [])
    def test_negative_balance_is_overdraft(self):
        self.assertEqual([f["type"] for f in risk.detect_flags("UPI-X", -1.0)], ["overdraft"])
        self.assertEqual(risk.detect_flags("UPI-X", 0.0), [])
    def test_manual_record_text_is_checked(self):
        self.assertEqual([f["type"] for f in risk.flags_for_record({"receiver_payer": "HDFC Bank", "notes": "EMI bounced"})], ["bounced_payment"])

class Integration(unittest.TestCase):
    def test_demo_statement_end_to_end(self):
        c = A.app.test_client()
        tok = c.post("/api/signup", json={"username": "riskuser", "password": "secret1"}).get_json()["token"]; H = {"Authorization": "Bearer " + tok}
        c.post("/api/masters", json={"categories": [], "subcategories": [], "receivers": [], "payers": [], "opening_balance": 0}, headers=H)
        f = os.path.join(HERE, "..", "sample_data", "statement_risk_demo_jan_feb_2026.csv")
        imp = c.post("/api/import", data={"file": (open(f, "rb"), "r.csv")}, headers=H, content_type="multipart/form-data").get_json()
        self.assertEqual(imp["rejected"], 0)
        self.assertEqual(imp["risk_flags_found"], {"bounced_payment": 3, "min_balance_penalty": 1, "overdraft": 2, "late_fee": 1, "payment_return": 1})
        recs = c.get("/api/records", headers=H).get_json()
        self.assertTrue(all("risk_flags" in r for r in recs)); self.assertEqual(sum(1 for r in recs if r["risk_flags"]), 8)
        rk = c.get("/api/risk", headers=H).get_json()
        self.assertEqual(rk["counts"]["bounced_payment"], 3); self.assertEqual(rk["distress_events"], 7)
        ins = c.get("/api/analytics", headers=H).get_json()["insights"]
        self.assertEqual(ins[0]["level"], "risk")

if __name__ == "__main__":
    unittest.main()
