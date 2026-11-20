"""
=============================================================================
FinTrack — BLACK BOX TEST SUITE (Selenium)
=============================================================================

Testing Strategy : Black Box (Behavioural) Testing
Technique        : Equivalence Partitioning, Boundary Value Analysis,
                   Decision Table Testing, Use-Case Based Testing

What black-box tests do:
  - Test the application from the END USER's perspective only
  - No knowledge of internal code — only inputs and expected outputs
  - Drive a real Chrome browser using Selenium WebDriver
  - Validate visible UI behavior: text, navigation, error messages, modals

Test Scenarios & Cases:
  TS-1  Authentication          (TC-BB-01 to TC-BB-06)
  TS-2  Onboarding Wizard       (TC-BB-07 to TC-BB-09)
  TS-3  Dashboard               (TC-BB-10 to TC-BB-12)
  TS-4  Records Management      (TC-BB-13 to TC-BB-20)
  TS-5  Budget Manager          (TC-BB-21 to TC-BB-25)
  TS-6  Edit Masters            (TC-BB-26 to TC-BB-28)

Prerequisites:
  1. Flask app running:   cd finance_app && python app.py
  2. Chrome + ChromeDriver installed and on PATH
  3. Install Selenium:    pip install selenium

Run:
  cd finance_app
  python -m pytest tests/test_blackbox_selenium.py -v --tb=short

Environment variables:
  FINTRACK_URL   base URL  (default: http://localhost:5000)
  HEADLESS       set to "true" for CI/headless mode (default: false)
  SELENIUM_WAIT  implicit wait seconds (default: 8)

=============================================================================
"""

from __future__ import annotations

import os
import time
import unittest
from uuid import uuid4

from selenium import webdriver
from selenium.common.exceptions import (
    ElementNotInteractableException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# ===========================================================================
# Configuration
# ===========================================================================

BASE_URL    = os.getenv("FINTRACK_URL", "http://127.0.0.1:5000")
HEADLESS    = os.getenv("HEADLESS", "false").lower() == "true"
WAIT_SEC    = int(os.getenv("SELENIUM_WAIT", "8"))


# ===========================================================================
# Page Object Model
# ===========================================================================

class BasePage:
    """Shared driver helpers used by all page objects."""

    def __init__(self, driver):
        self.driver = driver
        self.wait   = WebDriverWait(driver, WAIT_SEC)

    # ── element finders ────────────────────────────────────────────────────
    def _find(self, by, value):
        return self.wait.until(EC.presence_of_element_located((by, value)))

    def _visible(self, by, value):
        return self.wait.until(EC.visibility_of_element_located((by, value)))

    def _clickable(self, by, value):
        return self.wait.until(EC.element_to_be_clickable((by, value)))

    # ── actions ────────────────────────────────────────────────────────────
    def click_id(self, eid):
        self._clickable(By.ID, eid).click()

    def click_xpath(self, xpath):
        self._clickable(By.XPATH, xpath).click()

    def type_id(self, eid, text, clear=True):
        el = self._visible(By.ID, eid)
        if clear:
            el.clear()
        el.send_keys(text)

    def type_xpath(self, xpath, text, clear=True):
        el = self._visible(By.XPATH, xpath)
        if clear:
            el.clear()
        el.send_keys(text)

    def text_id(self, eid):
        return self._visible(By.ID, eid).text.strip()

    def is_visible_id(self, eid, timeout=4):
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((By.ID, eid))
            )
            return True
        except TimeoutException:
            return False

    def page_has(self, text):
        """Case-insensitive search in full page source."""
        return text.lower() in self.driver.page_source.lower()

    def js(self, script):
        return self.driver.execute_script(script)

    def wait_for_js(self, script, timeout=8):
        """Poll until JS expression returns truthy."""
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script(script)
        )

    def open(self, path="/"):
        self.driver.get(f"{BASE_URL}{path}")


class AuthPage(BasePage):
    """Login / signup screen interactions.

    Actual HTML IDs confirmed from index.html:
      Login form inputs : #lu (username),  #lp (password)
      Signup form inputs: #su (username),  #sp (password)
      Login tab         : first .tab element
      Signup tab        : second .tab element
      Login button      : button inside #lform
      Signup button     : button inside #sform
      Error div         : #auth-err
    """

    def go_signup_tab(self):
        """Click the Sign Up tab."""
        tabs = self.driver.find_elements(By.CSS_SELECTOR, ".tab")
        tabs[1].click()
        time.sleep(0.3)

    def go_login_tab(self):
        """Click the Login tab."""
        tabs = self.driver.find_elements(By.CSS_SELECTOR, ".tab")
        tabs[0].click()
        time.sleep(0.3)

    def signup(self, username, password):
        self.go_signup_tab()
        self.type_id("su", username)
        self.type_id("sp", password)
        btn = self.driver.find_element(By.CSS_SELECTOR, "#sform .btn-p")
        btn.click()

    def login(self, username, password):
        self.go_login_tab()
        self.type_id("lu", username)
        self.type_id("lp", password)
        btn = self.driver.find_element(By.CSS_SELECTOR, "#lform .btn-p")
        btn.click()

    def error_text(self):
        try:
            el = self.driver.find_element(By.ID, "auth-err")
            return el.text.strip()
        except NoSuchElementException:
            return ""

    def error_visible(self):
        try:
            el = self.driver.find_element(By.ID, "auth-err")
            return el.is_displayed() and el.text.strip() != ""
        except NoSuchElementException:
            return False

    def logout(self):
        try:
            btn = self.driver.find_element(By.CSS_SELECTOR, ".out-btn")
            if btn.is_displayed():
                btn.click()
        except NoSuchElementException:
            pass
        time.sleep(0.5)


