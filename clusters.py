"""Market clusters — clusters.py (HQ / multi-location layer)

The pilot bakery runs 8 locations across genuinely different Chicago markets, so a
single citywide read hides the thing that matters: a Dubai-chocolate special
that pops on Michigan Ave can flop in a suburban mall. Rather than scrape the
same national trends 8 times, we group the locations into a few MARKET CLUSTERS
that behave alike, scan neighborhood geo-tags once, and present per-cluster.

Efficient by design: national/brand trends are scanned once and shared across
all clusters (Dubai chocolate is Dubai chocolate everywhere). The per-cluster
signal is the LOCAL overlay — neighborhood geo-hashtags (all ride in one scan,
then grouped here by cluster) and each cluster's local competitors. Menu and
Brand DNA stay shared — it's one brand.

The clusters seed to data/clusters.json so the owner can edit locations, local
tags, and local competitors without code.
"""

from __future__ import annotations
import json

from tenancy import data_path

CLUSTERS_PATH = data_path("clusters.json")

# Buttercup Bakery — 8 locations grouped into 4 markets that behave alike.
DEFAULT_CLUSTERS: list[dict] = [
    {
        "key": "downtown",
        "name": "Downtown",
        "profile": "trend_forward",
        "blurb": "Tourists, office workers, high foot traffic — trend-forward, premium.",
        "locations": ["Downtown flagship", "Riverfront", "South Loop"],
        "geo_hashtags": ["chicagoloop", "michiganave", "streeterville", "southloop", "downtownchicago"],
        "competitors": ["stansdonuts", "doritedonuts", "firecakes"],
    },
    {
        "key": "lincoln_park",
        "name": "Lincoln Park",
        "profile": "balanced",
        "blurb": "Affluent residential, DePaul students — established foodie, classic-meets-trendy.",
        "locations": ["Lincoln Park"],
        "geo_hashtags": ["lincolnparkchicago", "lincolnpark"],
        "competitors": ["sweetmandybs"],
    },
    {
        "key": "suburban_malls",
        "name": "Suburban Malls",
        "profile": "classic",
        "blurb": "Suburban families, mall foot traffic — classic Americana, seasonal, kid-friendly.",
        "locations": ["Skokie mall", "Norridge mall", "Lombard mall"],
        "geo_hashtags": ["skokie", "oldorchard", "norridge", "lombard"],
        "competitors": ["nothingbundtcakes", "crumbl"],
    },
    {
        "key": "rosemont_outlet",
        "name": "Rosemont Outlet",
        "profile": "balanced",
        "blurb": "Outlet mall by O'Hare — travelers, tourists, bargain shoppers.",
        "locations": ["Rosemont outlet mall"],
        "geo_hashtags": ["rosemont"],
        "competitors": [],
    },
]


def load_clusters() -> list[dict]:
    """Owner-editable cluster list, seeding the demo defaults on first use."""
    if CLUSTERS_PATH.exists():
        try:
            data = json.loads(CLUSTERS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
        except (ValueError, OSError):
            pass
    CLUSTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLUSTERS_PATH.write_text(json.dumps(DEFAULT_CLUSTERS, indent=2, ensure_ascii=False),
                             encoding="utf-8")
    return list(DEFAULT_CLUSTERS)


def save_clusters(clusters: list[dict]) -> None:
    CLUSTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLUSTERS_PATH.write_text(json.dumps(clusters, indent=2, ensure_ascii=False),
                             encoding="utf-8")


def all_geo_hashtags() -> list[str]:
    """Every cluster's local tags, de-duped — the geo-tags to add to the scan
    watch lists so one refresh populates all clusters' local signal."""
    seen, out = set(), []
    for c in load_clusters():
        for t in c.get("geo_hashtags", []):
            t = t.lower().strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


# Per-market launch routing: which rising trends belong in which market. A
# market's "profile" sets how proven a trend must be before it fits there —
# trend-forward markets take early bets; classic markets wait for proven ones.
# This reuses the REAL confidence score (no new measurement) — it's Brand DNA's
# risk tolerance applied per market.
_PROFILE_FLOOR = {
    "trend_forward": {"high", "medium", "low"},
    "balanced": {"high", "medium"},
    "classic": {"high"},
}
_PROFILE_RATIONALE = {
    "trend_forward": "trend-forward — worth an early bet here",
    "balanced": "balanced — proven or well-corroborated",
    "classic": "classic-leaning — only well-proven trends",
}
PROFILES = ("trend_forward", "balanced", "classic")


def launch_picks_for_cluster(cluster: dict, scored: list[dict], limit: int = 3) -> list[dict]:
    """Rising/peaking trends that fit this market's profile, ranked by momentum.
    Uses the real confidence score — a market just sees the trends proven enough
    for its risk appetite."""
    allowed = _PROFILE_FLOOR.get(cluster.get("profile", "balanced"), _PROFILE_FLOOR["balanced"])
    picks = [c for c in (scored or [])
             if c.get("direction") in ("rising", "peaking") and c.get("confidence") in allowed]
    picks.sort(key=lambda c: -(c.get("delta") or 0))
    return picks[:limit]


def profile_rationale(cluster: dict) -> str:
    return _PROFILE_RATIONALE.get(cluster.get("profile", "balanced"), _PROFILE_RATIONALE["balanced"])


def _match(tag: str, geo: list[str]) -> bool:
    t = (tag or "").lower().replace(" ", "")
    return any(g in t or t in g for g in geo)


def group_by_cluster(instagram: dict | None, tiktok: dict | None) -> dict:
    """Group scanned IG/TikTok hashtag_trends into each cluster by matching the
    cluster's geo-hashtags. Returns {cluster_key: {local_ig:[...], local_tt:[...]}}.
    Clusters whose local tags haven't been scanned yet come back empty (honest —
    they populate after the geo-tags are added to the watch lists and a refresh
    runs), not fabricated."""
    ig_trends = (instagram or {}).get("hashtag_trends") or []
    tt_trends = (tiktok or {}).get("hashtag_trends") or []
    out: dict = {}
    for c in load_clusters():
        geo = [g.lower() for g in c.get("geo_hashtags", [])]
        out[c["key"]] = {
            "local_ig": [t for t in ig_trends if _match(t.get("hashtag", ""), geo)],
            "local_tt": [t for t in tt_trends if _match(t.get("hashtag", ""), geo)],
        }
    return out
