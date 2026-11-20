"""Income stream tests. Run: python -m unittest tests.test_income"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_fd, _db = tempfile.mkstemp(suffix=".db"); os.close(_fd)
os.environ["DB_PATH"] = _db
import income, app as A                                 # noqa: E402
SD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sample_data")

def cr(date, amt, who="", raw="", cat="Other Income", notes=""):
    return {"id": None, "date": date, "type": "earning", "amount": amt, "receiver_payer": who,
            "raw_narration": raw, "category": cat, "notes": notes}

def stream(records, i=0):
    return income.classify_credits(records)[id(records[i])]["stream"]

class Rules(unittest.TestCase):
    def test_each_stream(self):
        self.assertEqual(stream([cr("2026-08-01", 50000, "Acme", "NEFT CR-ACME-SALARY JUL")]), "salary")
        self.assertEqual(stream([cr("2026-08-05", 12000, "Brightpixel Studio Llp", "IMPS-BRIGHTPIXEL STUDIO LLP-FREELANCE INV 0231")]), "business_revenue")
        self.assertEqual(stream([cr("2026-09-30", 372, "Int.pd", "INT.PD:01-07-2026 TO 30-09-2026")]), "investment_returns")
        self.assertEqual(stream([cr("2026-08-09", 900, "Rohan Mehta Payment", "UPI-ROHAN MEHTA-PAYMENT")]), "p2p")
        self.assertEqual(stream([cr("2026-08-22", 1249, "Amazon Pay India", "UPI-AMAZON PAY INDIA-REFUND")]), "other")
        self.assertEqual(stream([cr("2026-02-08", 12500, "Ach D Ret Bajaj Finance", "ACH D RET-BAJAJ FINANCE LTD-EMI-INSUFFICIENT FUNDS")]), "other")
    def test_categories_for_manual_entries(self):
        self.assertEqual(stream([cr("2026-05-30", 6500, "Pixelcraft Design", "", "Freelance")]), "business_revenue")
        self.assertEqual(stream([cr("2026-05-01", 62000, "Acme", "", "Salary")]), "salary")
    def test_recurring_large_company_credit_without_salary_word_is_salary(self):
        rs = [cr(f"2026-0{m}-01", 55000, "Globex Corporation Pvt Ltd", "NEFT CR-GLOBEX CORPORATION PVT LTD") for m in (6, 7, 8)]
        self.assertEqual({v["stream"] for v in income.classify_credits(rs).values()}, {"salary"})
    def test_one_off_company_credit_is_business_and_small_recurring_is_not_salary(self):
        self.assertEqual(stream([cr("2026-08-05", 8000, "Delta Traders Pvt Ltd", "NEFT CR-DELTA TRADERS PVT LTD")]), "business_revenue")
        rs = [cr(f"2026-0{m}-05", 3000, "Delta Traders Pvt Ltd", "NEFT") for m in (6, 7, 8)] + [cr("2026-08-01", 60000, "Acme", "SALARY")]
        self.assertEqual(income.classify_credits(rs)[id(rs[0])]["stream"], "business_revenue")   # < 50% of largest credit
    def test_debits_ignored_and_empty_ok(self):
        self.assertEqual(income.classify_credits([{"type": "expense", "amount": 5, "date": "2026-01-01"}]), {})
        self.assertEqual(income.summarize([])["total_income"], 0)

class Integration(unittest.TestCase):
    def test_sample_datasets_and_api(self):
        c = A.app.test_client()
        tok = c.post("/api/signup", json={"username": "incuser", "password": "secret1"}).get_json()["token"]; H = {"Authorization": "Bearer " + tok}
        c.post("/api/masters", json={"categories": [], "subcategories": [], "receivers": [], "payers": [], "opening_balance": 0}, headers=H)
        for t, a, cat, sub, who, note, d in json.load(open(os.path.join(SD, "manual_entries_mar_jun_2026.json"))):
            c.post("/api/records", json={"type": t, "amount": a, "category": cat, "subcategory": sub, "receiver_payer": who, "notes": note, "date": d}, headers=H)
        for f in ("statement_1_jul_aug_2026.csv", "statement_2_15aug_30sep_2026.csv"):
            c.post("/api/import", data={"file": (open(os.path.join(SD, f), "rb"), f)}, headers=H, content_type="multipart/form-data")
        d = c.get("/api/income-streams", headers=H).get_json()
        self.assertEqual(d["by_stream"]["salary"]["total"], 7 * 62000); self.assertEqual(d["by_stream"]["salary"]["months_present"], 7)
        self.assertEqual(d["by_stream"]["investment_returns"]["total"], 372); self.assertEqual(d["by_stream"]["p2p"]["count"], 7)
        self.assertEqual(d["primary_stream"], "salary")
        recs = c.get("/api/records", headers=H).get_json()
        self.assertTrue(all(("income_stream" in r) for r in recs)); self.assertTrue(all(r["income_stream"] is None for r in recs if r["type"] == "expense"))

if __name__ == "__main__":
    unittest.main()