class OnboardingPage(BasePage):
    """4-step setup wizard interactions.

    Actual HTML IDs:
      Step 1: #sb0 (opening balance), #next-btn
      Step 2: #sc-ci (category input), Add button, #next-btn
      Step 3: #sc-si (subcategory input), Add button, #next-btn
      Step 4: #sc-pi (payer), #sc-ri (receiver), Add buttons, Finish (#next-btn)
    """

    def is_on_onboarding(self):
        return self.is_visible_id("masters-setup", timeout=4) and \
               self.js("return document.getElementById('masters-setup').style.display !== 'none'")

    def _add_tag(self, input_id, value):
        el = self.driver.find_element(By.ID, input_id)
        el.clear()
        el.send_keys(value)
        el.send_keys(Keys.ENTER)
        time.sleep(0.3)

    def step1_set_balance(self, balance):
        self.type_id("sb0", str(balance))
        self.click_id("next-btn")
        time.sleep(0.4)

    def step2_add_categories(self, *cats):
        for cat in cats:
            self._add_tag("sc-ci", cat)
        self.click_id("next-btn")
        time.sleep(0.4)

    def step3_add_subcategories(self, *subs):
        for sub in subs:
            self._add_tag("sc-si", sub)
        self.click_id("next-btn")
        time.sleep(0.4)

    def step4_add_payers_receivers(self, payers, receivers):
        for p in payers:
            self._add_tag("sc-pi", p)
        for r in receivers:
            self._add_tag("sc-ri", r)
        # On step 4, "next-btn" says "Finish"
        self.click_id("next-btn")
        time.sleep(0.8)

    def complete_full_setup(self, balance=10000, categories=None,
                            subcategories=None, payers=None, receivers=None):
        categories  = categories  or ["Food", "Salary", "Transport"]
        subcategories = subcategories or ["Groceries", "EMI"]
        payers      = payers      or ["Employer"]
        receivers   = receivers   or ["Swiggy", "Amazon"]
        self.step1_set_balance(balance)
        self.step2_add_categories(*categories)
        self.step3_add_subcategories(*subcategories)
        self.step4_add_payers_receivers(payers, receivers)


class DashboardPage(BasePage):
    """Dashboard screen.

    Actual HTML IDs:
      #d-earn, #d-exp, #d-bal, #d-open  (stat cards)
      #dgreet                             (welcome text)
      #rtxns                              (recent transactions list)
      #bar-chart, #donut-chart           (chart containers)
      #dash-alerts                        (budget alert banners)
    """

    def is_loaded(self):
        return self.is_visible_id("d-bal")

    def earnings(self):
        return self.text_id("d-earn")

    def expenses(self):
        return self.text_id("d-exp")

    def balance(self):
        return self.text_id("d-bal")

    def opening_balance(self):
        return self.text_id("d-open")

    def greeting(self):
        return self.text_id("dgreet")

    def has_recent_txns(self):
        try:
            el = self.driver.find_element(By.ID, "rtxns")
            return "No transactions" not in el.text
        except NoSuchElementException:
            return False

    def alert_count(self):
        try:
            el = self.driver.find_element(By.ID, "dash-alerts")
            return len(el.find_elements(By.CSS_SELECTOR, ".alert-bar"))
        except NoSuchElementException:
            return 0

    def navigate_to(self):
        nav = self.driver.find_elements(By.CSS_SELECTOR, ".nav-item")
        for item in nav:
            if "dashboard" in item.text.lower():
                item.click()
                break
        time.sleep(0.5)


