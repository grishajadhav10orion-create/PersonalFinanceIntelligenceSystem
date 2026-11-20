"""
MODULE 2: NARRATION INTELLIGENCE
====================================
Takes Module 1's raw narrations and extracts the counterparty (who the
transaction was with), stripping out UPI handles, bank/IFSC-style codes,
reference numbers, and channel labels (UPI, NEFT, POS, etc.).

Approach: split the narration on its delimiters ("-" and "/", both are
used in real statements) into segments, classify each segment as
"noise" or "meaningful" using a small set of patterns, and join
whatever survives. This is rule-based on purpose -- no ML yet -- per
the project's "simple, reliable" priority. ML/embeddings for narrations
these rules can't handle is a documented future extension, not built now.
"""

import re

from bsi.schema import Transaction

# --- Noise patterns -----------------------------------------------------
_VPA_PATTERN = re.compile(r".+@.+")                             # e.g. name13@okhdfcbank
_IFSC_LIKE_PATTERN = re.compile(r"^[A-Z]{3,5}0[A-Z0-9]{4,}$")    # e.g. HDFC0000019, YESB0YBLUPI, KBK0001768
_REF_PATTERN = re.compile(r"^REF\d+[A-Z]*$", re.IGNORECASE)       # e.g. REF77281AB
_NUMERIC_PATTERN = re.compile(r"^\d+$")                           # pure reference numbers, any length

_CHANNEL_TOKENS = {
    "UPI", "UPIINTENT", "NEFT", "IMPS", "RTGS", "ACH", "NACH",
    "POS", "SIP", "GPAY", "RET", "IN",
}
_NOISE_PHRASE_PREFIXES = ("PAY VIA", "PAID VIA")

# Known acronyms that should stay uppercase during title-casing, instead
# of being flattened (e.g. "HDFC" should not become "Hdfc").
KNOWN_ACRONYMS = {"HDFC", "ICICI", "SBI", "IDFC", "RBL", "EMI", "SIP", "IND", "IT", "GST"}


def _is_noise_segment(segment: str) -> bool:
    s = segment.strip()
    if s == "" or len(s) <= 1:
        return True
    if _VPA_PATTERN.match(s):
        return True
    if _IFSC_LIKE_PATTERN.match(s):
        return True
    if _REF_PATTERN.match(s):
        return True
    if _NUMERIC_PATTERN.match(s):
        return True
    upper = s.upper()
    if upper in _CHANNEL_TOKENS:
        return True
    if upper.startswith(_NOISE_PHRASE_PREFIXES):
        return True
    return False


def _title_case_preserve_acronyms(text: str) -> str:
    words = []
    for w in text.split():
        words.append(w.upper() if w.upper() in KNOWN_ACRONYMS else w.capitalize())
    return " ".join(words)


def extract_counterparty(raw_narration: str) -> tuple[str, str]:
    """
    Cleans a raw narration and extracts the counterparty.

    Returns (cleaned_narration, counterparty). Both hold the same value
    in this first version -- separating "what the transaction was for"
    (e.g. a DIVIDEND payment) from "who it was with" (e.g. Reliance Ind)
    is a harder problem left for a future iteration; for now both fields
    exist so later modules have a stable interface to build on.
    """
    if not raw_narration or not raw_narration.strip():
        return "", ""

    segments = re.split(r"[-/]", raw_narration)
    kept = [seg.strip() for seg in segments if not _is_noise_segment(seg)]

    if not kept:
        # Nothing meaningful survived filtering (e.g. a narration that's
        # only codes/numbers) -- fall back to the original text rather
        # than silently returning something empty.
        fallback = raw_narration.strip()
        return fallback, _title_case_preserve_acronyms(fallback)

    joined = " ".join(kept)
    joined = re.sub(r"\s+", " ", joined).strip()
    cleaned = _title_case_preserve_acronyms(joined)
    return cleaned, cleaned


def enrich_transactions(transactions: list[Transaction]) -> list[dict]:
    """
    Takes Module 1's validated transactions and adds narration_clean +
    counterparty to each. Returns a new list of dicts -- Module 1's
    Transaction objects/schema are left untouched, so nothing upstream
    needs to change.
    """
    enriched = []
    for t in transactions:
        cleaned, counterparty = extract_counterparty(t.narration)
        row = t.to_dict()
        row["narration_clean"] = cleaned
        row["counterparty"] = counterparty
        enriched.append(row)
    return enriched
