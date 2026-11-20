"""Cash-flow forecast tests. Run: python -m unittest tests.test_forecast  (no network; the LLM call is mocked)"""
import datetime, json, os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_persona import rec, A                                   # noqa: E402  (also sets a temporary DB_PATH)
import forecast as F, forecast_ai as FA, llm_insights as L         # noqa: E402

TODAY = datetime.date(2026, 12, 15)

def month(y, m, salary=60000, rent=20000, food=5000, extra=0):
    d = lambda x: f"{y}-{m:02d}-{x:02d}"
    out = [rec(d(1), "earning", salary, "Salary", "Acme Pvt Ltd", "SALARY"), rec(d(3), "expense", rent, "Rent", "Landlord Person"),
           rec(d(10), "expense", food, "Food", "Swiggy")]
    if extra: out.append(rec(d(20), "expense", extra, "Shopping", "Amazon"))
    return out

def run(n, start=1, **kw):
    out = []
    for i in range(n):
        t = start - 1 + i; out += month(2026 + t // 12, t % 12 + 1, **kw)
    return out

class Forecast(unittest.TestCase):
    def test_insufficient_data(self):
        self.assertEqual(F.compute_forecast([], TODAY)["status"], "insufficient_data")
        self.assertEqual(F.compute_forecast(run(1), TODAY)["status"], "insufficient_data")

    def test_stable_history_gives_stable_forecast_and_next_months(self):
        fc = F.compute_forecast(run(9), TODAY)
        self.assertEqual(fc["status"], "ok"); self.assertEqual([f["month"] for f in fc["forecast"]], ["2026-10", "2026-11", "2026-12"])
        for f in fc["forecast"]:
            self.assertAlmostEqual(f["income"]["value"], 60000, delta=500); self.assertAlmostEqual(f["expenses"]["value"], 25000, delta=500)
        self.assertEqual(fc["expense_model"]["confidence"], "high")

    def test_chosen_model_has_lowest_backtest_error(self):
        recs = run(8)
        recs = [r for r in recs if not (r["category"] == "Food")] + [rec(f"2026-{m:02d}-10", "expense", 3000 + 900 * m + (700 if m % 2 else 0), "Food", "Swiggy") for m in range(1, 9)]
        em = F.compute_forecast(recs, TODAY)["expense_model"]
        ok = [r for r in em["backtest"] if r["mae"] is not None]
        self.assertEqual(em["mae"], min(r["mae"] for r in ok)); self.assertTrue(any(r["chosen"] for r in em["backtest"]))

    def test_few_months_uses_average_without_range(self):
        fc = F.compute_forecast(run(3), TODAY)
        self.assertEqual(fc["expense_model"]["confidence"], "low"); self.assertIsNone(fc["forecast"][0]["net"]["low"])

    def test_current_partial_month_is_left_out(self):
        fc = F.compute_forecast(run(12), datetime.date(2026, 12, 10))
        self.assertEqual(fc["last_month"], "2026-11"); self.assertTrue(any("in progress" in n for n in fc["notes"]))

    def test_gap_uses_latest_contiguous_months_only(self):
        recs = run(3) + run(5, start=7)               # Jan-Mar, then Jul-Nov
        fc = F.compute_forecast(recs, TODAY)
        self.assertEqual(fc["months_used"], 5); self.assertEqual(fc["history"][0]["month"], "2026-07")
        self.assertTrue(any("gap" in n for n in fc["notes"]))

    def test_transfers_excluded_and_no_negative_values(self):
        recs = run(6) + [rec(f"2026-{m:02d}-12", "expense", 90000, "Transfers", "HDFC Credit Card") for m in range(1, 7)]
        fc = F.compute_forecast(recs, TODAY)
        self.assertAlmostEqual(fc["history"][0]["expenses"], 25000, delta=1)
        self.assertTrue(all(f[k]["value"] >= 0 and (f[k]["low"] is None or f[k]["low"] >= 0) for f in fc["forecast"] for k in ("income", "expenses")))

    def test_net_is_income_minus_expenses(self):
        f = F.compute_forecast(run(7, extra=2000), TODAY)["forecast"][0]
        self.assertAlmostEqual(f["net"]["value"], f["income"]["value"] - f["expenses"]["value"], places=1)

class ForecastAI(unittest.TestCase):
    def test_context_has_no_names(self):
        recs = run(7) + [rec("2026-03-05", "expense", 100, "Food", "SECRET PERSON", "UPI-SECRET PERSON-9988776655")]
        sent = json.dumps(FA.build_context(F.compute_forecast(recs, TODAY)))
        for bad in ("SECRET", "Acme", "Landlord", "Swiggy", "9988776655"): self.assertNotIn(bad, sent)

    def test_explain_uses_llm_and_validates(self):
        fc = F.compute_forecast(run(7), TODAY); FA._cache.clear(); FA._last_call.clear()
        good = json.dumps({"summary": "Expect about Rs. 35,000 net.", "watch_outs": ["Few months of data"], "suggestions": []})
        with mock.patch.object(L, "is_configured", return_value=True), mock.patch.object(L, "_call_api", return_value=good):
            self.assertEqual(FA.explain("u1", fc)["summary"], "Expect about Rs. 35,000 net.")
        with self.assertRaises(L.LLMError): FA.parse_response("not json")

class Routes(unittest.TestCase):
    def test_routes_require_login_and_work(self):
        c = A.app.test_client()
        self.assertEqual(c.get("/api/forecast").status_code, 401)
        t = c.post("/api/signup", json={"username": "fc_user", "password": "secret1"}).get_json()["token"]; H = {"Authorization": "Bearer " + t}
        self.assertEqual(c.get("/api/forecast", headers=H).get_json()["status"], "insufficient_data")
        self.assertEqual(c.post("/api/forecast/explain", headers=H, json={}).status_code, 502 if L.is_configured() else 503)

if __name__ == "__main__":
    unittest.main()