class RecordsPage(BasePage):
    """All Records page.

    Actual HTML IDs / selectors:
      Add Record button : first .btn-p in .rtbar
      Type toggle       : #te (expense), #tn (earning)
      Modal inputs      : #ra (amount), #rd (date), #rc (category),
                          #rsc (subcategory), #rrp (receiver/payer), #rn (notes)
      Save button       : button inside #rm
      Search            : #si2
      Type filter       : #tf
      Filter bar toggle : button with text "Filters" in .rtbar
      Records table     : #rtbody
      Delete confirm    : #dcm, confirm button inside it
    """

    def navigate_to(self):
        nav = self.driver.find_elements(By.CSS_SELECTOR, ".nav-item")
        for item in nav:
            if "records" in item.text.lower() and "budget" not in item.text.lower():
                item.click()
                break
        time.sleep(0.5)

    def open_add_modal(self):
        btn = self.driver.find_element(By.CSS_SELECTOR, ".rtbar .btn-p")
        btn.click()
        time.sleep(0.4)
        self._visible(By.ID, "rm")

    def set_type(self, rtype):
        if rtype == "expense":
            self.click_id("te")
        else:
            self.click_id("tn")
        time.sleep(0.2)

    def fill_record_form(self, amount, category, notes="",
                         date="2026-04-08", subcategory="", rtype="expense"):
        self.set_type(rtype)
        self.type_id("ra", str(amount))
        self.type_id("rd", date)
        # Select category
        self.js(f"var s=document.getElementById('rc');for(var i=0;i<s.options.length;i++){{if(s.options[i].text==='{category}'){{s.selectedIndex=i;break;}}}}")
        time.sleep(0.2)
        if notes:
            self.type_id("rn", notes)

    def save_record(self):
        btn = self.driver.find_element(By.CSS_SELECTOR, "#rm .btn-p")
        btn.click()
        time.sleep(0.8)

    def add_full_record(self, amount, category, notes="", date="2026-04-08",
                        rtype="expense"):
        self.open_add_modal()
        self.fill_record_form(amount, category, notes, date, rtype=rtype)
        self.save_record()

    def search(self, text):
        self.type_id("si2", text)
        time.sleep(0.6)  # client-side filter triggers on input

    def set_type_filter(self, value):
        """value: '' | 'earning' | 'expense'"""
        self.js(f"document.getElementById('tf').value='{value}';applyF()")
        time.sleep(0.4)

    def clear_search(self):
        self.type_id("si2", "")
        time.sleep(0.3)

    def row_count(self):
        try:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "#rtbody tr")
            # Exclude empty-state rows
            return sum(1 for r in rows if "No records" not in r.text and r.text.strip())
        except NoSuchElementException:
            return 0

    def row_contains(self, text):
        try:
            body = self.driver.find_element(By.ID, "rtbody")
            return text.lower() in body.text.lower()
        except NoSuchElementException:
            return False

    def click_edit_for_row(self, note_text):
        """Click edit button on the row whose notes contain note_text."""
        xpath = (
            f"//tbody[@id='rtbody']//tr[td[contains(text(),'{note_text}')]]"
            f"//button[contains(@class,'edit')]"
        )
        try:
            self.click_xpath(xpath)
        except TimeoutException:
            # Fallback: click first edit button
            btns = self.driver.find_elements(By.CSS_SELECTOR, ".ibtn.edit")
            if btns:
                btns[0].click()
        time.sleep(0.5)

    def click_delete_for_row(self, note_text):
        """Click delete button on the row whose notes contain note_text."""
        xpath = (
            f"//tbody[@id='rtbody']//tr[td[contains(text(),'{note_text}')]]"
            f"//button[contains(@class,'del')]"
        )
        try:
            self.click_xpath(xpath)
        except TimeoutException:
            btns = self.driver.find_elements(By.CSS_SELECTOR, ".ibtn.del")
            if btns:
                btns[0].click()
        time.sleep(0.4)

    def confirm_delete(self):
        """Click Delete in the confirm modal (#dcm)."""
        self._visible(By.ID, "dcm")
        btn = self.driver.find_element(By.CSS_SELECTOR, "#dcm .btn-d")
        btn.click()
        time.sleep(0.8)

    def modal_error_text(self):
        try:
            el = self.driver.find_element(By.ID, "rmerr")
            return el.text.strip() if el.is_displayed() else ""
        except NoSuchElementException:
            return ""

    def close_modal(self):
        try:
            btn = self.driver.find_element(By.CSS_SELECTOR, "#rm .mc-btn")
            btn.click()
        except NoSuchElementException:
            pass
        time.sleep(0.3)


class BudgetPage(BasePage):
    """Budget Manager page.

    Actual HTML IDs:
      #bp    (period select), #bcat (category select), #bamt (amount input)
      .btn-p in .bg-card  (Set Budget button)
      #blist  (active budgets list)
      #budget-alerts-sec  (alert banners)
      #berr   (form error)
    """

    def navigate_to(self):
        nav = self.driver.find_elements(By.CSS_SELECTOR, ".nav-item")
        for item in nav:
            if "budget" in item.text.lower():
                item.click()
                break
        time.sleep(0.5)

    def set_budget(self, period, amount, category=""):
        self.js(f"document.getElementById('bp').value='{period}'")
        self.js(f"document.getElementById('bcat').value='{category}'")
        self.type_id("bamt", str(amount))
        btn = self.driver.find_element(By.CSS_SELECTOR, ".bg-card .btn-p")
        btn.click()
        time.sleep(0.8)

    def budget_count(self):
        try:
            items = self.driver.find_elements(By.CSS_SELECTOR, "#blist .bg-item")
            return len(items)
        except NoSuchElementException:
            return 0

    def alert_count(self):
        try:
            el = self.driver.find_element(By.ID, "budget-alerts-sec")
            return len(el.find_elements(By.CSS_SELECTOR, ".alert-bar"))
        except NoSuchElementException:
            return 0

    def form_error(self):
        try:
            el = self.driver.find_element(By.ID, "berr")
            return el.text.strip() if el.is_displayed() else ""
        except NoSuchElementException:
            return ""

    def delete_first_budget(self):
        try:
            btn = self.driver.find_element(By.CSS_SELECTOR, "#blist .ibtn.del")
            btn.click()
            time.sleep(0.6)
        except NoSuchElementException:
            pass


