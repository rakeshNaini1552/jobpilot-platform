"""Delivery channels: SMTP email (SSL or STARTTLS by port) and
Slack/Discord incoming webhooks. Each returns (ok, error) — callers persist
the outcome on the notifications row; nothing here raises."""
import smtplib
from email.message import EmailMessage

import httpx
import structlog

from app.core.settings import get_settings

log = structlog.get_logger("notification.channels")


def email_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_user and s.smtp_password)


def send_email(to: str, subject: str, html: str,
               text: str = "") -> tuple[bool, str | None]:
    s = get_settings()
    if not email_configured():
        return False, "SMTP not configured"
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text or "This report is best viewed in an HTML mail client.")
    msg.add_alternative(html, subtype="html")
    try:
        if s.smtp_port == 465:
            with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=30) as smtp:
                smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        return True, None
    except Exception as e:  # noqa: BLE001
        log.warning("email_send_failed", to=to, error=str(e)[:200])
        return False, str(e)[:400]


def send_webhook(url: str, text: str) -> tuple[bool, str | None]:
    """Slack and Discord both accept a simple JSON POST; the payload key
    differs (text vs content) — send both, each service ignores the other."""
    try:
        r = httpx.post(url, json={"text": text, "content": text}, timeout=15)
        r.raise_for_status()
        return True, None
    except Exception as e:  # noqa: BLE001
        log.warning("webhook_send_failed", error=str(e)[:200])
        return False, str(e)[:400]
