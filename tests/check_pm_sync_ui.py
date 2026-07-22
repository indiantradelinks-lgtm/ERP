#!/usr/bin/env python3
import json
import os
from pathlib import Path

import requests

BASE = os.environ.get('TEST_FRONTEND_BASE', 'https://worksite-command.preview.emergentagent.com')
API = f"{BASE}/api"
OUT = Path('/app/test_reports/pm_sync_ui_api_probe.json')

s = requests.Session()
r = s.post(f"{API}/auth/login", json={'email':'admin@erp.com','password':'Admin@123'}, timeout=30)
r.raise_for_status()
# HTTPS preview cookies are usable directly; also set bearer fallback for deterministic local proxy behavior.
if s.cookies.get('access_token'):
    s.headers.update({'Authorization': f"Bearer {s.cookies.get('access_token')}"})
projects = s.get(f"{API}/projects", timeout=30)
projects.raise_for_status()
rows = projects.json()
row = next((p for p in rows if p.get('code') == 'PRJ-2026-0035' or p.get('id') == '147f9689-ff9d-421a-9f7b-69e5dae8800e'), None)
if not row:
    raise SystemExit('PRJ-2026-0035 not found from frontend API base')
result = {
    'frontend_base': BASE,
    'api_base': API,
    'project_code': row.get('code'),
    'project_id': row.get('id'),
    'project_manager_id': row.get('project_manager_id'),
    'project_manager_name': row.get('project_manager_name'),
    'manager_render_source': row.get('project_manager_name') or row.get('manager') or '—',
    'ui_code_contract': 'Projects.jsx Manager column renders project_manager_name || manager || —',
}
print(json.dumps(result, indent=2))
OUT.write_text(json.dumps(result, indent=2))
if result['manager_render_source'] == '—':
    raise SystemExit('Manager render source is dash')