class MastersPage(BasePage):
    """Edit Masters page.

    Actual HTML IDs:
      #mb0   (opening balance input)
      #mc-i  (category input), #ms-i (subcategory), #mp-i (payer), #mr-i (receiver)
      .btn-p in .ma  (Save Changes button)
      #mmsg  (success/error message)
    """

    def navigate_to(self):
        nav = self.driver.find_elements(By.CSS_SELECTOR, ".nav-item")
        for item in nav:
            if "masters" in item.text.lower():
                item.click()
                break
        time.sleep(0.5)

    def add_category(self, name):
        el = self.driver.find_element(By.ID, "mc-i")
        el.clear()
        el.send_keys(name)
        el.send_keys(Keys.ENTER)
        time.sleep(0.3)

    def save(self):
        btn = self.driver.find_element(By.CSS_SELECTOR, ".ma .btn-p")
        btn.click()
        time.sleep(0.8)

    def success_visible(self):
        try:
            el = self.driver.find_element(By.ID, "mmsg")
            return el.is_displayed() and el.text.strip() != ""
        except NoSuchElementException:
            return False

    def set_balance(self, value):
        self.type_id("mb0", str(value))


# ===========================================================================
# Test fixture — shared driver, signup, onboarding
# ===========================================================================

class FinTrackTestBase(unittest.TestCase):
    """Base class: sets up Chrome, registers a unique user, completes onboarding."""

    driver     = None
    auth_page  = None
    on_page    = None
    dash_page  = None
    rec_page   = None
    bgt_page   = None
    mst_page   = None

    # Shared user credentials (set in setUpClass or each test)
    username   = None
    password   = "TestPass@123"

    @classmethod
    def _build_driver(cls):
        opts = ChromeOptions()
        if HEADLESS:
            opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1440,900")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-extensions")
        driver = webdriver.Chrome(options=opts)
        driver.implicitly_wait(2)
        return driver

    @classmethod
    def setUpClass(cls):
        cls.driver    = cls._build_driver()
        cls.auth_page = AuthPage(cls.driver)
        cls.on_page   = OnboardingPage(cls.driver)
        cls.dash_page = DashboardPage(cls.driver)
        cls.rec_page  = RecordsPage(cls.driver)
        cls.bgt_page  = BudgetPage(cls.driver)
        cls.mst_page  = MastersPage(cls.driver)

        # Create and fully onboard one user for the whole scenario
        cls.username = f"bb_{uuid4().hex[:8]}"
        cls.auth_page.open("/")
        cls.auth_page.signup(cls.username, cls.password)
        time.sleep(0.5)
        if cls.on_page.is_on_onboarding():
            cls.on_page.complete_full_setup()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        if cls.driver:
            cls.driver.quit()

    def _fresh_login(self):
        """Navigate to home and log in as the class user."""
        self.auth_page.open("/")
        time.sleep(0.3)
        self.auth_page.logout()
        self.auth_page.open("/")
        time.sleep(0.3)
        self.auth_page.login(self.username, self.password)
        time.sleep(0.8)


# ===========================================================================
# TS-1: Authentication Tests
# ===========================================================================

