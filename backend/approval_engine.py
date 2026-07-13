"""Multi-level approval workflow engine: chain definitions + step helpers.

Iter 50 — Closed-Loop Revision Cycle
====================================
Statuses
--------
- ``pending``                       : created, waiting for level-1 approver
- ``in_progress``                   : at least one step approved; more remain
- ``approved``                      : all steps approved (terminal — happy path)
- ``rejected_revision_required``    : an approver rejected; bounced back to the originator
                                      for correction & re-submission (NOT terminal)
- ``additional_info_required``      : an approver requested extra docs/clarification;
                                      bounced back to the originator (NOT terminal)
- ``resubmitted``                   : originator pushed a revised version; chain is
                                      restarted (or resumed at the rejected step,
                                      per admin config) → status flips to ``pending``
                                      or ``in_progress`` immediately
- ``rejected``                      : LEGACY status — kept for back-compat with rows
                                      created before Iter 50. New rejects use
                                      ``rejected_revision_required``.
- ``cancelled``                     : originator/admin abandoned the request

Actions on POST /api/approvals/{id}/action
------------------------------------------
- ``approve``       : advance to next step (or finalise)
- ``reject``        : status → ``rejected_revision_required`` (min 5-char comment required)
- ``request_info``  : status → ``additional_info_required`` (min 5-char comment + optional
                      ``required_documents[]`` + ``deadline``)
- ``comment``       : annotation only, no status change

Resubmit cycle (creator-only)
-----------------------------
- POST /api/approvals/{id}/resubmit  body: { comment, file_ids[]? }
- Bumps ``version`` (semver-ish minor bump v1.0→v2.0); resets chain steps' status
  to ``pending``; resets ``current_step`` to 0 OR to the rejected index based on
  admin setting ``approval_workflow.restart_on_resubmit`` (default ``True``).
- Appends a ``resubmit`` history entry tagged with version + file_ids.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from core import db

# Each chain is an ordered list of approver roles. These are the built-in defaults;
# the admin "Approval Matrix" editor (collection `approval_chains`) can override any
# of these entries at runtime via build_chain() looking up the DB first.
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
    "department_move": [
        {"role": "dept_head", "label": "Department Head"},
        {"role": "hr_executive", "label": "HR"},
    ],
    "deployment": [
        {"role": "project_manager", "label": "Project Manager"},
        {"role": "dept_head", "label": "Operations Head"},
    ],
    "client_onboarding": [
        {"role": "sales_executive", "label": "Sales"},
        {"role": "accounts_executive", "label": "Finance"},
        {"role": "director", "label": "Director"},
    ],
    # Iter 60 — Projects & Operations Workflow
    "project_handover": [
        {"role": "dept_head", "label": "Project Head / Department Head"},
    ],
    "resource_request": [
        {"role": "project_manager", "label": "Project Manager"},
        {"role": "dept_head", "label": "Department Head"},
    ],
    "purchase_requisition": [
        {"role": "dept_head", "label": "Department Head"},
        {"role": "project_manager", "label": "Project Manager"},
        {"role": "purchase_officer", "label": "Procurement Head"},
        {"role": "accounts_executive", "label": "Finance"},
        {"role": "director", "label": "Management"},
    ],
    "rfq": [
        {"role": "purchase_officer", "label": "Procurement Head"},
        {"role": "director", "label": "Director"},
    ],
    "grn": [
        {"role": "store_incharge", "label": "Store"},
        {"role": "purchase_officer", "label": "Procurement"},
    ],
    "employee_advance": [
        {"role": "project_manager", "label": "Reporting Manager / Project Coordinator"},
        {"role": "dept_head", "label": "Department Head"},
        {"role": "hr_executive", "label": "HR"},
        {"role": "accounts_executive", "label": "Accounts"},
        {"role": "general_manager", "label": "Finance Head"},
        {"role": "director", "label": "Director"},
    ],
}


async def get_chain_template(approval_type: str) -> List[Dict[str, str]]:
    """Resolve chain template: DB-override first, fall back to module defaults."""
    row = await db.approval_chains.find_one({"type": approval_type}, {"_id": 0})
    if row and row.get("steps"):
        return [{"role": s["role"], "label": s.get("label", s["role"])} for s in row["steps"]]
    return APPROVAL_CHAINS.get(approval_type, [
        {"role": "dept_head", "label": "Department Head"},
        {"role": "director", "label": "Director"},
    ])


def build_chain_sync(template: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    return [{**step, "status": "pending", "approver": None, "at": None, "comment": None} for step in template]


async def build_chain(approval_type: str) -> List[Dict[str, Any]]:
    template = await get_chain_template(approval_type)
    return build_chain_sync(template)


# ─── Iter 63 · Universal Approval Documents Gate ─────────────────────────
# Every approval insert MUST go through insert_approval() so the documents
# policy is enforced uniformly:
#   • At least 1 reference document, OR
#   • documents_not_required=True with a reason ≥5 chars.
#
# A "document" is any of:
#   - newly uploaded file_id   (the caller already POST'd it to /api/uploads)
#   - linked record attachment (file_id already lives on db.files for the parent record)
#
# Field shape stored on db.approvals:
#   documents: List[{file_id, name, source: "upload"|"linked", url?: str}]
#   documents_not_required: bool
#   documents_not_required_reason: Optional[str]
#
# Per-step "request_info" continues to use the existing `required_documents`
# field on the chain step — orthogonal to this submission-time gate.
class ApprovalDocumentsRequired(Exception):
    """Raised when an approval doc fails the universal documents gate."""
    pass


def _normalise_documents_payload(approval_doc: dict) -> dict:
    """Mutate-in-place: coerce documents/linked_attachments into the
    canonical `documents` array and validate the gate.

    Accepts the following SHAPES on input (whichever the caller supplies):
      • documents: list[str | dict]      — newly uploaded file_ids or {file_id,name}
      • linked_attachments: list[str]    — existing file_ids on the record
      • documents_not_required: bool
      • documents_not_required_reason: str

    Returns the same dict for chaining."""
    raw_docs = approval_doc.pop("documents", []) or []
    linked = approval_doc.pop("linked_attachments", []) or []
    nr_flag = bool(approval_doc.get("documents_not_required") or False)
    nr_reason = (approval_doc.get("documents_not_required_reason") or "").strip()

    normalised: List[Dict[str, Any]] = []
    for d in raw_docs:
        if isinstance(d, str):
            normalised.append({"file_id": d, "source": "upload"})
        elif isinstance(d, dict) and (d.get("file_id") or d.get("id")):
            normalised.append({
                "file_id": d.get("file_id") or d.get("id"),
                "name": d.get("name"),
                "url": d.get("url"),
                "source": d.get("source") or "upload",
            })
    for fid in linked:
        if isinstance(fid, str) and fid:
            normalised.append({"file_id": fid, "source": "linked"})

    has_docs = len(normalised) > 0
    if not has_docs and not nr_flag:
        raise ApprovalDocumentsRequired(
            "Reference documents are required for this approval. "
            "Attach at least one file or mark 'Not Applicable' with a reason."
        )
    if nr_flag and len(nr_reason) < 5:
        raise ApprovalDocumentsRequired(
            "Please provide a short reason (min 5 characters) for marking documents as Not Applicable."
        )

    approval_doc["documents"] = normalised
    approval_doc["documents_not_required"] = nr_flag
    approval_doc["documents_not_required_reason"] = nr_reason if nr_flag else None
    return approval_doc


async def insert_approval(approval_doc: dict, *, skip_gate: bool = False) -> dict:
    """Universal approval insertion with the documents gate enforced.

    Args:
        approval_doc: the approval dict to insert (mutated in-place to
                      normalise the documents fields).
        skip_gate:    bypass the gate (only for legacy migrations / tests).

    Raises:
        ApprovalDocumentsRequired (caught by the FastAPI handler and turned
        into a 400 with the user-facing message).
    """
    if not skip_gate:
        _normalise_documents_payload(approval_doc)
    else:
        # Still normalise the shape so the read API is uniform
        approval_doc.setdefault("documents", [])
        approval_doc.setdefault("documents_not_required", False)
        approval_doc.setdefault("documents_not_required_reason", None)
    await db.approvals.insert_one(approval_doc)
    approval_doc.pop("_id", None)
    return approval_doc


# Caller convenience: copy the 4 docs fields from a request body / Pydantic
# model onto the approval doc that's about to be inserted.
APPROVAL_DOC_FIELDS = (
    "documents", "linked_attachments",
    "documents_not_required", "documents_not_required_reason",
)


def copy_approval_doc_fields(approval_doc: dict, source) -> dict:
    """Mutate approval_doc in place — pull the 4 approval-docs fields from
    `source` (a dict or a Pydantic BaseModel) onto the approval doc.
    Missing fields are left alone so insert_approval()'s gate can decide."""
    if source is None:
        return approval_doc
    if hasattr(source, "model_dump"):
        src = source.model_dump(exclude_unset=False)
    elif isinstance(source, dict):
        src = source
    else:
        try:
            src = dict(source)
        except Exception:
            return approval_doc
    for k in APPROVAL_DOC_FIELDS:
        if k in src and src[k] is not None:
            approval_doc[k] = src[k]
    return approval_doc




