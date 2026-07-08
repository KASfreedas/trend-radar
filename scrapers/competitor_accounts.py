"""
Competitor account scraper via Apify (apify~instagram-profile-scraper).

Unlike the hashtag scrapers (which sample whatever's posted under a tag), this
hits SPECIFIC competitor Instagram accounts directly and returns their recent
posts — the data briefing/competitors.py needs to compute "is X currently
overperforming their own baseline" (03_BRIEFING_LAYER.md §C).

COSTS REAL APIFY CREDITS PER PROFILE. This is NOT part of the regular refresh —
it's only triggered explicitly via POST /api/competitors/scan. Output post-field
names aren't live-verified yet; _extract_posts/_post_engagement_fields are
written defensively (try common Apify Instagram field-name variants) so a scan
degrades gracefully instead of crashing if the shape differs slightly.
Requires APIFY_TOKEN in .env.
"""
import json
import os
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", encoding="utf-8-sig")

TOKEN = os.getenv("APIFY_TOKEN", "")
RUN_URL = "https://api.apify.com/v2/acts/apify~instagram-profile-scraper/run-sync-get-dataset-items"

# Scan results are PAID — persist to disk so a server restart never silently
# forces (and pays for) a re-scrape. Only an explicit "Scan Competitors" click
# refreshes this.
from tenancy import data_path

CACHE_PATH = data_path("competitor_scan_cache.json")


def load_cached_scan() -> dict | None:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
    return None


def save_scan_cache(result: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


def _empty(error=None):
    return {
        "source": "Competitor Accounts", "scanned_at": datetime.utcnow().isoformat(),
        "profiles": [], **({"error": error} if error else {}),
    }


def _extract_posts(item: dict) -> list[dict]:
    """The actor's exact recent-posts field name isn't live-verified — try the
    common shapes Apify Instagram actors use, in order of likelihood."""
    for key in ("latestPosts", "posts", "recentPosts", "topPosts", "lastPosts"):
        v = item.get(key)
        if isinstance(v, list) and v:
            return v
    return []


def _num(v):
    return v if isinstance(v, (int, float)) else 0


def _post_engagement_fields(p: dict) -> dict:
    likes = p.get("likesCount", p.get("likes"))
    comments = p.get("commentsCount", p.get("comments"))
    short_code = p.get("shortCode") or p.get("shortcode")
    url = p.get("url") or (f"https://www.instagram.com/p/{short_code}/" if short_code else "")
    return {
        "likes": max(0, _num(likes)),
        "comments": max(0, _num(comments)),
        "timestamp": p.get("timestamp") or p.get("takenAtTimestamp") or p.get("createTime"),
        "url": url,
        "caption": (p.get("caption") or p.get("text") or "")[:160].strip(),
        "image_url": p.get("displayUrl") or p.get("imageUrl") or "",
    }


def run_full_scan(usernames: list[str]) -> dict:
    """Scrape specific competitor accounts. `usernames` must be passed
    explicitly — no silent default list, since every call here costs credits
    and callers must be deliberate about who gets scraped."""
    if not TOKEN:
        return _empty("No Apify token — add APIFY_TOKEN to .env")
    if not usernames:
        return _empty("No competitor usernames configured")

    try:
        resp = requests.post(
            RUN_URL,
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"usernames": usernames},
            timeout=300, params={"timeout": 300},
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        err = str(e)
        if "Client Error:" in err:
            err = err.split(" for url:")[0].strip()
        return _empty(err)

    profiles = []
    for item in items:
        username = item.get("username") or item.get("inputUsername") or ""
        posts_raw = _extract_posts(item)
        profiles.append({
            "username": username,
            "full_name": item.get("fullName") or item.get("full_name") or "",
            "followers": _num(item.get("followersCount") or item.get("followers")),
            "posts": [_post_engagement_fields(p) for p in posts_raw],
            "raw_post_keys": list(posts_raw[0].keys()) if posts_raw else [],  # debug aid for first real run
        })

    return {
        "source": "Competitor Accounts",
        "scanned_at": datetime.utcnow().isoformat(),
        "profiles": profiles,
        "total_scraped": len(items),
    }