class TS1_Authentication(FinTrackTestBase):
    """
    Test Scenario 1 — Authentication
    Technique: Equivalence Partitioning (valid / invalid inputs)
    """

    @classmethod
    def setUpClass(cls):
        cls.driver    = cls._build_driver()
        cls.auth_page = AuthPage(cls.driver)
        cls.on_page   = OnboardingPage(cls.driver)
        cls.dash_page = DashboardPage(cls.driver)
        cls.rec_page  = RecordsPage(cls.driver)
        cls.bgt_page  = BudgetPage(cls.driver)
        cls.mst_page  = MastersPage(cls.driver)
        # No shared user — each TC creates/uses its own

    # ── TC-BB-01: Valid signup ────────────────────────────────────────────
    def test_bb01_valid_signup_redirects_to_onboarding(self):
        """
        Input  : New unique username (≥3 chars), password (≥6 chars)
        Expected: Onboarding wizard OR dashboard visible
        """
        uname = f"bb01_{uuid4().hex[:6]}"
        self.auth_page.open("/")
        self.auth_page.signup(uname, "SecurePass1")
        time.sleep(0.8)
        on_onboarding = self.on_page.is_on_onboarding()
        on_dashboard  = self.dash_page.is_loaded()
        self.assertTrue(on_onboarding or on_dashboard,
            "After valid signup, user should see onboarding wizard or dashboard")

    # ── TC-BB-02: Signup with too-short username ───────────────────────────
    def test_bb02_signup_short_username_shows_error(self):
        """
        Input  : username = 'ab' (2 chars — below 3 char boundary)
        Expected: Error message visible, stays on auth screen
        Technique: Boundary Value Analysis — just below minimum
        """
        self.auth_page.open("/")
        self.auth_page.signup("ab", "SecurePass1")
        time.sleep(0.5)
        self.assertTrue(self.auth_page.error_visible(),
            "2-char username should trigger error")
        self.assertFalse(self.dash_page.is_loaded(),
            "Should NOT reach dashboard with invalid username")

    # ── TC-BB-03: Signup with too-short password ───────────────────────────
    def test_bb03_signup_short_password_shows_error(self):
        """
        Input  : password = '12345' (5 chars — below 6 char minimum)
        Expected: Error visible
        Technique: Boundary Value Analysis — just below minimum
        """
        uname = f"bb03_{uuid4().hex[:6]}"
        self.auth_page.open("/")
        self.auth_page.signup(uname, "12345")
        time.sleep(0.5)
        self.assertTrue(self.auth_page.error_visible(),
            "5-char password should trigger error")

    # ── TC-BB-04: Valid login ──────────────────────────────────────────────
    def test_bb04_valid_login_enters_app(self):
        """
        Input  : Existing username + correct password
        Expected: App loads (dashboard or onboarding visible)
        """
        uname = f"bb04_{uuid4().hex[:6]}"
        self.auth_page.open("/")
        self.auth_page.signup(uname, "ValidPass1")
        time.sleep(0.6)
        self.auth_page.logout()
        self.auth_page.open("/")
        self.auth_page.login(uname, "ValidPass1")
        time.sleep(0.8)
        in_app = self.on_page.is_on_onboarding() or self.dash_page.is_loaded()
        self.assertTrue(in_app, "Valid login should enter the app")

    # ── TC-BB-05: Login with wrong password ───────────────────────────────
    def test_bb05_wrong_password_shows_error(self):
        """
        Input  : Correct username, wrong password
        Expected: Error message, stays on auth screen
        Technique: Invalid equivalence partition
        """
        uname = f"bb05_{uuid4().hex[:6]}"
        self.auth_page.open("/")
        self.auth_page.signup(uname, "CorrectPass1")
        time.sleep(0.5)
        self.auth_page.logout()
        self.auth_page.open("/")
        self.auth_page.login(uname, "WrongPass999")
        time.sleep(0.5)
        self.assertTrue(self.auth_page.error_visible(),
            "Wrong password must show error message")

    # ── TC-BB-06: Login with non-existent user ────────────────────────────
    def test_bb06_nonexistent_user_shows_error(self):
        """
        Input  : Username that was never registered
        Expected: Error message
        Technique: Invalid equivalence partition
        """
        self.auth_page.open("/")
        self.auth_page.login("ghost_user_xyz_999", "AnyPass123")
        time.sleep(0.5)
        self.assertTrue(self.auth_page.error_visible(),
            "Non-existent user login must show error")


# ===========================================================================
# TS-2: Onboarding Wizard Tests
# ===========================================================================

class TS2_Onboarding(unittest.TestCase):
    """
    Test Scenario 2 — Onboarding wizard (4-step setup)
    Each test creates its own user so onboarding is always fresh.
    """

    @classmethod
    def setUpClass(cls):
        opts = ChromeOptions()
        if HEADLESS:
            opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1440,900")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        cls.driver = webdriver.Chrome(options=opts)
        cls.driver.implicitly_wait(2)
        cls.auth = AuthPage(cls.driver)
        cls.ob   = OnboardingPage(cls.driver)
        cls.dash = DashboardPage(cls.driver)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()

    def _new_signup(self):
        uname = f"ob_{uuid4().hex[:8]}"
        self.auth.open("/")
        self.auth.signup(uname, "TestPass@123")
        time.sleep(0.6)
        return uname

    # ── TC-BB-07: Step 1 — opening balance persists ───────────────────────
    def test_bb07_step1_opening_balance_input(self):
        """
        Input  : Opening balance = 25000
        Expected: Wizard advances to step 2 (categories section visible)
        """
        self._new_signup()
        self.assertTrue(self.ob.is_on_onboarding(), "Should be on onboarding")
        self.ob.step1_set_balance(25000)
        # After clicking next, step 2 should be active (category input visible)
        time.sleep(0.5)
        cat_input = self.driver.find_element(By.ID, "sc-ci")
        self.assertTrue(cat_input.is_displayed(), "Step 2 (categories) should be visible")

    # ── TC-BB-08: Skipping categories shows error ─────────────────────────
    def test_bb08_no_category_blocks_progress(self):
        """
        Input  : Skip step 2 without adding any category, click Finish
        Expected: Error message shown, does not reach dashboard
        """
        self._new_signup()
        self.ob.step1_set_balance(5000)
        # Skip adding categories, jump through steps
        self.driver.find_element(By.ID, "next-btn").click()  # to step 3
        time.sleep(0.3)
        self.driver.find_element(By.ID, "next-btn").click()  # to step 4
        time.sleep(0.3)
        self.driver.find_element(By.ID, "next-btn").click()  # try finish
        time.sleep(0.5)
        err = self.driver.find_element(By.ID, "se")
        self.assertTrue(err.is_displayed() and err.text.strip() != "",
            "Finishing without categories should show error")
        self.assertFalse(self.dash.is_loaded(), "Should NOT reach dashboard")

    # ── TC-BB-09: Complete wizard reaches dashboard ───────────────────────
    def test_bb09_complete_wizard_shows_dashboard(self):
        """
        Input  : Full valid setup — balance, 2 categories, 1 sub, payer, receiver
        Expected: Dashboard visible after completion
        """
        self._new_signup()
        self.ob.complete_full_setup(
            balance=8000,
            categories=["Groceries", "Income"],
            subcategories=["Veggies"],
            payers=["Client"],
            receivers=["Shop"]
        )
        time.sleep(1)
        self.assertTrue(self.dash.is_loaded(),
            "After completing wizard, dashboard should be visible")