def current_step(approval: dict) -> Dict[str, Any] | None:
    chain = approval.get("chain") or []
    idx = approval.get("current_step", 0)
    return chain[idx] if 0 <= idx < len(chain) else None


def apply_action(approval: dict, action: str, user: dict, comment: str | None = None,
                 required_documents: Optional[List[str]] = None,
                 deadline: Optional[str] = None) -> dict:
    chain = list(approval.get("chain") or [])
    idx = int(approval.get("current_step", 0))
    history = list(approval.get("history") or [])
    version = approval.get("version") or "1.0"

    # An approval is "open" when it's at the start, mid-chain, or has been bounced
    # back to the originator for revision / info — in all of these states an approver
    # can still act once the revision is resubmitted (status flips back).
    OPEN_STATUSES = {None, "pending", "in_progress"}
    if approval.get("status") not in OPEN_STATUSES:
        raise ValueError(f"Approval is already {approval.get('status')}")

    if idx >= len(chain):
        raise ValueError("Approval chain already exhausted")

    step = chain[idx]
    now = datetime.now(timezone.utc).isoformat()

    # Allow super_admin to act on any step, otherwise enforce role match
    if user.get("role") != "super_admin" and user.get("role") != step.get("role"):
        raise PermissionError(f"Only role '{step['role']}' can act on this step")

    # Mandatory comment for any "bounce-back" action (reject / request_info).
    if action in ("reject", "request_info"):
        if not comment or len(comment.strip()) < 5:
            raise ValueError(
                "A remark of at least 5 characters is required to reject or request information"
            )
        if action == "request_info" and not (required_documents or deadline):
            # Allow empty list as long as comment explains what is needed.
            pass

    record = {
        "step_index": idx,
        "step_label": step.get("label"),
        "step_role": step.get("role"),
        "action": action,
        "by": user.get("name") or user.get("email"),
        "by_role": user.get("role"),
        "by_id": user.get("id"),
        "comment": comment,
        "version": version,
        "at": now,
    }
    if required_documents:
        record["required_documents"] = required_documents
    if deadline:
        record["deadline"] = deadline
    history.append(record)

    if action == "reject":
        step["status"] = "rejected"
        step["approver"] = record["by"]
        step["at"] = now
        step["comment"] = comment
        chain[idx] = step
        # NEW: non-terminal — bounces back to the originator for revision.
        approval["status"] = "rejected_revision_required"
        approval["rejected_at_step"] = idx
        approval["last_reject_reason"] = comment
        approval["last_reject_by"] = record["by"]
        approval["last_reject_at"] = now
    elif action == "request_info":
        # Same idea — step stays "pending" but request blocks the approval until
        # the originator supplies the requested info.
        step["status"] = "info_requested"
        step["info_requested_by"] = record["by"]
        step["info_requested_at"] = now
        step["info_required_documents"] = required_documents or []
        step["info_deadline"] = deadline
        step["comment"] = comment
        chain[idx] = step
        approval["status"] = "additional_info_required"
        approval["info_required_at_step"] = idx
        approval["last_info_request"] = {
            "by": record["by"], "at": now,
            "required_documents": required_documents or [],
            "deadline": deadline, "comment": comment,
        }
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


