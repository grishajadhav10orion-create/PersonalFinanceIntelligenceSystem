"""
CSV / JSON READER
====================
Reused from the earlier Phase 1 extractor -- the raw file-reading logic
itself doesn't need to change, only what happens to the rows afterward
(they now go through the normalizer before validation, so this reader
just needs to return raw dict rows, headers-as-given).
"""

import csv
import json
from pathlib import Path


def read_csv(path: str) -> list[dict]:
    """CSV with or without title/account-detail lines above the table and totals/footers below it."""
    from bsi.readers.excel_text_reader import read_txt     # same delimiter + table-finding logic as TXT
    return read_txt(path)


def _find_transaction_list(node, depth=0):
    """Largest list of dict rows (anywhere in the JSON) whose keys look like statement columns."""
    from bsi.normalizer import build_column_map
    best = []
    if isinstance(node, list) and node and all(isinstance(x, dict) for x in node):
        m = build_column_map(list(node[0].keys()))
        if "date" in m and len(m) >= 3:
            return node
    children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else []
    if depth < 5:
        for ch in children:
            found = _find_transaction_list(ch, depth + 1)
            if len(found) > len(best):
                best = found
    return best


def read_json(path: str) -> list[dict]:
    """JSON list of transactions, or an object that also carries account details (the transaction list is located)."""
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("transactions"), list):
        return data["transactions"]
    found = _find_transaction_list(data)
    if found:
        return found
    return data if isinstance(data, list) else []


def read_csv_or_json(path: str) -> list[dict]:
    """Auto-detects CSV vs JSON from the file extension."""
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return read_csv(path)
    elif p.suffix.lower() == ".json":
        return read_json(path)
    else:
        raise ValueError(f"Unsupported file type for this reader: {p.suffix}")
