"""Iter 211 — CMS bank file formatting (ICICI pay mode, name/remarks cleanup)."""
import sys
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from routers.payment_processing_router import (  # noqa: E402
    _bank_xlsx, _cms_beneficiary, _cms_remarks,
)

FILE = {
    "debit_ac_no": "123456789",
    "payment_mode": "N",
    "created_at": "2026-06-24T10:00:00+00:00",
    "rows": [
        {"vendor_account_no": "111", "vendor_name": "M/s. Sharma & Co. (India) Pvt-Ltd, Delhi",
         "ifsc": "icic0000123", "amount": 5000, "narration": "REQ-2026-0213"},
        {"vendor_account_no": "222", "vendor_name": "HDFC Vendor-Name, Ltd.",
         "ifsc": "HDFC0001234", "amount": 2500, "narration": "REQ-2026-0214 advance"},
    ],
}


def _rows():
    wb = load_workbook(BytesIO(_bank_xlsx(FILE)))
    return list(wb.active.iter_rows(values_only=True))


def test_icici_pay_mode_i_and_blank_ifsc():
    icici = _rows()[1]
    assert icici[4] == "I"
    assert not icici[6]


def test_other_bank_keeps_mode_and_ifsc():
    hdfc = _rows()[2]
    assert hdfc[4] == "N"
    assert hdfc[6] == "HDFC0001234"


def test_beneficiary_name_stripped_of_symbols():
    for row in _rows()[1:]:
        name = row[2]
        assert not any(ch in name for ch in "-,().&/"), name
    assert _cms_beneficiary("M/s. Sharma & Co. (India) Pvt-Ltd, Delhi") == "M s Sharma Co India Pvt Ltd Delhi"


def test_remarks_hyphens_become_spaces():
    assert _rows()[1][20] == "REQ 2026 0213"
    assert _cms_remarks("REQ-2026-0214 advance") == "REQ 2026 0214 advance"


def test_amount_and_debit_account_untouched():
    rows = _rows()
    assert [r[0] for r in rows[1:]] == ["123456789", "123456789"]
    assert [r[3] for r in rows[1:]] == [5000, 2500]
    assert [r[1] for r in rows[1:]] == ["111", "222"]
    assert rows[1][5] == "24-JUN-2026"
