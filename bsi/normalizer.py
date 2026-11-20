"""
COLUMN NORMALIZER
====================
Real bank statements (and even different CSV/JSON exports) name their
columns differently: "Debit" vs "Withdrawal" vs "Dr", "Particulars" vs
"Narration" vs "Description", and so on -- and the columns can be in
any order. This module maps whatever headers a source actually has onto
our standard field names, so every source (CSV, JSON, PDF) converges
into one place before validation.
"""

import re

# Candidate header names for each standard field, most-common-first.
# Matching is case-insensitive and ignores punctuation/extra spaces.
FIELD_CANDIDATES = {
    "date": ["date", "txn date", "transaction date", "posting date", "tran date"],
    "narration": ["narration", "description", "particulars", "transaction details",
                  "details", "remarks"],
    "reference_number": ["reference number", "reference", "ref no", "chq ref no",
                          "cheque ref no", "cheque no", "chq no", "ref"],
    "value_date": ["value date", "val date", "value dt"],
    "withdrawal": ["withdrawal", "withdrawal amt", "withdrawal amount", "debit",
                   "debit amount", "dr"],
    "deposit": ["deposit", "deposit amt", "deposit amount", "credit",
                "credit amount", "cr"],
    "closing_balance": ["closing balance", "balance", "running balance",
                         "available balance", "balance amt"],
}


def _normalize_header(header: str) -> str:
    """'Debit Amount (INR)' -> 'debit amount inr' -- lowercase, strip
    punctuation, collapse whitespace, so matching is forgiving."""
    h = header.lower().strip()
    h = re.sub(r"[^a-z0-9 ]", " ", h)
    h = re.sub(r"\s+", " ", h).strip()
    return h


def build_column_map(headers: list[str]) -> dict[str, str]:
    """
    Given the actual headers found in a source (in whatever order/naming
    they use), returns a dict mapping standard_field -> actual_header,
    for every standard field we could confidently match.

    Matching strategy (deliberately simple, per project priorities):
      1. Exact match against a candidate name.
      2. Fallback: candidate name appears as a substring of the header
         (catches things like "Debit Amount (INR)" matching "debit amount").
    Each actual header is only used once, and first-matching standard
    field wins, so we don't double-map a single column.
    """
    normalized = {h: _normalize_header(h) for h in headers}
    column_map = {}
    used_headers = set()

    # Pass 1: exact matches (highest confidence)
    for field, candidates in FIELD_CANDIDATES.items():
        for header, norm in normalized.items():
            if header in used_headers:
                continue
            if norm in candidates:
                column_map[field] = header
                used_headers.add(header)
                break

    # Pass 2: substring fallback, only for fields not already mapped
    for field, candidates in FIELD_CANDIDATES.items():
        if field in column_map:
            continue
        for header, norm in normalized.items():
            if header in used_headers:
                continue
            if any(c in norm for c in candidates):
                column_map[field] = header
                used_headers.add(header)
                break

    return column_map


def normalize_row(raw_row: dict, column_map: dict[str, str]) -> dict:
    """Rebuilds a raw row (with source-specific headers) into a dict
    keyed by our standard field names, using the column map. Missing
    fields simply come through as empty strings -- validation decides
    what's actually required."""
    standard_row = {}
    for field in FIELD_CANDIDATES:
        source_header = column_map.get(field)
        standard_row[field] = raw_row.get(source_header, "") if source_header else ""
    return standard_row
