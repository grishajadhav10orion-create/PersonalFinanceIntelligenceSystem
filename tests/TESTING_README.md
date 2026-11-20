# FinTrack — Testing Documentation
## White Box + Black Box Testing with Selenium

---

## Overview

This project uses **two complementary testing strategies**:

| Strategy | File | Cases | Tool | Speed |
|---|---|---|---|---|
| White Box | `tests/test_whitebox.py` | 60 | Flask Test Client (no browser) | ~1.5 sec |
| Black Box | `tests/test_blackbox_selenium.py` | 28 | Selenium WebDriver (real Chrome) | ~2-3 min |

---

## Quick Start

### Run White Box Tests (no browser, no server needed)
```bash
cd finance_app
python -m unittest discover -s tests -p "test_whitebox.py" -v
```

### Run Black Box (Selenium) Tests
```bash
# Terminal 1 — start Flask server
cd finance_app
python app.py

# Terminal 2 — run Selenium tests
pip install selenium
python -m unittest discover -s tests -p "test_blackbox_selenium.py" -v
```

### Run Both Together
```bash
# Server must be running first
python -m unittest discover -s tests -v
```

### Headless Mode (for CI / no display)
```bash
HEADLESS=true python -m unittest discover -s tests -p "test_blackbox_selenium.py" -v
```

---

## White Box Testing

### What is White Box Testing?
White Box (Glass Box / Structural) testing examines the **internal logic** of the code. The tester knows the source code and designs test cases to cover:
- Every **statement** (statement coverage)
- Every **branch** of every if/else (branch coverage)
- Every **path** through a function (path coverage)

### How We Applied It
We used Flask's built-in `test_client()` to make direct HTTP requests to every API endpoint without needing a browser. Each test targets a specific branch in `app.py` or `database.py`.

### White Box Test Case Summary

