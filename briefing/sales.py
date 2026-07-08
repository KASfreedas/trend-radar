"""
Manual unit-sales tracker — briefing/sales.py

The owner enters roughly how many of each menu item sold each month
(Settings -> Sales Tracker). Combined with the same scored trend candidates
briefing/gaps.py uses, this surfaces suggestions for items ALREADY on the
menu — the complement to gaps.py, which only covers trending terms NOT yet
on the menu.

Every suggestion requires at least MIN_MONTHS_FOR_TREND real months of sales
for that specific item — a single data point has no trend, so no suggestion
is generated for it (same never-fabricate rule as the rest of the briefing).
"""

from __future__ import annotations
import json
from datetime import datetime

from tenancy import data_path

SALES_PATH = data_path("history", "sales.json")
MIN_MONTHS_FOR_TREND = 2
DECLINE_THRESHOLD = -0.15  # >=15% drop counts as "declining"
RISE_THRESHOLD = 0.15      # >=15% gain counts as "rising"


def load_sales() -> dict:
    if SALES_PATH.exists():
        try:
            return json.loads(SALES_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"months": {}}


def save_sales(data: dict) -> None:
    SALES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SALES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def save_month(month_label: str, entries: dict) -> None:
    """entries: {item_name: unit_count}. Replaces that month's record (re-saving
    the same month edits it, doesn't duplicate)."""
    data = load_sales()
    data.setdefault("months", {})[month_label] = entries
    save_sales(data)


def item_history(item: str) -> list[tuple[str, int]]:
    """[(month_label, units), ...] for one item, sorted chronologically."""
    data = load_sales()
    months = data.get("months", {})
    out = [(m, entries[item]) for m, entries in months.items() if item in entries]

    def _key(pair):
        try:
            return datetime.strptime(pair[0], "%B %Y")
        except ValueError:
            return datetime.min

    out.sort(key=_key)
    return out


def _normalize(s: str) -> str:
    return s.lower().strip()


def _matches_term(item: str, term: str) -> bool:
    i, t = _normalize(item), _normalize(term)
    if i == t:
        return True
    iw, tw = i.split(), t.split()
    return any(len(w) > 3 and w in tw for w in iw) or any(len(w) > 3 and w in iw for w in tw)


def compute_suggestions(menu: dict, scored_candidates: list[dict]) -> list[dict]:
    """Sales-informed suggestions for items already on the menu."""
    suggestions = []
    all_items = []
    for cat in ("flavors", "formats", "toppings", "seasonal"):
        all_items.extend(menu.get(cat, []))

    for item in all_items:
        hist = item_history(item)
        if len(hist) < MIN_MONTHS_FOR_TREND:
            continue
        first_month, first_units = hist[0]
        last_month, last_units = hist[-1]
        if first_units <= 0:
            continue
        delta = (last_units - first_units) / first_units
        delta_pct = round(delta * 100)

        match = next((c for c in scored_candidates if _matches_term(item, c.get("term", ""))), None)
        trend_rising = bool(match and match.get("direction") in ("rising", "peaking"))

        trend_note = f"{match['term']} is {match['direction']} on Google" if match else "no current trend signal"
        units_note = f"{first_units}→{last_units} units ({first_month} to {last_month})"

        if delta <= DECLINE_THRESHOLD and not trend_rising:
            suggestions.append({
                "item": item, "type": "retire_candidate", "delta_pct": delta_pct,
                "summary": f"{item}: {units_note}, {trend_note}.",
            })
        elif delta >= RISE_THRESHOLD and trend_rising:
            suggestions.append({
                "item": item, "type": "lean_in", "delta_pct": delta_pct,
                "summary": f"{item}: {units_note}, tracking with {trend_note}. Feature it.",
            })
        elif delta <= 0 and trend_rising:
            suggestions.append({
                "item": item, "type": "underperforming_despite_trend", "delta_pct": delta_pct,
                "summary": f"{item}: {units_note} despite {trend_note} — worth a marketing push or recipe refresh.",
            })

    type_rank = {"retire_candidate": 0, "underperforming_despite_trend": 1, "lean_in": 2}
    suggestions.sort(key=lambda s: (type_rank.get(s["type"], 3), -abs(s["delta_pct"])))
    return suggestions
