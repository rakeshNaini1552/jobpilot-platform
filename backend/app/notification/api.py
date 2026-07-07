"""Public facade of the notification module.

Phase 10 wires real channels (SMTP email, Slack, Discord). Until then the
facade logs deliveries so flows depending on it (password reset) work
end-to-end in development.
"""
import structlog

log = structlog.get_logger("notification")


def send_password_reset(email: str, token: str) -> None:
    # Phase 10: render Jinja2 template and send via SMTP.
    log.info("password_reset_email", email=email,
             reset_hint=f"POST /api/v1/auth/password/reset with token={token[:8]}…")
