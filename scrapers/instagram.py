"""
Instagram scraper via Apify.

v2: curated tag set (brand / local + national competitors / Chicago geo / format /
emerging / Asian-bakery bellwether), recency-bounded, ranked by *time-normalized
velocity* (engagement ÷ age) rather than raw likes. Geo tags get a dessert
co-occurrence filter so #chicagofood doesn't drag in pizza and burgers.
See scrapers/_engagement.py for the ranking math.
"""
import os
import re
import requests
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

from scrapers._engagement import (
    parse_timestamp, engagement_score, age_hours, posting_rate_per_day, MAX_AGE_H,
)

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", encoding="utf-8-sig")

TOKEN = os.getenv("APIFY_TOKEN", "")
RUN_URL = "https://api.apify.com/v2/acts/apify~instagram-hashtag-scraper/run-sync-get-dataset-items"

# ── Curated tags (30), grouped by role ──────────────────────────────────────
BRAND_TAGS       = ["yourbakery", "yourbakerychi"]
LOCAL_COMP_TAGS  = ["sweetmandybs", "firecakes", "stansdonuts", "westtownbakery",
                    "bangbangpie", "lostlarson", "doritedonuts"]
NATIONAL_TAGS    = ["crumbl", "magnoliabakery", "insomniacookies", "bakedbymelissa",
                    "georgetowncupcake"]
GEO_TAGS         = ["chicagofood", "chicagodesserts", "chicagobakery", "chicagofoodie",
                    "312eats", "windycityfoodies"]
FORMAT_TAGS      = ["cakedecorating", "buttercream", "dripcake", "cupcakebouquet",
                    "cupcakebox", "desserttable"]
BUZZ_TAGS        = ["viralcupcakes", "trendingdessert"]
BELLWETHER_TAGS  = ["koreanbakery", "asiandesserts"]

ALL_TAGS = (BRAND_TAGS + LOCAL_COMP_TAGS + NATIONAL_TAGS + GEO_TAGS
            + FORMAT_TAGS + BUZZ_TAGS + BELLWETHER_TAGS)

TAG_GROUP = {
    **{t: "brand" for t in BRAND_TAGS},
    **{t: "local_competitor" for t in LOCAL_COMP_TAGS},
    **{t: "national_competitor" for t in NATIONAL_TAGS},
    **{t: "geo" for t in GEO_TAGS},
    **{t: "format" for t in FORMAT_TAGS},
    **{t: "buzz" for t in BUZZ_TAGS},
    **{t: "bellwether" for t in BELLWETHER_TAGS},
}

GEO_SET = set(GEO_TAGS)
# A geo post is kept only if it also carries a dessert/bakery term.
DESSERT_TERMS = {
    "cupcake", "cupcakes", "cake", "cakes", "cookie", "cookies", "dessert", "desserts",
    "bakery", "pastry", "pastries", "brownie", "donut", "doughnut", "frosting",
    "buttercream", "sweets", "baked", "cheesecake", "macaron", "cannoli", "pie",
}

RESULTS_PER_TAG = 25  # cost dial — results requested per hashtag (tune for budget)
                      # 50→25 (2026-07-06): keeps a full refresh under a ~$4 budget

STOP_WORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "is","was","are","be","been","this","that","it","i","my","we","our",
    "you","your","so","just","have","has","had","get","got","its","as",
    "by","from","not","no","do","did","will","would","can","could","all",
    "they","them","their","there","here","what","how","when","who","which",
    "up","out","if","then","than","too","very","also","more","like","about",
}


def _fmt(n):
    n = int(n)
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(n)


def _hashtag_from_url(url):
    m = re.search(r"/tags/([^/?#]+)", url or "")
    return m.group(1).lower() if m else ""


def _extract_words(caption):
    words = re.findall(r"[a-zA-Z]{4,}", caption.lower())
    return [w for w in words if w not in STOP_WORDS]


def _empty(error=None):
    return {
        "source": "Instagram", "scanned_at": datetime.utcnow().isoformat(),
        "hashtag_trends": [], "top_posts": [], "trending_words": [], "related_tags": [],
        **({"error": error} if error else {}),
    }


