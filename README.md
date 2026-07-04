# marg-csv-import

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A tiny, dependency-free Python library that parses stock/inventory CSV exports
from Indian pharmacy desktop software — **Marg ERP**, **eVitalRx**, **Vyapar**
and similar — into clean, normalized Python dicts.

## Why

If you are migrating a pharmacy off desktop billing software, the first wall
you hit is the stock export: every tool names its columns differently
(`Item Name` vs `Product` vs `Medicine Name`), and expiry dates arrive in at
least five different formats (`07/27`, `Jul-27`, `31.07.2027`, `2027-07-31`,
`07-2027`). This library absorbs that mess so your import code sees one
consistent shape:

```python
{
    "name": "Paracetamol 500mg",
    "batch": "B123",
    "expiry_iso": "2027-07-01",
    "mrp": 25.5,
    "qty": 100.0,
    "hsn": "3004",
    "gst_percent": 12.0,
}
```

It is deliberately forgiving: title lines before the header are skipped,
blank and nameless footer rows are dropped, currency symbols and thousand
separators in numeric cells are handled, and malformed rows never crash the
import.

## Install

Stdlib only — no dependencies.

```bash
pip install git+https://github.com/nesayo/marg-csv-import.git
```

## Usage

### 1. Parse a whole export file

```python
from marg_csv_import import parse_csv

for item in parse_csv("marg_stock_export.csv"):
    print(item["name"], item["batch"], item["expiry_iso"], item["qty"])
```

### 2. Parse an in-memory upload (e.g. from a web request)

```python
import io
from marg_csv_import import parse_csv

uploaded_bytes = request_body  # bytes from your web framework
rows = list(parse_csv(io.StringIO(uploaded_bytes.decode("utf-8-sig"))))
print(f"Imported {len(rows)} stock items")
```

### 3. Use the pieces directly

```python
from marg_csv_import import detect_columns, parse_expiry

columns = detect_columns(["Medicine Name", "Batch No.", "Exp", "MRP", "Stock"])
# {'name': 0, 'batch': 1, 'expiry': 2, 'mrp': 3, 'qty': 4}

parse_expiry("Jul-27")      # '2027-07-01'
parse_expiry("31.07.2027")  # '2027-07-01'
parse_expiry("garbage")     # None
```

## Supported column aliases

Header matching is case-insensitive and ignores punctuation
(`Batch No.` == `batch_no` == `BATCH NO`).

| Canonical key | Recognized headers |
|---|---|
| `name` | item name, product, product name, medicine name, medicine, item, drug name, description, item description |
| `batch` | batch, batch no, batch number, batchno, batch code |
| `expiry` | exp, expiry, exp date, expiry date, exp dt, expdate |
| `mrp` | mrp, rate, price, sale rate, mrp rate, sale price |
| `qty` | qty, quantity, stock, stock qty, current stock, closing stock, balance qty |
| `hsn` | hsn, hsn code, hsn/sac, hsn no |
| `gst_percent` | gst, tax, gst %, gst rate, tax rate, tax %, igst, gst slab |

## Supported expiry-date formats

Pharmacy expiry is month-granular, so everything normalizes to the first of
the month in ISO form (`YYYY-MM-01`). Unparseable values return `None` —
never an exception.

| Format | Example | Result |
|---|---|---|
| MM/YY | `07/27` | `2027-07-01` |
| MMM-YY / MMM YYYY | `Jul-27`, `DEC 2029` | `2027-07-01`, `2029-12-01` |
| DD.MM.YYYY | `31.07.2027` | `2027-07-01` |
| ISO | `2027-07-31`, `2027-07` | `2027-07-01` |
| MM-YYYY | `07-2027`, `07/2027` | `2027-07-01` |

## Notes

- Column mappings and date formats were validated against real export files,
  including exports from a Bangalore-area pharmacy migrating off desktop
  software.
- This library only parses. What you do with H/H1 schedule handling, GST
  filing, or batch-level FEFO logic is up to your application.

## Who built this

Built by the team behind [Nesayo](https://nesayo.com) — free cloud pharmacy
billing for India. Try the free medicine tools at
[https://nesayo.com/tools](https://nesayo.com/tools).

Contact: hello@nesayo.com · Site: https://nesayo.com

## License

MIT — see [LICENSE](LICENSE).