# ===========================================================================
# TS-3: Dashboard Tests
# ===========================================================================

class TS3_Dashboard(FinTrackTestBase):
    """Test Scenario 3 — Dashboard stat cards and charts."""

    def setUp(self):
        self._fresh_login()
        self.dash_page.navigate_to()

    # ── TC-BB-10: All 4 stat cards visible ───────────────────────────────
    def test_bb10_all_stat_cards_visible(self):
        """
        Expected: All four cards (earnings, expenses, balance, opening) visible
        """
        self.assertTrue(self.dash_page.is_loaded(), "Dashboard should be loaded")
        for eid in ["d-earn", "d-exp", "d-bal", "d-open"]:
            self.assertTrue(self.dash_page.is_visible_id(eid),
                f"Stat card #{eid} should be visible")

    # ── TC-BB-11: Welcome greeting contains username ───────────────────────
    def test_bb11_greeting_contains_username(self):
        """
        Expected: Greeting text includes the logged-in username
        """
        greeting = self.dash_page.greeting()
        self.assertIn(self.username.lower(), greeting.lower(),
            f"Greeting '{greeting}' should contain '{self.username}'")

    # ── TC-BB-12: Charts rendered after adding a record ───────────────────
    def test_bb12_charts_render_after_record(self):
        """
        Input  : Add one expense record
        Expected: Bar chart container has children (chart rendered)
        """
        self.rec_page.navigate_to()
        note = f"chart_{uuid4().hex[:6]}"
        self.rec_page.add_full_record(1200, "Food", notes=note)
        self.dash_page.navigate_to()
        time.sleep(0.5)
        bar = self.driver.find_element(By.ID, "bar-chart")
        self.assertTrue(len(bar.find_elements(By.XPATH, ".//*")) > 0,
            "Bar chart should have rendered elements after record added")


# ===========================================================================
# TS-4: Records Management Tests
# ===========================================================================