def run_full_scan(hashtags=None, results_limit=None):
    """Scrape, filter to the 48h–30d window (+ geo co-occurrence), rank by velocity.

    `hashtags` / `results_limit` are overridable for cheap testing.
    """
    if not TOKEN:
        return _empty("No Apify token — add APIFY_TOKEN to .env")

    from scrapers._config import get_list
    tags = hashtags or get_list("instagram", "hashtags", ALL_TAGS)
    limit = results_limit or RESULTS_PER_TAG
    try:
        resp = requests.post(
            RUN_URL,
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"hashtags": tags, "resultsLimit": limit},
            timeout=300, params={"timeout": 300},
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        return _empty(str(e).split(" for url:")[0].strip())

    now = datetime.now(timezone.utc)
    by_tag: dict[str, list[dict]] = {}
    all_words = Counter()
    co_hashtags = Counter()

    for item in items:
        tag = _hashtag_from_url(item.get("inputUrl", ""))
        if not tag:
            continue

        likes = max(0, item.get("likesCount") or 0)
        comments = max(0, item.get("commentsCount") or 0)
        caption = item.get("caption") or ""
        post_tags = {h.lower().strip("#") for h in (item.get("hashtags") or [])}

        # Geo co-occurrence filter: drop non-dessert posts under geo tags.
        if tag in GEO_SET and not (post_tags & DESSERT_TERMS):
            continue

        # Recency ceiling only (30d). No min-age floor: this is a recent firehose,
        # so newness is expected — we measure posting volume, not per-post velocity.
        age_h = age_hours(parse_timestamp(item.get("timestamp")), now)
        if age_h is None or age_h > MAX_AGE_H:
            continue

        eng = engagement_score(likes, comments)
        all_words.update(_extract_words(caption))
        for h in post_tags:
            if h and h != tag:
                co_hashtags[h] += 1

        by_tag.setdefault(tag, []).append({
            "tag": tag,
            "group": TAG_GROUP.get(tag, "other"),
            "likes": likes,
            "comments": comments,
            "engagement": eng,
            "age_hours": round(age_h, 1),
            "caption": caption[:200].strip(),
            "image_url": item.get("displayUrl") or "",
            "post_url": item.get("url") or "",
            "owner": item.get("ownerUsername") or "",
            "likes_display": _fmt(likes),
        })

    # Per-tag trend metric = posting rate (how actively the topic is posted about).
    all_posts: list[dict] = []
    hashtag_trends = []
    for tag, posts in by_tag.items():
        all_posts.extend(posts)
        span_h = max((p["age_hours"] for p in posts), default=1.0)
        rate = posting_rate_per_day(len(posts), span_h)
        avg_eng = round(sum(p["engagement"] for p in posts) / len(posts), 1) if posts else 0
        hashtag_trends.append({
            "hashtag": tag,
            "group": TAG_GROUP.get(tag, "other"),
            "post_count": len(posts),
            "posts_per_day": rate,
            "avg_engagement": avg_eng,
            "span_hours": round(span_h, 1),
            "engagement_display": f"{rate}/day",  # dashboard chip shows posting rate
            "url": f"https://www.instagram.com/explore/tags/{tag}/",
        })

    hashtag_trends.sort(key=lambda x: x["posts_per_day"], reverse=True)
    # Visual feed: the most-engaged recent posts (raw engagement, not velocity).
    all_posts.sort(key=lambda x: x["engagement"], reverse=True)

    trending_words = [{"word": w, "count": c} for w, c in all_words.most_common(20) if len(w) > 3]
    related_tags = [{"tag": t, "count": c} for t, c in co_hashtags.most_common(15)]

    # "Top posts" = the most-engaged real posts in the last N days. We ALWAYS
    # surface the top few (so the card reflects what's actually resonating on
    # the local tags), and separately flag the ones that clear a high "viral"
    # bar (Settings-editable min likes AND comments) with `viral: True`. The
    # threshold becomes a highlight, not an all-or-nothing gate — the earlier
    # version showed nothing at all when niche/local tags never hit 10k likes +
    # 1k comments, which read as broken. No view-count floor: regular Instagram
    # feed posts don't expose a public view count via this scraper.
    from scrapers._config import get_value
    window_days = float(get_value("thresholds", "top_post_window_days", "10") or 10)
    min_likes = int(get_value("thresholds", "instagram_min_likes", "10000") or 10000)
    min_comments = int(get_value("thresholds", "instagram_min_comments", "1000") or 1000)

    in_window = [p for p in all_posts if p["age_hours"] <= window_days * 24]
    in_window.sort(key=lambda x: x["engagement"], reverse=True)
    top_posts = in_window[:12]
    for p in top_posts:
        p["viral"] = p["likes"] >= min_likes and p["comments"] >= min_comments

    return {
        "source": "Instagram",
        "scanned_at": datetime.utcnow().isoformat(),
        "hashtag_trends": hashtag_trends,
        "top_posts": top_posts,
        "top_posts_criteria": {
            "window_days": window_days, "min_likes": min_likes, "min_comments": min_comments,
            "viral_count": sum(1 for p in top_posts if p["viral"]),
            "note": "ranked by engagement; viral flag = cleared min likes AND comments",
        },
        "trending_words": trending_words,
        "related_tags": related_tags,
        "total_posts_scraped": len(items),
        "posts_in_window": len(all_posts),
        "ranking": "posting_volume",
    }
