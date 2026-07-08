"""Bi-weekly briefing cycles — briefing/cycle.py

The briefing used to be monthly: one file per month (briefing_YYYY-MM.html),
one outcomes key per month. Bi-weekly doubles the touchpoints — a send on the
1st covers the late half of last month's data, a send on the 15th catches
mid-month movement while there's still time to act on it.

Cycle A = days 1-14, Cycle B = days 15-end. Every cycle gets its own file id
(briefing_YYYY-MM-a.html / -b.html) so the second send never overwrites the
first, and its own human label ("Early July 2026" / "Late July 2026") which
also keys the outcomes proof loop (idempotency stays per-cycle).

Costs nothing extra: briefings render from the weekly scrape cache that
already exists — twice the briefings, zero additional Apify spend.
"""

from __future__ import annotations
from datetime import datetime, timezone


def cycle_half(dt: datetime | None = None) -> str:
    """'a' for days 1-14, 'b' for day 15 onward."""
    dt = dt or datetime.now(timezone.utc)
    return "a" if dt.day < 15 else "b"


def cycle_id(dt: datetime | None = None) -> str:
    """File id, e.g. '2026-07-a'. Sorts correctly (a < b, months ascend)."""
    dt = dt or datetime.now(timezone.utc)
    return f"{dt.strftime('%Y-%m')}-{cycle_half(dt)}"


def cycle_label(dt: datetime | None = None) -> str:
    """Human label, e.g. 'Early July 2026' / 'Late July 2026'."""
    dt = dt or datetime.now(timezone.utc)
    half = "Early" if cycle_half(dt) == "a" else "Late"
    return f"{half} {dt.strftime('%B %Y')}"


def label_for_id(stem: str) -> str:
    """Turn a saved briefing file id back into a display label.
    Supports the new '2026-07-a' shape and the legacy monthly '2026-07'."""
    try:
        if len(stem) == 9 and stem[-2] == "-" and stem[-1] in ("a", "b"):
            base = datetime.strptime(stem[:7], "%Y-%m")
            half = "Early" if stem[-1] == "a" else "Late"
            return f"{half} {base.strftime('%B %Y')}"
        return datetime.strptime(stem, "%Y-%m").strftime("%B %Y")
    except ValueError:
        return stem
