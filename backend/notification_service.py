"""Email notifications via Resend.

Templates are inline-CSS HTML (email-safe). All sends go through
`send_email()` which is fire-and-forget — failures are logged but never
propagate to the request flow.
"""
import os
import asyncio
import logging

import resend

logger = logging.getLogger("erp.email")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = "WorkSite Command"

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def email_enabled() -> bool:
    return bool(RESEND_API_KEY)


# ---------- HTML templates ----------
_BRAND_COLOR = "#2563eb"
_BG = "#0f172a"
_CARD = "#1e293b"


def _shell(title: str, preheader: str, body_html: str, cta_label: str | None = None, cta_url: str | None = None) -> str:
    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
        <tr><td style="padding:0 32px 28px 32px;">
          <a href="{cta_url}" style="display:inline-block;background:{_BRAND_COLOR};color:#1a0a00;text-decoration:none;
             font-weight:700;font-family:Arial,sans-serif;font-size:13px;letter-spacing:0.08em;text-transform:uppercase;
             padding:12px 22px;border-radius:4px;">{cta_label}</a>
        </td></tr>
        """
    return f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="margin:0;padding:0;background:#e2e8f0;font-family:Arial,Helvetica,sans-serif;">
<span style="display:none;color:transparent;height:0;width:0;overflow:hidden;">{preheader}</span>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#e2e8f0;padding:32px 12px;">
  <tr><td align="center">
    <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;background:#ffffff;border-radius:6px;overflow:hidden;border:1px solid #cbd5e1;">
      <tr><td style="background:{_BG};padding:20px 32px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
          <tr>
            <td style="color:#ffffff;font-weight:900;font-size:16px;letter-spacing:-0.01em;">
              <span style="color:{_BRAND_COLOR};">■</span> WORKSITE<span style="color:{_BRAND_COLOR};">.</span>CMD
            </td>
            <td align="right" style="color:#94a3b8;font-size:10px;letter-spacing:0.18em;text-transform:uppercase;">Industrial ERP</td>
          </tr>
        </table>
      </td></tr>
      <tr><td style="padding:32px 32px 8px 32px;">
        <div style="color:{_BRAND_COLOR};font-size:11px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;margin-bottom:8px;">{title}</div>
        {body_html}
      </td></tr>
      {cta_html}
      <tr><td style="background:#f8fafc;padding:18px 32px;border-top:1px solid #e2e8f0;color:#64748b;font-size:11px;line-height:1.5;">
        Automated notification from WorkSite Command · Do not reply to this email.<br/>
        Need help? Speak to your Super Admin.
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""


def tmpl_approval_pending(approval: dict, current_step: dict, app_url: str) -> dict:
    title = "Approval Pending"
    preheader = f"{approval.get('title')} is waiting on your action."
    amount = approval.get("amount") or 0
    body = f"""
      <h2 style="font-size:22px;font-weight:900;color:#0f172a;margin:0 0 8px 0;letter-spacing:-0.01em;">{approval.get('title')}</h2>
      <p style="color:#475569;font-size:13px;line-height:1.6;margin:0 0 18px 0;">
        A new approval request needs your review at step
        <strong>{current_step.get('label')}</strong>.
      </p>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e2e8f0;border-radius:4px;margin:0 0 18px 0;">
        <tr><td style="padding:10px 14px;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:0.12em;width:120px;border-right:1px solid #e2e8f0;">Type</td>
            <td style="padding:10px 14px;font-size:13px;color:#0f172a;">{(approval.get('type') or '').replace('_',' ').title()}</td></tr>
        <tr><td style="padding:10px 14px;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:0.12em;border-right:1px solid #e2e8f0;border-top:1px solid #e2e8f0;">Reference</td>
            <td style="padding:10px 14px;font-size:13px;color:#0f172a;border-top:1px solid #e2e8f0;">{approval.get('reference') or '—'}</td></tr>
        <tr><td style="padding:10px 14px;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:0.12em;border-right:1px solid #e2e8f0;border-top:1px solid #e2e8f0;">Amount</td>
            <td style="padding:10px 14px;font-size:13px;color:#0f172a;border-top:1px solid #e2e8f0;">₹ {int(amount):,}</td></tr>
        <tr><td style="padding:10px 14px;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:0.12em;border-right:1px solid #e2e8f0;border-top:1px solid #e2e8f0;">Requested by</td>
            <td style="padding:10px 14px;font-size:13px;color:#0f172a;border-top:1px solid #e2e8f0;">{approval.get('requested_by') or '—'}</td></tr>
      </table>
    """
    return {"subject": f"[Approval] {approval.get('title')} — waiting on {current_step.get('label')}", "html": _shell(title, preheader, body, "Review in WorkSite", f"{app_url}/app/approvals")}


def tmpl_approval_decided(approval: dict, action: str, by: str, app_url: str) -> dict:
    decided = "approved" if action == "approve" else "rejected"
    title = f"Approval {decided.title()}"
    preheader = f"{approval.get('title')} was {decided} by {by}."
    body = f"""
      <h2 style="font-size:22px;font-weight:900;color:#0f172a;margin:0 0 8px 0;letter-spacing:-0.01em;">{approval.get('title')}</h2>
      <p style="color:#475569;font-size:13px;line-height:1.6;margin:0 0 12px 0;">
        Status updated to <strong style="color:{'#10b981' if action == 'approve' else '#ef4444'};">{decided.upper()}</strong> by <strong>{by}</strong>.
      </p>
    """
    return {"subject": f"[Approval {decided.title()}] {approval.get('title')}", "html": _shell(title, preheader, body, "Open WorkSite", f"{app_url}/app/approvals")}


def tmpl_invoice_reminder(quotation: dict, app_url: str) -> dict:
    title = "Invoice Reminder"
    preheader = f"Invoice {quotation.get('quote_number')} pending for {quotation.get('client')}."
    body = f"""
      <h2 style="font-size:22px;font-weight:900;color:#0f172a;margin:0 0 8px 0;letter-spacing:-0.01em;">Outstanding invoice</h2>
      <p style="color:#475569;font-size:13px;line-height:1.6;margin:0 0 12px 0;">
        Invoice <strong>{quotation.get('quote_number')}</strong> issued to <strong>{quotation.get('client')}</strong>
        for <strong>₹ {int(quotation.get('total') or 0):,}</strong> is still open. Please process payment at the earliest.
      </p>
    """
    return {"subject": f"[Invoice Reminder] {quotation.get('quote_number')} — {quotation.get('client')}", "html": _shell(title, preheader, body, "View Invoice", f"{app_url}/app/quotations")}


def tmpl_doc_expiry(document: dict, days_left: int, app_url: str) -> dict:
    title = "Document Expiry Alert"
    preheader = f"{document.get('title')} expires in {days_left} day(s)."
    if days_left >= 0:
        status_text = f"Expires in <strong>{days_left} day(s)</strong>"
    else:
        status_text = f'<strong style="color:#ef4444;">Already expired {abs(days_left)} day(s) ago</strong>'
    project = document.get("project")
    project_text = f" · Project: {project}" if project else ""
    body = f"""
      <h2 style="font-size:22px;font-weight:900;color:#0f172a;margin:0 0 8px 0;letter-spacing:-0.01em;">{document.get('title')}</h2>
      <p style="color:#475569;font-size:13px;line-height:1.6;margin:0 0 12px 0;">
        {status_text}.
        Category: <strong>{document.get('category')}</strong>{project_text}.
      </p>
    """
    return {"subject": f"[Expiry] {document.get('title')} — {days_left}d", "html": _shell(title, preheader, body, "Open Documents", f"{app_url}/app/documents")}


# ---------- Send ----------
async def send_email(to: str, subject: str, html: str) -> bool:
    if not email_enabled():
        logger.info(f"[email-disabled] Would send: {subject} -> {to}")
        return False
    if not to:
        return False
    params = {
        "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
        "to": [to],
        "subject": subject,
        "html": html,
    }
    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Email sent to {to} ({subject}) id={result.get('id')}")
        return True
    except Exception as e:
        logger.error(f"Email send failed to {to}: {e}")
        return False
