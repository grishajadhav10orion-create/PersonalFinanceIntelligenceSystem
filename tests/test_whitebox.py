"""
=============================================================================
FinTrack — WHITE BOX TEST SUITE
=============================================================================

Testing Strategy: White Box (Structural / Glass-Box) Testing
Technique       : Statement Coverage, Branch Coverage, Path Coverage

What white-box tests do:
  - Test internal logic of every function in app.py and database.py
  - Verify every branch (if/else, try/except) is exercised
  - Use direct API calls via Flask test client (no browser needed)
  - Check exact HTTP status codes, JSON response shapes, DB side-effects

Coverage targets:
  Module          Functions Tested
  ----------      -----------------------
  app.py          signup, login, create_masters, edit_masters, fetch_masters,
                  dashboard, create_record, list_records, edit_record,
                  remove_record, create_budget, list_budgets, remove_budget,
                  budget_alerts, auth_required decorator
  database.py     init_db, create_user, get_user_by_username, has_masters,
                  save_masters, update_masters, get_masters, add_record,
                  get_record_by_id, get_records (all filter branches),
                  update_record, delete_record, get_dashboard_data,
                  set_budget, get_budgets, delete_budget, check_budget_alerts

Run:
  cd finance_app
  python -m pytest tests/test_whitebox.py -v --tb=short

=============================================================================
"""

import json
import os
import sys
import tempfile
import types
import unittest

# ---------------------------------------------------------------------------
# bcrypt mock — makes the suite runnable even if bcrypt is not pip-installed.
# When bcrypt IS installed the real module takes precedence automatically.
# ---------------------------------------------------------------------------
try:
    import bcrypt  # noqa: F401
except ModuleNotFoundError:
    _mock_bcrypt = types.ModuleType("bcrypt")
    _mock_bcrypt.hashpw   = lambda pw, salt: b"hashed_" + (pw if isinstance(pw, bytes) else pw.encode())
    _mock_bcrypt.gensalt  = lambda: b"salt"
    _mock_bcrypt.checkpw  = lambda pw, hashed: True   # always passes in test env
    sys.modules["bcrypt"] = _mock_bcrypt

# ---------------------------------------------------------------------------
# Path setup — allow importing app and database from parent directory
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Use a temp DB so tests never touch production finance.db
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DB_PATH"] = _tmp_db.name

import database  # noqa: E402  (must come after DB_PATH is set)
import app as flask_app  # noqa: E402

flask_app.app.config["TESTING"] = True
flask_app.app.config["SECRET_KEY"] = "test-secret-key-whitebox"


# ===========================================================================
# Helper utilities
# ===========================================================================

def _client():
    return flask_app.app.test_client()


def _register_and_login(client, username="wbuser", password="Secure123"):
    """Register a fresh user and return (token, user_id)."""
    rv = client.post("/api/signup", json={"username": username, "password": password})
    data = rv.get_json()
    return data.get("token"), username


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_masters(client, token, balance=5000.0):
    """POST masters for a logged-in user and return response."""
    return client.post(
        "/api/masters",
        json={
            "categories": ["Food", "Salary", "Transport"],
            "subcategories": ["Groceries", "Dining"],
            "receivers": ["Swiggy", "Amazon"],
            "payers": ["Employer"],
            "opening_balance": balance,
        },
        headers=_auth_headers(token),
    )


# ===========================================================================
# WB-TS1 — Authentication Module
# ===========================================================================

