"""Terms & Conditions formatter for printed documents (Iter 207).

The Terms box is a plain textarea, and two very different styles are typed into it:

  • "one clause per line" — every line is a clause and the ERP numbers them 1…n
  • a fully formatted document — headings, paragraphs, bullets and clauses that
    already carry their own numbers (1., 1.1, (a), (i) …), very often pasted from
    Word with each clause hard-wrapped across several lines

`terms_to_html` keeps both working: it classifies every line, joins wrapped
continuation lines back into their clause, and only auto-numbers plain clause
lines — the moment the text carries its own clause numbers the auto numbering
steps aside so nothing is numbered twice.
"""
from __future__ import annotations

import re
from html import escape
from typing import Any, Dict, List

# 1.  1)  1.2  1.2.3   — a numbered clause (sub-levels need no trailing dot)
_NUM = re.compile(r"^(\d+)\s*[.)]\s+(.*)$|^(\d+(?:\.\d+)+)\s*[.)]?\s+(.*)$")
# (a)  a.  (i)  iv)     — a lettered / roman sub-clause
_ALPHA = re.compile(r"^\(([a-zA-Z]|[ivxlcIVXLC]{1,5})\)\s+(.*)$|^([a-zA-Z])[.)]\s+(.*)$")
_BULLET = re.compile(r"^[-*•▪·–]\s+(.*)$")
_MD_HEAD = re.compile(r"^#{1,4}\s+(.*)$")
_BOLD_LINE = re.compile(r"^\*\*(.+?)\*\*:?\s*$")
_BOLD_SPAN = re.compile(r"\*\*(.+?)\*\*")


def _inline(text: str) -> str:
    """Escape, then honour **bold** spans."""
    return _BOLD_SPAN.sub(r"<b>\1</b>", escape(text.strip()))


def _is_heading(line: str) -> bool:
    body = line.strip()
    if len(body) > 90 or not body:
        return False
    if _MD_HEAD.match(body) or _BOLD_LINE.match(body):
        return True
    letters = [c for c in body if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(body.split()) <= 12:
        return True
    # "Scope of Work:" style — a short label ending with a colon
    return body.endswith(":") and len(body.split()) <= 10


def has_manual_numbering(text: str) -> bool:
    return any(_NUM.match(raw.strip()) for raw in (text or "").replace("\r", "").split("\n"))


def _blocks(text: str) -> List[Dict[str, Any]]:
    auto_mode = not has_manual_numbering(text)
    out: List[Dict[str, Any]] = []
    counter = 0

    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            if out and out[-1]["kind"] != "gap":
                out.append({"kind": "gap"})
            continue

        if _is_heading(line):
            head = _MD_HEAD.match(line)
            bold = _BOLD_LINE.match(line)
            out.append({"kind": "heading", "body": head.group(1) if head else (bold.group(1) if bold else line)})
            continue

        bullet = _BULLET.match(line)
        if bullet:
            out.append({"kind": "bullet", "marker": "•", "body": bullet.group(1)})
            continue

        num = _NUM.match(line)
        if num:
            marker = num.group(1) or num.group(3)
            body = num.group(2) if num.group(2) is not None else num.group(4)
            out.append({"kind": "item", "marker": marker if marker.count(".") else f"{marker}.",
                        "sub": bool(marker.count(".")), "body": body or ""})
            continue

        alpha = _ALPHA.match(line)
        if alpha and not auto_mode:
            marker = alpha.group(1) or alpha.group(3)
            body = alpha.group(2) if alpha.group(2) is not None else alpha.group(4)
            out.append({"kind": "item", "marker": f"({marker})", "sub": True, "body": body or ""})
            continue

        if auto_mode:
            counter += 1
            out.append({"kind": "item", "marker": f"{counter}.", "sub": False, "body": line})
            continue

        # Formatted text: a plain line right after a clause/paragraph is the
        # hard-wrapped remainder of it, not a new clause.
        if out and out[-1]["kind"] in ("item", "bullet", "para"):
            out[-1]["body"] = f"{out[-1]['body']} {line}".strip()
        else:
            out.append({"kind": "para", "body": line})

    while out and out[-1]["kind"] == "gap":
        out.pop()
    return out


def terms_to_html(text: str, *, placeholder: str = "As mutually agreed.") -> str:
    """Render the Terms & Conditions text as print-ready HTML."""
    blocks = _blocks(text)
    if not blocks:
        return f"<div class='note'>{escape(placeholder)}</div>"
    html: List[str] = []
    for b in blocks:
        if b["kind"] == "gap":
            html.append("<div class='tnc-gap'></div>")
        elif b["kind"] == "heading":
            html.append(f"<div class='tnc-heading'>{_inline(b['body'])}</div>")
        elif b["kind"] == "para":
            html.append(f"<div class='tnc-para'>{_inline(b['body'])}</div>")
        else:
            cls = "tnc-item tnc-bullet" if b["kind"] == "bullet" else (
                "tnc-item tnc-sub" if b.get("sub") else "tnc-item")
            html.append(f"<div class='{cls}'><span class='tnc-num'>{escape(b['marker'])}</span>"
                        f"<span class='tnc-body'>{_inline(b['body'])}</span></div>")
    return "".join(html)
