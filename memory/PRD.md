# Corporate ERP - PRD

## Original Problem Statement
Modern cloud-based Corporate ERP for Service Industry Company (Scaffolding, Painting, Roof Sheeting, Rope Access, Industrial Shutdown & Maintenance). Enterprise-level, secure, multi-client, role-based, single-window dashboard for higher management, 14+ modules, mobile responsive.

## Architecture
- Frontend: React 19 + Shadcn UI + Tailwind + Recharts (Chivo / IBM Plex Sans)
- Backend: FastAPI + Motor (MongoDB) + JWT auth (bcrypt + httpOnly cookies)
- Theme: Industrial slate/steel + amber/orange accent, dark default + light

## Roles (RBAC)
super_admin, director, general_manager, dept_head, project_manager, site_engineer, supervisor, store_incharge, accounts_executive, hr_executive, safety_officer, purchase_officer, client_rep, vendor

## Implemented (Feb 2026)
- JWT auth with admin seed, RBAC scaffolding, brute force protection
- Executive Dashboard with KPIs + charts (revenue/expense, project status, attendance, safety)
- 14 module pages with CRUD: Clients, Vendors, Employees, Attendance, Projects, Inventory, Purchase Orders, Quotations, Accounts (Journal), Safety Reports, Assets, Payroll, Logistics (Vehicles), Documents
- Approvals queue, Reports landing, Profile
- Landing page, Login, Protected layout with sidebar + topbar, dark/light theme toggle
- Sample data seeding on startup if collections empty

## Backlog / Next (P0/P1)
- P0: OTP login real integration (Twilio), Email notifications (Resend)
- P0: Granular RBAC enforcement per module
- P1: Approval workflow engine (multi-level chains, history)
- P1: Reports export (PDF/Excel), drill-downs
- P1: Document upload to object storage
- P2: WhatsApp notifications, GPS tracking, barcode/QR for inventory
- P2: Mobile app native shell

## Credentials
See `/app/memory/test_credentials.md`