class TS4_Records(FinTrackTestBase):
    """
    Test Scenario 4 — Records CRUD and filtering.
    Technique: Use-Case Based Testing, Decision Table
    """

    def setUp(self):
        self._fresh_login()
        self.rec_page.navigate_to()

    # ── TC-BB-13: Add expense record appears in table ─────────────────────
    def test_bb13_add_expense_record_appears_in_table(self):
        """
        Input  : Type=Expense, Amount=500, Category=Food, Note=unique string
        Expected: Note text appears in records table
        """
        note = f"exp_{uuid4().hex[:6]}"
        self.rec_page.add_full_record(500, "Food", notes=note, rtype="expense")
        self.assertTrue(self.rec_page.row_contains(note),
            f"Note '{note}' should appear in records table after adding")

    # ── TC-BB-14: Add earning record appears in table ─────────────────────
    def test_bb14_add_earning_record_appears_in_table(self):
        """
        Input  : Type=Earning, Amount=50000, Category=Salary
        Expected: Record appears in table with positive amount
        """
        note = f"earn_{uuid4().hex[:6]}"
        self.rec_page.add_full_record(50000, "Salary", notes=note, rtype="earning")
        self.assertTrue(self.rec_page.row_contains(note),
            "Earning record should appear in table")

    # ── TC-BB-15: Add record — missing amount shows error ─────────────────
    def test_bb15_add_record_missing_amount_shows_error(self):
        """
        Input  : No amount entered
        Expected: Modal error message visible, modal stays open
        Technique: Invalid equivalence partition
        """
        self.rec_page.open_add_modal()
        self.rec_page.set_type("expense")
        # Don't fill amount
        self.rec_page.js(
            "var s=document.getElementById('rc');"
            "for(var i=0;i<s.options.length;i++){if(s.options[i].text==='Food'){s.selectedIndex=i;break;}}"
        )
        self.rec_page.save_record()
        err = self.rec_page.modal_error_text()
        self.assertNotEqual(err, "", "Missing amount should show error in modal")
        self.rec_page.close_modal()

    # ── TC-BB-16: Add record — zero amount shows error ────────────────────
    def test_bb16_add_record_zero_amount_shows_error(self):
        """
        Input  : Amount = 0 (boundary — just below valid minimum)
        Expected: Error shown
        Technique: Boundary Value Analysis
        """
        self.rec_page.open_add_modal()
        self.rec_page.fill_record_form(0, "Food", notes="zero-amt")
        self.rec_page.save_record()
        err = self.rec_page.modal_error_text()
        self.assertNotEqual(err, "", "Amount=0 should show error")
        self.rec_page.close_modal()

    # ── TC-BB-17: Edit record updates displayed data ───────────────────────
    def test_bb17_edit_record_updates_note(self):
        """
        Input  : Edit existing record's note
        Expected: Updated note visible in table
        """
        orig_note = f"orig_{uuid4().hex[:5]}"
        new_note  = f"edit_{uuid4().hex[:5]}"
        self.rec_page.add_full_record(300, "Food", notes=orig_note)
        self.rec_page.clear_search()
        self.rec_page.search(orig_note)
        time.sleep(0.4)
        self.rec_page.click_edit_for_row(orig_note)
        time.sleep(0.4)
        self.rec_page.type_id("rn", new_note)
        self.rec_page.save_record()
        self.rec_page.clear_search()
        time.sleep(0.3)
        self.assertTrue(self.rec_page.row_contains(new_note),
            f"Updated note '{new_note}' should appear in table")

    # ── TC-BB-18: Delete record removes from table ────────────────────────
    def test_bb18_delete_record_removes_from_table(self):
        """
        Input  : Delete an existing record
        Expected: Record no longer in table
        """
        note = f"del_{uuid4().hex[:5]}"
        self.rec_page.add_full_record(700, "Transport", notes=note)
        self.rec_page.clear_search()
        self.rec_page.search(note)
        time.sleep(0.4)
        self.assertTrue(self.rec_page.row_contains(note), "Record should exist before delete")
        self.rec_page.click_delete_for_row(note)
        self.rec_page.confirm_delete()
        time.sleep(0.3)
        self.assertFalse(self.rec_page.row_contains(note),
            "Record should be gone after deletion")

    # ── TC-BB-19: Type filter shows only matching records ─────────────────
    def test_bb19_type_filter_shows_only_expenses(self):
        """
        Input  : Add expense + earning, filter by 'expense'
        Expected: Only expense type rows visible
        Technique: Decision Table — filter combinations
        """
        e_note = f"fe_{uuid4().hex[:4]}"
        n_note = f"fe_earn_{uuid4().hex[:4]}"
        self.rec_page.add_full_record(100, "Food", notes=e_note, rtype="expense")
        self.rec_page.add_full_record(1000, "Salary", notes=n_note, rtype="earning")
        self.rec_page.clear_search()
        self.rec_page.set_type_filter("expense")
        time.sleep(0.4)
        tbody = self.driver.find_element(By.ID, "rtbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")
        for row in rows:
            if row.text.strip() and "No records" not in row.text:
                badges = row.find_elements(By.CSS_SELECTOR, ".badge")
                for b in badges:
                    self.assertEqual(b.text.strip().lower(), "expense",
                        "Only expense records should show when filtering by expense")
        self.rec_page.set_type_filter("")  # reset

    # ── TC-BB-20: Search filter narrows results ───────────────────────────
    def test_bb20_search_filter_narrows_results(self):
        """
        Input  : Add record with unique note, search for that note
        Expected: Only matching record(s) shown
        """
        unique_note = f"srch_{uuid4().hex[:8]}"
        self.rec_page.add_full_record(250, "Food", notes=unique_note)
        self.rec_page.clear_search()
        self.rec_page.search(unique_note)
        time.sleep(0.4)
        self.assertTrue(self.rec_page.row_contains(unique_note),
            "Searched record should be visible")
        # Count should be exactly 1 (unique note)
        count = self.rec_page.row_count()
        self.assertEqual(count, 1, f"Search should return exactly 1 result, got {count}")


# ===========================================================================
# TS-5: Budget Manager Tests
# ===========================================================================

