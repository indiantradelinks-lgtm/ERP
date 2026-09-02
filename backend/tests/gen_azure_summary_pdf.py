"""One-off: generate the Azure Assessment Executive Summary PDF."""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

NAVY = colors.HexColor("#1E3A5F")
AMBER = colors.HexColor("#B45309")
GREY = colors.HexColor("#475569")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Title"], fontSize=16, textColor=NAVY, spaceAfter=2)
SUB = ParagraphStyle("SUB", parent=styles["Normal"], fontSize=9, textColor=GREY, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, textColor=NAVY, spaceBefore=8, spaceAfter=3)
CELL = ParagraphStyle("CELL", parent=styles["Normal"], fontSize=7.6, leading=9.6)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold")
NOTE = ParagraphStyle("NOTE", parent=styles["Normal"], fontSize=7.5, textColor=GREY, spaceBefore=6)


def tbl(rows, widths):
    data = [[Paragraph(c, CELLB) for c in rows[0]]] + [[Paragraph(str(c), CELL) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


el = [
    Paragraph("Azure Architecture Assessment — Executive Summary", H1),
    Paragraph("INDIAN TRADE LINKS ERP (\u201cWorkSite Command\u201d) · Prepared June 2026 · Verified from live environment & configuration · No secrets disclosed", SUB),

    Paragraph("1 · Current Landscape (verified)", H2),
    tbl([
        ["Area", "Current State"],
        ["Hosting", "Emergent managed Kubernetes. Preview pod: 4 vCPU / 16 GB, Debian 12. Ingress: /api → FastAPI :8001, /* → React :3000 (HTTPS). Prod: https://worksite-command.emergent.host"],
        ["Application", "React 18 SPA + FastAPI (Python 3.11, 119 routers) + in-process APScheduler (12 cron/interval jobs). Single instance per service (supervisord)."],
        ["Database", "MongoDB (Motor). Preview measured: 347 collections, ~27,183 docs, ~15.3 MB data + 12.6 MB indexes. Read-heavy OLTP + scheduled batch (payroll, exports, email)."],
        ["File Storage", "Emergent object storage (138 files ≈ 9.8 MB preview) + OneDrive mirror: push queue every 2 min, nightly DB backup 18:30 IST."],
        ["Security", "Custom JWT (httpOnly cookies) + email OTP; dynamic RBAC (resource×action, custom roles) with project/department row-level scope; full audit trail; PII masking in exports."],
        ["Network", "Public HTTPS only; no VPN/private link. Outbound: M365 SMTP :587, MS Graph (OneDrive), Emergent LLM & storage. Custom domain used for email identities only."],
        ["Integrations", "Microsoft 365 SMTP (system + personal mailboxes, Fernet-encrypted passwords) · OneDrive DMS/backup · Emergent LLM (AI quotations, bulk parsing) · Object storage."],
    ], [30 * mm, 145 * mm]),

    Paragraph("2 · Gaps to Confirm Before Sizing", H2),
    tbl([
        ["#", "Item", "Owner"],
        ["1", "Production pod specs, replica counts, autoscaling & platform SLA", "Emergent"],
        ["2", "Production DB size & 2–3 month growth baseline; request-volume metrics (no APM today)", "ITL + Emergent"],
        ["3", "Formal RPO / RTO targets (current effective RPO ≈ 24 h via nightly backup; restore runbook undefined)", "ITL business"],
        ["4", "Backup & document retention policies (currently indefinite retention, no purge)", "ITL business"],
        ["5", "Compliance scope (GST/PF/ESI statutory handled in-app; ISO/SOC/data-residency undefined)", "ITL business"],
        ["6", "Microsoft Entra ID / SSO / enforced MFA decision (auth is app-native today)", "ITL + Azure team"],
        ["7", "Custom application domain & DNS plan (Emergent subdomains in use)", "ITL IT"],
    ], [8 * mm, 132 * mm, 35 * mm]),

    Paragraph("3 · Indicative Azure Target Mapping", H2),
    tbl([
        ["Current Component", "Azure Candidate"],
        ["K8s pods (FastAPI + React)", "AKS, or Azure Container Apps / App Service"],
        ["MongoDB", "Azure Cosmos DB for MongoDB (vCore) or MongoDB Atlas on Azure"],
        ["Object storage + OneDrive mirror", "Azure Blob Storage (optionally retain OneDrive mirror)"],
        ["Ingress / TLS", "Azure Front Door or Application Gateway"],
        ["Secrets (env vars / platform Secrets)", "Azure Key Vault"],
        ["Custom JWT auth", "Retain, or migrate to Microsoft Entra ID (SSO + MFA)"],
        ["APScheduler jobs", "Retain in-process, or Azure Container Apps Jobs / Functions"],
        ["Email (M365 SMTP)", "Unchanged (Exchange Online) or Azure Communication Services"],
    ], [70 * mm, 105 * mm]),

    Paragraph("Full data sheet: /app/AZURE_ASSESSMENT.md · Architecture: /app/ARCHITECTURE.md · "
              "All credentials referenced are CONFIGURED — SECRET VALUES NOT DISCLOSED.", NOTE),
]

doc = SimpleDocTemplate("/app/frontend/public/Azure-Assessment-Executive-Summary.pdf",
                        pagesize=A4, topMargin=14 * mm, bottomMargin=12 * mm,
                        leftMargin=14 * mm, rightMargin=14 * mm,
                        title="Azure Architecture Assessment — Executive Summary")
doc.build(el)
print("PDF written")
