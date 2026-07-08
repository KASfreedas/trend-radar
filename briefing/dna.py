"""
Brand DNA — briefing/dna.py

Two halves, both editable from Settings:
  - voice: free text fed into the LLM synthesis prompt (briefing/synthesize.py)
    as brand context. Shapes tone and judgment on which picks get featured —
    the guardrails (never invent numbers) still apply on top, unchanged. Has
    no effect on deterministic synthesis (no LLM key) — that path is
    intentionally evidence-only with no room for "voice".
  - structured filters: risk_tolerance and dietary_exclusions mechanically
    filter gap candidates wherever /api/menu-gaps is consumed; these are
    simple, explicit, inspectable rules — not AI judgment — so the owner can
    always tell exactly why a term did or didn't show up. max_new_items_per_
    month caps how many of those are surfaced as "act on this now" (Suggestions
    page), separate from the full Menu & Gaps browsing list.
"""

from __future__ import annotations
from scrapers._config import get_value, set_value

RISK_LEVELS = ("conservative", "balanced", "adventurous")


def load_dna() -> dict:
    try:
        max_items = int(get_value("dna", "max_new_items_per_month", "3") or 3)
    except ValueError:
        max_items = 3
    risk = get_value("dna", "risk_tolerance", "balanced")
    if risk not in RISK_LEVELS:
        risk = "balanced"
    return {
        "voice": get_value("dna", "voice", ""),
        "risk_tolerance": risk,
        "max_new_items_per_month": max_items,
        "dietary_exclusions": get_value("dna", "dietary_exclusions", ""),
    }


def save_dna(voice: str, risk_tolerance: str, max_new_items_per_month: int, dietary_exclusions: str) -> None:
    set_value("dna", "voice", voice)
    set_value("dna", "risk_tolerance", risk_tolerance if risk_tolerance in RISK_LEVELS else "balanced")
    set_value("dna", "max_new_items_per_month", str(max(0, int(max_new_items_per_month))))
    set_value("dna", "dietary_exclusions", dietary_exclusions)


def _confidence_floor(risk_tolerance: str) -> set[str]:
    if risk_tolerance == "conservative":
        return {"high"}
    if risk_tolerance == "adventurous":
        return {"high", "medium", "low"}
    return {"high", "medium"}  # balanced (default)


def apply_filters(candidates: list[dict], dna: dict | None = None) -> list[dict]:
    """Filter a list of gap/candidate dicts (each needs 'confidence' and
    'term') by risk tolerance and dietary exclusions. Does NOT apply the
    max-items cap — that's specific to "what to act on now" surfaces, not
    full browsing pages, so callers apply it themselves where it makes sense."""
    dna = dna or load_dna()
    allowed_conf = _confidence_floor(dna["risk_tolerance"])
    exclusions = [t.strip().lower() for t in dna["dietary_exclusions"].split(",") if t.strip()]

    out = []
    for c in candidates:
        if c.get("confidence", "low") not in allowed_conf:
            continue
        term = (c.get("term") or "").lower()
        if exclusions and any(ex in term for ex in exclusions):
            continue
        out.append(c)
    return out
