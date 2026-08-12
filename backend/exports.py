"""Excel + PDF export helpers for module data tables."""
import io
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage

from pdf_watermark import attach_watermark

# Brand asset (kept at repo path so both Excel/PDF can embed it)
BRAND_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "itl-logo.jpg")
BRAND_NAME = "INDIAN TRADE LINKS"
BRAND_SUB = ""

# ─── DPDP Act 2023 — PII fields per resource ───────────────────────────────
# These fields are masked for non-privileged users in PDF/Excel exports.
# Privileged roles can see them in full (computed in exports_router.py).
PII_FIELDS: Dict[str, Set[str]] = {
    "clients":   {"contact", "phone", "email", "gst", "pan", "address", "billing_address"},
    "vendors":   {"contact", "phone", "email", "gst", "pan", "bank_account", "bank_account_no",
                  "ifsc", "address", "billing_address"},
    "employees": {"phone", "email", "salary", "ctc", "pan", "aadhaar", "aadhar", "bank_account",
                  "bank_account_no", "ifsc", "address", "permanent_address", "current_address",
                  "emergency_contact", "father_name", "mother_name", "spouse_name", "dob",
                  "date_of_birth"},
    "candidates": {"phone", "email", "pan", "aadhaar", "aadhar", "address", "dob", "date_of_birth"},
    "attendance": {"phone", "email"},
    "payroll":   {"pan", "aadhaar", "aadhar", "bank_account", "bank_account_no", "ifsc", "uan",
                  "esi_no", "pf_no"},
    "documents": {"uploaded_by"},
}


def _mask_value(key: str, val: Any) -> Any:
    """DPDP-compliant masking. Strategy is field-type aware:
       - email     → keep first char + ***@<domain>
       - phone     → last 4 digits visible, rest as X
       - account   → last 4 digits, rest as X
       - aadhaar   → XXXX-XXXX-1234
       - pan       → XXXXX1234X (first-5 + last char masked)
       - gst       → keep state code (first 2) + ***
       - dob/date  → year only
       - amount    → "***"  (salary/ctc)
       - default   → fully redacted with ***
    """
    if val is None or val == "":
        return val
    s = str(val)
    k = key.lower()
    if k in ("email",):
        if "@" in s:
            user, _, dom = s.partition("@")
            return f"{user[:1]}***@{dom}"
        return "***"
    if k in ("phone", "mobile", "contact", "emergency_contact"):
        digits = re.sub(r"\D", "", s)
        if len(digits) >= 4:
            return "X" * (len(digits) - 4) + digits[-4:]
        return "X" * len(digits) if digits else "***"
    if k in ("aadhaar", "aadhar"):
        digits = re.sub(r"\D", "", s)
        return f"XXXX-XXXX-{digits[-4:]}" if len(digits) >= 4 else "***"
    if k == "pan":
        return f"XXXXX{s[5:9]}X" if len(s) == 10 else "***"
    if k in ("gst", "gstin"):
        return f"{s[:2]}***{s[-1:]}" if len(s) >= 3 else "***"
    if k in ("bank_account", "bank_account_no", "account_no", "account_number"):
        digits = re.sub(r"\D", "", s)
        return "X" * max(0, len(digits) - 4) + digits[-4:] if digits else "***"
    if k == "ifsc":
        return f"{s[:4]}*****" if len(s) >= 4 else "***"
    if k in ("dob", "date_of_birth"):
        # Keep only year if it looks like YYYY-MM-DD
        m = re.match(r"^(\d{4})", s)
        return f"{m.group(1)}-XX-XX" if m else "***"
    if k in ("salary", "ctc", "gross", "net"):
        return "***"
    return "***"


