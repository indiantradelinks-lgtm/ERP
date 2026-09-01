# INDIAN TRADE LINKS — ERP ("WorkSite Command")
## Application Architecture Document

**Version:** June 2026 · **Stack:** FastAPI + React + MongoDB · **Deployment:** Emergent Platform (Kubernetes)

---

## 1. High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                            USERS (Browser)                             │
│   Super Admin · Director · GM · Dept Heads · PM/Manager OP · HR ·      │
│   Accounts · Sales · Safety · Store · Logistics · Employees            │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ HTTPS
                ┌──────────────▼──────────────┐
                │   Kubernetes Ingress        │
                │   /api/* → backend :8001    │
                │   /*     → frontend :3000   │
                └───────┬─────────────┬───────┘
                        │             │
        ┌───────────────▼──┐   ┌──────▼──────────────────┐
        │  REACT FRONTEND  │   │  FASTAPI BACKEND        │
        │  (CRA + Shadcn)  │   │  119 routers (modular)  │
        │  225+ pages      │   │  /api prefix, JWT auth  │
        └──────────────────┘   └──┬──────┬──────┬────────┘
                                  │      │      │
                     ┌────────────▼─┐ ┌──▼───┐ ┌▼─────────────────────┐
                     │  MongoDB     │ │Sched │ │ External Services    │
                     │  (Motor,     │ │uler  │ │ · M365 SMTP (email)  │
                     │  340+ colls) │ │(cron)│ │ · OneDrive (DMS)     │
                     └──────────────┘ └──────┘ │ · Emergent LLM (AI)  │
                                               └──────────────────────┘
```

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 (CRA + CRACO), Shadcn/UI, Tailwind CSS, Axios, lucide-react, sonner |
| Backend | FastAPI (Python 3.11), Pydantic v2, Motor (async MongoDB) |
| Database | MongoDB — 340+ collections, UUID string ids (no ObjectId in APIs) |
| Auth | JWT (httpOnly cookies), access+refresh tokens, OTP option |
| PDF Engine | ReportLab / HTML renderers (`pdf_generator.py`, `document_pdf.py`) |
| Excel | openpyxl (templates, bulk import/export) |
| Email | Microsoft 365 SMTP (per-user App Passwords + system mailboxes, e.g. noreply@indiantradelinks.in) |
| Documents | Emergent object storage + OneDrive centralized push queue |
| AI | Emergent LLM key via `emergentintegrations` (AI Quotation builder, bulk beneficiary parsing) |
| Scheduler | In-process cron (`scheduler.py`) — email queue drain, OneDrive push, DB backup, reminders |
| Process mgmt | supervisord (backend :8001, frontend :3000, MongoDB) |

## 3. Backend Architecture

### 3.1 Structure
```
/app/backend/
├── server.py                  # FastAPI app, router registration, scheduler startup
├── core.py                    # db handle, auth deps (get_current_user, require_permission)
├── access_control.py          # dynamic RBAC (roles + permission matrix from DB)
├── approval_engine.py         # multi-level approval chains (build_chain, apply_action)
├── accounting_service.py      # double-entry ledger, AR/AP aging, P&L, trial balance
├── pdf_generator.py           # payslips, POs, reports (branded PDFs)
├── m365_email.py              # SMTP transport w/ system + personal mailboxes
├── onedrive_service.py        # Graph API document sync
├── scheduler.py               # cron jobs
├── scope.py / pm_scope.py     # project/department row-level scoping
├── audit.py                   # audit log (before/after snapshots, IP)
└── routers/ (119 modules)     # feature routers, all under /api
```

### 3.2 Module Map (routers grouped by domain)

| Domain | Key Routers | Highlights |
|---|---|---|
| **Auth & Admin** | auth, users, roles, role_catalog, impersonation, admin, settings | JWT login/OTP, dynamic roles & permissions, user admin, impersonation |
| **Sales** | enquiries → quotations (quotation_builder, ai_quotation) → orders | AI Quotation Builder (LLM), condition library, win/lose pipeline, Super-Admin override edit of WON quotes |
| **Projects & Ops** | projects_ops* (11 phases), project_requests, project_expenses, ra_bills, work orders, DPR, measurements | Contract Handovers (PM allocation, admin-edit + history), Project Request Center (multi-beneficiary split), P&L per project |
| **Procurement** | procurement, purchase requisitions, RFQs, purchase_orders, GRN, vendors | PO PDF generation, vendor evaluations, GRN → vendor bill prefill (line-item GST inheritance) |
| **Accounts / Finance** | accounts, finance_phase2–10, vendor_billing, billing_pending, payment_processing, receivables | Payment Processing Center (verify → bank file → paid), AR/AP aging, dashboards with operational fallbacks, client invoices auto-synced from RA bills |
| **HR** | hr_phase1–5, employees, attendance*, payroll, advance, recruitment | Payroll (DA, attendance bonus, bulk upload w/ preview), payslip PDF + one-click email, single & bulk employee advances, attendance approval preflight |
| **Safety** | safety_* (HIRA, JSA, incidents, inspections, permits, trainings) | Registers + CAPA + audit log |
| **Store/Inventory** | inventory_phase2–5, store, materials | Stock, issues, transfers, intel dashboards |
| **Logistics** | logistics_phase1–5 | Transport vendor bills, dispatches, challans |
| **Cross-cutting** | approvals, my_inbox, notifications, exports, files, dms, email, help | Unified approval inbox, Excel/PDF export engine, file store + OneDrive, in-app notifications |

### 3.3 Cross-Cutting Concerns
- **RBAC:** every route uses `require_permission(resource, action)`; roles + custom roles (e.g. `manager_o_p`) come from DB; frontend `RouteGuard` mirrors this.
- **Row-level scope:** PM-scoped users see only their projects (`scope.py`); department heads see only their department's records.
- **Approval Engine:** configurable chains (project head → GM → Director etc.) shared by advances, requests, quotations, deployments; document gates (required attachments) enforced pre-approval.
- **Audit:** all sensitive mutations write to the audit log with before/after and IP; admin overrides carry per-field change history.
- **Exports:** central column registry (`exports.py`) drives both Excel and PDF; enrichment hooks per resource (e.g. projects gain contract dates/PM from handovers).

## 4. Frontend Architecture

```
/app/frontend/src/
├── App.js                 # 230 routes, ProtectedShell + RouteGuard
├── contexts/AuthContext   # session, role, permissions
├── lib/api.js             # axios instance → REACT_APP_BACKEND_URL/api
├── components/            # Shadcn UI + shared (MasterSelect dropdowns,
│                          #  EmployeeSearchSelect, RowAttachments, FileUploader,
│                          #  ApprovalDetail, DataTableShell…)
└── pages/ (225 pages)     # domain folders: accounts/ admin/ hr/ logistics/
                           #  ops/ procurement/ safety/ sales/ store/
```
- **Design system:** Shadcn/UI + Tailwind; data-testid on all interactive elements.
- **Dropdown masters:** centralized in `MasterSelect.jsx` (projects, clients, sites, site locations, items, POs) with per-session caching.
- **Uploads:** chunk-safe `FileUploader` → `/api/uploads` (folder allow-list) → object storage → OneDrive queue.

## 5. Data Architecture (key collections)

| Collection | Purpose |
|---|---|
| users / roles | Accounts + dynamic permission matrix |
| employees / payroll_master / payslips / attendance | HR core (payroll_master unique-indexed by employee_id) |
| employee_advances (+ batch_id) | Single & bulk advances |
| project_handovers → projects | Sales→Ops handover; PM allocation; contract dates; WO number |
| project_requests | Material/service/payment requests (multi-beneficiary children via parent_request_id) |
| quotations / enquiries / orders | Sales pipeline |
| purchase_orders / grn / vendor_bills | Procurement → payables (line-item GST) |
| ra_bills → client_invoices | Client billing (1:1 sync), Tally invoice attachments via files |
| payment_verifications | Payment Processing stages |
| journal_entries / chart_of_accounts | Double-entry ledger |
| files (+ OneDrive fields) | Central document store |
| approvals | Unified approval chains |
| email_outbox / system_mailboxes | M365 email queue + sender configs |
| audit_log | Compliance trail |

## 6. Key Workflows

1. **Sales → Project:** Enquiry → AI Quotation → Won → Contract Handover → Project Head allocation → Project (PM, contract dates, WO).
2. **Procure-to-Pay:** PR → RFQ → PO (PDF) → GRN → Vendor Bill (inherits line-item GST from PO) → Payment Processing (verify → bank file → paid) → project P&L.
3. **Bill-to-Cash:** Measurements → RA Bill → approve → invoice (auto-syncs Client Invoice) → receipts; Tally invoice attached per bill; AR aging feeds dashboards.
4. **HR:** Attendance (fill → approve) → Payroll run (preflight, DA & attendance-bonus aware, prorated by paid days) → Payslips (PDF / bulk / email-all) → advance EMI recovery.
5. **Requests & Approvals:** Project Request Center (incl. multi-employee payment split) → chain approvals → Payment Processing per beneficiary.

## 7. Integrations

| Integration | Use | Notes |
|---|---|---|
| Microsoft 365 SMTP | Payslips, billing reminders, approvals mail | System mailboxes (noreply@…) with app passwords; per-purpose senders |
| OneDrive (MS Graph) | Centralized DMS backup of all uploads + DB backups | Push queue via scheduler |
| Emergent LLM (emergentintegrations) | AI quotation parsing, bulk beneficiary extraction | Universal key |
| Emergent Object Storage | Primary file storage | `/api/uploads`, `/api/files/{id}/download` |

## 8. Environments & Deployment

- **Preview (dev):** Emergent pod — hot-reload; supervisor manages `backend :8001`, `frontend :3000`, MongoDB.
- **Production:** https://worksite-command.emergent.host — deployed via Emergent "Deploy"; env vars managed in the platform **Secrets** tab (MONGO_URL, JWT secret, M365 passwords…). Changes reach production only after **Redeploy**.
- **Config rules:** frontend always calls `REACT_APP_BACKEND_URL/api/*`; backend reads `MONGO_URL`/`DB_NAME` from env; all backend routes prefixed `/api`.

## 9. Security

- JWT in httpOnly cookies (access+refresh); OTP-capable login; impersonation with audit.
- Dynamic RBAC + route guards on both tiers; row-level project/department scoping.
- PII masking in exports for non-privileged roles; file-type & size limits on uploads.
- Full audit trail (who/when/before/after/IP) incl. Super-Admin override edits.

## 10. Operational Jobs (scheduler)

- Email outbox drain & retry (M365 throttle-aware)
- OneDrive push queue + nightly DB backup
- Pending-billing reminder emails
- Notification digests

---
*Generated June 2026. Companion docs: `/app/memory/PRD.md` (requirements & changelog), `/app/memory/test_credentials.md` (test accounts).*
