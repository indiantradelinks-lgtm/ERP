"""Indian statutory ID validators — PAN, Aadhaar, UAN, ESIC, IFSC.

Lightweight regex + checksum checks only. They are FORGIVING: they accept
empty/missing values (HR may not have collected the ID yet) but reject
clearly-malformed entries that would later fail at the EPFO / IT-Dept gateway.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
AADHAAR_RE = re.compile(r"^\d{12}$")
UAN_RE = re.compile(r"^\d{12}$")
ESIC_RE = re.compile(r"^\d{10,17}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
PHONE_RE = re.compile(r"^[\+\-\d\s\(\)]{7,20}$")


def _verhoeff_check(number: str) -> bool:
    """Aadhaar checksum (Verhoeff)."""
    mul_table = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
        [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
        [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
        [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
        [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
    ]
    perm_table = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
        [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
        [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
        [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
    ]
    if not number.isdigit():
        return False
    c = 0
    for i, item in enumerate(reversed(number)):
        c = mul_table[c][perm_table[i % 8][int(item)]]
    return c == 0


def validate_employee_compliance(doc: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable validation errors, [] if all OK."""
    errs: List[str] = []

    def _norm(k: str) -> str:
        return str(doc.get(k) or "").strip().upper().replace(" ", "").replace("-", "")

    pan = _norm("pan_number")
    if pan and not PAN_RE.match(pan):
        errs.append("Invalid PAN — expected format ABCDE1234F (5 letters + 4 digits + 1 letter)")
    if pan:
        doc["pan_number"] = pan  # normalise

    aadhaar = _norm("aadhaar_number")
    if aadhaar:
        if not AADHAAR_RE.match(aadhaar):
            errs.append("Invalid Aadhaar — must be 12 digits")
        elif not _verhoeff_check(aadhaar):
            errs.append("Invalid Aadhaar — checksum mismatch")
        else:
            doc["aadhaar_number"] = aadhaar

    uan = _norm("uan")
    if uan and not UAN_RE.match(uan):
        errs.append("Invalid UAN — must be 12 digits")
    if uan:
        doc["uan"] = uan

    esic = _norm("esic_number")
    if esic and not ESIC_RE.match(esic):
        errs.append("Invalid ESIC IP Number — must be the 10-digit Insurance Person No. or the 17-digit ESIC Identity No.")
    if esic:
        doc["esic_number"] = esic

    ifsc = _norm("bank_ifsc")
    if ifsc and not IFSC_RE.match(ifsc):
        errs.append("Invalid IFSC — expected 11 chars like SBIN0001234 (4 letters + '0' + 6 alphanumeric)")
    if ifsc:
        doc["bank_ifsc"] = ifsc

    # Employment-type specific
    etype = (doc.get("employment_type") or "permanent").lower()
    if etype not in ("permanent", "daily_wages", "contractual"):
        errs.append(f"Unknown employment_type '{etype}'")
    doc["employment_type"] = etype

    if etype == "daily_wages":
        rate = doc.get("daily_rate")
        if rate is not None and float(rate or 0) < 0:
            errs.append("daily_rate cannot be negative")
    if etype == "contractual":
        cs, ce = doc.get("contract_start_date"), doc.get("contract_end_date")
        if cs and ce and str(ce) < str(cs):
            errs.append("contract_end_date is before contract_start_date")

    # Nominee share sanity
    share = doc.get("nominee_share_pct")
    if share is not None and share != "":
        try:
            s = float(share)
            if s < 0 or s > 100:
                errs.append("nominee_share_pct must be 0–100")
        except (TypeError, ValueError):
            errs.append("nominee_share_pct must be a number")

    return errs


def mask_aadhaar(num: str) -> str:
    """Return Aadhaar masked to last 4 (e.g. 'XXXX-XXXX-1234') for exports/PDFs."""
    s = str(num or "").strip()
    if len(s) == 12 and s.isdigit():
        return f"XXXX-XXXX-{s[-4:]}"
    return s