| TC ID | Test Scenario | Function Tested | Branch Covered | Expected |
|---|---|---|---|---|
| WB-01 | Auth | `signup()` | Empty username (`not username`) | 400 |
| WB-02 | Auth | `signup()` | `len(username) < 3` | 400 |
| WB-03 | Auth | `signup()` | `len(password) < 6` | 400 |
| WB-04 | Auth | `signup()` | All valid → success path | 201 + token |
| WB-05 | Auth | `signup()` | Duplicate username → `get_user_by_username` not None | 409 |
| WB-06 | Auth | `login()` | User not found → None returned | 401 |
| WB-07 | Auth | `login()` | bcrypt.checkpw fails | 401 (skipped w/ mock) |
| WB-08 | Auth | `login()` | Valid credentials, no masters | 200, needs_masters=True |
| WB-09 | Auth | `login()` | has_masters() → True | needs_masters=False |
| WB-10 | Auth | `auth_required` | Missing Authorization header | 401 |
| WB-11 | Auth | `auth_required` | InvalidTokenError raised | 401 |
| WB-12 | Masters | `create_masters()` | Missing required field | 400 |
| WB-13 | Masters | `create_masters()` | `float(opening_balance)` raises ValueError | 400 |
| WB-14 | Masters | `create_masters()` | All valid fields | 201 |
| WB-15 | Masters | `create_masters()` | `has_masters()` → True | 409 |
| WB-16 | Masters | `fetch_masters()` | `get_masters()` returns None | 404 |
| WB-17 | Masters | `fetch_masters()` | Masters exist, JSON deserialized | 200 |
| WB-18 | Masters | `edit_masters()` | `not has_masters()` | 404 |
| WB-19 | Masters | `edit_masters()` | Valid update, DB changed | 200 |
| WB-20 | Records | `create_record()` | `not data.get("category")` | 400 |
| WB-21 | Records | `create_record()` | type not in allowed set | 400 |
| WB-22 | Records | `create_record()` | amount=0 (falsy, treated as missing) | 400 |
| WB-22b | Records | `create_record()` | amount=-1 (float<=0 → ValueError) | 400 |
| WB-23 | Records | `create_record()` | expense type → `check_budget_alerts()` called | 201 + budget_alerts |
| WB-24 | Records | `create_record()` | earning type → budget_alerts not checked | 201, alerts=[] |
| WB-25 | Records | `get_records()` | No filters — base query only | All records returned |
| WB-26 | Records | `get_records()` | `filters["record_type"]` set | Only matching type |
| WB-27 | Records | `get_records()` | `filters["category"]` set | Only matching category |
| WB-28 | Records | `get_records()` | `filters["min_amount"]` set | Only amount >= min |
| WB-29 | Records | `get_records()` | `filters["max_amount"]` set | Only amount <= max |
| WB-30 | Records | `get_records()` | date_from + date_to set | Only in date range |
| WB-31 | Records | `edit_record()` | `get_record_by_id()` returns None | 404 |
| WB-32 | Records | `edit_record()` | `float(amount)` fails | 400 |
| WB-33 | Records | `edit_record()` | Valid update path | 200 + DB updated |
| WB-34 | Records | `remove_record()` | Record not found | 404 |
| WB-35 | Records | `remove_record()` | Record found + deleted | 200 + gone from DB |
| WB-36 | Dashboard | `get_dashboard_data()` | Balance = opening + earnings - expenses | Correct arithmetic |
| WB-37 | Dashboard | `get_dashboard_data()` | Monthly GROUP BY path | Month keys present |
| WB-38 | Dashboard | `get_dashboard_data()` | Category GROUP BY, ORDER BY total DESC | First = highest spend |
| WB-39 | Dashboard | `dashboard()` route | `check_budget_alerts()` always called | budget_alerts key present |
| WB-40 | Budget | `create_budget()` | period not in allowed values | 400 |
| WB-41 | Budget | `create_budget()` | amount <= 0 | 400 |
| WB-42 | Budget | `create_budget()` | Valid period + amount | 201 |
| WB-43 | Budget | `set_budget()` | ON CONFLICT → upsert (no duplicate row) | Single row, updated amount |
| WB-44 | Budget | `check_budget_alerts()` | No budgets → loop skipped | [] |
| WB-45 | Budget | `check_budget_alerts()` | spent < 80% of limit | [] |
| WB-46 | Budget | `check_budget_alerts()` | pct >= 80, spent < amount | status="warning" |
| WB-47 | Budget | `check_budget_alerts()` | spent >= amount | status="exceeded" + suggestion |
| WB-48 | Budget | `delete_budget()` | DELETE SQL executed | Budget gone from list |
| WB-49 | DB Layer | `create_user()` | INSERT succeeds | Returns integer ID |
| WB-50 | DB Layer | `get_user_by_username()` | User found | Returns dict with username |
| WB-51 | DB Layer | `get_user_by_username()` | User not found | Returns None |
| WB-52 | DB Layer | `has_masters()` | No masters row | False |
| WB-53 | DB Layer | `has_masters()` | Masters row exists | True |
| WB-54 | DB Layer | `get_masters()` | JSON deserialization | Lists correctly parsed |
| WB-55 | DB Layer | `update_masters()` | SQL UPDATE | New values in DB |
| WB-56 | DB Layer | `add_record()` + `get_record_by_id()` | INSERT + SELECT | Round-trip correct |
| WB-57 | DB Layer | `get_record_by_id()` | Wrong user_id | Returns None |
| WB-58 | DB Layer | `delete_record()` | DELETE SQL | Record gone |
| WB-59 | DB Layer | `set_budget()` | ON CONFLICT upsert | Single row, updated |

---

## Black Box Testing (Selenium)

### What is Black Box Testing?
Black Box testing treats the system as a **black box** — the tester has no knowledge of internal code. Tests are written purely based on:
- **Requirements** (SRS document)
- **User stories** (what a user would do)
- **Inputs and expected outputs** only

### Techniques Applied

| Technique | Applied In | Example |
|---|---|---|
| **Equivalence Partitioning** | Auth, Records | Valid username ≥3 chars = one partition; invalid <3 chars = another |
| **Boundary Value Analysis** | Auth, Records, Budget | Username exactly 2 chars (just below) → fail; 3 chars → pass |
| **Decision Table Testing** | Budget Alerts, Filter | Budget: safe / warning (≥80%) / exceeded (≥100%) — 3 decision outcomes |
| **Use-Case Based Testing** | All scenarios | Full user journey: signup → onboard → add record → check dashboard |

### Page Object Model (POM)
The Selenium suite uses the **Page Object Model design pattern**:
```
BasePage          ← shared driver helpers (click, type, wait, is_visible)
  ├── AuthPage    ← login/signup screen
  ├── OnboardingPage  ← 4-step wizard
  ├── DashboardPage   ← stat cards, charts, alerts
  ├── RecordsPage     ← CRUD table, modal, filters
  ├── BudgetPage      ← budget form and list
  └── MastersPage     ← edit masters page
```

