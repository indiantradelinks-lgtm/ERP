"""Microsoft 365 SMTP email service.

- Sends mail via smtp.office365.com:587 (STARTTLS) using mailbox + App Password.
- Fernet-based encryption helpers for storing per-user app passwords at rest.
- Async-safe via aiosmtplib.
- Builds multipart/alternative + attachments (PDF/DOCX/images) MIME messages.

Two sender modes:
  - 'shared' uses M365_SMTP_SHARED_USERNAME / _PASSWORD from .env
  - 'user'   pulls encrypted per-user credentials from db.smtp_user_credentials

See routers/email_router.py for the HTTP surface.
"""
from __future__ import annotations

import asyncio
import os
import logging
import random
from email.message import EmailMessage
from email.utils import formataddr
from typing import Iterable, Optional

import aiosmtplib
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("erp.m365_email")


# ---------- configuration ----------
SMTP_HOST = os.environ.get("M365_SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.environ.get("M365_SMTP_PORT", "587"))
SMTP_TIMEOUT = int(os.environ.get("M365_SMTP_TIMEOUT", "30"))

SHARED_USERNAME = os.environ.get("M365_SMTP_SHARED_USERNAME", "").strip()
SHARED_PASSWORD = os.environ.get("M365_SMTP_SHARED_PASSWORD", "").strip()
SHARED_DISPLAY_NAME = os.environ.get("M365_SMTP_SHARED_DISPLAY_NAME", "INDIAN TRADE LINKS ERP").strip()

_FERNET_KEY = os.environ.get("M365_FERNET_KEY", "").strip()
_fernet: Optional[Fernet] = None
if _FERNET_KEY:
    try:
        _fernet = Fernet(_FERNET_KEY.encode())
    except Exception as e:
        logger.error(f"Invalid M365_FERNET_KEY — per-user SMTP credentials disabled: {e}")


def shared_mailbox_configured() -> bool:
    return bool(SHARED_USERNAME and SHARED_PASSWORD)


def fernet_ready() -> bool:
    return _fernet is not None


# ---------- encryption helpers ----------
def encrypt_secret(plaintext: str) -> str:
    if not _fernet:
        raise RuntimeError("M365_FERNET_KEY is not configured")
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    if not _fernet:
        raise RuntimeError("M365_FERNET_KEY is not configured")
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Failed to decrypt stored secret (key rotated?)") from e


# ---------- exceptions ----------
class SMTPAuthError(Exception):
    """Invalid creds OR SMTP AUTH disabled at tenant/mailbox level."""


class SMTPThrottleError(Exception):
    """4xx — transient, safe to retry."""


class SMTPPermanentError(Exception):
    """5xx (non-auth) — bad recipient, message rejected, quota exceeded, etc."""


# ---------- MIME builder ----------
class Attachment:
    def __init__(self, filename: str, content: bytes, content_type: str = "application/octet-stream"):
        self.filename = filename or "attachment.bin"
        self.content = content
        if "/" in content_type:
            self.maintype, self.subtype = content_type.split("/", 1)
        else:
            self.maintype, self.subtype = "application", "octet-stream"


def _split_addrs(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [a.strip() for a in value.split(",") if a.strip()]
    return [a.strip() for a in value if a and a.strip()]


def build_email_message(
    *,
    from_email: str,
    from_name: Optional[str],
    to: Iterable[str] | str,
    cc: Iterable[str] | str | None = None,
    bcc: Iterable[str] | str | None = None,
    reply_to: Optional[str] = None,
    subject: str,
    text_body: str = "",
    html_body: Optional[str] = None,
    attachments: Iterable[Attachment] | None = None,
) -> tuple[EmailMessage, list[str]]:
    """Returns (EmailMessage, envelope_recipients).

    BCC recipients are added to the envelope only — never the headers.
    """
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    to_list = _split_addrs(to)
    cc_list = _split_addrs(cc)
    bcc_list = _split_addrs(bcc)
    if not to_list:
        raise ValueError("At least one 'to' recipient is required")
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject or "(no subject)"

    msg.set_content(text_body or " ")
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    for att in (attachments or []):
        msg.add_attachment(att.content, maintype=att.maintype, subtype=att.subtype, filename=att.filename)

    return msg, to_list + cc_list + bcc_list


# ---------- send ----------
async def _send_once(
    msg: EmailMessage,
    recipients: list[str],
    username: str,
    password: str,
) -> dict:
    smtp = aiosmtplib.SMTP(hostname=SMTP_HOST, port=SMTP_PORT, start_tls=False, timeout=SMTP_TIMEOUT)
    try:
        await smtp.connect()
        await smtp.starttls()
        await smtp.login(username, password)
        errors, response = await smtp.send_message(msg, sender=username, recipients=recipients)
        return {"errors": errors or {}, "response": str(response) if response else ""}
    except aiosmtplib.errors.SMTPAuthenticationError as e:
        raise SMTPAuthError(f"{e.code} {e.message}") from e
    except aiosmtplib.errors.SMTPResponseException as e:
        code = getattr(e, "code", 0) or 0
        message = getattr(e, "message", "")
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8", errors="replace")
            except Exception:
                message = str(message)
        if 400 <= code < 500:
            raise SMTPThrottleError(f"{code} {message}") from e
        if code == 535 or "5.7.3" in str(message) or "5.7.30" in str(message) or "AUTH" in str(message).upper():
            raise SMTPAuthError(f"{code} {message}") from e
        raise SMTPPermanentError(f"{code} {message}") from e
    finally:
        try:
            await smtp.quit()
        except Exception:
            pass


async def send_email(
    *,
    msg: EmailMessage,
    recipients: list[str],
    username: str,
    password: str,
    max_attempts: int = 3,
    base_delay: float = 2.0,
) -> dict:
    """Send with exponential backoff for transient (4xx) errors.

    Returns a dict with {ok, attempts, last_error, smtp_response}.
    Auth and permanent errors are NOT retried.
    """
    last_error: str = ""
    smtp_response: str = ""
    for attempt in range(1, max_attempts + 1):
        try:
            result = await _send_once(msg, recipients, username, password)
            smtp_response = result.get("response", "")
            partial = result.get("errors") or {}
            if partial:
                # Some recipients refused but message accepted overall
                return {
                    "ok": True,
                    "attempts": attempt,
                    "smtp_response": smtp_response,
                    "partial_failures": {k: str(v) for k, v in partial.items()},
                }
            return {"ok": True, "attempts": attempt, "smtp_response": smtp_response}
        except SMTPAuthError as e:
            return {"ok": False, "attempts": attempt, "error_type": "auth", "last_error": str(e)}
        except SMTPPermanentError as e:
            return {"ok": False, "attempts": attempt, "error_type": "permanent", "last_error": str(e)}
        except SMTPThrottleError as e:
            last_error = f"throttle: {e}"
            if attempt >= max_attempts:
                return {"ok": False, "attempts": attempt, "error_type": "throttle", "last_error": str(e)}
            delay = min(base_delay * (2 ** (attempt - 1)), 30.0)
            await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
        except Exception as e:
            last_error = f"unexpected: {e}"
            if attempt >= max_attempts:
                return {"ok": False, "attempts": attempt, "error_type": "unknown", "last_error": str(e)}
            delay = min(base_delay * (2 ** (attempt - 1)), 30.0)
            await asyncio.sleep(delay + random.uniform(0, delay * 0.2))

    return {"ok": False, "attempts": max_attempts, "error_type": "unknown", "last_error": last_error}


def friendly_error_message(error_type: str, raw: str) -> str:
    """Translate SMTP errors into operator-friendly text."""
    if error_type == "auth":
        return (
            "Authentication failed. Verify the M365 App Password is correct, MFA is enabled, "
            "and that the tenant admin has run "
            "`Set-CASMailbox -Identity <user> -SmtpClientAuthenticationDisabled $false` and "
            "`Set-TransportConfig -SmtpClientAuthenticationDisabled $false`. If you see 5.7.30, "
            "Basic Auth for SMTP submission has been disabled on the tenant — you will need to "
            "migrate to OAuth / Graph API."
        )
    if error_type == "throttle":
        return (
            "Microsoft 365 throttled the connection. Each mailbox is capped at ~30 messages/min "
            "and ~10,000 recipients/day. Auto-retry exhausted — try again later or distribute "
            "load across multiple mailboxes."
        )
    if error_type == "permanent":
        return f"Message permanently rejected by M365: {raw}"
    return raw or "Unknown SMTP error"
