"""
Proof loop (v2 — manual) — briefing/outcomes.py (03_BRIEFING_LAYER.md §F)

After each briefing, the "Launch Next" + "Menu Gap" candidates are logged to
data/history/outcomes.json. The owner later marks what actually happened
(Settings → Past Picks). Once prior-month outcomes are resolved, the NEXT
briefing opens with: "2 of the 3 items we flagged last cycle are now top
sellers." — the sentence that renews the retainer.

v2 is manual (owner self-reports) — zero ongoing Apify cost. v1 (auto-tracking
the brand's own account engagement) is deferred until that cost is worth it.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone

from tenancy import data_path

OUTCOMES_PATH = data_path("history", "outcomes.json")

STATUSES = ("not_yet", "selling_well", "underperformed", "not_tried")
STATUS_LABELS = {
    "not_yet": "Too soon to tell",
    "selling_well": "Selling well",
    "underperformed": "Didn't take off",
    "not_tried": "Never launched",
}


def _load() -> list[dict]:
    if OUTCOMES_PATH.exists():
        try:
            return json.loads(OUTCOMES_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
    return []


def _save(items: list[dict]) -> None:
    OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTCOMES_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def record_picks(synthesis: dict, month_label: str) -> None:
    """Log this month's Launch Next + Menu Gap items as new outcome-tracking
    rows (status starts 'not_yet'). Idempotent per (month, term)."""
    items = _load()
    existing = {(i["month"], i["term"]) for i in items}
    candidates = (synthesis.get("launch") or []) + (synthesis.get("gaps") or [])
    seen = set()
    for c in candidates:
        term = c.get("term", "")
        if not term or term in seen:
            continue
        seen.add(term)
        if (month_label, term) in existing:
            continue
        items.append({
            "month": month_label,
            "term": term,
            "category": c.get("category", ""),
            "status": "not_yet",
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        })
    _save(items)


def list_outcomes() -> list[dict]:
    items = _load()
    items.sort(key=lambda i: i.get("logged_at", ""), reverse=True)
    return items


def set_status(month: str, term: str, status: str) -> bool:
    if status not in STATUSES:
        return False
    items = _load()
    found = False
    for i in items:
        if i.get("month") == month and i.get("term") == term:
            i["status"] = status
            i["updated_at"] = datetime.now(timezone.utc).isoformat()
            found = True
            break
    if found:
        _save(items)
    return found


def hit_rate_sentence(current_month: str) -> str | None:
    """Opening line once prior-cycle outcomes are resolved. Only counts months
    BEFORE the current one — never claims credit early. Stays silent (returns
    None) when there are zero wins — this line exists to build trust, not to
    report failures."""
    items = [i for i in _load() if i.get("month") != current_month]
    resolved = [i for i in items if i.get("status") in ("selling_well", "underperformed")]
    if not resolved:
        return None
    win_terms = [i["term"] for i in resolved if i["status"] == "selling_well"]
    wins = len(win_terms)
    total = len(resolved)
    if wins == 0:
        return None
    # Name the actual items — a receipt is only convincing when it's specific.
    named = ", ".join(win_terms[:4])
    if total == 1:
        return f"The item we flagged last cycle — {named} — is now a top seller."
    return f"{wins} of the {total} items we flagged last cycle are now top sellers: {named}."
