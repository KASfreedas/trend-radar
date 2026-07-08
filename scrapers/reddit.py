"""
Reddit trend scraper. Two backends, picked automatically:

  - praw (official OAuth API): used when REDDIT_CLIENT_ID/SECRET are set in
    .env. No 429 throttling, so a full 14-subreddit scan is fast and
    reliable. Free — register a "script" app at reddit.com/prefs/apps.
  - public RSS feeds (fallback, default): no auth required, but Reddit
    hard-throttles unauthenticated bursts (~11/12 requests 429'd in testing),
    so a full scan can take ~10 minutes even with retry/backoff.

Both backends feed the same downstream pipeline: drop stale posts (>30d),
and use Reddit's own *rising* listing as the native acceleration signal — a
keyword surging in /rising is heating up faster than one merely present in
/hot. Keywords are aligned to the current flavor/format watch list so Reddit
corroborates the same terms Google Trends scores.
"""
import os
import time
import requests
from pathlib import Path
from xml.etree import ElementTree as ET
from datetime import datetime, timezone

from dotenv import load_dotenv

from scrapers._engagement import parse_timestamp, age_hours

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", encoding="utf-8-sig")

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "").strip()
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "TrendRadarBot/1.0").strip()
_USE_PRAW = bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)

HEADERS = {
    "User-Agent": "TrendRadarBot/1.0 (bakery trend research)"
}

MAX_AGE_DAYS = 30
PRAW_LIMIT = 20  # posts per subreddit per listing, matches the RSS ?limit=20

SUBREDDITS = [
    "Baking", "cakedecorating", "pastry", "Cupcakes", "bakersofreddit", "ArtisanBread",
    "DessertPorn", "FoodPorn", "Breadit", "cookies", "chocolate", "foodphotography",
    "PastryChefs", "veganbaking",
]

# Aligned to the flavor/format watch list (+ generic trend words) so a hit here
# confirms the same term Google/Instagram are tracking.
TREND_KEYWORDS = [
    # generic trend signals
    "trend", "trending", "new", "trying", "viral", "obsessed", "recipe",
    "aesthetic", "decoration", "packaging", "filling", "frosting", "ganache",
    # flavors on the watch list
    "matcha", "ube", "pistachio", "dubai", "bento", "crinkle", "biscoff",
    "tiramisu", "black sesame", "knafeh", "earl grey", "tahini", "tres leches",
    "creme brulee", "cannoli", "horchata", "dulce de leche", "lavender",
    # formats / cuisines
    "cupcake", "cookie", "korean", "mochi", "croissant", "stuffed", "lambeth",
]

NS = {"atom": "http://www.w3.org/2005/Atom"}


def _parse_rss(xml_text: str, subreddit: str, feed: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    posts = []
    for entry in root.findall("atom:entry", NS):
        title_el = entry.find("atom:title", NS)
        link_el = entry.find("atom:link", NS)
        updated_el = entry.find("atom:updated", NS)
        title = title_el.text if title_el is not None else ""
        if title.startswith("r/") and "moderator" in title.lower():
            continue
        posts.append({
            "title": title,
            "url": link_el.attrib.get("href", "") if link_el is not None else "",
            "updated": updated_el.text if updated_el is not None else "",
            "subreddit": subreddit,
            "feed": feed,                # "hot" or "rising"
            "is_rising": feed == "rising",
        })
    return posts


def _fetch_subreddit(subreddit: str, sort: str) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/{sort}/.rss?limit=20"
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                return _parse_rss(resp.text, subreddit, sort)
            if resp.status_code == 429:  # Reddit throttles unauthenticated bursts
                time.sleep(2 + 2 * attempt)
                continue
            return []
        except Exception:
            return []
    return []


def _score_relevance(post: dict, keywords: list[str]) -> int:
    title = post.get("title", "").lower()
    return sum(1 for kw in keywords if kw in title)


def _praw_client():
    import praw
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )


def _fetch_subreddit_praw(client, subreddit: str, listing: str) -> list[dict]:
    posts = []
    sub = client.subreddit(subreddit)
    for submission in getattr(sub, listing)(limit=PRAW_LIMIT):
        posts.append({
            "title": submission.title or "",
            "url": f"https://www.reddit.com{submission.permalink}",
            "updated": submission.created_utc,  # epoch seconds; parse_timestamp handles it
            "subreddit": subreddit,
            "feed": listing,
            "is_rising": listing == "rising",
        })
    return posts


def _collect_posts(subs: list[str]) -> tuple[list[dict], str]:
    """Returns (posts, backend_used). Falls back to RSS if praw creds are
    missing or the praw call fails for any reason (e.g. bad/expired creds) —
    a broken official API should never take Reddit data to zero."""
    if _USE_PRAW:
        try:
            client = _praw_client()
            posts = []
            for sub in subs:
                posts.extend(_fetch_subreddit_praw(client, sub, "hot"))
                posts.extend(_fetch_subreddit_praw(client, sub, "rising"))
            return posts, "praw"
        except Exception:
            pass  # fall through to RSS

    posts = []
    for sub in subs:
        posts.extend(_fetch_subreddit(sub, "hot"))
        time.sleep(0.4)  # space requests — Reddit RSS throttles rapid bursts
        posts.extend(_fetch_subreddit(sub, "rising"))
        time.sleep(0.4)
    return posts, "rss"


def run_full_scan() -> dict:
    from scrapers._config import get_list
    subs = get_list("reddit", "subreddits", SUBREDDITS)
    keywords = get_list("reddit", "keywords", TREND_KEYWORDS)

    now = datetime.now(timezone.utc)
    all_posts, backend = _collect_posts(subs)

    # Recency window + relevance. Posts with an unparseable date are kept (age=None).
    fresh = []
    for p in all_posts:
        a = age_hours(parse_timestamp(p.get("updated")), now)
        if a is not None and a > MAX_AGE_DAYS * 24:
            continue
        p["age_hours"] = round(a, 1) if a is not None else None
        p["relevance"] = _score_relevance(p, keywords)
        fresh.append(p)

    # De-dup by title; prefer the rising-feed copy when a post is in both.
    best: dict[str, dict] = {}
    for p in fresh:
        key = p["title"][:60]
        if key not in best or (p["is_rising"] and not best[key]["is_rising"]):
            best[key] = p
    unique = list(best.values())

    # Top posts: rising first, then relevance, then recency.
    unique.sort(key=lambda x: (x["is_rising"], x["relevance"],
                               -(x["age_hours"] or 1e9)), reverse=True)
    top_posts = unique[:10]

    # Keyword mention volume across recent posts, with a separate rising count
    # (mentions in the rising feed) as the acceleration proxy.
    counts: dict[str, int] = {}
    rising_counts: dict[str, int] = {}
    for p in unique:
        title = p.get("title", "").lower()
        for kw in keywords:
            if kw in title:
                counts[kw] = counts.get(kw, 0) + 1
                if p["is_rising"]:
                    rising_counts[kw] = rising_counts.get(kw, 0) + 1

    trending = sorted(counts.items(), key=lambda x: (rising_counts.get(x[0], 0), x[1]), reverse=True)

    return {
        "source": "Reddit",
        "scanned_at": datetime.utcnow().isoformat(),
        "top_posts": top_posts,
        "trending_keywords": [
            {"keyword": k, "count": v, "rising_count": rising_counts.get(k, 0)}
            for k, v in trending[:15]
        ],
        "subreddits_scanned": subs,
        "posts_in_window": len(unique),
        "ranking": "recency_weighted_mentions",
        "backend": backend,
    }
