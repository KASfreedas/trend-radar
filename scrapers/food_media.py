"""
Food media trend scraper — reads RSS feeds from major food publications.
Aggregates baking/pastry content to surface editorial trend signals.
All feeds are publicly available; no authentication required.
"""
import requests
from xml.etree import ElementTree as ET
from datetime import datetime

HEADERS = {"User-Agent": "TrendRadarBot/1.0 (bakery trend research)"}

FEEDS = [
    ("Bon Appétit",   "https://www.bonappetit.com/feed/rss"),
    ("Food52",        "https://food52.com/blog.rss"),
    ("Serious Eats",  "https://www.seriouseats.com/feeds/all"),
    ("The Kitchn",    "https://www.thekitchn.com/main.rss"),
    ("Epicurious",    "https://www.epicurious.com/feed/rss"),
    ("King Arthur",   "https://www.kingarthurbaking.com/blog/feed"),
]

BAKING_KEYWORDS = [
    "cake", "cupcake", "cookie", "pastry", "bread", "croissant",
    "baking", "dessert", "frosting", "ganache", "filling",
    "matcha", "ube", "pistachio", "dubai", "bento", "crinkle",
    "sourdough", "laminated", "stuffed", "layered",
    "packaging", "bakery", "trend", "viral", "new",
]

# XML namespace map for common RSS/Atom formats
NS_MAP = {
    "atom":    "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc":      "http://purl.org/dc/elements/1.1/",
}


def _safe_text(el) -> str:
    return el.text.strip() if el is not None and el.text else ""


def _parse_feed(xml_text: str, source: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    articles = []
    # RSS 2.0 format
    for item in root.findall(".//item"):
        title = _safe_text(item.find("title"))
        link  = _safe_text(item.find("link"))
        pub   = _safe_text(item.find("pubDate"))
        if title:
            articles.append({"title": title, "url": link, "published": pub, "source": source})
    # Atom format
    for entry in root.findall(f".//{{{NS_MAP['atom']}}}entry"):
        title_el = entry.find(f"{{{NS_MAP['atom']}}}title")
        link_el  = entry.find(f"{{{NS_MAP['atom']}}}link")
        upd_el   = entry.find(f"{{{NS_MAP['atom']}}}updated")
        title = _safe_text(title_el)
        link  = link_el.attrib.get("href", "") if link_el is not None else ""
        pub   = _safe_text(upd_el)
        if title:
            articles.append({"title": title, "url": link, "published": pub, "source": source})
    return articles


def _is_baking_relevant(title: str) -> bool:
    low = title.lower()
    return any(kw in low for kw in BAKING_KEYWORDS)


def _score(article: dict) -> int:
    title = article.get("title", "").lower()
    return sum(1 for kw in BAKING_KEYWORDS if kw in title)


def run_full_scan() -> dict:
    all_articles = []
    sources_ok = []
    for name, url in FEEDS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                parsed = _parse_feed(resp.text, name)
                all_articles.extend(parsed)
                sources_ok.append(name)
        except Exception:
            pass

    # Filter to baking-relevant and score
    relevant = [a for a in all_articles if _is_baking_relevant(a["title"])]
    for a in relevant:
        a["relevance"] = _score(a)
    relevant.sort(key=lambda x: x["relevance"], reverse=True)

    # Keyword frequency across all relevant articles
    counts: dict[str, int] = {}
    for a in relevant:
        title = a.get("title", "").lower()
        for kw in BAKING_KEYWORDS:
            if kw in title:
                counts[kw] = counts.get(kw, 0) + 1

    hot_topics = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "source": "Food Media",
        "scanned_at": datetime.utcnow().isoformat(),
        "top_articles": relevant[:12],
        "hot_topics": [{"keyword": k, "count": v} for k, v in hot_topics[:15]],
        "sources_fetched": sources_ok,
        "total_articles_scanned": len(all_articles),
    }
