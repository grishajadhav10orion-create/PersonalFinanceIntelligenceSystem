"""
Selenium black-box test suite for FinTrack.

Structure used:
- Object relation: driver -> page objects -> test scenario methods
- Class relation:
    BasePage
      ├── AuthPage
      ├── OnboardingPage
      ├── SidebarPage
      ├── DashboardPage
      └── RecordsPage
    FinTrackBlackBoxTests (unittest.TestCase)

Notes:
- This suite follows black-box testing: it validates visible behavior only.
- Selectors are written to be easy to adapt. Prefer adding stable data-testid or id
  attributes in your frontend and update the locator values below.
- Run app first: python app.py
- Then run tests: python -m unittest test_fintrack_selenium.py -v
"""

from __future__ import annotations

import os
import time
import unittest
from dataclasses import dataclass
from typing import Tuple
from uuid import uuid4

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


# -----------------------------
# Configuration object
# -----------------------------

@dataclass
class TestConfig:
    base_url: str = os.getenv("FINTRACK_BASE_URL", "http://localhost:5000")
    headless: bool = os.getenv("HEADLESS", "false").lower() == "true"
    timeout: int = int(os.getenv("SELENIUM_TIMEOUT", "10"))
    browser: str = os.getenv("BROWSER", "chrome")


# -----------------------------
# Base page object
# -----------------------------

class BasePage:
    def __init__(self, driver: WebDriver, config: TestConfig):
        self.driver = driver
        self.config = config
        self.wait = WebDriverWait(driver, config.timeout)

    def open(self, path: str = "/") -> None:
        self.driver.get(f"{self.config.base_url}{path}")

    def click(self, locator: Tuple[str, str]) -> None:
        self.wait.until(EC.element_to_be_clickable(locator)).click()

    def type(self, locator: Tuple[str, str], value: str, clear_first: bool = True) -> None:
        element = self.wait.until(EC.visibility_of_element_located(locator))
        if clear_first:
            element.clear()
        element.send_keys(value)

    def select_by_text(self, locator: Tuple[str, str], text: str) -> None:
        element = self.wait.until(EC.visibility_of_element_located(locator))
        Select(element).select_by_visible_text(text)

    def text_of(self, locator: Tuple[str, str]) -> str:
        return self.wait.until(EC.visibility_of_element_located(locator)).text.strip()

    def is_visible(self, locator: Tuple[str, str]) -> bool:
        try:
            self.wait.until(EC.visibility_of_element_located(locator))
            return True
        except TimeoutException:
            return False

    def wait_for_text(self, text: str) -> None:
        self.wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), text))

    def page_contains(self, text: str) -> bool:
        return text.lower() in self.driver.page_source.lower()


# -----------------------------
# Page objects
# -----------------------------

class AuthPage(BasePage):
    # Update these selectors to match your HTML.
    signup_username = (By.NAME, "dhruva")
    signup_password = (By.NAME, "123456")
    signup_button = (By.ID, "signup-btn")

    login_username = (By.NAME, "grisha")
    login_password = (By.NAME, "123456")
    login_button = (By.ID, "login-btn")

    logout_button = (By.ID, "logout-btn")
    auth_error = (By.CSS_SELECTOR, ".auth-error, .error-message, .toast-error")

    def signup(self, username: str, password: str) -> None:
        self.type(self.signup_username, username)
        self.type(self.signup_password, password)
        self.click(self.signup_button)

    def login(self, username: str, password: str) -> None:
        self.type(self.login_username, username)
        self.type(self.login_password, password)
        self.click(self.login_button)

    def logout(self) -> None:
        self.click(self.logout_button)


class OnboardingPage(BasePage):
    opening_balance_input = (By.NAME, "opening_balance")
    next_button = (By.ID, "next-step-btn")
    finish_button = (By.ID, "finish-onboarding-btn")

    category_input = (By.NAME, "category_name")
    add_category_button = (By.ID, "add-category-btn")

    subcategory_name_input = (By.NAME, "subcategory_name")
    subcategory_parent_select = (By.NAME, "subcategory_parent")
    add_subcategory_button = (By.ID, "add-subcategory-btn")

    payer_input = (By.NAME, "payer_name")
    add_payer_button = (By.ID, "add-payer-btn")

    receiver_input = (By.NAME, "receiver_name")
    add_receiver_button = (By.ID, "add-receiver-btn")

    def complete_setup(
        self,
        opening_balance: str,
        expense_category: str,
        earning_category: str,
        subcategory: str,
        payer: str,
        receiver: str,
    ) -> None:
        self.type(self.opening_balance_input, opening_balance)
        self.click(self.next_button)

        self.type(self.category_input, expense_category)
        self.click(self.add_category_button)
        self.type(self.category_input, earning_category)
        self.click(self.add_category_button)
        self.click(self.next_button)

        self.type(self.subcategory_name_input, subcategory)
        self.select_by_text(self.subcategory_parent_select, expense_category)
        self.click(self.add_subcategory_button)
        self.click(self.next_button)

        self.type(self.payer_input, payer)
        self.click(self.add_payer_button)
        self.type(self.receiver_input, receiver)
        self.click(self.add_receiver_button)
        self.click(self.finish_button)


