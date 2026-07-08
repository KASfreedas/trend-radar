import random
import time
from pytrends.request import TrendReq
from datetime import datetime

# 30 keywords total (16 flavor + 7 packaging + 7 design).
# Edit these lists to change what the radar watches. Keep each group's terms
# specific ("pistachio pastry", not "pistachio") so Google Trends returns
# bakery-relevant interest rather than the raw ingredient.
FLAVOR_KEYWORDS = [
    "matcha cupcake",
    "bento cake",
    "dubai chocolate",
    "pistachio pastry",
    "ube dessert",
    "strawberry crunch cake",
    "crinkle cookies",
    "tres leches",        # Mexican — translates to cupcake/frosting
    "creme brulee",       # French
    "cannoli",            # Italian
    "biscoff dessert",
    "tiramisu cake",
    "black sesame dessert",
    "knafeh chocolate",
    "earl grey cake",
    "tahini cookie",
]

PACKAGING_KEYWORDS = [
    "bakery box design",
    "cupcake packaging trend",
    "clear cake container",
    "eco bakery packaging",
    "custom cake box",
    "minimalist bakery packaging",
    "kraft pastry box",
]

DESIGN_KEYWORDS = [
    "coquette cake",
    "bento cake design",
    "cottagecore baking",
    "Y2K cake design",
    "korean minimalist cake",
    "vintage lambeth cake",
    "piping cake design",
]

# Weekly granularity over a year: gives ~52 points so score.py can compute a
# true 30-day-vs-90-day trajectory and capture seasonality. (geo="US" keeps the
# signal national — national rising trends are the leading indicator a local
# shop wants to catch early. Use "US-IL" to localize to Illinois.)
TIMEFRAME = "today 12-m"
GEO = "US"


def _build_pytrends():
    # No retries= param — incompatible with urllib3 2.x
    return TrendReq(hl="en-US", tz=360, timeout=(10, 25))


MAX_RETRIES = 3          # extra attempts on HTTP 429 (Google rate limit)
BACKOFF = [8, 25, 60]    # seconds to wait before each retry (Google throttles by IP)


def _harvest_rising(pytrends, keywords: list[str]) -> list[dict]:
    """Pull Google's *rising* related queries for the just-built payload.

    Reuses the existing build_payload (no extra payload build) and is fully
    best-effort: any failure returns [] and never affects the trend results.
    These are terms Google sees accelerating — the radar's auto-discovery feed.
    """
    rising = []
    try:
        rq = pytrends.related_queries() or {}
    except Exception:
        return rising
    for seed, payload in rq.items():
        df = (payload or {}).get("rising")
        if df is None or getattr(df, "empty", True):
            continue
        for _, row in df.iterrows():
            query = str(row.get("query", "")).strip()
            if not query:
                continue
            raw = row.get("value")
            try:
                value, breakout = int(raw), False
            except (TypeError, ValueError):
                value, breakout = 10000, True  # pytrends "Breakout"
            rising.append({"query": query, "value": value, "breakout": breakout, "seed": seed})
    return rising


def _fetch_chunk(pytrends, keywords: list[str], timeframe: str = TIMEFRAME) -> tuple[list[dict], list[dict]]:
    """Returns (trend_results, rising_queries) for one chunk of <=5 keywords."""
    last_err = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=GEO)
            interest = pytrends.interest_over_time()
            if interest.empty:
                return [], _harvest_rising(pytrends, keywords)
            results = []
            for kw in keywords:
                if kw in interest.columns:
                    series = interest[kw]
                    avg = int(series.mean())
                    latest = int(series.iloc[-1])
                    prev_week = int(series.iloc[-2]) if len(series) >= 2 else latest
                    delta = latest - prev_week
                    # Full time series feeds both the dashboard chart and the
                    # briefing momentum scorer (score.py expects {date, value}).
                    time_series = [
                        {"date": idx.strftime("%Y-%m-%d"), "value": int(val)}
                        for idx, val in series.items()
                    ]
                    results.append(
                        {
                            "keyword": kw,
                            "avg_interest": avg,
                            "current_interest": latest,
                            "week_delta": delta,
                            "trend": "up" if delta > 2 else "down" if delta < -2 else "flat",
                            "time_series": time_series,
                        }
                    )
            return results, _harvest_rising(pytrends, keywords)
        except Exception as e:
            last_err = str(e)
            # Retry only the rate-limit case; back off with jitter so we stop
            # hammering Google (which only deepens the throttle).
            if "429" in last_err and attempt < MAX_RETRIES:
                time.sleep(BACKOFF[attempt] + random.uniform(0, 4))
                continue
            break
    fallback = [{"keyword": kw, "current_interest": 0, "trend": "flat",
                 "time_series": [], "error": last_err} for kw in keywords]
    return fallback, []


