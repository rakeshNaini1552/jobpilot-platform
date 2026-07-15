"""Public facade of the notification module."""
import structlog

from .channels import email_configured, send_email
from .models import Notification, NotificationSettings

log = structlog.get_logger("notification")

__all__ = ["Notification", "NotificationSettings", "send_password_reset"]


def send_password_reset(email: str, token: str) -> None:
    """Real email when SMTP is configured; logged hint otherwise so the flow
    still works end-to-end in development."""
    if email_configured():
        html = (f"<p>Someone requested a JobPilot password reset for {email}.</p>"
                f"<p>Reset token (valid 30 minutes):</p>"
                f"<pre style='font-size:16px'>{token}</pre>"
                f"<p>POST it with a new password to /api/v1/auth/password/reset. "
                f"If this wasn't you, ignore this email.</p>")
        ok, err = send_email(email, "JobPilot password reset", html)
        if ok:
            return
        log.warning("password_reset_email_failed", error=err)
    log.info("password_reset_email", email=email,
             reset_hint=f"POST /api/v1/auth/password/reset with token={token[:8]}…")
