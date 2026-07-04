"""Clean-room parser for stock/inventory CSV exports from Indian pharmacy
desktop software (Marg ERP, eVitalRx, Vyapar and similar).

Design goals:
  * stdlib only (``csv``, ``io``, ``re``) — no third-party dependencies
  * tolerant of messy real-world exports:
    inconsistent header names, mixed expiry-date formats, currency
    symbols and thousand separators inside numeric cells
  * never raises on a bad data row — malformed rows are skipped so a
    150,000-row export with a few broken lines still imports

Public API (re-exported from the package root):
  detect_columns(header_row)  -> {canonical_key: column_index}
  parse_expiry(raw)           -> "YYYY-MM-01" or None
  parse_csv(path_or_file)     -> iterator of normalized dicts
"""

from __future__ import annotations

import csv
import io
import re
from typing import IO, Dict, Iterator, List, Optional, Union

# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

# Canonical keys -> the header spellings seen in Marg ERP, eVitalRx and
# Vyapar exports. Matching is done on a normalized form of the header
# (lowercased, punctuation stripped, whitespace collapsed), so
# "Batch No.", "BATCH_NO" and "batch  no" all match "batch no".
_COLUMN_ALIASES: Dict[str, List[str]] = {
    "name": [
        "item name", "product", "product name", "medicine name",
        "medicine", "item", "drug name", "description", "item description",
    ],
    "batch": [
        "batch", "batch no", "batch number", "batchno", "batch code",
    ],
    "expiry": [
        "exp", "expiry", "exp date", "expiry date", "exp dt", "expdate",
    ],
    "mrp": [
        "mrp", "rate", "price", "sale rate", "mrp rate", "sale price",
    ],
    "qty": [
        "qty", "quantity", "stock", "stock qty", "current stock",
        "closing stock", "balance qty",
    ],
    "hsn": [
        "hsn", "hsn code", "hsn sac", "hsn no",
    ],
    "gst_percent": [
        "gst", "tax", "gst percent", "gst rate", "tax rate", "tax percent",
        "igst", "gst slab",
    ],
}


def _normalize_header(cell: str) -> str:
    """Lowercase a header cell and strip punctuation/extra whitespace.

    "Batch No."  -> "batch no"
    "GST %"      -> "gst percent"
    "HSN/SAC"    -> "hsn sac"
    """
    text = cell.strip().lower()
    text = text.replace("%", " percent ")
    # Any run of non-alphanumeric characters becomes a single space.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def detect_columns(header_row: List[str]) -> Dict[str, int]:
    """Map a CSV header row to canonical column indices.

    Returns a dict like ``{"name": 0, "batch": 2, "expiry": 3, ...}``
    containing only the canonical keys that were found. First match
    wins for each canonical key (left-most column).
    """
    detected: Dict[str, int] = {}
    for index, raw_cell in enumerate(header_row):
        normalized = _normalize_header(raw_cell)
        if not normalized:
            continue
        for key, aliases in _COLUMN_ALIASES.items():
            if key not in detected and normalized in aliases:
                detected[key] = index
                break
    return detected


# ---------------------------------------------------------------------------
# Expiry-date parsing
# ---------------------------------------------------------------------------