class WB_TS1_Authentication(unittest.TestCase):
    """
    Test Scenario 1: Authentication — signup and login logic.

    Branch coverage goals:
      signup:  missing fields / short username / short password /
               duplicate username / success
      login:   user not found / wrong password / success
      auth_required: missing header / invalid token / expired token / success
    """

    def setUp(self):
        database.init_db()
        self.client = _client()
        self.unique = id(self)  # makes usernames unique per test

    # ── TC-WB-01: Signup — missing username ──────────────────────────────
    def test_wb01_signup_missing_username(self):
        """Branch: not username → 400."""
        rv = self.client.post("/api/signup", json={"username": "", "password": "pass123"})
        self.assertEqual(rv.status_code, 400)
        self.assertIn("required", rv.get_json()["error"].lower())

    # ── TC-WB-02: Signup — username too short ────────────────────────────
    def test_wb02_signup_username_too_short(self):
        """Branch: len(username) < 3 → 400."""
        rv = self.client.post("/api/signup", json={"username": "ab", "password": "pass123"})
        self.assertEqual(rv.status_code, 400)
        self.assertIn("3", rv.get_json()["error"])

    # ── TC-WB-03: Signup — password too short ────────────────────────────
    def test_wb03_signup_password_too_short(self):
        """Branch: len(password) < 6 → 400."""
        rv = self.client.post("/api/signup", json={"username": "validuser", "password": "abc"})
        self.assertEqual(rv.status_code, 400)
        self.assertIn("6", rv.get_json()["error"])

    # ── TC-WB-04: Signup — success path ──────────────────────────────────
    def test_wb04_signup_success(self):
        """Branch: all valid → 201, token returned, needs_masters=True."""
        uname = f"wb_user_{self.unique}"
        rv = self.client.post("/api/signup", json={"username": uname, "password": "Secure123"})
        self.assertEqual(rv.status_code, 201)
        body = rv.get_json()
        self.assertIn("token", body)
        self.assertTrue(body["needs_masters"])

    # ── TC-WB-05: Signup — duplicate username ────────────────────────────
    def test_wb05_signup_duplicate_username(self):
        """Branch: get_user_by_username returns user → 409."""
        uname = f"dup_user_{self.unique}"
        self.client.post("/api/signup", json={"username": uname, "password": "Secure123"})
        rv = self.client.post("/api/signup", json={"username": uname, "password": "Secure123"})
        self.assertEqual(rv.status_code, 409)
        self.assertIn("taken", rv.get_json()["error"].lower())

    # ── TC-WB-06: Login — user not found ─────────────────────────────────
    def test_wb06_login_user_not_found(self):
        """Branch: get_user_by_username returns None → 401."""
        rv = self.client.post("/api/login", json={"username": "no_such_user", "password": "whatever"})
        self.assertEqual(rv.status_code, 401)

    # ── TC-WB-07: Login — wrong password ─────────────────────────────────
    def test_wb07_login_wrong_password(self):
        """
        Branch: bcrypt.checkpw fails → 401.
        When real bcrypt is installed: wrong password → 401 Unauthorized.
        When mock bcrypt used (no package): checkpw always True → test skipped.
        Branch is covered by TC-BB-05 in the Selenium black-box suite.
        """
        import sys
        bcrypt_mod = sys.modules.get("bcrypt")
        # Real bcrypt has __file__ attribute; our mock does not
        using_mock = not hasattr(bcrypt_mod, "__file__")
        if using_mock:
            self.skipTest(
                "bcrypt mock active — wrong-password branch not exercisable. "
                "Install bcrypt (pip install bcrypt) to enable this test case."
            )
        uname = f"wb_login_{self.unique}"
        self.client.post("/api/signup", json={"username": uname, "password": "RightPass1"})
        rv = self.client.post("/api/login", json={"username": uname, "password": "WrongPass1"})
        self.assertEqual(rv.status_code, 401)

    # ── TC-WB-08: Login — success, needs_masters flag ─────────────────────
    def test_wb08_login_success_needs_masters_true(self):
        """Branch: valid credentials, no masters yet → needs_masters=True."""
        uname = f"wb_nm_{self.unique}"
        self.client.post("/api/signup", json={"username": uname, "password": "Secure123"})
        rv = self.client.post("/api/login", json={"username": uname, "password": "Secure123"})
        self.assertEqual(rv.status_code, 200)
        body = rv.get_json()
        self.assertIn("token", body)
        self.assertTrue(body["needs_masters"])

    # ── TC-WB-09: Login — needs_masters false after masters set ───────────
    def test_wb09_login_needs_masters_false_after_setup(self):
        """Branch: has_masters → True → needs_masters=False in response."""
        uname = f"wb_has_{self.unique}"
        rv = self.client.post("/api/signup", json={"username": uname, "password": "Secure123"})
        token = rv.get_json()["token"]
        _setup_masters(self.client, token)
        rv = self.client.post("/api/login", json={"username": uname, "password": "Secure123"})
        self.assertFalse(rv.get_json()["needs_masters"])

    # ── TC-WB-10: auth_required — missing Authorization header ───────────
    def test_wb10_protected_route_no_token(self):
        """Branch: auth header missing → 401."""
        rv = self.client.get("/api/dashboard")
        self.assertEqual(rv.status_code, 401)
        self.assertIn("Unauthorized", rv.get_json()["error"])

    # ── TC-WB-11: auth_required — malformed token ─────────────────────────
    def test_wb11_protected_route_bad_token(self):
        """Branch: jwt.decode raises InvalidTokenError → 401."""
        rv = self.client.get("/api/dashboard", headers={"Authorization": "Bearer not.a.valid.jwt"})
        self.assertEqual(rv.status_code, 401)


