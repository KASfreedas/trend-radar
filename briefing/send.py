"""
Email delivery — briefing/send.py  (03_BRIEFING_LAYER.md §E)

Sends the monthly briefing HTML to the client via a transactional email
provider. The email is the primary product; the dashboard is the backup.

Provider: defaults to Resend (simple JSON API). Override with EMAIL_PROVIDER.
Secrets (from .env, UTF-8 no BOM):
    EMAIL_API_KEY   transactional provider key
    EMAIL_FROM      verified sender, e.g. "Trend Radar <radar@yourdomain.com>"
    CLIENT_EMAIL    briefing recipient (the owner)
    OPERATOR_EMAIL  you — for failure alerts (01_ARCHITECTURE.md reliability)

Graceful degradation: if no key or no recipient is configured, the send is a
DRY RUN — the email is written to data/history/ and a clear status is returned,
never an exception. This keeps Phase 1/2 runnable before billing keys exist.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", encoding="utf-8-sig")

EMAIL_API_KEY = os.getenv("EMAIL_API_KEY", "").strip()
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "resend").strip().lower()
EMAIL_FROM = os.getenv("EMAIL_FROM", "Trend Radar <onboarding@resend.dev>").strip()
CLIENT_EMAIL_DEFAULT = os.getenv("CLIENT_EMAIL", "").strip()  # .env fallback
OPERATOR_EMAIL = os.getenv("OPERATOR_EMAIL", "").strip()      # operator-only; not Settings-editable


def _client_email() -> str:
    """Recipient is editable from Settings (data/config.json, NOT a secret) and
    falls back to CLIENT_EMAIL in .env. Resolved per-call so a Settings edit
    takes effect without a restart."""
    from scrapers._config import get_value
    return get_value("delivery", "client_email", CLIENT_EMAIL_DEFAULT)

from tenancy import data_path

HISTORY_DIR = data_path("history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

RESEND_URL = "https://api.resend.com/emails"


def _dry_run(html: str, subject: str, to: str | None, reason: str) -> dict:
    """Write the email to disk instead of sending; report why."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    path = HISTORY_DIR / f"email_{ts}.html"
    path.write_text(html, encoding="utf-8")
    return {
        "status": "dry_run",
        "reason": reason,
        "subject": subject,
        "to": to,
        "saved_to": str(path),
    }


def _send_resend(html: str, subject: str, to: str) -> dict:
    import requests
    resp = requests.post(
        RESEND_URL,
        headers={
            "Authorization": f"Bearer {EMAIL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"from": EMAIL_FROM, "to": [to], "subject": subject, "html": html},
        timeout=30,
    )
    resp.raise_for_status()
    return {"status": "sent", "provider": "resend", "to": to,
            "id": resp.json().get("id"), "subject": subject}


_PROVIDERS = {"resend": _send_resend}


def send_briefing(html: str, subject: str | None = None, to: str | None = None) -> dict:
    """
    Email the briefing. Returns a status dict; never raises for missing config.
    Falls back to a dry run (saved to disk) when no key / recipient / provider.
    """
    subject = subject or f"Specials Board Briefing — {datetime.now(timezone.utc):%B %Y}"
    recipient = (to or _client_email()).strip()

    if not EMAIL_API_KEY:
        return _dry_run(html, subject, recipient or None, "EMAIL_API_KEY not set")
    if not recipient:
        return _dry_run(html, subject, None,
                        "no recipient (set in Settings → Delivery, or CLIENT_EMAIL in .env)")
    sender = _PROVIDERS.get(EMAIL_PROVIDER)
    if sender is None:
        return _dry_run(html, subject, recipient,
                        f"unknown EMAIL_PROVIDER '{EMAIL_PROVIDER}' (supported: {', '.join(_PROVIDERS)})")

    try:
        return sender(html, subject, recipient)
    except Exception as e:
        # Delivery failure is operator-actionable; surface it, don't crash the run.
        result = _dry_run(html, subject, recipient, f"send failed: {e!r}")
        send_operator_alert(
            subject=f"[Trend Radar] Briefing send FAILED ({EMAIL_PROVIDER})",
            body=f"Could not deliver the briefing to {recipient}.\n\nError: {e!r}\n"
                 f"A copy was saved to {result['saved_to']}.",
        )
        return result


def send_operator_alert(subject: str, body: str) -> dict:
    """
    Email the operator (you) about a failure — e.g. a broken scraper or a failed
    send (01_ARCHITECTURE.md: 'never let a broken source silently produce an
    empty briefing'). Plain-text body wrapped in minimal HTML. Best-effort.
    """
    if not EMAIL_API_KEY or not OPERATOR_EMAIL:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        path = HISTORY_DIR / f"alert_{ts}.txt"
        path.write_text(f"{subject}\n\n{body}", encoding="utf-8")
        return {"status": "dry_run", "reason": "EMAIL_API_KEY or OPERATOR_EMAIL not set",
                "saved_to": str(path)}
    html = f"<pre style='font-family:monospace;white-space:pre-wrap'>{body}</pre>"
    sender = _PROVIDERS.get(EMAIL_PROVIDER, _send_resend)
    try:
        return sender(html, subject, OPERATOR_EMAIL)
    except Exception as e:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        path = HISTORY_DIR / f"alert_{ts}.txt"
        path.write_text(f"{subject}\n\n{body}\n\n(alert send also failed: {e!r})", encoding="utf-8")
        return {"status": "failed", "error": repr(e), "saved_to": str(path)}