class SidebarPage(BasePage):
    dashboard_link = (By.ID, "nav-dashboard")
    records_link = (By.ID, "nav-records")
    edit_masters_link = (By.ID, "nav-edit-masters")

    def go_dashboard(self) -> None:
        self.click(self.dashboard_link)

    def go_records(self) -> None:
        self.click(self.records_link)

    def go_edit_masters(self) -> None:
        self.click(self.edit_masters_link)


class DashboardPage(BasePage):
    earnings_card = (By.ID, "total-earnings")
    expenses_card = (By.ID, "total-expenses")
    net_balance_card = (By.ID, "net-balance")
    opening_balance_card = (By.ID, "opening-balance")
    recent_txn_section = (By.ID, "recent-transactions")

    def dashboard_loaded(self) -> bool:
        return self.is_visible(self.net_balance_card)


class RecordsPage(BasePage):
    add_record_button = (By.ID, "add-record-btn")
    record_type_select = (By.NAME, "record_type")
    amount_input = (By.NAME, "amount")
    category_select = (By.NAME, "category")
    subcategory_select = (By.NAME, "subcategory")
    party_select = (By.NAME, "receiver_payer")
    note_input = (By.NAME, "note")
    date_input = (By.NAME, "date")
    save_record_button = (By.ID, "save-record-btn")

    type_filter = (By.NAME, "filter_type")
    category_filter = (By.NAME, "filter_category")
    min_amount_filter = (By.NAME, "filter_min_amount")
    max_amount_filter = (By.NAME, "filter_max_amount")
    search_filter = (By.NAME, "filter_search")
    apply_filters_button = (By.ID, "apply-filters-btn")
    reset_filters_button = (By.ID, "reset-filters-btn")

    records_table = (By.ID, "records-table")
    pagination_next = (By.ID, "pagination-next")

    def add_record(
        self,
        record_type: str,
        amount: str,
        category: str,
        subcategory: str,
        party: str,
        note: str,
        date_str: str,
    ) -> None:
        self.click(self.add_record_button)
        self.select_by_text(self.record_type_select, record_type)
        self.type(self.amount_input, amount)
        self.select_by_text(self.category_select, category)
        self.select_by_text(self.subcategory_select, subcategory)
        self.select_by_text(self.party_select, party)
        self.type(self.note_input, note)
        self.type(self.date_input, date_str)
        self.click(self.save_record_button)

    def apply_type_filter(self, record_type: str) -> None:
        self.select_by_text(self.type_filter, record_type)
        self.click(self.apply_filters_button)

    def search_text(self, text: str) -> None:
        self.type(self.search_filter, text)
        self.click(self.apply_filters_button)

    def apply_amount_range(self, min_amount: str, max_amount: str) -> None:
        self.type(self.min_amount_filter, min_amount)
        self.type(self.max_amount_filter, max_amount)
        self.click(self.apply_filters_button)

    def row_action(self, row_text: str, action: str) -> None:
        # action should be: edit or delete
        xpath = (
            f"//table[@id='records-table']//tr[td[contains(., '{row_text}')]]"
            f"//button[contains(@class, '{action}') or contains(@data-action, '{action}') or @title='{action.title()}']"
        )
        self.click((By.XPATH, xpath))

    def row_exists(self, row_text: str) -> bool:
        xpath = f"//table[@id='records-table']//tr[td[contains(., '{row_text}')]]"
        return len(self.driver.find_elements(By.XPATH, xpath)) > 0

    def update_note_and_save(self, new_note: str) -> None:
        self.type(self.note_input, new_note)
        self.click(self.save_record_button)

    def confirm_delete(self) -> None:
        self.driver.switch_to.alert.accept()


# -----------------------------
# Test class
# -----------------------------

