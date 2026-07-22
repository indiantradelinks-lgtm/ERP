# Focused PM Sync Bug Verification Plan

User-reported bug: Project Manager assigned in Contract Handovers is not appearing in Projects Master → Manager field; assigned manager must automatically sync, save, and display across related modules.

No relevant testing skill found.

Affected flow:
1. Admin allocates/reallocates Project Manager in Contract Handovers (`POST /api/ops/handovers/{hid}/allocate`).
2. Backend persists PM id/name to linked project (`GET /api/projects/{project_id}`).
3. Projects Master UI (`/app/projects`) Manager column displays PM name.
4. PM-scoped modules (`GET /api/projects`, `GET /api/ops/my-projects`, handover list) show the assigned project/labels.

Code to inspect:
- `/app/backend/routers/projects_ops_router.py` allocate/backfill logic.
- `/app/backend/server.py` startup backfill hook.
- `/app/frontend/src/pages/Projects.jsx` Manager column rendering.
- Recent git status/diff.

Proof needed for fixed:
- Reallocate real handover `4a16236b-68bd-45d4-b0a3-6b08f54d98ec` to real PM id `f4abf031-9eaa-4fdb-bba8-8828fdc4f467`; endpoint returns ok and project `147f9689-ff9d-421a-9f7b-69e5dae8800e` has both `project_manager_id` and non-empty `project_manager_name`.
- Projects UI row for `PRJ-2026-0035` shows `Test PM` in Manager column, not `—`.
- First allocation (submitted/under_review + project_id) syncs on first allocate, not only reassignment. If no suitable row exists, create disposable linked handover/project test data and clean it up.
- Invalid project_manager_id returns 400 with the specified message and does not overwrite project manager fields.
- Admin project list has no rows with project_manager_id and blank project_manager_name.
- test_pm sees assigned project via `/api/projects` and `/api/ops/my-projects`; handovers list includes PM label.
- Allocation notification/email path does not crash endpoint.

Important edge cases:
- Dangling assignee id guard.
- First allocation with linked project.
- PM scoped visibility after sync.
- UI/backend consistency after page refresh/navigation.
