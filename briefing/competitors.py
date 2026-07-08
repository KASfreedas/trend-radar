"""
Competitor move detection — briefing/competitors.py (03_BRIEFING_LAYER.md §C)

For each tracked competitor, computes their own baseline engagement (median of
their recent posts) and flags whichever SINGLE post — across all tracked
competitors — is overperforming its own account's baseline by the widest
margin. This is the "I couldn't get this myself" moment: a real post, a real
link, a real multiple. No invented numbers: a competitor with too few posts to
establish a meaningful baseline is skipped rather than guessed at.
"""

from __future__ import annotations
import json
import statistics

from scrapers._engagement import engagement_score
from tenancy import data_path

COMPETITORS_PATH = data_path("competitors.json")

MIN_POSTS_FOR_BASELINE = 3   # too few posts -> a median is meaningless, skip
MIN_NOTABLE_MULTIPLE = 1.2   # a "best" post barely above baseline isn't a move


def load_competitors() -> list[dict]:
    if COMPETITORS_PATH.exists():
        try:
            data = json.loads(COMPETITORS_PATH.read_text(encoding="utf-8"))
            return data.get("competitors", [])
        except (ValueError, OSError):
            return []
    return []


def save_competitors(competitors: list[dict]) -> None:
    COMPETITORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPETITORS_PATH.write_text(
        json.dumps({"competitors": competitors}, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _competitor_moves(profile: dict, competitor_name: str) -> list[dict]:
    """Every post from this profile, scored against the profile's own median."""
    posts = profile.get("posts", [])
    if len(posts) < MIN_POSTS_FOR_BASELINE:
        return []
    scores = [engagement_score(p.get("likes", 0), p.get("comments", 0)) for p in posts]
    baseline = statistics.median(scores)
    if baseline <= 0:
        return []
    return [
        {
            "competitor": competitor_name,
            "username": profile.get("username", ""),
            "item": p.get("caption", "")[:100] or "(no caption)",
            "multiple": round(score / baseline, 2),
            "url": p.get("url", ""),
            "image_url": p.get("image_url", ""),
            "likes": p.get("likes", 0),
            "comments": p.get("comments", 0),
            "baseline": round(baseline, 1),
        }
        for p, score in zip(posts, scores)
    ]


def compute_competitor_move(scan_result: dict, competitors_meta: list[dict]) -> dict | None:
    """Returns the single biggest overperforming post across all tracked
    competitors, or None if there isn't enough real data to say anything."""
    name_by_username = {
        (c.get("instagram") or "").lower(): c.get("name") or c.get("instagram", "")
        for c in competitors_meta
    }

    all_moves = []
    for profile in scan_result.get("profiles", []):
        username = (profile.get("username") or "").lower()
        name = name_by_username.get(username, username or "Unknown")
        all_moves.extend(_competitor_moves(profile, name))

    if not all_moves:
        return None

    best = max(all_moves, key=lambda m: m["multiple"])
    if best["multiple"] <= MIN_NOTABLE_MULTIPLE:
        return None
    return best
