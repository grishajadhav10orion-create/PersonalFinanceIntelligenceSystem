"""
XLS / XLSX / TXT READER
=======================
Returns raw dict rows (headers-as-given), exactly like the CSV/JSON reader, so the rows go through the same
normalizer + validator. Bank exports usually have title/account-detail lines above the table and totals/footers below it, so the table is
located by content (bsi/table_finder.py), not assumed to start at row 1.

Pure-Python libraries only (openpyxl, xlrd), so behaviour is identical on Windows and macOS.
Password-protected workbooks are rejected, never opened.
"""
from __future__ import annotations

import csv
import datetime
import io
import re
from pathlib import Path

from bsi.readers.errors import PasswordProtectedError
from bsi.table_finder import rows_to_dicts

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"      # legacy container; encrypted .xlsx also uses it
_ZIP_MAGIC = b"PK"


def _cell(v) -> str:
    """Excel cell -> string the existing parsers understand (dates become ISO, whole floats lose '.0')."""
    if v is None:
        return ""
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _rows_to_dicts(rows: list[list[str]]) -> list[dict]:
    """Find the transaction table among title lines, account details, totals and footers (see bsi/table_finder.py)."""
    return rows_to_dicts(rows)


def _check_container(path: str, expect_zip: bool):
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(_OLE_MAGIC):
        if expect_zip:                               # .xlsx that is really an OLE file => encrypted package
            raise PasswordProtectedError("Excel file")
        return
    if expect_zip and not head.startswith(_ZIP_MAGIC):
        raise ValueError("This file is not a valid .xlsx workbook.")


def read_xlsx(path: str) -> list[dict]:
    import openpyxl
    _check_container(path, expect_zip=True)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:                     # first sheet that actually contains a statement table
            rows = [[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)]
            found = _rows_to_dicts(rows)
            if found:
                return found
        return []
    finally:
        wb.close()


def read_xls(path: str) -> list[dict]:
    import xlrd
    _check_container(path, expect_zip=False)
    try:
        wb = xlrd.open_workbook(path)
    except xlrd.XLRDError as e:
        if "encrypt" in str(e).lower() or "password" in str(e).lower():
            raise PasswordProtectedError("Excel file")
        raise ValueError(f"Could not read this .xls file: {e}")
    for sh in wb.sheets():
        rows = []
        for r in range(sh.nrows):
            row = []
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        row.append(xlrd.xldate.xldate_as_datetime(cell.value, wb.datemode).date().isoformat())
                        continue
                    except Exception:
                        pass
                row.append(_cell(cell.value))
            rows.append(row)
        found = _rows_to_dicts(rows)
        if found:
            return found
    return []


def _decode(path: str) -> str:
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read_txt(path: str) -> list[dict]:
    """Delimited text: tab, pipe, semicolon, comma, or columns separated by 2+ spaces. Any Windows (CRLF),
    macOS/Unix (LF) or old-Mac (CR) line endings. Metadata lines around the table are ignored."""
    lines = [l for l in io.StringIO(_decode(path), newline=None).read().split("\n") if l.strip()]
    splitters = [
        lambda l: next(csv.reader([l], delimiter="\t")),
        lambda l: next(csv.reader([l], delimiter="|")),
        lambda l: next(csv.reader([l], delimiter=";")),
        lambda l: next(csv.reader([l], delimiter=",")),
        lambda l: re.split(r"\s{2,}", l.strip()),
    ]
    for split in splitters:
        try:
            rows = [[c.strip() for c in split(l)] for l in lines]
        except csv.Error:
            continue
        found = _rows_to_dicts(rows)
        if found and len(found[0]) >= 3:
            return found
    return []
