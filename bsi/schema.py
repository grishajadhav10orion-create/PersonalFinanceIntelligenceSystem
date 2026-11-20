"""
STANDARDIZED TRANSACTION SCHEMA
==================================
This is the single target shape every input source (CSV, JSON, PDF)
gets normalized into. All later modules (narration intelligence, income
detection, recurring detection, risk detection, etc.) are built to
consume records in exactly this shape.

Fields:
    date              -- transaction date (ISO string, YYYY-MM-DD)
    narration         -- transaction description, cleaned of line-wrap artifacts
    reference_number  -- cheque/reference number, if present (optional)
    value_date        -- value date (ISO string). Defaults to `date` if the
                         source doesn't provide one separately.
    withdrawal        -- debit amount (float, 0.0 if not a withdrawal)
    deposit           -- credit amount (float, 0.0 if not a deposit)
    closing_balance   -- running balance after this transaction (float)

Note: this schema replaces the earlier CSV/JSON-only draft (which used a
single signed `amount` + `type` field). Real bank statements almost
always use separate withdrawal/deposit columns, so this version matches
real-world statement structure more closely.
"""
from __future__ import annotations


from dataclasses import dataclass, asdict
from datetime import datetime

REQUIRED_FIELDS = ["date", "narration", "closing_balance"]

# Date formats we'll try, in order, when parsing dates pulled from real
# statements -- these vary a lot bank to bank. 2-digit-year formats are
# tried as DD/MM/YY first, since that's the dominant convention on Indian
# bank statements (which is what this project is built around).
DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
    "%d %B %Y",
    "%d-%b-%Y",
    "%m/%d/%Y",
    "%m/%d/%y",
]


def try_parse_date(value: str):
    """Tries each known date format in turn. Returns an ISO date string
    on success, or None if nothing matched."""
    value = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def clean_number(value) -> float | None:
    """Parses a money value that may contain currency symbols, commas,
    or be wrapped in parentheses for negatives (e.g. '(500.00)').
    Returns None if the value can't be parsed as a number. Blank/empty
    values return 0.0, since a blank withdrawal/deposit cell just means
    'not applicable', not an error."""
    if value is None:
        return 0.0
    s = str(value).strip()
    if s == "":
        return 0.0
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = s.replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    try:
        num = float(s)
        return -num if negative else num
    except ValueError:
        return None


@dataclass
class Transaction:
    date: str
    narration: str
    reference_number: str
    value_date: str
    withdrawal: float
    deposit: float
    closing_balance: float

    def to_dict(self):
        return asdict(self)


def validate_and_build(row: dict) -> tuple["Transaction | None", str]:
    """
    Validates a normalized row (already mapped onto standard field names
    by the normalizer) and builds a Transaction. Returns (transaction, "")
    on success, or (None, reason) on failure -- nothing is silently
    dropped, every rejection has a specific reason.
    """
    narration = str(row.get("narration", "")).strip()
    if not narration:
        return None, "missing or empty narration"

    date_iso = try_parse_date(row.get("date", ""))
    if date_iso is None:
        return None, f"could not parse date: '{row.get('date')}'"

    value_date_raw = row.get("value_date", "")
    value_date_iso = try_parse_date(value_date_raw) if str(value_date_raw).strip() else None
    if value_date_iso is None:
        value_date_iso = date_iso  # fall back to transaction date

    withdrawal = clean_number(row.get("withdrawal", ""))
    if withdrawal is None:
        return None, f"invalid withdrawal amount: '{row.get('withdrawal')}'"

    deposit = clean_number(row.get("deposit", ""))
    if deposit is None:
        return None, f"invalid deposit amount: '{row.get('deposit')}'"

    closing_balance = clean_number(row.get("closing_balance", ""))
    if closing_balance is None:
        return None, f"invalid closing balance: '{row.get('closing_balance')}'"
    if row.get("closing_balance") in (None, ""):
        return None, "missing closing balance"

    txn = Transaction(
        date=date_iso,
        narration=narration,
        reference_number=str(row.get("reference_number", "")).strip(),
        value_date=value_date_iso,
        withdrawal=round(withdrawal, 2),
        deposit=round(deposit, 2),
        closing_balance=round(closing_balance, 2),
    )
    return txn, ""