def _redact_row(resource: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow-copied row with PII fields masked per DPDP rules."""
    fields = PII_FIELDS.get(resource)
    if not fields:
        return row
    return {k: (_mask_value(k, v) if k in fields else v) for k, v in row.items()}


# Per-resource column definitions for exports.
COLUMNS: Dict[str, List[Dict[str, str]]] = {
    "clients": [
        {"key": "code", "label": "Code"}, {"key": "name", "label": "Client"},
        {"key": "contact", "label": "Contact"}, {"key": "phone", "label": "Phone"},
        {"key": "gst", "label": "GST"}, {"key": "credit_limit", "label": "Credit Limit"},
        {"key": "status", "label": "Status"},
    ],
    "vendors": [
        {"key": "code", "label": "Code"}, {"key": "name", "label": "Vendor"},
        {"key": "category", "label": "Category"}, {"key": "contact", "label": "Contact"},
        {"key": "phone", "label": "Phone"}, {"key": "rating", "label": "Rating"},
        {"key": "status", "label": "Status"},
    ],
    "employees": [
        {"key": "emp_code", "label": "Code"}, {"key": "name", "label": "Name"},
        {"key": "role", "label": "Role"}, {"key": "department", "label": "Department"},
        {"key": "phone", "label": "Phone"}, {"key": "joining_date", "label": "Joined"},
        {"key": "salary", "label": "Salary"}, {"key": "status", "label": "Status"},
    ],
    "attendance": [
        {"key": "date", "label": "Date"}, {"key": "employee_name", "label": "Employee"},
        {"key": "check_in", "label": "In"}, {"key": "check_out", "label": "Out"},
        {"key": "hours", "label": "Hours"}, {"key": "status", "label": "Status"},
    ],
    "projects": [
        {"key": "code", "label": "Code"}, {"key": "name", "label": "Project"},
        {"key": "client", "label": "Client"}, {"key": "type", "label": "Type"},
        {"key": "site", "label": "Site"}, {"key": "manager", "label": "Manager"},
        {"key": "budget", "label": "Budget"}, {"key": "progress", "label": "Progress %"},
        {"key": "status", "label": "Status"},
    ],
    "inventory": [
        {"key": "code", "label": "Code"}, {"key": "name", "label": "Item"},
        {"key": "category", "label": "Category"}, {"key": "uom", "label": "UOM"},
        {"key": "quantity", "label": "Qty"}, {"key": "min_stock", "label": "Min"},
        {"key": "rate", "label": "Rate"}, {"key": "location", "label": "Location"},
    ],
    "purchase_orders": [
        {"key": "po_number", "label": "PO #"}, {"key": "vendor", "label": "Vendor"},
        {"key": "project", "label": "Project"}, {"key": "date", "label": "Date"},
        {"key": "total", "label": "Total"}, {"key": "paid", "label": "Paid"},
        {"key": "status", "label": "Status"},
    ],
    "quotations": [
        {"key": "quote_number", "label": "Quote #"}, {"key": "client", "label": "Client"},
        {"key": "project", "label": "Project"}, {"key": "date", "label": "Date"},
        {"key": "valid_until", "label": "Valid Till"}, {"key": "total", "label": "Total"},
        {"key": "status", "label": "Status"},
    ],
    "journal_entries": [
        {"key": "je_number", "label": "JE #"}, {"key": "date", "label": "Date"},
        {"key": "account", "label": "Account"}, {"key": "type", "label": "Type"},
        {"key": "cost_centre", "label": "Cost Centre"}, {"key": "amount", "label": "Amount"},
        {"key": "narration", "label": "Narration"},
    ],
    "safety_reports": [
        {"key": "report_id", "label": "Report"}, {"key": "date", "label": "Date"},
        {"key": "project", "label": "Project"}, {"key": "type", "label": "Type"},
        {"key": "severity", "label": "Severity"}, {"key": "reporter", "label": "Reporter"},
        {"key": "status", "label": "Status"},
    ],
    "assets": [
        {"key": "asset_id", "label": "Asset ID"}, {"key": "name", "label": "Asset"},
        {"key": "category", "label": "Category"}, {"key": "purchase_date", "label": "Purchased"},
        {"key": "cost", "label": "Cost"}, {"key": "location", "label": "Location"},
        {"key": "assigned_to", "label": "Assigned"}, {"key": "status", "label": "Status"},
    ],
    "payroll": [
        {"key": "employee_name", "label": "Employee"}, {"key": "month", "label": "Month"},
        {"key": "gross", "label": "Gross"}, {"key": "deductions", "label": "Deductions"},
        {"key": "net", "label": "Net Pay"}, {"key": "status", "label": "Status"},
    ],
    "vehicles": [
        {"key": "reg_number", "label": "Reg #"}, {"key": "type", "label": "Type"},
        {"key": "capacity", "label": "Capacity"}, {"key": "driver", "label": "Driver"},
        {"key": "last_service", "label": "Last Service"}, {"key": "fuel_avg", "label": "Fuel km/L"},
        {"key": "status", "label": "Status"},
    ],
    "documents": [
        {"key": "doc_id", "label": "Doc ID"}, {"key": "title", "label": "Title"},
        {"key": "category", "label": "Category"}, {"key": "project", "label": "Project"},
        {"key": "uploaded_by", "label": "Uploaded By"}, {"key": "version", "label": "Version"},
        {"key": "expiry", "label": "Expiry"},
    ],
    "approvals": [
        {"key": "title", "label": "Request"}, {"key": "type", "label": "Type"},
        {"key": "reference", "label": "Ref"}, {"key": "amount", "label": "Amount"},
        {"key": "requested_by", "label": "Requested By"}, {"key": "status", "label": "Status"},
    ],
    "scaf_stock": [
        {"key": "item_code", "label": "Code"},
        {"key": "item_name", "label": "Material"},
        {"key": "size", "label": "Size"},
        {"key": "spec", "label": "Specification"},
        {"key": "location_name", "label": "Location"},
        {"key": "location_type", "label": "Type"},
        {"key": "quantity", "label": "Qty On Hand"},
        {"key": "unit", "label": "Unit"},
    ],
    "scaf_challans": [
        {"key": "challan_no", "label": "Challan #"},
        {"key": "transfer_no", "label": "Transfer #"},
        {"key": "from_location", "label": "From"},
        {"key": "to_location", "label": "To"},
        {"key": "vehicle_no", "label": "Vehicle"},
        {"key": "driver_name", "label": "Driver"},
        {"key": "items_summary", "label": "Items"},
        {"key": "status", "label": "Status"},
        {"key": "dispatched_at", "label": "Dispatched"},
        {"key": "received_at", "label": "Received"},
    ],
    "project_requests": [
        {"key": "request_no", "label": "Request #"},
        {"key": "created_at", "label": "Raised On"},
        {"key": "project_code", "label": "Project"},
        {"key": "request_type_label", "label": "Type"},
        {"key": "owning_dept", "label": "Department"},
        {"key": "description", "label": "Description"},
        {"key": "est_value", "label": "Est. Value"},
        {"key": "vendor", "label": "Vendor"},
        {"key": "status", "label": "Status"},
        {"key": "pr_number", "label": "PR #"},
        {"key": "created_by", "label": "Raised By"},
        {"key": "fulfilled_by", "label": "Fulfilled By"},
    ],
    "project_expenses": [
        {"key": "expense_no", "label": "Expense #"},
        {"key": "expense_date", "label": "Date"},
        {"key": "project_code", "label": "Project"},
        {"key": "category_name", "label": "Cost Center"},
        {"key": "expense_type_label", "label": "Type"},
        {"key": "description", "label": "Description"},
        {"key": "amount", "label": "Amount"},
        {"key": "paid_to", "label": "Paid To"},
        {"key": "bill_no", "label": "Bill #"},
        {"key": "status", "label": "Status"},
        {"key": "created_by", "label": "Booked By"},
    ],
    "project_pnl": [
        {"key": "project_code", "label": "Project"},
        {"key": "project_name", "label": "Project Name"},
        {"key": "client", "label": "Client"},
        {"key": "income_billed", "label": "Sales (Billed)"},
        {"key": "receipts", "label": "Receipts"},
        {"key": "total_expense", "label": "Expenses"},
        {"key": "gross_profit", "label": "Gross Profit"},
        {"key": "margin_pct", "label": "Margin %"},
    ],
    "gmc_members": [
        {"key": "emp_code", "label": "Emp Code"},
        {"key": "name", "label": "Employee Name"},
        {"key": "designation", "label": "Designation"},
        {"key": "department", "label": "Department"},
        {"key": "coverage_scope", "label": "Coverage"},
        {"key": "project_code", "label": "Project"},
        {"key": "sum_insured", "label": "Sum Insured"},
        {"key": "premium", "label": "Premium"},
        {"key": "dependents", "label": "Dependents"},
        {"key": "dependent_names", "label": "Spouse / Kids Covered"},
        {"key": "status", "label": "Status"},
        {"key": "added_at", "label": "Added On"},
        {"key": "removed_at", "label": "Removed On"},
        {"key": "removal_reason", "label": "Removal Reason"},
    ],
    "ptws": [
        {"key": "ptw_no", "label": "PTW #"},
        {"key": "work_type", "label": "Work Type"},
        {"key": "location", "label": "Location"},
        {"key": "valid_from", "label": "Valid From"},
        {"key": "valid_to", "label": "Valid To"},
        {"key": "status", "label": "Status"},
        {"key": "created_by", "label": "Created By"},
        {"key": "created_at", "label": "Created"},
    ],
    "project_resources": [
        {"key": "project_code", "label": "Project Code"},
        {"key": "project_name", "label": "Project"},
        {"key": "resource_type", "label": "Type"},
        {"key": "description", "label": "Resource / Description"},
        {"key": "qty", "label": "Qty"},
        {"key": "uom", "label": "UOM"},
        {"key": "rate", "label": "Rate"},
        {"key": "total_cost", "label": "Total Cost"},
        {"key": "required_by_date", "label": "Required By"},
        {"key": "remarks", "label": "Remarks"},
    ],
    "project_handovers": [
        {"key": "handover_no", "label": "Handover #"},
        {"key": "project_code", "label": "Project Code"},
        {"key": "project_name", "label": "Project"},
        {"key": "client_name", "label": "Client"},
        {"key": "quotation_no", "label": "Quotation #"},
        {"key": "work_order_number", "label": "Work Order #"},
        {"key": "site_location", "label": "Site"},
        {"key": "contract_value", "label": "Contract Value"},
        {"key": "contract_start_date", "label": "Start"},
        {"key": "contract_end_date", "label": "End"},
        {"key": "scope_of_work", "label": "Scope of Work"},
        {"key": "project_manager_label", "label": "Project Manager"},
        {"key": "project_coordinator_label", "label": "Coordinator"},
        {"key": "priority", "label": "Priority"},
        {"key": "status", "label": "Status"},
        {"key": "created_at", "label": "Created"},
    ],
    "enquiries": [
        {"key": "enquiry_no", "label": "Enquiry #"},
        {"key": "customer_enquiry_no", "label": "Customer Enq #"},
        {"key": "dept_doc_no", "label": "Dept Doc #"},
        {"key": "enquiry_date", "label": "Date"},
        {"key": "client_code", "label": "Client Code"},
        {"key": "customer", "label": "Customer"},
        {"key": "site_code", "label": "Site Code"},
        {"key": "site_name", "label": "Site Name"},
        {"key": "site_location", "label": "Site Location"},
        {"key": "department", "label": "Department"},
        {"key": "contact_person", "label": "Contact Person"},
        {"key": "contact_email", "label": "Contact Email"},
        {"key": "contact_phone", "label": "Contact Phone"},
        {"key": "rfq_type", "label": "RFQ Type"},
        {"key": "service_categories", "label": "Services"},
        {"key": "priority", "label": "Priority"},
        {"key": "expected_value", "label": "Expected Value"},
        {"key": "scope_of_work", "label": "Scope of Work"},
        {"key": "technical_requirements", "label": "Technical Requirements"},
        {"key": "material_requirement", "label": "Material Requirement"},
        {"key": "manpower_requirement", "label": "Manpower Requirement"},
        {"key": "site_conditions", "label": "Site Conditions"},
        {"key": "special_instructions", "label": "Special Instructions"},
        {"key": "commercial_notes", "label": "Commercial Notes"},
        {"key": "submission_deadline", "label": "Submission Deadline"},
        {"key": "bid_closing_date", "label": "Bid Closing Date"},
        {"key": "status", "label": "Status"},
        {"key": "open_at", "label": "Opened At"},
        {"key": "under_review_at", "label": "Under Review At"},
        {"key": "submitted_at", "label": "Submitted At"},
        {"key": "negotiation_at", "label": "Negotiation At"},
        {"key": "hold_at", "label": "Hold At"},
        {"key": "won_at", "label": "Won At"},
        {"key": "lost_at", "label": "Lost At"},
        {"key": "quotation_no", "label": "Quotation #"},
        {"key": "order_no", "label": "Order #"},
        {"key": "project_code", "label": "Project Number"},
        {"key": "created_at", "label": "Created At"},
        {"key": "created_by_name", "label": "Created By"},
        {"key": "updated_at", "label": "Last Updated"},
    ],
}


ENQ_STATUSES = ("open", "under_review", "submitted", "negotiation", "hold", "won", "lost")


def enrich_enquiries(rows: List[Dict[str, Any]], name_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """Flatten enquiry docs for export: status-history milestones, list joins, name resolution."""
    for r in rows:
        hist = r.get("status_history") or []
        for st in ENQ_STATUSES:
            first = next((h for h in hist if h.get("status") == st), None)
            r[f"{st}_at"] = (first.get("at") or "")[:16].replace("T", " ") if first else ""
        for k in ("rfq_type", "service_categories"):
            if isinstance(r.get(k), list):
                r[k] = ", ".join(str(x).replace("_", " ") for x in r[k])
        r["material_requirement"] = r.get("material_requirement") or r.get("material_requirements") or ""
        r["created_by_name"] = name_map.get(r.get("created_by") or "", r.get("created_by") or "")
        for k in ("created_at", "updated_at"):
            r[k] = (r.get(k) or "")[:16].replace("T", " ")
    return rows


def to_excel(resource: str, rows: List[Dict[str, Any]], mask_pii: bool = False) -> bytes:
    if mask_pii:
        rows = [_redact_row(resource, r) for r in rows]
    cols = COLUMNS.get(resource, [{"key": k, "label": k} for k in (rows[0].keys() if rows else [])])
    wb = Workbook()
    ws = wb.active
    ws.title = resource[:31]

    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    thin = Side(border_style="thin", color="E2E8F0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Logo (top-left A1:B3)
    try:
        if os.path.exists(BRAND_LOGO_PATH):
            img = XLImage(BRAND_LOGO_PATH)
            img.height = 45
            img.width = 134
            ws.add_image(img, "A1")
            ws.row_dimensions[1].height = 22
            ws.row_dimensions[2].height = 22
            ws.row_dimensions[3].height = 22
    except Exception:
        pass

    # Brand text block (rows 1-3, columns C+)
    ws.cell(row=1, column=3, value=BRAND_NAME).font = Font(bold=True, size=14, color="0F172A")
    ws.cell(row=2, column=3, value="").font = Font(italic=True, color="475569", size=9)
    ws.cell(row=3, column=3, value=f"{resource.replace('_', ' ').title()} · Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}").font = Font(italic=True, color="64748B", size=9)
    if mask_pii:
        ws.cell(row=4, column=3, value="⚠ DPDP Act 2023 — PII fields are masked for the current viewer.").font = Font(italic=True, color="B45309", size=9)

    # Header row at row 5
    for j, c in enumerate(cols, start=1):
        cell = ws.cell(row=5, column=j, value=c["label"])
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="left", vertical="center")
        cell.border = border

    for i, row in enumerate(rows, start=6):
        for j, c in enumerate(cols, start=1):
            val = row.get(c["key"])
            if isinstance(val, (dict, list)):
                val = str(val)
            cell = ws.cell(row=i, column=j, value=val)
            cell.border = border
            cell.alignment = Alignment(horizontal="left", vertical="center")

    for j, c in enumerate(cols, start=1):
        ws.column_dimensions[ws.cell(row=5, column=j).column_letter].width = max(14, min(40, len(str(c["label"])) + 4))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# Narrower column subsets for PDF (landscape A4 fits ~10 columns).
# Optional "w" = column width in mm; used when every column declares one.
PDF_COLUMNS: Dict[str, List[Dict[str, Any]]] = {
    "project_resources": [
        {"key": "project_code", "label": "Proj Code", "w": 26},
        {"key": "resource_type", "label": "Type", "w": 24},
        {"key": "description", "label": "Resource / Description", "w": 62},
        {"key": "qty", "label": "Qty", "w": 18},
        {"key": "uom", "label": "UOM", "w": 16},
        {"key": "rate", "label": "Rate", "w": 22},
        {"key": "total_cost", "label": "Total", "w": 26},
        {"key": "required_by_date", "label": "Required By", "w": 24},
        {"key": "remarks", "label": "Remarks", "w": 45},
    ],
    "project_handovers": [
        {"key": "handover_no", "label": "Handover #", "w": 28},
        {"key": "project_code", "label": "Proj Code", "w": 24},
        {"key": "project_name", "label": "Project", "w": 40},
        {"key": "client_name", "label": "Client", "w": 35},
        {"key": "quotation_no", "label": "Quotation #", "w": 26},
        {"key": "contract_value", "label": "Value", "w": 24},
        {"key": "contract_start_date", "label": "Start", "w": 18},
        {"key": "contract_end_date", "label": "End", "w": 18},
        {"key": "project_manager_label", "label": "PM", "w": 30},
        {"key": "status", "label": "Status", "w": 22},
    ],
    "enquiries": [
        {"key": "enquiry_no", "label": "Enquiry #", "w": 19},
        {"key": "enquiry_date", "label": "Date", "w": 14},
        {"key": "customer", "label": "Client / Site", "w": 24},
        {"key": "site_location", "label": "Location", "w": 16},
        {"key": "rfq_type", "label": "RFQ Type", "w": 15},
        {"key": "service_categories", "label": "Services", "w": 19},
        {"key": "priority", "label": "Priority", "w": 11},
        {"key": "expected_value", "label": "Value", "w": 15},
        {"key": "submission_deadline", "label": "Deadline", "w": 14},
        {"key": "status", "label": "Status", "w": 13},
        {"key": "open_at", "label": "Opened", "w": 17},
        {"key": "submitted_at", "label": "Submitted", "w": 17},
        {"key": "won_at", "label": "Won", "w": 17},
        {"key": "quotation_no", "label": "Quote #", "w": 16},
        {"key": "order_no", "label": "Order #", "w": 16},
        {"key": "project_code", "label": "Project #", "w": 16},
    ],
}


def to_pdf(resource: str, rows: List[Dict[str, Any]], mask_pii: bool = False) -> bytes:
    if mask_pii:
        rows = [_redact_row(resource, r) for r in rows]
    cols = PDF_COLUMNS.get(resource) or COLUMNS.get(resource, [{"key": k, "label": k} for k in (rows[0].keys() if rows else [])])
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    attach_watermark(doc, width_mm=180.0)  # landscape A4 → wider watermark
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#0f172a"), spaceAfter=4)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#475569"), spaceAfter=2)
    meta_style = ParagraphStyle("meta", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#475569"))

    story = []
    # Top brand band: logo (left) + INDIAN TRADE LINKS title block
    logo_cell = ""
    try:
        if os.path.exists(BRAND_LOGO_PATH):
            logo_cell = RLImage(BRAND_LOGO_PATH, width=33 * mm, height=11.1 * mm)
    except Exception:
        logo_cell = ""
    brand_block = [
        Paragraph(f"<b>{BRAND_NAME}</b>", title_style),
        Paragraph(f"{resource.replace('_', ' ').title()} · Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} · {len(rows)} records", meta_style),
    ]
    if mask_pii:
        brand_block.append(Paragraph(
            "<font color='#b45309'>⚠ DPDP Act 2023 — Personal data is masked for the current viewer.</font>",
            meta_style,
        ))
    brand_band = Table([[logo_cell, brand_block]], colWidths=[37 * mm, 227 * mm])
    brand_band.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(brand_band)
    story.append(Spacer(1, 4 * mm))

    table_data = [[c["label"] for c in cols]]
    if resource == "enquiries":  # many columns — wrap cell text so nothing is clipped
        cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontSize=6.5, leading=8)
        for r in rows:
            table_data.append([Paragraph(str(_fmt(r.get(c["key"]))), cell_style) for c in cols])
    else:
        for r in rows:
            table_data.append([_fmt(r.get(c["key"])) for c in cols])

    col_widths = [c["w"] * mm for c in cols] if all("w" in c for c in cols) else None
    t = Table(table_data, repeatRows=1, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#ffffff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (dict, list)):
        return str(v)
    s = str(v)
    return s[:80] + "…" if len(s) > 81 else s