# ===========================================================================
# WB-TS2 — Masters Module
# ===========================================================================

class WB_TS2_Masters(unittest.TestCase):
    """
    Test Scenario 2: Masters — create, fetch, edit logic.

    Branch coverage goals:
      create_masters: missing field / bad balance / already exists / success
      edit_masters:   no masters yet / missing field / success
      fetch_masters:  not configured / success
    """

    def setUp(self):
        database.init_db()
        self.client = _client()
        uname = f"mst_{id(self)}"
        rv = self.client.post("/api/signup", json={"username": uname, "password": "Secure123"})
        self.token = rv.get_json()["token"]

    def _hdrs(self):
        return _auth_headers(self.token)

    # ── TC-WB-12: Create masters — missing required field ─────────────────
    def test_wb12_create_masters_missing_field(self):
        """Branch: field not in data → 400."""
        rv = self.client.post(
            "/api/masters",
            json={"categories": ["Food"], "subcategories": [], "receivers": [], "payers": []},
            # opening_balance missing
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn("opening_balance", rv.get_json()["error"])

    # ── TC-WB-13: Create masters — invalid balance type ───────────────────
    def test_wb13_create_masters_invalid_balance(self):
        """Branch: float(opening_balance) raises ValueError → 400."""
        rv = self.client.post(
            "/api/masters",
            json={
                "categories": ["Food"], "subcategories": [],
                "receivers": [], "payers": [], "opening_balance": "not-a-number"
            },
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn("number", rv.get_json()["error"].lower())

    # ── TC-WB-14: Create masters — success path ───────────────────────────
    def test_wb14_create_masters_success(self):
        """Branch: all valid → 201, DB row created."""
        rv = _setup_masters(self.client, self.token)
        self.assertEqual(rv.status_code, 201)
        self.assertIn("saved", rv.get_json()["message"].lower())

    # ── TC-WB-15: Create masters — already configured ────────────────────
    def test_wb15_create_masters_already_exists(self):
        """Branch: has_masters → True → 409."""
        _setup_masters(self.client, self.token)
        rv = _setup_masters(self.client, self.token)
        self.assertEqual(rv.status_code, 409)

    # ── TC-WB-16: Fetch masters — not yet configured ──────────────────────
    def test_wb16_fetch_masters_not_configured(self):
        """Branch: get_masters returns None → 404."""
        rv = self.client.get("/api/masters", headers=self._hdrs())
        self.assertEqual(rv.status_code, 404)

    # ── TC-WB-17: Fetch masters — success ────────────────────────────────
    def test_wb17_fetch_masters_success(self):
        """Branch: masters exist → 200, returns correct JSON structure."""
        _setup_masters(self.client, self.token, balance=7500.0)
        rv = self.client.get("/api/masters", headers=self._hdrs())
        self.assertEqual(rv.status_code, 200)
        body = rv.get_json()
        self.assertIn("categories", body)
        self.assertIn("Food", body["categories"])
        self.assertAlmostEqual(body["opening_balance"], 7500.0)

    # ── TC-WB-18: Edit masters — no masters yet ───────────────────────────
    def test_wb18_edit_masters_not_yet_created(self):
        """Branch: not has_masters → 404."""
        rv = self.client.put(
            "/api/masters",
            json={
                "categories": ["New"], "subcategories": [],
                "receivers": [], "payers": [], "opening_balance": 0
            },
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 404)

    # ── TC-WB-19: Edit masters — success, values updated ─────────────────
    def test_wb19_edit_masters_success(self):
        """Branch: has_masters, valid data → 200, DB updated."""
        _setup_masters(self.client, self.token)
        rv = self.client.put(
            "/api/masters",
            json={
                "categories": ["Rent", "Salary"],
                "subcategories": ["EMI"],
                "receivers": ["Landlord"],
                "payers": ["Company"],
                "opening_balance": 15000.0,
            },
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 200)
        # Verify the change persisted
        rv2 = self.client.get("/api/masters", headers=self._hdrs())
        body = rv2.get_json()
        self.assertIn("Rent", body["categories"])
        self.assertAlmostEqual(body["opening_balance"], 15000.0)


# ===========================================================================
# WB-TS3 — Records Module
# ===========================================================================

class WB_TS3_Records(unittest.TestCase):
    """
    Test Scenario 3: Records — add, list (all filter branches), edit, delete.

    Branch coverage goals:
      create_record: missing type/amount/category / bad amount (≤0) /
                     wrong type string / success + budget check called
      get_records:   each filter branch individually (min/max/type/cat/date)
      edit_record:   not found / bad amount / success
      remove_record: not found / success
    """

    def setUp(self):
        database.init_db()
        self.client = _client()
        uname = f"rec_{id(self)}"
        rv = self.client.post("/api/signup", json={"username": uname, "password": "Secure123"})
        self.token = rv.get_json()["token"]
        _setup_masters(self.client, self.token)

    def _hdrs(self):
        return _auth_headers(self.token)

    def _add(self, amount=500, rtype="expense", cat="Food",
             notes="test-note", date="2026-01-15"):
        return self.client.post(
            "/api/records",
            json={"type": rtype, "amount": amount, "category": cat,
                  "subcategory": "Groceries", "receiver_payer": "Swiggy",
                  "notes": notes, "date": date},
            headers=self._hdrs(),
        )

    # ── TC-WB-20: Add record — missing required field ─────────────────────
    def test_wb20_add_record_missing_category(self):
        """Branch: not data.get('category') → 400."""
        rv = self.client.post(
            "/api/records",
            json={"type": "expense", "amount": 100},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 400)

    # ── TC-WB-21: Add record — invalid type string ────────────────────────
    def test_wb21_add_record_invalid_type(self):
        """Branch: type not in ('expense','earning') → 400."""
        rv = self.client.post(
            "/api/records",
            json={"type": "transfer", "amount": 100, "category": "Food"},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn("expense", rv.get_json()["error"].lower())

    # ── TC-WB-22a: Add record — amount=0 (falsy, treated as missing) ─────
    def test_wb22_add_record_zero_amount_treated_as_missing(self):
        """
        Branch: not data.get("amount") → True when amount=0 (falsy in Python) → 400.
        Note: In app.py the guard is `if not data.get(field)` which treats 0 as missing.
        Error message: "Missing required field: amount"
        """
        rv = self.client.post(
            "/api/records",
            json={"type": "expense", "amount": 0, "category": "Food"},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn("amount", rv.get_json()["error"].lower())

    # ── TC-WB-22b: Add record — negative amount ───────────────────────────
    def test_wb22b_add_record_negative_amount(self):
        """
        Branch: float(amount) succeeds but value <= 0 → ValueError raised → 400.
        This is the true "positive number" validation branch.
        Error message: "Amount must be a positive number"
        Technique: Boundary Value Analysis — just below valid minimum (0.001)
        """
        rv = self.client.post(
            "/api/records",
            json={"type": "expense", "amount": -1, "category": "Food"},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn("positive", rv.get_json()["error"].lower())

    # ── TC-WB-23: Add expense record — success, budget_alerts in response ─
    def test_wb23_add_expense_success_budget_alerts_present(self):
        """Branch: type==expense → check_budget_alerts() called → key in response."""
        rv = self._add()
        self.assertEqual(rv.status_code, 201)
        body = rv.get_json()
        self.assertIn("id", body)
        self.assertIn("budget_alerts", body)
        self.assertIsInstance(body["budget_alerts"], list)

    # ── TC-WB-24: Add earning record — budget_alerts NOT checked ──────────
    def test_wb24_add_earning_no_budget_check(self):
        """Branch: type==earning → budget_alerts=[] without checking."""
        rv = self._add(rtype="earning", cat="Salary")
        self.assertEqual(rv.status_code, 201)
        self.assertEqual(rv.get_json()["budget_alerts"], [])

    # ── TC-WB-25: List records — no filters (all records returned) ────────
    def test_wb25_list_records_no_filters(self):
        """Path: query builds with no filter clauses."""
        self._add(notes="r1", date="2026-01-10")
        self._add(notes="r2", date="2026-02-10")
        rv = self.client.get("/api/records", headers=self._hdrs())
        self.assertEqual(rv.status_code, 200)
        self.assertGreaterEqual(len(rv.get_json()), 2)

    # ── TC-WB-26: Filter — by type ────────────────────────────────────────
    def test_wb26_filter_by_type(self):
        """Branch: filters['record_type'] is set → AND type=? added."""
        self._add(rtype="expense", notes="exp-only")
        self._add(rtype="earning", cat="Salary", notes="earn-only")
        rv = self.client.get("/api/records?type=expense", headers=self._hdrs())
        records = rv.get_json()
        self.assertTrue(all(r["type"] == "expense" for r in records))

    # ── TC-WB-27: Filter — by category ───────────────────────────────────
    def test_wb27_filter_by_category(self):
        """Branch: filters['category'] is set → AND category=? added."""
        self._add(cat="Food", notes="food-rec")
        self._add(cat="Transport", notes="trans-rec")
        rv = self.client.get("/api/records?category=Food", headers=self._hdrs())
        records = rv.get_json()
        self.assertTrue(all(r["category"] == "Food" for r in records))

    # ── TC-WB-28: Filter — min_amount ─────────────────────────────────────
    def test_wb28_filter_min_amount(self):
        """Branch: filters['min_amount'] valid float → AND amount>=? added."""
        self._add(amount=100, notes="low")
        self._add(amount=1000, notes="high")
        rv = self.client.get("/api/records?min_amount=500", headers=self._hdrs())
        records = rv.get_json()
        self.assertTrue(all(r["amount"] >= 500 for r in records))

    # ── TC-WB-29: Filter — max_amount ─────────────────────────────────────
    def test_wb29_filter_max_amount(self):
        """Branch: filters['max_amount'] valid float → AND amount<=? added."""
        self._add(amount=200, notes="small")
        self._add(amount=9000, notes="big")
        rv = self.client.get("/api/records?max_amount=500", headers=self._hdrs())
        records = rv.get_json()
        self.assertTrue(all(r["amount"] <= 500 for r in records))

    # ── TC-WB-30: Filter — date range ─────────────────────────────────────
    def test_wb30_filter_date_range(self):
        """Branch: date_from and date_to both added to query."""
        self._add(notes="jan", date="2026-01-15")
        self._add(notes="mar", date="2026-03-15")
        rv = self.client.get(
            "/api/records?date_from=2026-01-01&date_to=2026-01-31",
            headers=self._hdrs(),
        )
        records = rv.get_json()
        self.assertTrue(all("2026-01" in r["date"] for r in records))

    # ── TC-WB-31: Edit record — not found ─────────────────────────────────
    def test_wb31_edit_record_not_found(self):
        """Branch: get_record_by_id returns None → 404."""
        rv = self.client.put(
            "/api/records/99999",
            json={"type": "expense", "amount": 100, "category": "Food",
                  "subcategory": "", "receiver_payer": "", "notes": "", "date": "2026-01-01"},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 404)

    # ── TC-WB-32: Edit record — bad amount ────────────────────────────────
    def test_wb32_edit_record_bad_amount(self):
        """Branch: float(amount) fails → 400."""
        add_rv = self._add()
        rid = add_rv.get_json()["id"]
        rv = self.client.put(
            f"/api/records/{rid}",
            json={"type": "expense", "amount": "abc", "category": "Food",
                  "subcategory": "", "receiver_payer": "", "notes": "", "date": "2026-01-01"},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 400)

    # ── TC-WB-33: Edit record — success ───────────────────────────────────
    def test_wb33_edit_record_success(self):
        """Branch: valid data → UPDATE executed → 200."""
        add_rv = self._add(notes="original")
        rid = add_rv.get_json()["id"]
        rv = self.client.put(
            f"/api/records/{rid}",
            json={"type": "expense", "amount": 750, "category": "Food",
                  "subcategory": "Dining", "receiver_payer": "Swiggy",
                  "notes": "updated-note", "date": "2026-01-20"},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 200)
        # Verify update
        rv2 = self.client.get(f"/api/records/{rid}", headers=self._hdrs())
        self.assertEqual(rv2.get_json()["notes"], "updated-note")
        self.assertAlmostEqual(rv2.get_json()["amount"], 750)

    # ── TC-WB-34: Delete record — not found ──────────────────────────────
    def test_wb34_delete_record_not_found(self):
        """Branch: get_record_by_id returns None → 404."""
        rv = self.client.delete("/api/records/99999", headers=self._hdrs())
        self.assertEqual(rv.status_code, 404)

    # ── TC-WB-35: Delete record — success ────────────────────────────────
    def test_wb35_delete_record_success(self):
        """Branch: record exists → DELETE executed → 200, gone from DB."""
        add_rv = self._add(notes="to-delete")
        rid = add_rv.get_json()["id"]
        rv = self.client.delete(f"/api/records/{rid}", headers=self._hdrs())
        self.assertEqual(rv.status_code, 200)
        rv2 = self.client.get(f"/api/records/{rid}", headers=self._hdrs())
        self.assertEqual(rv2.status_code, 404)


# ===========================================================================
# WB-TS4 — Dashboard Module
# ===========================================================================

class WB_TS4_Dashboard(unittest.TestCase):
    """
    Test Scenario 4: Dashboard data aggregation.

    Verifies:
      - Correct total_earnings and total_expenses calculation
      - Balance = opening_balance + earnings - expenses
      - monthly_breakdown contains correct month keys
      - category_breakdown groups expenses correctly
      - budget_alerts key always present
    """

    def setUp(self):
        database.init_db()
        self.client = _client()
        uname = f"dash_{id(self)}"
        rv = self.client.post("/api/signup", json={"username": uname, "password": "Secure123"})
        self.token = rv.get_json()["token"]
        _setup_masters(self.client, self.token, balance=10000.0)

    def _hdrs(self):
        return _auth_headers(self.token)

    def _add(self, rtype, amount, cat, date):
        self.client.post(
            "/api/records",
            json={"type": rtype, "amount": amount, "category": cat,
                  "subcategory": "", "receiver_payer": "", "notes": "", "date": date},
            headers=self._hdrs(),
        )

    # ── TC-WB-36: Dashboard — correct balance calculation ─────────────────
    def test_wb36_dashboard_balance_calculation(self):
        """Path: opening(10000) + earning(5000) - expense(2000) = 13000."""
        self._add("earning", 5000, "Salary", "2026-03-01")
        self._add("expense", 2000, "Food", "2026-03-05")
        rv = self.client.get("/api/dashboard", headers=self._hdrs())
        body = rv.get_json()
        self.assertEqual(rv.status_code, 200)
        self.assertAlmostEqual(body["total_earnings"], 5000)
        self.assertAlmostEqual(body["total_expenses"], 2000)
        self.assertAlmostEqual(body["balance"], 13000)  # 10000+5000-2000

    # ── TC-WB-37: Dashboard — monthly breakdown structure ─────────────────
    def test_wb37_dashboard_monthly_breakdown(self):
        """Path: GROUP BY strftime('%Y-%m') returns month keys."""
        self._add("expense", 1000, "Food", "2026-01-10")
        self._add("expense", 2000, "Transport", "2026-02-10")
        rv = self.client.get("/api/dashboard", headers=self._hdrs())
        body = rv.get_json()
        months = [m["month"] for m in body["monthly_breakdown"]]
        self.assertIn("2026-01", months)
        self.assertIn("2026-02", months)

    # ── TC-WB-38: Dashboard — category breakdown ──────────────────────────
    def test_wb38_dashboard_category_breakdown(self):
        """Path: GROUP BY category on expenses, ordered by total DESC."""
        self._add("expense", 3000, "Food", "2026-01-05")
        self._add("expense", 1000, "Transport", "2026-01-06")
        rv = self.client.get("/api/dashboard", headers=self._hdrs())
        body = rv.get_json()
        cats = [c["category"] for c in body["category_breakdown"]]
        self.assertIn("Food", cats)
        # Food should be first (highest spend)
        self.assertEqual(body["category_breakdown"][0]["category"], "Food")

    # ── TC-WB-39: Dashboard — budget_alerts always present ────────────────
    def test_wb39_dashboard_budget_alerts_key_always_present(self):
        """Path: dashboard always calls check_budget_alerts → key in response."""
        rv = self.client.get("/api/dashboard", headers=self._hdrs())
        body = rv.get_json()
        self.assertIn("budget_alerts", body)
        self.assertIsInstance(body["budget_alerts"], list)


# ===========================================================================
# WB-TS5 — Budget Module
# ===========================================================================

class WB_TS5_Budget(unittest.TestCase):
    """
    Test Scenario 5: Budget CRUD and alert generation logic.

    Branch coverage goals:
      create_budget: invalid period / bad amount / success / upsert on duplicate
      check_budget_alerts: no budgets / within limit / 80% warning / exceeded
      delete_budget: success
    """

    def setUp(self):
        database.init_db()
        self.client = _client()
        uname = f"bgt_{id(self)}"
        rv = self.client.post("/api/signup", json={"username": uname, "password": "Secure123"})
        self.token = rv.get_json()["token"]
        _setup_masters(self.client, self.token, balance=0)

    def _hdrs(self):
        return _auth_headers(self.token)

    def _add_expense(self, amount, cat="Food", date=None):
        import datetime as _dt; date = date or _dt.date.today().isoformat()  # alerts use the current month
        self.client.post(
            "/api/records",
            json={"type": "expense", "amount": amount, "category": cat,
                  "subcategory": "", "receiver_payer": "", "notes": "", "date": date},
            headers=self._hdrs(),
        )

    # ── TC-WB-40: Create budget — invalid period ──────────────────────────
    def test_wb40_create_budget_invalid_period(self):
        """Branch: period not in ('weekly','monthly') → 400."""
        rv = self.client.post(
            "/api/budgets",
            json={"period": "yearly", "amount": 5000, "category": ""},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 400)

    # ── TC-WB-41: Create budget — zero amount ─────────────────────────────
    def test_wb41_create_budget_zero_amount(self):
        """Branch: amount <= 0 → 400."""
        rv = self.client.post(
            "/api/budgets",
            json={"period": "monthly", "amount": 0, "category": ""},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 400)

    # ── TC-WB-42: Create budget — success ─────────────────────────────────
    def test_wb42_create_budget_success(self):
        """Branch: valid period + amount → 201."""
        rv = self.client.post(
            "/api/budgets",
            json={"period": "monthly", "amount": 5000, "category": ""},
            headers=self._hdrs(),
        )
        self.assertEqual(rv.status_code, 201)

    # ── TC-WB-43: Budget upsert — updating same period+category ───────────
    def test_wb43_budget_upsert_same_period_category(self):
        """Branch: ON CONFLICT → UPDATE (not INSERT duplicate)."""
        self.client.post("/api/budgets",
            json={"period": "monthly", "amount": 5000, "category": ""},
            headers=self._hdrs())
        self.client.post("/api/budgets",
            json={"period": "monthly", "amount": 8000, "category": ""},
            headers=self._hdrs())
        rv = self.client.get("/api/budgets", headers=self._hdrs())
        budgets = rv.get_json()["budgets"]
        overall = [b for b in budgets if b["period"] == "monthly" and b["category"] == ""]
        self.assertEqual(len(overall), 1)
        self.assertAlmostEqual(overall[0]["amount"], 8000)

    # ── TC-WB-44: Budget alerts — no budgets → empty list ─────────────────
    def test_wb44_budget_alerts_no_budgets(self):
        """Branch: budgets list empty → alerts = []."""
        rv = self.client.get("/api/budgets/alerts", headers=self._hdrs())
        self.assertEqual(rv.get_json(), [])

    # ── TC-WB-45: Budget alerts — within limit → no alert ─────────────────
    def test_wb45_budget_alerts_within_limit(self):
        """Branch: spent < 80% of limit → no alert generated."""
        self.client.post("/api/budgets",
            json={"period": "monthly", "amount": 10000, "category": ""},
            headers=self._hdrs())
        self._add_expense(3000)  # 30% — safe
        rv = self.client.get("/api/budgets/alerts", headers=self._hdrs())
        self.assertEqual(rv.get_json(), [])

    # ── TC-WB-46: Budget alerts — warning at >=80% ────────────────────────
    def test_wb46_budget_alerts_warning_at_80_percent(self):
        """Branch: pct >= 80 and spent < amount → status='warning'."""
        self.client.post("/api/budgets",
            json={"period": "monthly", "amount": 10000, "category": ""},
            headers=self._hdrs())
        self._add_expense(8500)  # 85% — warning
        rv = self.client.get("/api/budgets/alerts", headers=self._hdrs())
        alerts = rv.get_json()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["status"], "warning")
        self.assertGreaterEqual(alerts[0]["pct"], 80)

    # ── TC-WB-47: Budget alerts — exceeded ────────────────────────────────
    def test_wb47_budget_alerts_exceeded(self):
        """Branch: spent >= amount → status='exceeded', suggestion generated."""
        self.client.post("/api/budgets",
            json={"period": "monthly", "amount": 5000, "category": ""},
            headers=self._hdrs())
        self._add_expense(6000)  # 120% — exceeded
        rv = self.client.get("/api/budgets/alerts", headers=self._hdrs())
        alerts = rv.get_json()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["status"], "exceeded")
        self.assertGreater(alerts[0]["pct"], 100)
        self.assertIn("suggestion", alerts[0])

    # ── TC-WB-48: Delete budget — success ─────────────────────────────────
    def test_wb48_delete_budget_success(self):
        """Path: DELETE removes budget from DB."""
        self.client.post("/api/budgets",
            json={"period": "weekly", "amount": 2000, "category": ""},
            headers=self._hdrs())
        rv = self.client.get("/api/budgets", headers=self._hdrs())
        bid = rv.get_json()["budgets"][0]["id"]
        rv_del = self.client.delete(f"/api/budgets/{bid}", headers=self._hdrs())
        self.assertEqual(rv_del.status_code, 200)
        rv2 = self.client.get("/api/budgets", headers=self._hdrs())
        self.assertEqual(rv2.get_json()["budgets"], [])


# ===========================================================================
# WB-TS6 — Database Layer (Unit Tests)
# ===========================================================================

class WB_TS6_DatabaseLayer(unittest.TestCase):
    """
    Test Scenario 6: Direct database.py function unit tests.
    Tests internal DB functions without going through Flask.
    """

    def setUp(self):
        database.init_db()
        # Create a fresh user for each test
        self.uid = database.create_user(f"db_unit_{id(self)}", "hashed_pw")

    # ── TC-WB-49: create_user returns integer ID ──────────────────────────
    def test_wb49_create_user_returns_id(self):
        uid = database.create_user(f"newu_{id(self)}", "pw")
        self.assertIsInstance(uid, int)
        self.assertGreater(uid, 0)

    # ── TC-WB-50: get_user_by_username — found ────────────────────────────
    def test_wb50_get_user_found(self):
        uname = f"find_{id(self)}"
        database.create_user(uname, "pw123")
        user = database.get_user_by_username(uname)
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], uname)

    # ── TC-WB-51: get_user_by_username — not found returns None ──────────
    def test_wb51_get_user_not_found(self):
        result = database.get_user_by_username("ghost_user_xyz")
        self.assertIsNone(result)

    # ── TC-WB-52: has_masters — false before save ─────────────────────────
    def test_wb52_has_masters_false_initially(self):
        self.assertFalse(database.has_masters(self.uid))

    # ── TC-WB-53: has_masters — true after save ───────────────────────────
    def test_wb53_has_masters_true_after_save(self):
        database.save_masters(self.uid, ["Food"], ["Groceries"], ["Shop"], ["Boss"], 1000.0)
        self.assertTrue(database.has_masters(self.uid))

    # ── TC-WB-54: get_masters — JSON deserialized correctly ───────────────
    def test_wb54_get_masters_deserializes_json(self):
        database.save_masters(self.uid, ["A", "B"], ["X"], ["R1"], ["P1"], 2500.0)
        m = database.get_masters(self.uid)
        self.assertEqual(m["categories"], ["A", "B"])
        self.assertEqual(m["opening_balance"], 2500.0)

    # ── TC-WB-55: update_masters — values replaced ────────────────────────
    def test_wb55_update_masters_replaces_values(self):
        database.save_masters(self.uid, ["Old"], [], [], [], 0)
        database.update_masters(self.uid, ["New1", "New2"], ["Sub"], ["Rec"], ["Pay"], 9999.0)
        m = database.get_masters(self.uid)
        self.assertEqual(m["categories"], ["New1", "New2"])
        self.assertAlmostEqual(m["opening_balance"], 9999.0)

    # ── TC-WB-56: add_record and get_record_by_id round-trip ─────────────
    def test_wb56_add_and_retrieve_record(self):
        rid = database.add_record(self.uid, "expense", 333.0, "Food",
                                  "Groceries", "Shop", "note", "2026-03-15")
        rec = database.get_record_by_id(rid, self.uid)
        self.assertEqual(rec["amount"], 333.0)
        self.assertEqual(rec["category"], "Food")
        self.assertEqual(rec["type"], "expense")

    # ── TC-WB-57: get_record_by_id — wrong user returns None ─────────────
    def test_wb57_get_record_wrong_user_returns_none(self):
        rid = database.add_record(self.uid, "expense", 100, "Food",
                                  "", "", "", "2026-01-01")
        other_uid = database.create_user(f"other_{id(self)}", "pw")
        self.assertIsNone(database.get_record_by_id(rid, other_uid))

    # ── TC-WB-58: delete_record removes from DB ───────────────────────────
    def test_wb58_delete_record(self):
        rid = database.add_record(self.uid, "expense", 50, "Food",
                                  "", "", "", "2026-01-01")
        database.delete_record(rid, self.uid)
        self.assertIsNone(database.get_record_by_id(rid, self.uid))

    # ── TC-WB-59: set_budget upsert — only one row per period+category ────
    def test_wb59_set_budget_upsert(self):
        database.set_budget(self.uid, "monthly", 5000, "")
        database.set_budget(self.uid, "monthly", 7000, "")
        budgets = database.get_budgets(self.uid)
        overall = [b for b in budgets if b["period"] == "monthly" and b["category"] == ""]
        self.assertEqual(len(overall), 1)
        self.assertAlmostEqual(overall[0]["amount"], 7000)


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
