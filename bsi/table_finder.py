"""
TABLE FINDER: locate the transaction table inside a statement that also contains other text
(bank name, account holder, address, period, opening/closing summary, footers, disclaimers).

Every reader (CSV, TXT, XLS, XLSX, JSON, PDF) turns its file into plain rows of cells and calls this module, so metadata is
handled the same way for every format and never has to be removed by hand:
  1. Header row = a row whose individual cells match several standard column names (date, narration, debit, credit,
     balance...) AND is followed by a row with a real date in the date column. Metadata lines such as
     "Statement date | Closing balance" do not pass the second check.
  2. Data rows = rows with a valid date, or with numeric amount + balance cells (kept so that a bad date is reported as a
     rejected row, not hidden). Everything else (account details, totals, footers, blank lines) is ignored.
  3. Repeated header rows (page breaks) are skipped.
Rule-based (no ML). Nothing outside the table is stored.
"""
from __future__ import annotations

import re

from bsi.normalizer import build_column_map
from bsi.schema import try_parse_date, clean_number

MAX_SCAN_ROWS = 200
LOOKAHEAD_ROWS = 15
_FOOTER = re.compile(r"\b(page\s+\d+|generated on|computer generated|statement summary|end of statement|"
                     r"this is a system|registered office|disclaimer|opening balance|closing balance|total)\b", re.I)


def _is_number(v) -> bool:
    s = str(v or "").strip()
    return s != "" and clean_number(s) is not None


def header_fields(cells):
    """Standard fields matched by the individual cells of this row ({} if it does not look like a header)."""
    named = [c for c in cells if c and len(c) <= 40]
    if len(named) < 3:
        return {}
    fmap = build_column_map(named)
    others = [f for f in fmap if f in ("narration", "withdrawal", "deposit", "closing_balance")]
    return fmap if "date" in fmap and len(others) >= 2 else {}


def _unique_header(cells):
    seen, out = {}, []
    for j, c in enumerate(cells):
        name = c or f"column_{j}"
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return out


def find_header(rows):
    """Index of the header row in `rows` (list of lists of str), or None."""
    for i, cells in enumerate(rows[:MAX_SCAN_ROWS]):
        fmap = header_fields(cells)
        if not fmap:
            continue
        didx = cells.index(fmap["date"]) if fmap["date"] in cells else None
        if didx is None:
            continue
        for r in rows[i + 1:i + 1 + LOOKAHEAD_ROWS]:
            if didx < len(r) and try_parse_date(r[didx]) is not None:
                return i
    return None


def _row_is_transaction(d):
    if try_parse_date(d.get("date", "")) is not None:
        return True
    money = [d.get(k, "") for k in ("withdrawal", "deposit")]
    return _is_number(d.get("closing_balance", "")) and any(_is_number(m) and str(m).strip() for m in money) \
        and str(d.get("date", "")).strip() != ""


def rows_to_dicts(rows):
    """Header-keyed dict rows for the transaction table found in `rows`; [] if there is none."""
    i = find_header(rows)
    if i is None:
        return []
    cells = rows[i]
    header = _unique_header(cells)
    cmap = build_column_map(header)
    from bsi.normalizer import normalize_row
    out = []
    for r in rows[i + 1:]:
        if not any(c for c in r):
            continue
        if header_fields(list(r)) and len(header_fields(list(r))) >= 3:
            continue                                            # repeated header (page break)
        r = list(r) + [""] * (len(header) - len(r))
        d = dict(zip(header, r))
        if _row_is_transaction(normalize_row(d, cmap)):
            out.append(d)                                       # else: metadata, totals or footer: ignored
    return out


def continuation_text(std_row, cells):
    """PDF helper: text of a wrapped-narration line (only the narration cell filled), else None."""
    if any(str(std_row.get(k, "")).strip() for k in ("date", "withdrawal", "deposit", "closing_balance")):
        return None
    text = str(std_row.get("narration", "")).strip()
    return text if text and not _FOOTER.search(text) else None
