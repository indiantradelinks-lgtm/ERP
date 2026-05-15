"""Multi-level approval workflow engine: chain definitions + step helpers."""
from datetime import datetime, timezone
from typing import List, Dict, Any

# Each chain is an ordered list of approver roles.
APPROVAL_CHAINS: Dict[str, List[Dict[str, str]]] = {
    "purchase_order": [
        {"role": "dept_head", "label": "Department Head"},
        {"role": "purchase_officer", "label": "Purchase Manager"},
        {"role": "accounts_executive", "label": "Finance"},
        {"role": "director", "label": "Director"},
    ],
    "leave": [
        {"role": "supervisor", "label": "Supervisor"},
        {"role": "dept_head", "label": "Department Head"},
        {"role": "hr_executive", "label": "HR"},
    ],
    "capex": [
        {"role": "dept_head", "label": "Department Head"},
        {"role": "accounts_executive", "label": "Finance"},
        {"role": "general_manager", "label": "GM"},
        {"role": "director", "label": "Director"},
    ],
    "expense": [
        {"role": "supervisor", "label": "Supervisor"},
        {"role": "accounts_executive", "label": "Finance"},
    ],
    "vendor": [
        {"role": "purchase_officer", "label": "Purchase Manager"},
        {"role": "accounts_executive", "label": "Finance"},
        {"role": "director", "label": "Director"},
    ],
    "quotation": [
        {"role": "dept_head", "label": "Department Head"},
        {"role": "director", "label": "Director"},
    ],
}


def build_chain(approval_type: str) -> List[Dict[str, Any]]:
    template = APPROVAL_CHAINS.get(approval_type, [
        {"role": "dept_head", "label": "Department Head"},
        {"role": "director", "label": "Director"},
    ])
    return [{**step, "status": "pending", "approver": None, "at": None, "comment": None} for step in template]


def current_step(approval: dict) -> Dict[str, Any] | None:
    chain = approval.get("chain") or []
    idx = approval.get("current_step", 0)
    return chain[idx] if 0 <= idx < len(chain) else None


def apply_action(approval: dict, action: str, user: dict, comment: str | None = None) -> dict:
    chain = list(approval.get("chain") or [])
    idx = int(approval.get("current_step", 0))
    history = list(approval.get("history") or [])

    if approval.get("status") not in (None, "pending", "in_progress"):
        raise ValueError(f"Approval is already {approval.get('status')}")

    if idx >= len(chain):
        raise ValueError("Approval chain already exhausted")

    step = chain[idx]
    now = datetime.now(timezone.utc).isoformat()

    # Allow super_admin to act on any step, otherwise enforce role match
    if user.get("role") != "super_admin" and user.get("role") != step.get("role"):
        raise PermissionError(f"Only role '{step['role']}' can act on this step")

    record = {
        "step_index": idx,
        "step_label": step.get("label"),
        "step_role": step.get("role"),
        "action": action,
        "by": user.get("name") or user.get("email"),
        "by_role": user.get("role"),
        "by_id": user.get("id"),
        "comment": comment,
        "at": now,
    }
    history.append(record)

    if action == "reject":
        step["status"] = "rejected"
        step["approver"] = record["by"]
        step["at"] = now
        step["comment"] = comment
        chain[idx] = step
        approval["status"] = "rejected"
    elif action == "approve":
        step["status"] = "approved"
        step["approver"] = record["by"]
        step["at"] = now
        step["comment"] = comment
        chain[idx] = step
        idx += 1
        if idx >= len(chain):
            approval["status"] = "approved"
        else:
            approval["status"] = "in_progress"
    elif action == "comment":
        # Comments don't advance the chain; just keep status as-is.
        if not approval.get("status"):
            approval["status"] = "pending"
    else:
        raise ValueError(f"Unknown action '{action}'")

    approval["chain"] = chain
    approval["current_step"] = idx
    approval["history"] = history
    approval["updated_at"] = now
    return approval
