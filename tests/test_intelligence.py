"""Tests for import / categorisation / analytics. Run: python -m unittest tests.test_intelligence
(The ML test builds a small labelled set purely as a test fixture; nothing here is shipped as data.)"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_fd, _db = tempfile.mkstemp(suffix=".db"); os.close(_fd)
os.environ["DB_PATH"] = _db
import analytics, categorizer, database, importer   # noqa: E402

def rec(date, typ, amt, cat, who=""):
    return {"date": date, "type": typ, "amount": amt, "category": cat, "receiver_payer": who}

class Analytics(unittest.TestCase):
    def test_summary_and_savings_rate(self):
        s = analytics.compute_summary([rec("2026-01-05", "earning", 1000, "Salary"), rec("2026-01-06", "expense", 400, "Food")])
        self.assertEqual((s["total_income"], s["total_expenses"], s["net_cash_flow"], s["savings_rate"]), (1000, 400, 600, 60.0))
    def test_no_income_gives_none(self):
        self.assertIsNone(analytics.compute_summary([rec("2026-01-06", "expense", 400, "Food")])["savings_rate"])
    def test_mom_and_recurring(self):
        rs = [rec(f"2026-0{m}-05", "expense", 500, "Rent", "Landlord") for m in (1, 2, 3)]
        rs += [rec("2026-02-10", "expense", 1500, "Food")]
        a = analytics.compute_all(rs)
        self.assertEqual(a["month_over_month"]["expense_change_pct"], -75.0)   # Mar 500 vs Feb 2000
        self.assertEqual(a["recurring"][0]["name"], "Landlord")
        self.assertEqual(a["recurring"][0]["frequency"], "monthly")
    def test_empty(self):
        self.assertEqual(analytics.compute_all([])["insights"][0]["title"], "No transactions yet")

class Categorizer(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(categorizer.rule_categorize("UPI SWIGGY ORDER", "expense"), "Food")
        self.assertEqual(categorizer.rule_categorize("ACME SALARY AUG", "earning"), "Salary")
        self.assertIsNone(categorizer.rule_categorize("RANDOM TEXT", "expense"))
    def test_untrained_falls_back_to_rules(self):
        ml = categorizer.train_for_user([])
        self.assertFalse(ml.info["trained"])
        self.assertEqual(categorizer.categorize(None, "zomato", "expense")[:2], ("Food", "rule"))
        self.assertEqual(categorizer.categorize(None, "zzz", "expense")[:2], ("Other", "default"))
    def test_ml_trains_and_predicts(self):
        data = []
        for i in range(20):
            data.append({"type": "expense", "category": "Pets", "receiver_payer": f"Happy Paws Vet {i}", "notes": "", "subcategory": ""})
            data.append({"type": "expense", "category": "Gym", "receiver_payer": f"Iron Gym Fee {i}", "notes": "", "subcategory": ""})
        ml = categorizer.train_for_user(data)
        self.assertTrue(ml.info["trained"])
        self.assertEqual(ml.predict("Happy Paws Vet", "expense")[0], "Pets")
        self.assertIsNotNone(ml.info["cv_accuracy"])

class ImportDedupe(unittest.TestCase):
    def test_same_file_twice(self):
        database.init_db()
        uid = database.create_user("t_imp", "x")
        database.save_masters(uid, ["Food"], [], [], [], 0)
        class F:  # minimal FileStorage stand-in
            filename = "s.csv"
            def save(self, p): open(p, "wb").write(open(os.path.join(os.path.dirname(__file__), "..", "sample_data", "sample_statement.csv"), "rb").read())
        r1 = importer.import_statement(uid, F()); r2 = importer.import_statement(uid, F())
        self.assertEqual((r1["inserted"], r2["inserted"], r2["duplicates_skipped"]), (25, 0, 25))



class FixedBugs(unittest.TestCase):
    def test_rent_detected_despite_varied_narration_dates_and_amount_change(self):
        rs = [rec("2026-06-03","expense",15000,"Rent","Ramesh Kumar Sharma Rent Jun"),
              rec("2026-07-05","expense",15000,"Rent","RAMESH K SHARMA RENT PAYMENT"),
              rec("2026-08-01","expense",15000,"Rent","Ramesh Kumar Sharma Rent Aug"),
              rec("2026-09-03","expense",25000,"Rent","Ramesh Kumar Sharma Rent Sep"),
              rec("2026-10-03","expense",25000,"Rent","Ramesh Kumar Sharma Rent Oct")]
        got = [(s["typical_amount"], s["occurrences"]) for s in analytics.recurring_signals(rs)]
        self.assertIn((25000, 2), got)      # new rent level detected
    def test_rent_found_by_category_when_payee_differs_and_duplicates_counted_once(self):
        rs = [rec("2026-08-03","expense",25000,"Rent","Landlord A"), rec("2026-08-03","expense",25000,"Rent","Landlord A"),
              rec("2026-09-04","expense",25000,"Rent","House Owner")]
        s = analytics.recurring_signals(rs)
        self.assertEqual((s[0]["typical_amount"], s[0]["occurrences"], s[0]["frequency"]), (25000, 2, "monthly"))
    def test_variable_spending_not_recurring(self):
        rs = [rec("2026-08-02","expense",300,"Food","Swiggy"), rec("2026-08-20","expense",640,"Food","Swiggy"),
              rec("2026-09-09","expense",410,"Food","Swiggy"), rec("2026-09-28","expense",220,"Food","Swiggy")]
        self.assertEqual(analytics.recurring_signals(rs), [])
    def test_budget_counts_existing_records(self):
        database.init_db()
        uid = database.create_user("t_budget", "x")
        database.save_masters(uid, ["Food"], [], [], [], 0)
        import datetime
        conn = database.get_db()
        for d, a in [("2026-09-02", 1000), ("2026-09-15", 700)]:     # records that exist BEFORE the budget
            conn.execute("INSERT INTO records (user_id,type,amount,category,subcategory,receiver_payer,notes,date) VALUES (?,?,?,?,?,?,?,?)", (uid,"expense",a,"Food","","","",d))
        conn.commit(); conn.close()
        database.set_budget(uid, "monthly", 2000, "food")
        b = database.get_budget_progress(uid)[0]
        self.assertEqual((b["spent"], b["pct"]), (1700, 85))
        self.assertEqual(database.check_budget_alerts(uid)[0]["status"], "warning")

if __name__ == "__main__":
    unittest.main()
