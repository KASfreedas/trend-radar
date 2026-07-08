"""Client feedback capture — briefing/feedback.py

The user-facing complement to the internal SCORECARD: a way for the bakery to
tell you, in their own words and with one number, whether a briefing was
actually useful — and optionally which specific recommendation they'd try. This
is how you get real data and improvement ideas instead of guessing, and every
term-level rating is also a future training label alongside the proof loop.

Two grains, both optional:
  - a quick 1-5 rating on the whole briefing (one click),
  - free-text detail ("what would make this more useful?"),
  - optionally attached to a specific term (a per-recommendation thumbs).
"""

from __future__ import annotations
import json
from datetime import datetime, timezone

from tenancy import data_path

FEEDBACK_PATH = data_path("history", "feedback.json")


def _load() -> list[dict]:
    if FEEDBACK_PATH.exists():
        try:
            return json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
    return []


def _save(items: list[dict]) -> None:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False),
                             encoding="utf-8")


def record_feedback(rating=None, note: str = "", cycle: str = "",
                    term: str = "") -> dict | None:
    """Store one feedback entry. Accepts a rating (1-5), a free-text note, or
    both — at least one must be present. Returns the stored entry, or None if
    empty. Note is capped so a runaway paste can't bloat the file."""
    r = None
    if rating is not None and str(rating).strip() != "":
        try:
            r = max(1, min(5, int(rating)))
        except (ValueError, TypeError):
            r = None
    note = (note or "").strip()[:2000]
    if r is None and not note:
        return None
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "cycle": (cycle or "").strip()[:40],
        "term": (term or "").strip()[:80],
        "rating": r,
        "note": note,
    }
    items = _load()
    items.append(entry)
    _save(items)
    return entry


def list_feedback() -> list[dict]:
    """Newest first, for the operator to read. Entries are appended
    chronologically, so reversing insertion order is exact even when two
    entries share a timestamp."""
    return list(reversed(_load()))


def feedback_by_term() -> dict:
    """term(lower) -> {ratings:[...], avg, notes:[...], count} — term-level
    feedback aggregated, for joining into the training table."""
    out: dict = {}
    for i in _load():
        term = (i.get("term") or "").lower()
        if not term:
            continue
        agg = out.setdefault(term, {"ratings": [], "notes": [], "count": 0})
        agg["count"] += 1
        if i.get("rating") is not None:
            agg["ratings"].append(i["rating"])
        if i.get("note"):
            agg["notes"].append(i["note"])
    for term, agg in out.items():
        agg["avg"] = round(sum(agg["ratings"]) / len(agg["ratings"]), 2) if agg["ratings"] else None
    return out


def summary() -> dict:
    """Overall counts for the operator dashboard."""
    items = _load()
    rated = [i["rating"] for i in items if i.get("rating") is not None]
    return {
        "total": len(items),
        "avg_rating": round(sum(rated) / len(rated), 2) if rated else None,
        "with_notes": sum(1 for i in items if i.get("note")),
    }
