# ERP Fixes — Summary of Changes

Simple explanation of what was changed, why, and the result.
All changes were tested against live data and the app builds cleanly.

---

## 1. Duplicate projects on the dashboard

**Why:** The Project Dashboard showed the same project many times (e.g. "ONGC — Project" 3 times).

**What I did:**
- Added a safety filter so the dashboard never shows the same project twice.
- Fixed the cause: when a Won enquiry becomes an order, it no longer creates a duplicate project, and auto-named projects now get a unique, readable name.
- Cleaned the existing duplicates: merged them into one project each and moved all linked records (orders, enquiries, etc.) onto the kept project. A full backup was taken first.

**Result:** Dashboard now shows **16 real projects, zero duplicates**.

---

## 2. Missing "Site" dropdown in Purchase Requisitions

**Why:** When creating a PR, the Site field always said "No sites for project".

**What I did:** Sites are linked to clients, not projects. Fixed the backend to find the project's client and show that client's sites, and fixed the form to read the correct site fields.

**Result:** The Site dropdown now lists the right sites for the chosen project.

---

## 3. Free-text fields that should be dropdowns

**Why:** Many forms let you type Client, Project, Site, PO, Item by hand instead of picking from the master lists. This caused typos and wrong/duplicate data.

**What I did:**
- Built one shared set of dropdown components (Project / Site / Client / Category / Item / PO) that pull from the existing master databases.
- Replaced the free-text boxes with these dropdowns in: RA Bills, Material/Asset Allocation, DPRs, Store/Inventory, HR, Accounts, and Ops screens.
- Left genuinely free-text fields (like "Location", which has no master list) as they were, to avoid breaking documents.

**Result:** Across the system, these fields now come from the correct master data. Saved values keep working everywhere (tables, search, printing).

---

## 4. User accounts could be created for anyone

**Why:** A login could be created for any name/email, even people not in the Employee List.

**What I did:**
- The "Create User" form now requires picking a **registered employee**; it auto-fills their name/email.
- The backend rejects any account whose employee is not in the Employee List (or has left the company).
- Existing users and logins are untouched — the rule only applies to **new** accounts.

**Result:** New logins can only be made for real, registered employees.

---

## 5. Dashboard showed all projects to everyone

**Why:** The Project Dashboard listed every project to any user. A project manager should only see the projects assigned to them.

**What I did:**
- The dashboard now filters projects by assignment: a **project manager / project coordinator** sees only projects where they are the project manager, coordinator, or reporting manager.
- **Admins (super admin, director, general manager)** and other roles keep full visibility.
- Also locked the project detail page — opening a project you are not assigned to is blocked (403), not just hidden from the list.
- No data was changed; projects show up for a manager once they are assigned (done in the Projects/Operations module).

**Result:** Each project manager now sees only their own projects; managers/admins still see everything.

---

## Safety notes
- No existing feature was broken; each change was checked and the app compiles cleanly.
- The duplicate-data cleanup was the only step that changed data — it was approved first, done with a backup, and verified (0 orphaned records).
- Backup of deleted/merged data: `backend/scripts/phase7_backup_<timestamp>.json`.
