"""
Shared helpers for the social scrapers (Instagram, TikTok).

These Apify hashtag actors return a *recency-ordered firehose* — the newest
posts for a tag, often minutes old with little engagement yet. So the trend
signal we extract is **posting volume**: how actively a topic is being posted
about (posts/day), plus the early engagement those posts attract. Individual
"most-engaged recent post" is still surfaced for the visual feed, ranked by raw
engagement — but the per-tag trend metric is posting rate, not per-post velocity.

(Per-post velocity needs *top* posts spanning a range of ages, which this actor
doesn't provide. Week-over-week *acceleration* of posting rate will come once the
scheduler stores history across weekly scrapes.)
"""

from __future__ import annotations
from datetime import datetime, timezone

MAX_AGE_H = 24 * 30     # 30-day ceiling, matched to the monthly briefing


def parse_timestamp(ts) -> datetime | None:
    """Apify gives ISO-8601 ('2026-06-01T12:00:00.000Z') or sometimes epoch secs."""
    if ts in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def engagement_score(likes=0, comments=0, shares=0) -> int:
    """Comments ≈ 6× a like, shares ≈ 8× (intent rises like → comment → share)."""
    likes = max(0, likes or 0)
    comments = max(0, comments or 0)
    shares = max(0, shares or 0)
    return likes + 6 * comments + 8 * shares


def age_hours(posted_at: datetime | None, now: datetime | None = None):
    """Hours since a post was made, or None if the timestamp didn't parse."""
    if posted_at is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - posted_at).total_seconds() / 3600.0


def posting_rate_per_day(n_posts: int, span_hours: float) -> float:
    """Posts/day given n posts spanning span_hours. Span floored to 1h so a burst
    of same-minute posts doesn't divide by ~zero."""
    span_days = max(span_hours, 1.0) / 24.0
    return round(n_posts / span_days, 1)
