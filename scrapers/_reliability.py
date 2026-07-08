"""
Per-source reliability wrapper — scrapers/_reliability.py  (Phase 4)

Wraps each scraper's run_full_scan() so a single broken source never blanks
its signal for the cycle: on failure, falls back to the last successful
result (persisted to data/cache/), marked stale, and fires an operator
alert (edge-triggered on the ok->error transition, then throttled to at
most once per ALERT_COOLDOWN_HOURS while it stays broken).

"Never let a broken source silently produce an empty briefing" — 01_ARCHITECTURE.md.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from tenancy import data_path

CACHE_DIR = data_path("cache")
ALERTS_PATH = data_path("alerts_state.json")
ALERT_COOLDOWN_HOURS = 24


def _last_good_path(source: str) -> Path:
    return CACHE_DIR / f"last_good_{source}.json"


def load_last_good(source: str) -> dict | None:
    p = _last_good_path(source)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def save_last_good(source: str, result: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _last_good_path(source).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_alert_state() -> dict:
    if ALERTS_PATH.exists():
        try:
            return json.loads(ALERTS_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _save_alert_state(state: dict) -> None:
    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _clear_alert_state(source: str) -> None:
    state = _load_alert_state()
    state[source] = {"last_status": "ok", "last_alert_at": None}
    _save_alert_state(state)


def _maybe_alert(source: str, error: str, used_fallback: bool) -> None:
    from briefing.send import send_operator_alert

    state = _load_alert_state()
    entry = state.get(source, {"last_status": "ok", "last_alert_at": None})
    now = datetime.now(timezone.utc)

    just_broke = entry.get("last_status") != "error"
    cooldown_elapsed = True
    if entry.get("last_alert_at"):
        try:
            elapsed_h = (now - datetime.fromisoformat(entry["last_alert_at"])).total_seconds() / 3600
            cooldown_elapsed = elapsed_h >= ALERT_COOLDOWN_HOURS
        except ValueError:
            cooldown_elapsed = True

    if just_broke or cooldown_elapsed:
        fallback_note = (
            "A last-good cached result is being served instead (marked stale in the briefing)."
            if used_fallback else
            "No prior good result exists for this source yet — it will read as empty this cycle."
        )
        send_operator_alert(
            subject=f"[Trend Radar] {source} scraper failing",
            body=f"Source: {source}\nError: {error}\n\n{fallback_note}\n\nTime: {now.isoformat()}",
        )
        entry["last_alert_at"] = now.isoformat()

    entry["last_status"] = "error"
    state[source] = entry
    _save_alert_state(state)


def run_with_fallback(source: str, fn) -> dict:
    """Run a scraper's run_full_scan(), falling back to last-good on failure.
    Always returns a dict — never raises — so one bad source can't take down
    a parallel refresh_all() run."""
    try:
        result = fn()
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(result["error"])
        save_last_good(source, result)
        _clear_alert_state(source)
        from scrapers._history import record_snapshot
        record_snapshot(source, result)
        return result
    except Exception as e:
        error_msg = str(e)
        fallback = load_last_good(source)
        if fallback is not None:
            stale = dict(fallback)
            stale["stale"] = True
            stale["stale_error"] = error_msg
            stale["stale_checked_at"] = datetime.now(timezone.utc).isoformat()
            _maybe_alert(source, error_msg, used_fallback=True)
            return stale
        _maybe_alert(source, error_msg, used_fallback=False)
        return {"source": source, "error": error_msg,
                "scanned_at": datetime.now(timezone.utc).isoformat()}
