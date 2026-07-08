"""
TikTok trend scraper via Apify (clockworks~free-tiktok-scraper).

Unlike the Instagram hashtag actor (a recent firehose), this one returns *top*
videos per hashtag — real play counts spanning a range of ages — so we can rank
by true engagement velocity (plays ÷ age), which is what the original spec
wanted. Per-tag trend metric = posting volume (videos/day) + peak play-velocity.
Requires APIFY_TOKEN in .env.
"""
import os
import requests
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

from scrapers._engagement import parse_timestamp, age_hours

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", encoding="utf-8-sig")

TOKEN = os.getenv("APIFY_TOKEN", "")
RUN_URL = "https://api.apify.com/v2/acts/clockworks~free-tiktok-scraper/run-sync-get-dataset-items"

# Curated for TikTok (national/global discovery — geo tags carry little here).
BRAND_TAGS      = ["yourbakery"]
COMPETITOR_TAGS = ["crumbl", "magnoliabakery", "insomniacookies", "georgetowncupcake"]
FLAVOR_TAGS     = ["dubaichocolate", "matcha", "pistachio", "ube", "tresleches",
                   "biscoff", "tiramisu", "knafeh", "blacksesame"]
FORMAT_TAGS     = ["viralcake", "cupcake", "cakedecorating", "bentocake", "dessert"]
BELLWETHER_TAGS = ["koreanbakery", "asiandessert"]

ALL_TAGS = BRAND_TAGS + COMPETITOR_TAGS + FLAVOR_TAGS + FORMAT_TAGS + BELLWETHER_TAGS
TAG_GROUP = {
    **{t: "brand" for t in BRAND_TAGS},
    **{t: "competitor" for t in COMPETITOR_TAGS},
    **{t: "flavor" for t in FLAVOR_TAGS},
    **{t: "format" for t in FORMAT_TAGS},
    **{t: "bellwether" for t in BELLWETHER_TAGS},
}

RESULTS_PER_TAG = 5     # cost dial — videos requested per hashtag
MIN_AGE_H = 12          # let a video accrue plays before judging velocity
MAX_AGE_H = 24 * 30     # 30-day ceiling


def _fmt(n):
    n = int(n)
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(n)


def _empty(error=None):
    return {
        "source": "TikTok", "scanned_at": datetime.utcnow().isoformat(),
        "top_videos": [], "hashtag_trends": [],
        **({"error": error} if error else {}),
    }


def _cover(item):
    vm = item.get("videoMeta") or {}
    return vm.get("coverUrl") or vm.get("originalCoverUrl") or \
        (item.get("mediaUrls") or [""])[0] or ""