class FinTrackBlackBoxTests(unittest.TestCase):
    """
    8 black-box test cases across 3 test scenarios:

    Scenario 1: Authentication
      TC1 - valid signup
      TC2 - valid login
      TC3 - invalid login

    Scenario 2: Onboarding / dashboard
      TC4 - complete onboarding wizard
      TC5 - dashboard displays after onboarding

    Scenario 3: Records management
      TC6 - add record
      TC7 - edit record
      TC8 - filter and delete record
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = TestConfig()
        options = ChromeOptions()
        if cls.config.headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        cls.driver = webdriver.Chrome(options=options)
        cls.driver.implicitly_wait(2)

        cls.auth = AuthPage(cls.driver, cls.config)
        cls.onboarding = OnboardingPage(cls.driver, cls.config)
        cls.sidebar = SidebarPage(cls.driver, cls.config)
        cls.dashboard = DashboardPage(cls.driver, cls.config)
        cls.records = RecordsPage(cls.driver, cls.config)

        cls.test_user = f"user_{uuid4().hex[:8]}"
        cls.test_password = "Pass@12345"
        cls.expense_category = "Food"
        cls.earning_category = "Salary"
        cls.subcategory = "Dinner"
        cls.payer = "Employer"
        cls.receiver = "Restaurant"
        cls.record_note = f"selenium-expense-{uuid4().hex[:6]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.driver.quit()

    def setUp(self) -> None:
        self.auth.open("/")

    # -------- Scenario 1: Authentication --------

    def test_tc1_signup_with_valid_data(self) -> None:
        self.auth.signup(self.test_user, self.test_password)
        self.assertTrue(
            self.dashboard.dashboard_loaded() or self.onboarding.page_contains("opening balance"),
            "After signup, user should enter onboarding or dashboard.",
        )

    def test_tc2_login_with_valid_credentials(self) -> None:
        # If previous test kept us logged in, log out first when possible.
        try:
            if self.auth.is_visible(self.auth.logout_button):
                self.auth.logout()
        except Exception:
            pass

        self.auth.open("/")
        self.auth.login(self.test_user, self.test_password)
        self.assertTrue(
            self.dashboard.dashboard_loaded() or self.onboarding.page_contains("opening balance"),
            "Valid login should navigate into the application.",
        )

    def test_tc3_login_with_invalid_password_shows_error(self) -> None:
        try:
            if self.auth.is_visible(self.auth.logout_button):
                self.auth.logout()
        except Exception:
            pass

        self.auth.open("/")
        self.auth.login(self.test_user, "WrongPassword123")
        self.assertTrue(
            self.auth.is_visible(self.auth.auth_error) or self.auth.page_contains("invalid") or self.auth.page_contains("incorrect"),
            "Invalid login should show an error message.",
        )

    # -------- Scenario 2: Onboarding / Dashboard --------

    def test_tc4_complete_onboarding_wizard(self) -> None:
        self.auth.open("/")
        self.auth.login(self.test_user, self.test_password)

        # Only run wizard steps if onboarding page is visible.
        if self.onboarding.page_contains("opening balance") or self.onboarding.is_visible(self.onboarding.opening_balance_input):
            self.onboarding.complete_setup(
                opening_balance="10000",
                expense_category=self.expense_category,
                earning_category=self.earning_category,
                subcategory=self.subcategory,
                payer=self.payer,
                receiver=self.receiver,
            )

        self.assertTrue(
            self.dashboard.dashboard_loaded() or self.dashboard.page_contains("dashboard"),
            "Completing onboarding should open dashboard.",
        )

    def test_tc5_dashboard_displays_summary_cards(self) -> None:
        self.auth.open("/")
        self.auth.login(self.test_user, self.test_password)
        self.assertTrue(self.dashboard.is_visible(self.dashboard.net_balance_card))
        self.assertTrue(self.dashboard.is_visible(self.dashboard.opening_balance_card))
        self.assertTrue(self.dashboard.is_visible(self.dashboard.recent_txn_section))

    # -------- Scenario 3: Records Management --------

    def test_tc6_add_expense_record(self) -> None:
        self.auth.open("/")
        self.auth.login(self.test_user, self.test_password)
        self.sidebar.go_records()

        self.records.add_record(
            record_type="expense",
            amount="250",
            category=self.expense_category,
            subcategory=self.subcategory,
            party=self.receiver,
            note=self.record_note,
            date_str="2026-04-08",
        )

        self.assertTrue(
            self.records.row_exists(self.record_note) or self.records.page_contains(self.record_note),
            "Newly added expense record should appear in records table.",
        )

    def test_tc7_edit_existing_record(self) -> None:
        updated_note = f"{self.record_note}-edited"

        self.auth.open("/")
        self.auth.login(self.test_user, self.test_password)
        self.sidebar.go_records()

        self.records.row_action(self.record_note, "edit")
        self.records.update_note_and_save(updated_note)

        self.assertTrue(
            self.records.row_exists(updated_note) or self.records.page_contains(updated_note),
            "Edited record should display updated note text.",
        )
        self.__class__.record_note = updated_note

    def test_tc8_filter_then_delete_record(self) -> None:
        self.auth.open("/")
        self.auth.login(self.test_user, self.test_password)
        self.sidebar.go_records()

        self.records.apply_type_filter("expense")
        self.records.search_text(self.record_note)
        self.assertTrue(self.records.row_exists(self.record_note), "Filtered record should be visible.")

        self.records.row_action(self.record_note, "delete")
        self.records.confirm_delete()
        time.sleep(1)

        self.assertFalse(
            self.records.row_exists(self.record_note),
            "Record should disappear from the table after deletion.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
