"""
MODULE 1: STATEMENT INGESTION & EXTRACTION
=============================================
The single entry point every UI page / script should call. Detects the
file type, reads it with the right reader, normalizes whatever columns
it has onto the standard schema, and validates every row.

Every input source (CSV, JSON, XLS, XLSX, TXT, PDF) converges here -- none of them
implement their own validation logic, so behavior is guaranteed
consistent regardless of source.
"""
from __future__ import annotations


from pathlib import Path

from bsi.readers.csv_json_reader import read_csv_or_json
from bsi.readers.excel_text_reader import read_txt, read_xls, read_xlsx
from bsi.readers.pdf_reader import extract_pdf_rows
from bsi.normalizer import build_column_map, normalize_row
from bsi.schema import validate_and_build, Transaction


def extract_statement(path: str) -> tuple[list[Transaction], list[dict], str]:
    """
    Returns (valid_transactions, rejected_rows, detected_file_type).
    Each rejected row keeps its original data plus a "reason" field --
    nothing is silently dropped.
    """
    suffix = Path(path).suffix.lower()

    if suffix == ".pdf":
        file_type = "pdf"
        standardized_rows = extract_pdf_rows(path)  # already normalized inside the PDF reader
    elif suffix in (".csv", ".json", ".xls", ".xlsx", ".txt"):
        file_type = suffix.lstrip(".")
        raw_rows = {".xls": read_xls, ".xlsx": read_xlsx, ".txt": read_txt}.get(suffix, read_csv_or_json)(path)
        if not raw_rows:
            raise ValueError("Could not find a transaction table in this file. Expected columns like Date, "
                             "Narration/Description, Withdrawal/Debit, Deposit/Credit and Balance.")
        column_map = build_column_map(list(raw_rows[0].keys()))
        standardized_rows = [normalize_row(r, column_map) for r in raw_rows]
    else:
        raise ValueError(f"Unsupported file type: {suffix} (expected .csv, .json, .xls, .xlsx, .txt or .pdf)")

    valid: list[Transaction] = []
    rejected: list[dict] = []

    for row in standardized_rows:
        txn, reason = validate_and_build(row)
        if txn is not None:
            valid.append(txn)
        else:
            rejected.append({**row, "reason": reason})

    return valid, rejected, file_type
