"""
PDF READER
=============
Extracts transaction tables from a PDF bank statement using pdfplumber,
then handles the messiest real-world problem: narrations that wrap onto
a second physical line, with the other columns left blank on that line.

Approach (kept deliberately simple, per project priorities): if an
extracted table row has no parseable date, its text is treated as a
continuation of the previous row's narration rather than a new
transaction. This is a reliable heuristic because every real
transaction row has a date -- a row without one is either a wrapped
narration continuation or a formatting artifact.
"""
from __future__ import annotations


import pdfplumber

from bsi.readers.errors import PasswordProtectedError

from bsi.schema import try_parse_date
from bsi.normalizer import build_column_map, normalize_row
from bsi.table_finder import find_header, header_fields, continuation_text


def _looks_like_header(cells: list[str]) -> bool:
    """Kept for compatibility: does this row look like the transaction-table header?"""
    return bool(header_fields([c for c in cells]))


def _open_pdf(path: str):
    try:
        return pdfplumber.open(path)
    except Exception as e:                                   # pdfplumber wraps pdfminer errors
        inner = e.args[0] if e.args else e
        name = type(inner).__name__ + type(e).__name__
        if "Password" in name or "Encrypt" in name:
            raise PasswordProtectedError("PDF")
        raise


def extract_pdf_rows(path: str) -> list[dict]:
    """
    Returns standardized dict rows (column-mapped via the normalizer), with wrapped-narration continuation lines merged
    into the row they belong to. Tables or text outside the transaction table (account details, summaries, page footers)
    are ignored: the header is found by content and confirmed by a dated row below it.
    """
    all_rows: list[list[str]] = []
    with _open_pdf(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw_row in table or []:
                    all_rows.append([c.strip().replace("\n", " ") if c else "" for c in raw_row])

    i = find_header(all_rows)
    if i is None:
        raise ValueError(
            "Could not find a transaction table in this PDF. Expected a table "
            "with columns like Date, Narration/Description, Withdrawal/Debit, "
            "Deposit/Credit, and Balance."
        )
    header = [c or f"column_{j}" for j, c in enumerate(all_rows[i])]
    column_map = build_column_map(header)
    out: list[dict] = []
    for cells in all_rows[i + 1:]:
        if all(c == "" for c in cells) or header_fields(cells):
            continue                                   # blank spacer row / header repeated on a later page
        std = normalize_row(dict(zip(header, cells)), column_map)
        if try_parse_date(std.get("date", "")) is not None:
            out.append(std)
        else:
            extra = continuation_text(std, cells)      # wrapped narration; totals, footers, page numbers are ignored
            if extra and out:
                out[-1]["narration"] = (out[-1]["narration"] + " " + extra).strip()
    return out
