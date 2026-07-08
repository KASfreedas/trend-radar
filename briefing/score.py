"""
Momentum scoring — briefing/score.py

For each candidate term, computes:
  direction  : "rising" | "peaking" | "fading"
  delta      : avg(last_30d) / avg(prior_90d) - 1
  confidence : "low" | "medium" | "high"  (how many sources agree)
  evidence   : list of plain-English evidence strings citing real numbers only

Input: the full cached data dict from /api/data
Output: list of scored candidate dicts, sorted by momentum
"""

from __future__ import annotations
from datetime import datetime, timezone


def _trajectory(time_series: list[dict]) -> tuple[str, float]:
    """
    Return (direction, delta) from a Google Trends time-series list.
    Each element: {"date": "YYYY-MM-DD", "value": int}
    """
    if not time_series or len(time_series) < 4:
        return "flat", 0.0

    values = [p.get("value", 0) for p in time_series]
    n = len(values)

    # last ~30 days vs prior ~90 days (weekly pytrends = ~4 pts/month)
    last30 = values[max(0, n - 4):]
    prior90 = values[max(0, n - 16): max(0, n - 4)]

    avg_last = sum(last30) / len(last30) if last30 else 0
    avg_prior = sum(prior90) / len(prior90) if prior90 else 0

    if avg_prior < 1:
        delta = 0.0
    else:
        delta = (avg_last / avg_prior) - 1.0

    peak = max(values)
    near_peak = avg_last >= 0.8 * peak if peak > 0 else False

    if delta > 0.15:
        direction = "rising"
    elif delta < -0.15:
        direction = "fading"
    elif near_peak:
        direction = "peaking"
    else:
        direction = "flat"

    return direction, round(delta, 3)


# Minimum real sample size before a source counts as "corroborating" rather
# than noise. A single stray post mentioning a term isn't a trend — these
# floors were added after a real test showed local-tag posting volume as low
# as 0.2-0.5 posts/day, which would otherwise count the same as an
# established pattern. Food media is exempt: a single editorial mention is
# real signal on its own (professional food journalism doesn't publish
# noise), so it has no floor.
MIN_REDDIT_MENTIONS = 2
MIN_IG_POSTS = 3
MIN_IG_WORD_MENTIONS = 3
MIN_TIKTOK_VIDEOS = 3


def _cross_source_score(term: str, data: dict) -> tuple[int, list[str]]:
    """
    Count how many non-Google sources also surface this term WITH a real
    minimum sample behind it. Returns (count, evidence_strings).

    Pinterest is deliberately excluded: a real test (2026-07-01) found the
    same search query returning 0 boards one run and 784+ another — that's
    not sample-size noise a floor can fix, it's an inconsistent data source.
    Pinterest's own dashboard card still shows its data; it just no longer
    contributes to cross-source confidence here.
    """
    term_lower = term.lower().replace(" ", "")
    count = 0
    evidence = []

    # Reddit keywords
    reddit = data.get("reddit") or {}
    for kw in (reddit.get("trending_keywords") or []):
        if term_lower in kw.get("keyword", "").lower().replace(" ", ""):
            n = kw.get("count", 0)
            if n >= MIN_REDDIT_MENTIONS:
                evidence.append(f"Reddit: \"{kw['keyword']}\" mentioned {n}x in hot posts")
                count += 1
            break

    # Instagram hashtags — require a real minimum number of posts observed,
    # not just that the hashtag was scanned at all.
    instagram = data.get("instagram") or {}
    for ht in (instagram.get("hashtag_trends") or []):
        tag = ht.get("hashtag", "").lower().replace(" ", "")
        if term_lower in tag or tag in term_lower:
            posts = ht.get("post_count", 0)
            if posts >= MIN_IG_POSTS:
                eng = ht.get("engagement_display", "0")
                evidence.append(f"Instagram #{ht['hashtag']}: {eng} engagement ({posts} posts observed)")
                count += 1
            break

    # Instagram trending words — same floor used for Suggested Keywords discovery
    for w in (instagram.get("trending_words") or []):
        if term_lower in w.get("word", "").lower():
            if w.get("count", 0) >= MIN_IG_WORD_MENTIONS:
                evidence.append(f"Instagram captions: \"{w['word']}\" appears {w.get('count', 0)}x")
                count += 1
            break

    # TikTok hashtags — require a real minimum number of videos observed
    tiktok = data.get("tiktok") or {}
    for ht in (tiktok.get("hashtag_trends") or []):
        tag = ht.get("hashtag", "").lower().replace(" ", "")
        if term_lower in tag or tag in term_lower:
            videos = ht.get("video_count", 0)
            if videos >= MIN_TIKTOK_VIDEOS:
                plays = ht.get("plays_display", "0")
                evidence.append(f"TikTok #{ht['hashtag']}: {plays} total plays ({videos} videos observed)")
                count += 1
            break

    # Food media — no floor; see module note above.
    food_media = data.get("food_media") or {}
    for a in (food_media.get("top_articles") or []):
        if term_lower in (a.get("title") or "").lower().replace(" ", ""):
            count += 1
            evidence.append(f"Editorial: \"{a['title'][:60]}…\" ({a.get('source', '')})")
            break

    return count, evidence


def _confidence(sources_agreeing: int) -> str:
    if sources_agreeing >= 3:
        return "high"
    if sources_agreeing >= 1:
        return "medium"
    return "low"


def score_all(data: dict) -> list[dict]:
    """
    Score every Google Trends term across all three groups.
    Returns list sorted by momentum (rising+high first).
    """
    google = data.get("google") or {}
    all_trends = (
        [(t, "flavor") for t in (google.get("flavor_trends") or [])]
        + [(t, "packaging") for t in (google.get("packaging_trends") or [])]
        + [(t, "design") for t in (google.get("design_trends") or [])]
    )

    candidates = []
    for term_data, category in all_trends:
        keyword = term_data.get("keyword", "")
        if not keyword:
            continue

        ts = term_data.get("time_series") or []
        direction, delta = _trajectory(ts)

        current = term_data.get("current_interest", 0) or 0
        gtrends_evidence = []
        if current > 0:
            pct = f"+{round(delta*100)}%" if delta >= 0 else f"{round(delta*100)}%"
            gtrends_evidence.append(f"Google Trends: {current}/100 ({pct} vs prior period)")

        sources_count, cross_evidence = _cross_source_score(keyword, data)
        all_evidence = gtrends_evidence + cross_evidence

        candidates.append({
            "term": keyword,
            "category": category,
            "direction": direction,
            "delta": delta,
            "current_interest": current,
            "confidence": _confidence(sources_count),
            "sources_agreeing": sources_count,
            "evidence": all_evidence,
            "scored_at": datetime.now(timezone.utc).isoformat(),
        })

    # Sort: rising first, then peaking, then flat/fading; within each by current_interest
    direction_rank = {"rising": 0, "peaking": 1, "flat": 2, "fading": 3}
    candidates.sort(key=lambda c: (direction_rank.get(c["direction"], 4), -c["current_interest"]))

    return candidates