def run_full_scan(hashtags=None, results_per_page=None):
    if not TOKEN:
        return _empty("No Apify token — add APIFY_TOKEN to .env")

    from scrapers._config import get_list
    tags = hashtags or get_list("tiktok", "hashtags", ALL_TAGS)
    per = results_per_page or RESULTS_PER_TAG
    try:
        resp = requests.post(
            RUN_URL,
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "hashtags": tags, "resultsPerPage": per,
                "shouldDownloadVideos": False, "shouldDownloadCovers": False,
                "shouldDownloadSubtitles": False,
            },
            timeout=300, params={"timeout": 300},
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        err = str(e)
        if "Client Error:" in err:
            err = err.split(" for url:")[0].strip()
        return _empty(err)

    now = datetime.now(timezone.utc)
    by_tag: dict[str, list[dict]] = {}

    for item in items:
        sh = item.get("searchHashtag")
        if isinstance(sh, dict):
            sh = sh.get("name") or sh.get("hashtag") or ""
        seed = (sh or "").lower()
        if not seed:
            tags_in = [h.get("name", "") for h in (item.get("hashtags") or []) if h.get("name")]
            seed = next((t.lower() for t in tags_in if t.lower() in TAG_GROUP), "")
        if not seed:
            continue

        age_h = age_hours(parse_timestamp(item.get("createTimeISO")), now)
        if age_h is None or age_h < MIN_AGE_H or age_h > MAX_AGE_H:
            continue

        plays = max(0, item.get("playCount") or 0)
        likes = max(0, item.get("diggCount") or 0)
        comments = max(0, item.get("commentCount") or 0)
        shares = max(0, item.get("shareCount") or 0)
        author = (item.get("authorMeta") or {}).get("name") or ""
        velocity = plays / age_h  # plays per hour

        by_tag.setdefault(seed, []).append({
            "tag": seed,
            "group": TAG_GROUP.get(seed, "other"),
            "description": (item.get("text") or "")[:120],
            "author": author,
            "plays": plays, "likes": likes, "comments": comments, "shares": shares,
            "velocity": round(velocity, 1),
            "age_hours": round(age_h, 1),
            "plays_display": _fmt(plays),
            "likes_display": _fmt(likes),
            "velocity_display": f"{_fmt(velocity)}/h",
            "cover_url": _cover(item),
            "url": item.get("webVideoUrl") or f"https://www.tiktok.com/@{author}/video/{item.get('id','')}",
            "hashtags": [h.get("name", "") for h in (item.get("hashtags") or []) if h.get("name")][:5],
        })

    all_videos: list[dict] = []
    hashtag_trends = []
    for tag, vids in by_tag.items():
        all_videos.extend(vids)
        span_h = max((v["age_hours"] for v in vids), default=1.0)
        per_day = round(len(vids) / (max(span_h, 1.0) / 24.0), 1)
        peak_vel = max((v["velocity"] for v in vids), default=0)
        total_plays = sum(v["plays"] for v in vids)
        hashtag_trends.append({
            "hashtag": tag,
            "group": TAG_GROUP.get(tag, "other"),
            "video_count": len(vids),
            "videos_per_day": per_day,
            "peak_velocity": peak_vel,
            "total_plays": total_plays,
            "plays_display": _fmt(total_plays),
            "velocity_display": f"{_fmt(peak_vel)}/h",
            "url": f"https://www.tiktok.com/tag/{tag}",
        })

    # Videos ranked by play-velocity (fastest-accelerating first) — this
    # ranking still drives hashtag_trends' peak_velocity; it's unrelated to
    # the "top posts" definition below.
    all_videos.sort(key=lambda x: x["velocity"], reverse=True)
    hashtag_trends.sort(key=lambda x: x["peak_velocity"], reverse=True)

    # "Top posts" = the most-played real videos in the last N days. We ALWAYS
    # surface the top few and separately flag the ones that clear a high
    # "viral" bar (Settings-editable min views AND likes AND comments) with
    # `viral: True`. Threshold is a highlight, not an all-or-nothing gate —
    # matches the Instagram card so both behave consistently and never render
    # empty just because niche content didn't hit viral-tier numbers.
    from scrapers._config import get_value
    window_days = float(get_value("thresholds", "top_post_window_days", "10") or 10)
    min_views = int(get_value("thresholds", "tiktok_min_views", "10000") or 10000)
    min_likes = int(get_value("thresholds", "tiktok_min_likes", "10000") or 10000)
    min_comments = int(get_value("thresholds", "tiktok_min_comments", "1000") or 1000)

    in_window = [v for v in all_videos if v["age_hours"] <= window_days * 24]
    in_window.sort(key=lambda x: x["plays"], reverse=True)
    top_videos = in_window[:8]
    for v in top_videos:
        v["viral"] = (v["plays"] >= min_views and v["likes"] >= min_likes
                      and v["comments"] >= min_comments)

    return {
        "source": "TikTok",
        "scanned_at": datetime.utcnow().isoformat(),
        "top_videos": top_videos,
        "top_videos_criteria": {
            "window_days": window_days, "min_views": min_views,
            "min_likes": min_likes, "min_comments": min_comments,
            "viral_count": sum(1 for v in top_videos if v["viral"]),
        },
        "hashtag_trends": hashtag_trends[:12],
        "total_scraped": len(items),
        "videos_in_window": len(all_videos),
        "ranking": "engagement_velocity",
    }
