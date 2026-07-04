"""Pytest suite for marg_csv_import.parser."""

import io

from marg_csv_import import detect_columns, parse_csv, parse_expiry

# ---------------------------------------------------------------------------
# detect_columns — header alias detection
# ---------------------------------------------------------------------------


def test_detect_columns_marg_style_headers():
    header = ["Item Name", "Batch No.", "Exp Date", "MRP", "Qty", "HSN", "GST %"]
    columns = detect_columns(header)
    assert columns == {
        "name": 0,
        "batch": 1,
        "expiry": 2,
        "mrp": 3,
        "qty": 4,
        "hsn": 5,
        "gst_percent": 6,
    }


def test_detect_columns_evitalrx_style_headers():
    header = ["Medicine Name", "Batch", "Expiry", "Rate", "Stock", "HSN Code", "Tax"]
    columns = detect_columns(header)
    assert columns["name"] == 0
    assert columns["batch"] == 1
    assert columns["expiry"] == 2
    assert columns["mrp"] == 3
    assert columns["qty"] == 4
    assert columns["hsn"] == 5
    assert columns["gst_percent"] == 6


def test_detect_columns_vyapar_style_headers_case_insensitive():
    header = ["PRODUCT", "batch_no", "EXP", "Price", "QUANTITY", "hsn/sac", "gst rate"]
    columns = detect_columns(header)
    assert set(columns) == {
        "name", "batch", "expiry", "mrp", "qty", "hsn", "gst_percent",
    }


def test_detect_columns_partial_header():
    columns = detect_columns(["Product", "Qty"])
    assert columns == {"name": 0, "qty": 1}


# ---------------------------------------------------------------------------
# parse_expiry — every supported date format
# ---------------------------------------------------------------------------


def test_parse_expiry_mm_slash_yy():
    assert parse_expiry("07/27") == "2027-07-01"
    assert parse_expiry("1/28") == "2028-01-01"


def test_parse_expiry_mmm_dash_yy():
    assert parse_expiry("Jul-27") == "2027-07-01"
    assert parse_expiry("DEC-29") == "2029-12-01"
    assert parse_expiry("Mar 2028") == "2028-03-01"


def test_parse_expiry_dd_dot_mm_dot_yyyy():
    assert parse_expiry("31.07.2027") == "2027-07-01"
    assert parse_expiry("1.2.2028") == "2028-02-01"


def test_parse_expiry_iso():
    assert parse_expiry("2027-07-31") == "2027-07-01"
    assert parse_expiry("2027-07") == "2027-07-01"


def test_parse_expiry_mm_dash_yyyy():
    assert parse_expiry("07-2027") == "2027-07-01"
    assert parse_expiry("11/2028") == "2028-11-01"


def test_parse_expiry_garbage_returns_none():
    assert parse_expiry("") is None
    assert parse_expiry(None) is None
    assert parse_expiry("N/A") is None
    assert parse_expiry("13/27") is None  # month 13 is invalid
    assert parse_expiry("00-2027") is None  # month 0 is invalid


# ---------------------------------------------------------------------------
# parse_csv — end-to-end normalization
# ---------------------------------------------------------------------------


def _rows(csv_text):
    return list(parse_csv(io.StringIO(csv_text)))


def test_parse_csv_normalizes_full_rows():
    csv_text = (
        "Item Name,Batch No,Exp Date,MRP,Qty,HSN,GST %\n"
        "Paracetamol 500mg,B123,07/27,\"₹25.50\",100,3004,12\n"
        "Amoxicillin 250mg,AX9,Jul-28,45,50,3004,12\n"
    )
    rows = _rows(csv_text)
    assert len(rows) == 2
    assert rows[0] == {
        "name": "Paracetamol 500mg",
        "batch": "B123",
        "expiry_iso": "2027-07-01",
        "mrp": 25.5,
        "qty": 100.0,
        "hsn": "3004",
        "gst_percent": 12.0,
    }
    assert rows[1]["expiry_iso"] == "2028-07-01"


def test_parse_csv_skips_malformed_rows():
    csv_text = (
        "Product,Batch,Expiry,Rate,Stock\n"
        "Cetirizine 10mg,C1,31.12.2027,18,30\n"
        ",,,,\n"  # blank row — skipped
        "   ,B2,07/27,10,5\n"  # whitespace-only name — skipped
        "Grand Total,,,,1200\n"  # footer row still has a "name"; kept
        "Ibuprofen 400mg,I7,2028-03,32,12\n"
    )
    rows = _rows(csv_text)
    names = [row["name"] for row in rows]
    assert "Cetirizine 10mg" in names
    assert "Ibuprofen 400mg" in names
    assert all(row["name"].strip() for row in rows)
    # The two nameless rows were dropped.
    assert len(rows) == 3


def test_parse_csv_short_rows_and_bad_cells_do_not_raise():
    csv_text = (
        "Item Name,Batch No,Exp Date,MRP,Qty\n"
        "Dolo 650\n"  # row shorter than the header
        "Azithral 500,AZ1,bad-date,not-a-number,ten\n"
    )
    rows = _rows(csv_text)
    assert len(rows) == 2
    assert rows[0]["name"] == "Dolo 650"
    assert rows[0]["batch"] is None
    assert rows[1]["expiry_iso"] is None
    assert rows[1]["mrp"] is None
    assert rows[1]["qty"] is None


def test_parse_csv_skips_preamble_before_header():
    csv_text = (
        "Stock Report\n"
        "\n"
        "Medicine Name,Batch,Exp,MRP,Quantity\n"
        "Pantoprazole 40mg,P5,05/28,90,20\n"
    )
    rows = _rows(csv_text)
    assert len(rows) == 1
    assert rows[0]["name"] == "Pantoprazole 40mg"
    assert rows[0]["expiry_iso"] == "2028-05-01"


def test_parse_csv_no_usable_header_yields_nothing():
    assert _rows("foo,bar\n1,2\n") == []
