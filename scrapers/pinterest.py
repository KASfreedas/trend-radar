"""
Pinterest trend scraper via Apify (easyapi~pinterest-search-scraper).

NOTE: the previous actor (emastra~pinterest-scraper) was removed from Apify
(404). This actor searches Pinterest and returns *boards* matching a query,
each with a pinCount. So Pinterest is treated as an evergreen **topic-interest**
signal — which broad dessert topics have large Pinterest presence — rather than
a recency/velocity signal (Pinterest content resurfaces over time, so "fresh"
doesn't really apply here). Each query is one actor run, so the query list is
kept short to respect the budget.
Requires APIFY_TOKEN in .env.
"""
import os
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", encoding="utf-8-sig")

TOKEN = os.getenv("APIFY_TOKEN", "")
RUN_URL = "https://api.apify.com/v2/acts/easyapi~pinterest-search-scraper/run-sync-get-dataset-items"

# Broad enough to return boards (niche queries like "dubai chocolate cake" return
# nothing). Aligned to the flavor/format watch list.
SEARCH_QUERIES = [
    "dubai chocolate",
    "matcha dessert",
    "pistachio cake",
    "korean cake",
    "cupcake design",
    "bento cake",
]

LIMIT = 20  # actor minimum is 20


def _fmt(n):
    n = int(n)
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(n)


def _empty(error=None):
    return {
        "source": "Pinterest", "scanned_at": datetime.utcnow().isoformat(),
        "top_pins": [], "trending_topics": [],
        **({"error": error} if error else {}),
    }


def _search(query: str, limit: int) -> list[dict]:
    resp = requests.post(
        RUN_URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"query": query, "filter": "all", "limit": limit},
        timeout=180, params={"timeout": 180},
    )
    resp.raise_for_status()
    return resp.json()


def _search_resilient(query: str, limit: int) -> tuple[list[dict], bool]:
    """Pinterest returns wildly inconsistent results run-to-run — the same
    query has come back with 0 boards one scan and hundreds the next (proven
    in two real tests). A zero is therefore far more likely a transient blip
    than a true empty, so retry ONCE before trusting it. Bounded to a single
    extra paid run per zero query. Returns (items, retried)."""
    items = _search(query, limit)
    if items:
        return items, False
    return _search(query, limit), True


def run_full_scan(queries=None, limit=None):
    if not TOKEN:
        return _empty("No Apify token — add APIFY_TOKEN to .env")

    from scrapers._config import get_list
    qs = queries or get_list("pinterest", "queries", SEARCH_QUERIES)
    lim = limit or LIMIT
    boards = []
    topics = []
    last_err = None
    retried = 0

    for q in qs:
        try:
            items, did_retry = _search_resilient(q, lim)
            retried += 1 if did_retry else 0
        except Exception as e:
            last_err = str(e).split(" for url:")[0].strip()
            continue

        total_pins = 0
        for it in items:
            pin_count = int(it.get("pinCount") or 0)
            total_pins += pin_count
            boards.append({
                "title": (it.get("name") or "")[:80],
                "description": (it.get("owner") or ""),
                "image_url": it.get("coverURL") or it.get("thumbnailURL") or "",
                "url": it.get("slashURL") or "",
                "saves": pin_count,            # board size = interest proxy
                "saves_display": _fmt(pin_count),
                "query": q,
            })
        topics.append({
            "topic": q,
            "board_count": len(items),
            "total_pins": total_pins,
            "pin_count": total_pins,           # interest magnitude for this topic
        })

    if not boards and last_err:
        return _empty(last_err)

    boards.sort(key=lambda x: x["saves"], reverse=True)
    topics.sort(key=lambda x: x["total_pins"], reverse=True)

    return {
        "source": "Pinterest",
        "scanned_at": datetime.utcnow().isoformat(),
        "top_pins": boards[:9],
        "trending_topics": topics,
        "queries_searched": len(qs),
        "queries_retried": retried,
        "ranking": "board_interest",
    }
