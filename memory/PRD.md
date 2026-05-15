# Corporate ERP - PRD

## Original Problem Statement
Modern cloud-based Corporate ERP for Service Industry Company (Scaffolding, Painting, Roof Sheeting, Rope Access, Industrial Shutdown & Maintenance). Enterprise-level, secure, multi-client, role-based, single-window dashboard for higher management, 14+ modules, mobile responsive.

## Architecture
- Frontend: React 19 + Shadcn UI + Tailwind + Recharts + qrcode.react (Chivo / IBM Plex Sans)
- Backend: FastAPI + Motor (MongoDB) + JWT auth (bcrypt + httpOnly cookies) + openpyxl/reportlab for exports
- Theme: Industrial slate/steel + amber/orange accent, dark default + light, PWA-ready

## Roles (RBAC) — Granular per-resource enforcement
super_admin, director, general_manager, dept_head, project_manager, site_engineer, supervisor, store_incharge, accounts_executive, hr_executive, safety_officer, purchase_officer, client_rep, vendor.
Permission map in `/app/backend/rbac.py` — read/write/delete per resource. Sidebar nav and table CRUD buttons hide automatically per role; backend returns 403 on disallowed actions.

## Implemented

### Iteration 1 (Feb 2026)
- JWT auth with admin seed, brute force protection
- Executive Dashboard with KPIs + charts (revenue/expense, project status, attendance, safety)
- 14 module pages with CRUD: Clients, Vendors, Employees, Attendance, Projects, Inventory, Purchase Orders, Quotations, Accounts (Journal), Safety Reports, Assets, Payroll, Logistics (Vehicles), Documents
- Approvals queue (basic), Reports landing, Profile, Landing page, Login
- Sample data seeding on startup if collections empty

### Iteration 2 (May 2026)
- **P0 RBAC**: per-resource permission map enforced on every endpoint via `require_permission(resource, action)`; `/api/auth/permissions` exposes the current user's permission map to the frontend; sidebar nav filters by perm; CRUD action buttons hide when user lacks write/delete.
- **P1 Approval chains + history**: 6 chain templates (purchase_order, leave, capex, expense, vendor, quotation). New approvals auto-attach the chain. `/api/approvals/{id}/action` advances chain, records history with `by/role/at/comment`. Approval Detail dialog shows visual chain timeline + activity feed; approve/reject buttons gated by current step's required role (super_admin bypass). Migration backfills legacy approval docs.
- **P1 Excel & PDF exports**: `/api/export/{resource}.{xlsx|pdf}` (openpyxl + reportlab). Excel/PDF icon buttons in every module table header + Reports page Run/PDF/Excel buttons trigger downloads.
- **P1 Dashboard drill-downs**: KPI cards + sub-cards clickable, navigate to relevant module page.
- **P2 Inventory QR**: each item has a QR-code label dialog (qrcode.react) with Print button.
- **P2 PWA polish**: manifest.json, theme-color, apple-mobile-web-app meta tags, installable on mobile.

## Test Results
- Iteration 1: 35/35 backend, 100% frontend
- Iteration 2: 53/53 backend (18 new + 35 regression), 100% frontend

## Credentials
See `/app/memory/test_credentials.md` — admin@erp.com / Admin@123

## Backlog
### Pending user-provided keys (deferred)
- **Object storage** — AWS S3 / Cloudinary for Document Management upload + Safety photo upload
- **Email notifications via Resend** — invoice reminders, expiry alerts, approval pings

### Future iterations (P2+)
- WhatsApp notifications (Twilio)
- Live GPS tracking integration
- Native mobile shell (React Native)
- Granular field-level audit log explorer
- Reports: drill-into-data and pivot views
- Multi-tenant / multi-company support
