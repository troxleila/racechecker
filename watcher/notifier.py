"""Email notifications via Gmail SMTP (STARTTLS)."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import Config
from .models import Opening

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _send(cfg: Config, subject: str, body: str) -> None:
    if not cfg.email_ready:
        print(f"[email] SKIPPED (missing credentials): {subject}")
        return
    msg = EmailMessage()
    msg["From"] = cfg.gmail_address
    msg["To"] = cfg.recipient_email
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(cfg.gmail_address, cfg.gmail_app_password)
        server.send_message(msg)
    print(f"[email] sent: {subject}")


def _fmt(op: Opening) -> str:
    label = "Race entry" if op.kind == "registration" else "Volunteer"
    return (f"• {op.event_name} — {op.option_name}\n"
            f"  ({label}) Register: {op.register_url}")


def notify_openings(cfg: Config, openings: list[Opening]) -> None:
    n = len(openings)
    lead = openings[0].event_name if n == 1 else f"{n} openings"
    subject = f"🏃 NYRR spot open: {lead}"
    body = "New NYRR openings just detected:\n\n" + "\n\n".join(_fmt(o) for o in openings)
    body += "\n\nSpots can fill quickly — register soon."
    _send(cfg, subject, body)


def notify_init(cfg: Config, openings: list[Opening]) -> None:
    subject = "✅ NYRR watcher started"
    if openings:
        body = ("Watcher is now running. These 9+1 options are currently open "
                "(baseline — you'll only be emailed about *new* openings from now on):\n\n"
                + "\n\n".join(_fmt(o) for o in openings))
    else:
        body = ("Watcher is now running. Nothing is open right now; you'll get an "
                "email as soon as a 9+1 race or volunteer spot opens.")
    _send(cfg, subject, body)


def notify_heartbeat(cfg: Config, watched_count: int, open_count: int) -> None:
    subject = "💓 NYRR watcher — weekly check-in"
    body = (f"Still watching. Tracking {watched_count} 9+1 events; "
            f"{open_count} option(s) currently open.\n\n"
            "If you ever stop getting these, the job may have stalled.")
    _send(cfg, subject, body)


def notify_error(cfg: Config, message: str) -> None:
    _send(cfg, "⚠️ NYRR watcher error", f"The watcher hit a problem:\n\n{message}")