_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Each pattern captures (month, year) in some order; the handlers below
# normalize them. Pharmacy expiry is month-granular, so the day is
# always normalized to "01".
_RE_MM_YY = re.compile(r"^(\d{1,2})\s*/\s*(\d{2})$")          # 07/27
_RE_MM_YYYY = re.compile(r"^(\d{1,2})\s*[-/]\s*(\d{4})$")     # 07-2027
_RE_MMM_YY = re.compile(r"^([A-Za-z]{3,9})\s*[-/ ]\s*(\d{2,4})$")  # Jul-27
_RE_DD_MM_YYYY = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")    # 31.07.2027
_RE_ISO = re.compile(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$")   # 2027-07[-31]


def parse_expiry(raw: Optional[str]) -> Optional[str]:
    """Parse an expiry cell into ISO ``YYYY-MM-01``, or None if unparseable.

    Supported formats (all seen in real Marg/eVitalRx/Vyapar exports):
      MM/YY       "07/27"
      MMM-YY      "Jul-27", "JUL 2027"
      DD.MM.YYYY  "31.07.2027"
      ISO         "2027-07-31", "2027-07"
      MM-YYYY     "07-2027", "07/2027"
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    month: Optional[int] = None
    year: Optional[int] = None

    if match := _RE_MM_YY.match(text):
        month, year = int(match.group(1)), 2000 + int(match.group(2))
    elif match := _RE_MM_YYYY.match(text):
        month, year = int(match.group(1)), int(match.group(2))
    elif match := _RE_DD_MM_YYYY.match(text):
        month, year = int(match.group(2)), int(match.group(3))
    elif match := _RE_ISO.match(text):
        year, month = int(match.group(1)), int(match.group(2))
    elif match := _RE_MMM_YY.match(text):
        month = _MONTH_NAMES.get(match.group(1)[:3].lower())
        raw_year = int(match.group(2))
        year = raw_year if raw_year >= 1000 else 2000 + raw_year

    if month is None or year is None:
        return None
    if not (1 <= month <= 12) or not (2000 <= year <= 2099):
        return None
    return f"{year:04d}-{month:02d}-01"


# ---------------------------------------------------------------------------
# Numeric cell helpers
# ---------------------------------------------------------------------------

def _parse_number(raw: Optional[str]) -> Optional[float]:
    """Parse a numeric cell, tolerating currency symbols and separators.

    "₹1,250.50" -> 1250.5   "45" -> 45.0   "" / "N/A" -> None
    """
    if raw is None:
        return None
    cleaned = re.sub(r"[₹$,\s]", "", raw.strip())
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Row-level parsing
# ---------------------------------------------------------------------------

def _cell(row: List[str], columns: Dict[str, int], key: str) -> Optional[str]:
    """Fetch the raw cell for a canonical key, or None if absent."""
    index = columns.get(key)
    if index is None or index >= len(row):
        return None
    return row[index]


def parse_csv(path_or_file: Union[str, IO[str]]) -> Iterator[Dict[str, object]]:
    """Parse a stock-export CSV, yielding one normalized dict per item row.

    Accepts either a filesystem path or an already-open text file object.
    The first row containing recognizable headers is treated as the
    header (Marg exports sometimes prepend title/blank lines). Rows that
    do not carry an item name (blank lines, footer/total rows, garbage)
    are skipped rather than raising.

    Yielded dict shape::

        {
            "name": str,                 # always present, non-empty
            "batch": str | None,
            "expiry_iso": str | None,    # "YYYY-MM-01"
            "mrp": float | None,
            "qty": float | None,
            "hsn": str | None,
            "gst_percent": float | None,
        }
    """
    if isinstance(path_or_file, str):
        handle: IO[str] = open(path_or_file, newline="", encoding="utf-8-sig")
        owns_handle = True
    else:
        handle = path_or_file
        owns_handle = False

    try:
        reader = csv.reader(handle)

        # Find the header: the first row that yields at least one known
        # column.
        columns: Dict[str, int] = {}
        for row in reader:
            candidate = detect_columns(row)
            if candidate:
                columns = candidate
                break
        if "name" not in columns:
            return  # No usable header found — nothing to yield.

        for row in reader:
            name_cell = _cell(row, columns, "name")
            name = name_cell.strip() if name_cell else ""
            if not name:
                continue  # Malformed / footer / blank row — skip.

            batch_cell = _cell(row, columns, "batch")
            hsn_cell = _cell(row, columns, "hsn")

            yield {
                "name": name,
                "batch": batch_cell.strip() if batch_cell and batch_cell.strip() else None,
                "expiry_iso": parse_expiry(_cell(row, columns, "expiry")),
                "mrp": _parse_number(_cell(row, columns, "mrp")),
                "qty": _parse_number(_cell(row, columns, "qty")),
                "hsn": hsn_cell.strip() if hsn_cell and hsn_cell.strip() else None,
                "gst_percent": _parse_number(_cell(row, columns, "gst_percent")),
            }
    finally:
        if owns_handle:
            handle.close()
