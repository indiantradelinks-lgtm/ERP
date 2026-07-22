#!/usr/bin/env python3
import json
import requests

API='http://localhost:8001/api'
s=requests.Session()
r=s.post(f'{API}/auth/login', json={'email':'admin@erp.com','password':'Admin@123'}, timeout=20)
r.raise_for_status()
access=s.cookies.get('access_token')
if access:
    s.headers.update({'Authorization': f'Bearer {access}'})
rows=s.get(f'{API}/ops/handovers', timeout=30)
rows.raise_for_status()
h=next((x for x in rows.json() if x.get('id')=='4a16236b-68bd-45d4-b0a3-6b08f54d98ec'), None)
print(json.dumps({
    'handover_id': h.get('id') if h else None,
    'project_code': h.get('project_code') if h else None,
    'project_manager_id': h.get('project_manager_id') if h else None,
    'project_manager_label': h.get('project_manager_label') if h else None,
    'allocation_cell_will_render': (h.get('project_manager_label') if h and h.get('project_manager_label') else (h.get('project_manager_id') or '')[:6] if h else None)
}, indent=2))
if not h:
    raise SystemExit('target handover not found')
if h.get('project_manager_label') != 'Test PM':
    raise SystemExit('FAIL: /api/ops/handovers list missing project_manager_label=Test PM')