Each page object knows only its own element IDs. Test cases call page methods and assert on results — no raw `driver.find_element()` in test code.

### Black Box Test Case Summary

| TC ID | Scenario | Input | Expected Output | Technique |
|---|---|---|---|---|
| BB-01 | Auth | Valid new username + password | Onboarding/Dashboard visible | Equivalence Partitioning |
| BB-02 | Auth | Username = "ab" (2 chars) | Error message visible | Boundary Value Analysis |
| BB-03 | Auth | Password = "12345" (5 chars) | Error message visible | Boundary Value Analysis |
| BB-04 | Auth | Existing user + correct password | App loads | Equivalence Partitioning |
| BB-05 | Auth | Correct username + wrong password | Error message | Invalid partition |
| BB-06 | Auth | Non-existent username | Error message | Invalid partition |
| BB-07 | Onboarding | Enter opening balance, click Next | Step 2 (categories) visible | Use-Case Based |
| BB-08 | Onboarding | Skip categories, click Finish | Error shown, no dashboard | Decision Table |
| BB-09 | Onboarding | Complete all 4 steps | Dashboard visible | Use-Case Based |
| BB-10 | Dashboard | Login with setup complete | All 4 stat cards visible | Use-Case Based |
| BB-11 | Dashboard | Login as user | Greeting contains username | Use-Case Based |
| BB-12 | Dashboard | Add a record, go to dashboard | Bar chart has rendered elements | Use-Case Based |
| BB-13 | Records | Add Expense record | Note visible in table | Use-Case Based |
| BB-14 | Records | Add Earning record | Note visible, positive amount | Use-Case Based |
| BB-15 | Records | Save with empty amount | Modal error visible | Equivalence Partitioning |
| BB-16 | Records | Amount = 0 | Error shown | Boundary Value Analysis |
| BB-17 | Records | Edit record's note | Updated note in table | Use-Case Based |
| BB-18 | Records | Delete record | Record gone from table | Use-Case Based |
| BB-19 | Records | Filter by type=expense | Only expense badges shown | Decision Table |
| BB-20 | Records | Search unique note text | Exactly 1 row shown | Use-Case Based |
| BB-21 | Budget | Set monthly budget | Appears in Active Budgets | Use-Case Based |
| BB-22 | Budget | Set budget with amount=0 | Error message shown | Boundary Value Analysis |
| BB-23 | Budget | Budget=1000, add expense=2000 | Alert banner on dashboard | Decision Table (exceeded) |
| BB-24 | Budget | Delete a budget | Budget count decreases | Use-Case Based |
| BB-25 | Budget | Food budget=500, add Transport=1000, Food=600 | Alert only for Food | Decision Table (per-category) |
| BB-26 | Masters | Open Edit Masters | Pre-populated tags visible | Use-Case Based |
| BB-27 | Masters | Add new category + Save | Success message visible | Use-Case Based |
| BB-28 | Masters | Change opening balance + Save | Dashboard card updated | Use-Case Based |

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `FINTRACK_URL` | `http://localhost:5000` | Flask server URL |
| `HEADLESS` | `false` | Set to `true` for CI (no browser window) |
| `SELENIUM_WAIT` | `8` | Seconds to wait for elements |

---

## Notes on bcrypt Mock

The white box suite includes a mock for `bcrypt` so it runs even without the package installed. The mock's `checkpw` always returns `True`, which means **TC-WB-07** (wrong password → 401) is automatically skipped when the mock is active. This is expected behaviour — install real bcrypt to enable it:

```bash
pip install bcrypt
python -m unittest discover -s tests -p "test_whitebox.py" -v
# TC-WB-07 will now run and pass
```

---

## Defects Found During Testing

| Defect | Found By | Description | Status |
|---|---|---|---|
| Bar chart invisible | White Box (WB-36/37) + Visual | Flex container not anchoring bars to bottom — `align-items:flex-end` missing on inner container | Fixed |
| amount=0 error message misleading | White Box (WB-22) | `not data.get("amount")` treats 0 as missing, returns "Missing required field" instead of "Amount must be positive" | Documented |
| Masters not editable | Use-case review | Original design only allowed POST /api/masters once; users could never change categories | Fixed — PUT /api/masters added |
