"""
Rolling per-source snapshot history — scrapers/_history.py

Keeps the last MAX_SNAPSHOTS successful scrape results for Instagram/TikTok as
a compact {hashtag: metric} dict + timestamp, so the dashboard can draw a tiny
directional sparkline next to the top tags. Snapshots are only recorded on a
SUCCESSFUL scrape (hooked into scrapers/_reliability.run_with_fallback), so
this accumulates for free across whatever real refreshes the owner already
runs — nothing here triggers an extra scrape or costs a credit. A sparkline
needs at least 2 snapshots for a tag before it can draw anything; a freshly
added tag (or a brand-new install) just shows no sparkline until then.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone

from tenancy import data_path

HISTORY_DIR = data_path("cache")
# ~6 months of weekly scans. Raised from 8 (2026-07): with the bi-weekly
# briefing cadence, longer per-tag history is what turns sparklines into
# real trajectory evidence.
MAX_SNAPSHOTS = 26

# Real, already-computed numeric fields per source — same ones the chip
# already displays (posts_per_day -> "X/day", peak_velocity -> "X/h").
_METRIC_FIELD = {
    "instagram": "posts_per_day",
    "tiktok": "peak_velocity",
}


def _history_path(source: str) -> Path:
    return HISTORY_DIR / f"history_{source}.json"


def _extract_metrics(source: str, result: dict) -> dict:
    field = _METRIC_FIELD.get(source)
    if not field:
        return {}
    return {
        t["hashtag"]: t.get(field, 0)
        for t in (result.get("hashtag_trends") or [])
        if t.get("hashtag")
    }


def record_snapshot(source: str, result: dict) -> None:
    if source not in _METRIC_FIELD:
        return
    metrics = _extract_metrics(source, result)
    if not metrics:
        return
    path = _history_path(source)
    snapshots = load_history(source)
    snapshots.append({"at": datetime.now(timezone.utc).isoformat(), "metrics": metrics})
    snapshots = snapshots[-MAX_SNAPSHOTS:]
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshots, indent=2, ensure_ascii=False), encoding="utf-8")


def load_history(source: str) -> list[dict]:
    path = _history_path(source)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []


# ── Per-POST engagement history ──────────────────────────────────────────────
# "Became viral this week" is only measurable against what a post's engagement
# WAS at the previous scan. Scrapers include a compact {post_url: engagement}
# map in their result; we keep a short rolling history of those maps so the
# next scan can compute real gained-since-last-scan deltas. Recorded only on
# successful scrapes (same hook as the hashtag snapshots above).
MAX_POST_SNAPSHOTS = 8


def _post_history_path(source: str) -> Path:
    return HISTORY_DIR / f"history_posts_{source}.json"


def record_post_snapshot(source: str, result: dict) -> None:
    metrics = result.get("post_engagements")
    if not isinstance(metrics, dict) or not metrics:
        return
    snapshots = load_post_history(source)
    snapshots.append({"at": datetime.now(timezone.utc).isoformat(), "metrics": metrics})
    snapshots = snapshots[-MAX_POST_SNAPSHOTS:]
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    _post_history_path(source).write_text(
        json.dumps(snapshots, ensure_ascii=False), encoding="utf-8")


def load_post_history(source: str) -> list[dict]:
    path = _post_history_path(source)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []


def previous_post_engagements(source: str) -> dict:
    """{post_url: engagement} from the most recent recorded scan, else {}."""
    snaps = load_post_history(source)
    return dict(snaps[-1].get("metrics") or {}) if snaps else {}