def _scan_keywords(keywords: list[str]) -> tuple[list[dict], list[dict]]:
    """Scan keywords in payload chunks of 5. Returns (results, raw rising rows)."""
    pt = _build_pytrends()
    results, rising = [], []
    chunks = list(range(0, len(keywords), 5))
    for n, i in enumerate(chunks):
        chunk = keywords[i: i + 5]
        r, rs = _fetch_chunk(pt, chunk)
        results.extend(r)
        rising.extend(rs)
        if n < len(chunks) - 1:
            time.sleep(2.5 + random.uniform(0, 2))  # jittered spacing to dodge 429s
    return results, rising


def _is_crushed(r: dict) -> bool:
    """True if a real term (no fetch error) came back all-zeros — meaning a
    higher-volume chunk-mate dominated Google's within-payload 0–100 scaling and
    rounded this term's whole series to 0 (so it has no readable trajectory)."""
    if r.get("error"):
        return False  # fetch failure, not a normalization crush
    ts = r.get("time_series") or []
    return bool(ts) and max((p.get("value", 0) for p in ts), default=0) == 0


def get_trends(keywords: list[str], _depth: int = 0) -> tuple[list[dict], list[dict]]:
    """Returns (sorted trend results, raw rising rows), with crushed terms
    re-queried among comparable-volume peers so each gets a real trajectory."""
    results, rising = _scan_keywords(keywords)

    crushed = [r["keyword"] for r in results if _is_crushed(r)]
    # Re-query only the crushed terms, grouped together (no breakout to dominate
    # them). Recurse up to twice in case the cohort still has an internal leader.
    if crushed and 0 < len(crushed) < len(keywords) and _depth < 2:
        time.sleep(2.0 + random.uniform(0, 2))
        requeried, rising2 = get_trends(crushed, _depth + 1)
        rq_by_kw = {r["keyword"]: r for r in requeried}
        merged = []
        for r in results:
            rq = rq_by_kw.get(r["keyword"])
            if rq is not None and _is_crushed(r) and not rq.get("error"):
                rq["cohort_normalized"] = True  # values relative to its volume cohort
                merged.append(rq)
            else:
                merged.append(r)
        results = merged
        rising.extend(rising2)

    results.sort(key=lambda x: x.get("current_interest", 0), reverse=True)
    return results, rising


def _aggregate_rising(raw: list[dict], seed_terms: list[str], limit: int = 15) -> list[dict]:
    """Dedupe + rank discovered rising queries, dropping ones we already watch.

    Ranking: breakouts first, then how many seeds surfaced it (broader signal),
    then the rising % value. Every number shown is a real Google figure.
    """
    # Match on full seed phrases only — sharing a single word (e.g. "pistachio")
    # must NOT suppress a genuine new combo like "pistachio knafeh".
    seed_phrases = [t.lower().strip() for t in seed_terms]

    agg: dict[str, dict] = {}
    for r in raw:
        q = r["query"].lower().strip()
        if not q:
            continue
        # Skip terms we already track: exact, or query just pads a full seed
        # phrase with noise ("pistachio pastry near me").
        if any(q == p or p in q for p in seed_phrases):
            continue
        cur = agg.get(q)
        if cur is None:
            agg[q] = {"query": r["query"].strip(), "value": r["value"],
                      "breakout": r["breakout"], "seeds": {r["seed"]}}
        else:
            cur["value"] = max(cur["value"], r["value"])
            cur["breakout"] = cur["breakout"] or r["breakout"]
            cur["seeds"].add(r["seed"])

    out = [{"query": v["query"], "value": v["value"], "breakout": v["breakout"],
            "seed_count": len(v["seeds"]), "seeds": sorted(v["seeds"])} for v in agg.values()]
    out.sort(key=lambda x: (x["breakout"], x["seed_count"], x["value"]), reverse=True)

    # Drop competitor brand names (not a menu opportunity) and anything the
    # owner has already dismissed as noise — see scrapers/_discovery.py.
    try:
        from scrapers._discovery import is_denylisted, competitor_denylist, dismissed_terms
        denylist, dismissed = competitor_denylist(), dismissed_terms()
        out = [r for r in out if not is_denylisted(r["query"], denylist, dismissed)]
    except Exception:
        pass  # discovery filtering is a nice-to-have, never block real trend data on it

    return out[:limit]


def run_full_scan() -> dict:
    from scrapers._config import get_list
    flavor_kw    = get_list("google", "flavor", FLAVOR_KEYWORDS)
    packaging_kw = get_list("google", "packaging", PACKAGING_KEYWORDS)
    design_kw    = get_list("google", "design", DESIGN_KEYWORDS)

    flavor, rf = get_trends(flavor_kw)
    packaging, rp = get_trends(packaging_kw)
    design, rd = get_trends(design_kw)

    all_seeds = flavor_kw + packaging_kw + design_kw
    rising_queries = _aggregate_rising(rf + rp + rd, all_seeds)

    return {
        "source": "Google Trends",
        "scanned_at": datetime.utcnow().isoformat(),
        "keyword_count": len(all_seeds),
        "flavor_trends": flavor,
        "packaging_trends": packaging,
        "design_trends": design,
        "rising_queries": rising_queries,  # auto-discovered accelerating searches
    }