def _bump_version(current: str) -> str:
    """v1.0 → v2.0 → v3.0 … (major bumps only — keeps it readable)."""
    try:
        major = int(str(current).split(".")[0]) + 1
        return f"{major}.0"
    except Exception:
        return "2.0"


async def apply_resubmit(approval: dict, user: dict, comment: str | None,
                         file_ids: Optional[List[str]] = None) -> dict:
    """Originator-driven revision cycle.

    Pre-conditions (caller must enforce):
      - approval.status ∈ {rejected_revision_required, additional_info_required, rejected}
      - user is the originator (or super_admin / hr_executive override)

    Behaviour:
      - Bumps ``approval.version`` (v1.0→v2.0).
      - Resets every chain step's ``status`` back to ``pending`` (clears past
        approver / at / comment so the next pass is a fresh decision).
      - Decides where to resume from based on
        ``settings.approval_workflow.restart_on_resubmit`` (default ``True`` → step 0).
      - Appends a ``resubmit`` history entry carrying the new version + file_ids.
      - Final status: ``pending`` (when restart from 0 and the chain length > 0)
        OR ``in_progress`` (when resuming mid-chain).
    """
    cfg = await db.settings.find_one({"_id": "approval_workflow"}, {"_id": 0}) or {}
    restart_default = cfg.get("restart_on_resubmit", True)

    chain = [
        {**s, "status": "pending", "approver": None, "at": None, "comment": None,
         "info_requested_by": None, "info_requested_at": None,
         "info_required_documents": None, "info_deadline": None}
        for s in (approval.get("chain") or [])
    ]
    old_version = approval.get("version") or "1.0"
    new_version = _bump_version(old_version)
    now = datetime.now(timezone.utc).isoformat()

    if restart_default:
        new_idx = 0
    else:
        # Resume at the step that bounced us back.
        new_idx = approval.get("rejected_at_step") or approval.get("info_required_at_step") or 0

    history = list(approval.get("history") or [])
    history.append({
        "action": "resubmit",
        "by": user.get("name") or user.get("email"),
        "by_role": user.get("role"),
        "by_id": user.get("id"),
        "comment": comment,
        "file_ids": list(file_ids or []),
        "from_version": old_version,
        "version": new_version,
        "resume_step": new_idx,
        "at": now,
    })

    approval["chain"] = chain
    approval["current_step"] = new_idx
    approval["history"] = history
    approval["version"] = new_version
    approval["status"] = "pending" if new_idx == 0 else "in_progress"
    approval["resubmitted_at"] = now
    approval["resubmitted_by"] = user.get("name") or user.get("email")
    approval["resubmit_count"] = int(approval.get("resubmit_count", 0)) + 1
    if file_ids:
        approval["attachments"] = list(set((approval.get("attachments") or []) + list(file_ids)))
    approval["updated_at"] = now
    return approval
