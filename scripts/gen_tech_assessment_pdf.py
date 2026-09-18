"""One-off: generate the ERP Technical Assessment PDF (read-only measurement report)."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

NAVY = colors.HexColor("#1E3A5F")
GREY = colors.HexColor("#475569")
LINE = colors.HexColor("#CBD5E1")

s = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=s["Title"], fontSize=16, textColor=NAVY, spaceAfter=2)
SUB = ParagraphStyle("SUB", parent=s["Normal"], fontSize=8.4, textColor=GREY, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=s["Heading2"], fontSize=11, textColor=NAVY, spaceBefore=10, spaceAfter=4)
CELL = ParagraphStyle("CELL", parent=s["Normal"], fontSize=7.4, leading=9.4)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold")
VAL = ParagraphStyle("VAL", parent=CELL, fontName="Helvetica-Bold", textColor=NAVY)
NOTE = ParagraphStyle("NOTE", parent=s["Normal"], fontSize=7.4, textColor=GREY, spaceBefore=6, leading=9.6)


def tbl(rows, widths, header=True):
    data = ([[Paragraph(c, CELLB) for c in rows[0]]] if header else []) + [
        [Paragraph(str(c), VAL if (i == 1 and header) else CELL) for i, c in enumerate(r)]
        for r in (rows[1:] if header else rows)
    ]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY if header else colors.white),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if header else colors.black),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


W = [46 * mm, 55 * mm, 88 * mm]

main_rows = [
    ["Requirement", "Actual / Estimated Value", "Details / Source"],
    ["1 · Number of applications to be assessed",
     "1 application = 2 deployable code services + 1 database<br/>(11 functional departments · 123 backend router modules · 235 frontend page files · 239 SPA routes · 333 menu entries)",
     "Single monorepo, single FastAPI process (<font face='Courier'>backend/server.py</font>, uvicorn :8001) + one React SPA (CRA/craco :3000) + MongoDB. No microservices — <font face='Courier'>routers_registry.py</font> logs \u201cRegistered 123 module routers\u201d into one ASGI app; APScheduler (15 scheduled jobs) runs in-process. Supervisor app programs: backend, frontend, mongodb (code-server / nginx-proxy / webhook-crond are tooling). Departments (menuConfig.js): dashboard, sales, ops, procurement, store, logistics, hr, safety, accounts, finance, admin."],
    ["2 · Application code repository / location",
     "Emergent-managed Git repository (local to the Emergent workspace) \u2014 NO external remote configured",
     "<font face='Courier'>git remote -v</font> returns empty; branch <font face='Courier'>main</font>, 250 commits, pack size 4.29 MiB. No GitHub / GitLab / Bitbucket / Azure DevOps remote exists. Code lives at <font face='Courier'>/app</font> in the Emergent workspace (checkpoint per step + rollback). Mirroring requires the \u201cSave to GitHub\u201d action. Production: worksite-command.emergent.host · Preview: worksite-command.preview.emergentagent.com"],
    ["3 · Approximate application size (LOC)",
     "Total own code \u2248 150,000 LOC physical (\u2248 134,000 non-blank / non-comment)<br/><br/>Backend (Python): 74,410 LOC / 168 files<br/>Frontend (JSX/JS/CSS): 75,157 LOC / 300 files<br/>Build &amp; config: \u2248 521 LOC<br/><br/>Automated tests (excluded above): 37,067 LOC / 175 files<br/>Grand total incl. tests \u2248 188,000 LOC",
     "Measured with <font face='Courier'>find \u2026 | xargs wc -l</font>, excluding node_modules, __pycache__, yarn.lock, .ruff_cache, build output and the generated shadcn-ui scaffold (46 files / 2,862 LOC). Non-blank/non-comment: backend 63,252 · frontend 70,716. Frontend split: .jsx 76,113 · .js 1,749 · .css 157 (incl. ui scaffold). No DB-side code / stored procedures (MongoDB, schema-less)."],
    ["4a · Number of APIs (own REST surface)",
     "1,599 REST operations across 1,602 /api routes and 119 tag groups<br/><br/>GET 707 · POST 507 · PUT 120 · DELETE 96 · PATCH 8 (1,438 explicit decorators) + 161 auto-generated CRUD operations (23 collections)",
     "Counted at runtime by importing <font face='Courier'>server.app</font> and enumerating <font face='Courier'>app.routes</font> (method+path pairs), cross-checked with <font face='Courier'>grep '@router.&lt;verb&gt;'</font>. Every route is /api-prefixed and RBAC-guarded via <font face='Courier'>require_permission</font>. Largest groups: crud 115, hr 106, service-workflow 38, procurement 36, projects-ops 35, admin 33, logistics 33, vendor-billing 30."],
    ["4b · Number of external integrations",
     "7 external integrations (+ internal auth; no payment gateway)",
     "1. <b>MongoDB</b> \u2014 Motor 3.3.1 / pymongo via MONGO_URL; 357 collections, \u2248 30,222 documents (preview).<br/>2. <b>Microsoft 365 Exchange SMTP</b> \u2014 m365_email.py, M365_SMTP_*, per-user app passwords encrypted with Fernet.<br/>3. <b>Microsoft Graph API + MSAL 1.36</b> \u2014 onedrive_service.py: OneDrive document push queue (2 min) + nightly DB backup 18:30 IST (login.microsoftonline.com, graph.microsoft.com).<br/>4. <b>Resend Email API</b> \u2014 notification_service.py, RESEND_API_KEY.<br/>5. <b>Emergent LLM gateway</b> \u2014 emergentintegrations LlmChat (OpenAI / Anthropic / Gemini) in 5 routers: AI quotation, attendance bulk parse, email actions, project-request beneficiary parse, HR documents.<br/>6. <b>Emergent managed object storage</b> \u2014 storage.py \u2192 integrations.emergentagent.com/objstore for all uploads.<br/>7. <b>OpenStreetMap tile service</b> \u2014 react-leaflet in ClientMap.jsx."],
    ["Authentication service",
     "Internal JWT + bcrypt (no external IdP)",
     "PyJWT 2.12 / passlib / bcrypt, httpOnly cookie sessions, JWT_SECRET; role register in rbac.py (62 role-override entries). No Azure AD/Entra, Google or Auth0 login integration today."],
    ["Payment / SMS / WhatsApp gateways",
     "None",
     "No Stripe, Razorpay, Paystack, PayPal, Twilio, SendGrid or WhatsApp code in backend/ (only a <font face='Courier'>whatsapp</font> contact field on clients). Bank payments are handled as generated bank files + manual UTR capture."],
    ["Third-party libraries (context, not counted as LOC)",
     "54 frontend prod deps / 15 dev deps · 145 Python packages",
     "frontend/package.json: React 19, Radix UI, axios, recharts, react-leaflet, lucide-react. backend/requirements.txt: FastAPI 0.110, uvicorn, motor, openpyxl, reportlab, pandas, APScheduler, msal, resend, emergentintegrations."],
]

na_rows = [
    ["Item", "Status", "What is required to obtain it"],
    ["Production infrastructure sizing \u2014 pod/VM specs, replica count, DB topology, autoscaling, SLA / RPO / RTO",
     "Not Available",
     "Not visible from the codebase \u2014 the production plane is Emergent-managed. Requires confirmation from Emergent platform/support for the deployed app. A prior assessment of the same scope exists at <font face='Courier'>/app/AZURE_ASSESSMENT.md</font> (June 2026) and marks these items \u201cTO BE CONFIRMED\u201d."],
    ["Request / transaction volume, APM metrics",
     "Not Available",
     "No APM or metrics instrumentation in the code. Requires enabling request telemetry (or platform logs/analytics) for 2\u20134 weeks to baseline."],
    ["External-consumer API contracts (who calls this ERP)",
     "Not Available / none found",
     "The API is consumed only by its own SPA \u2014 no public API keys, inbound webhooks or partner clients are defined in the code. Inbound integration requirements must come from the business."],
    ["Production database size &amp; growth rate",
     "Not Available (preview measured: 357 collections, \u2248 30,222 documents)",
     "Preview pod figures only. Production DB size/growth requires access to the production MongoDB (Emergent-managed)."],
]

def build_elements():
    return [
        Paragraph("ERP Technical Assessment \u2014 Codebase Measurement Report", H1),
        Paragraph("INDIAN TRADE LINKS ERP (\u201cWorkSite Command\u201d) \u00b7 Prepared 18 June 2026 \u00b7 Source: direct read-only measurement of the live Emergent workspace at commit 4a03587 (250 commits, branch main) \u00b7 No code was modified \u00b7 No secrets disclosed", SUB),
        Paragraph("Assessment Summary", H2),
        tbl(main_rows, W),
        Spacer(1, 8),
        Paragraph("Items that cannot be determined from the codebase", H2),
        tbl(na_rows, W),
        Paragraph(
            "<b>Method &amp; reproducibility:</b> API counts were produced by importing the FastAPI application and enumerating its route table "
            "(unique METHOD+path pairs), cross-checked against decorator counts. LOC was measured with <font face='Courier'>wc -l</font> over "
            "source files with explicit exclusion of dependencies (node_modules, site-packages), caches (__pycache__, .ruff_cache), lockfiles, "
            "build output and the generated shadcn-ui component scaffold. Integrations were identified from imports, outbound URLs and environment "
            "keys (msal, smtplib, resend, emergentintegrations, integrations.emergentagent.com, tile.openstreetmap.org). "
            "Figures are point-in-time and will drift as development continues.", NOTE),
    ]


for out in ("/app/ERP-Technical-Assessment.pdf", "/app/frontend/public/ERP-Technical-Assessment.pdf"):
    SimpleDocTemplate(out, pagesize=A4, leftMargin=10 * mm, rightMargin=10 * mm,
                      topMargin=12 * mm, bottomMargin=12 * mm,
                      title="ERP Technical Assessment \u2014 INDIAN TRADE LINKS",
                      author="INDIAN TRADE LINKS ERP").build(build_elements())
    print("written:", out)