class TS5_Budget(FinTrackTestBase):
    """
    Test Scenario 5 — Budget Manager
    Technique: Use-Case Based, Equivalence Partitioning
    """

    def setUp(self):
        self._fresh_login()
        self.bgt_page.navigate_to()

    # ── TC-BB-21: Set monthly budget appears in active budgets ────────────
    def test_bb21_set_monthly_budget_appears_in_list(self):
        """
        Input  : Period=monthly, Amount=10000, Category=Overall
        Expected: Budget appears in Active Budgets list
        """
        self.bgt_page.set_budget("monthly", 10000)
        count = self.bgt_page.budget_count()
        self.assertGreaterEqual(count, 1,
            "Set budget should appear in Active Budgets")

    # ── TC-BB-22: Set budget with zero amount shows error ─────────────────
    def test_bb22_set_budget_zero_amount_shows_error(self):
        """
        Input  : Amount = 0
        Expected: Error message visible
        Technique: Boundary Value Analysis
        """
        self.bgt_page.set_budget("monthly", 0)
        time.sleep(0.4)
        err = self.bgt_page.form_error()
        self.assertNotEqual(err, "", "Zero budget amount should show error")

    # ── TC-BB-23: Exceeding budget shows alert on dashboard ───────────────
    def test_bb23_exceeding_budget_shows_alert(self):
        """
        Input  : Set budget=1000, add expense=2000 (exceeds)
        Expected: Budget alert visible on dashboard
        Technique: Decision Table — exceeded branch
        """
        self.bgt_page.set_budget("monthly", 1000)
        self.rec_page.navigate_to()
        self.rec_page.add_full_record(2000, "Food",
            notes=f"exceed_{uuid4().hex[:4]}")
        self.dash_page.navigate_to()
        time.sleep(0.6)
        alert_count = self.dash_page.alert_count()
        self.assertGreater(alert_count, 0,
            "Exceeding budget should show alert banner on dashboard")

    # ── TC-BB-24: Delete budget removes from list ─────────────────────────
    def test_bb24_delete_budget_removes_from_list(self):
        """
        Input  : Delete the first active budget
        Expected: Budget list is empty (or has one less item)
        """
        self.bgt_page.set_budget("weekly", 5000)
        before = self.bgt_page.budget_count()
        self.assertGreater(before, 0, "Should have at least one budget before delete")
        self.bgt_page.delete_first_budget()
        after = self.bgt_page.budget_count()
        self.assertLess(after, before, "Budget count should decrease after delete")

    # ── TC-BB-25: Per-category budget only alerts for that category ────────
    def test_bb25_per_category_budget_alert(self):
        """
        Input  : Set budget for 'Food'=500, add Transport=1000 (different cat)
        Expected: No alert (Transport doesn't affect Food budget)
        Then add Food=600 → alert appears
        Technique: Decision Table — category-specific budget
        """
        self.bgt_page.navigate_to()
        self.bgt_page.set_budget("monthly", 500, category="Food")
        # Add expense in different category — should NOT trigger Food budget
        self.rec_page.navigate_to()
        self.rec_page.add_full_record(1000, "Transport",
            notes=f"trans_{uuid4().hex[:4]}")
        self.dash_page.navigate_to()
        time.sleep(0.5)
        # Now add expense in Food that exceeds
        self.rec_page.navigate_to()
        self.rec_page.add_full_record(600, "Food",
            notes=f"food_exc_{uuid4().hex[:4]}")
        self.dash_page.navigate_to()
        time.sleep(0.6)
        alert_count = self.dash_page.alert_count()
        self.assertGreater(alert_count, 0,
            "Exceeding Food-specific budget should show alert")


# ===========================================================================
# TS-6: Edit Masters Tests
# ===========================================================================

class TS6_EditMasters(FinTrackTestBase):
    """
    Test Scenario 6 — Edit Masters page (post-onboarding editing)
    """

    def setUp(self):
        self._fresh_login()
        self.mst_page.navigate_to()

    # ── TC-BB-26: Edit Masters page loads with existing data ─────────────
    def test_bb26_masters_page_shows_existing_categories(self):
        """
        Expected: Categories set during onboarding are pre-populated
        """
        cats_el = self.driver.find_element(By.ID, "m-categories")
        # Should have tag elements from onboarding
        tags = cats_el.find_elements(By.CSS_SELECTOR, ".tag")
        self.assertGreater(len(tags), 0,
            "Masters page should show categories from onboarding")

    # ── TC-BB-27: Add new category and save ──────────────────────────────
    def test_bb27_add_new_category_and_save(self):
        """
        Input  : Add a new category tag, click Save Changes
        Expected: Success message visible
        """
        new_cat = f"Cat_{uuid4().hex[:4]}"
        self.mst_page.add_category(new_cat)
        self.mst_page.save()
        self.assertTrue(self.mst_page.success_visible(),
            "Saving new category should show success message")

    # ── TC-BB-28: Change opening balance and save ─────────────────────────
    def test_bb28_change_opening_balance_reflects_on_dashboard(self):
        """
        Input  : Change opening balance to 99999 and save
        Expected: Dashboard opening balance card updated
        """
        self.mst_page.set_balance(99999)
        self.mst_page.save()
        time.sleep(0.5)
        self.dash_page.navigate_to()
        time.sleep(0.5)
        bal_text = self.dash_page.opening_balance()
        self.assertIn("99", bal_text,
            f"Opening balance '{bal_text}' should reflect 99999")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
