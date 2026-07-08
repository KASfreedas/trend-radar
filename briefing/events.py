"""Upcoming-events engine — briefing/events.py

Bakeries plan specials around calendar moments, and they need lead time: a
Valentine's line has to be decided by late January. This module keeps a
curated calendar of bakery-relevant events (major holidays, floating holidays
computed by rule, and national dessert days), computes what's coming inside a
planning window, and cross-references each event against the CURRENT scored
trend terms so a suggestion arrives with real evidence attached.

Same honesty rule as everywhere else: dates are facts, keyword matches are
mechanical, and every statistic shown next to a tie-in comes from the scored
data — nothing here invents a number. If no trend matches an event, the event
still shows (the date is real) with no tie-in claimed.

The calendar seeds to data/events.json on first use so the owner can edit it
(add local events — Chicago marathon, neighborhood festivals) without code.
"""

from __future__ import annotations
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from tenancy import data_path

EVENTS_PATH = data_path("events.json")

# How far ahead the radar looks, and default prep time for a bakery special.
DEFAULT_WINDOW_DAYS = 60
DEFAULT_LEAD_DAYS = 21


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th `weekday` (Mon=0..Sun=6) of a month. n=-1 means the last one."""
    if n > 0:
        d = date(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        return d + timedelta(days=offset + 7 * (n - 1))
    # last weekday of month
    d = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    offset = (d.weekday() - weekday) % 7
    return d - timedelta(days=offset)


# Easter (Anonymous Gregorian algorithm) — needed for its own tie-ins and
# because several bakery moments key off it.
def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(month, 1, 1).replace(year=year, month=month, day=day + 1)


def _fixed(name, month, day, lead, keywords):
    return {"name": name, "rule": {"type": "fixed", "month": month, "day": day},
            "lead_days": lead, "keywords": keywords}


def _floating(name, month, weekday, n, lead, keywords):
    return {"name": name, "rule": {"type": "nth_weekday", "month": month,
            "weekday": weekday, "n": n}, "lead_days": lead, "keywords": keywords}


# Curated defaults — bakery-relevant, US-centric. Owner-editable after seeding.
_DEFAULT_EVENTS: list[dict] = [
    _fixed("Valentine's Day", 2, 14, 28, ["valentine", "heart", "red velvet", "chocolate covered strawberry", "rose"]),
    _fixed("St. Patrick's Day", 3, 17, 21, ["st patrick", "green", "mint", "irish cream", "shamrock"]),
    {"name": "Easter", "rule": {"type": "easter"}, "lead_days": 28,
     "keywords": ["easter", "spring", "carrot cake", "pastel", "egg", "bunny"]},
    _floating("Mother's Day", 5, 6, 2, 28, ["mother", "floral", "brunch", "pastel", "bouquet"]),
    _fixed("Graduation Season kickoff", 5, 15, 21, ["graduation", "grad cap", "class of"]),
    _floating("National Donut Day", 6, 4, 1, 14, ["donut", "doughnut"]),
    _floating("Father's Day", 6, 6, 3, 21, ["father", "dad"]),
    _fixed("Independence Day", 7, 4, 21, ["4th of july", "fourth of july", "stars", "red white", "patriotic", "berry"]),
    _floating("National Ice Cream Day", 7, 6, 3, 14, ["ice cream", "soft serve", "sundae"]),
    _fixed("National Cheesecake Day", 7, 30, 14, ["cheesecake"]),
    _fixed("National S'mores Day", 8, 10, 14, ["smores", "s'mores", "marshmallow", "campfire"]),
    _fixed("Back to School", 8, 15, 21, ["back to school", "lunchbox", "school"]),
    _floating("Labor Day", 9, 0, 1, 14, ["labor day", "end of summer", "picnic"]),
    _fixed("National Coffee Day", 9, 29, 14, ["coffee", "espresso", "latte", "mocha"]),
    _fixed("Halloween", 10, 31, 28, ["halloween", "pumpkin", "spooky", "ghost", "candy"]),
    _fixed("National Dessert Day", 10, 14, 14, ["dessert"]),
    _floating("Thanksgiving", 11, 3, 4, 28, ["thanksgiving", "pumpkin", "pecan", "pie", "maple"]),
    _fixed("National Cupcake Day", 12, 15, 14, ["cupcake"]),
    _fixed("Christmas", 12, 25, 35, ["christmas", "gingerbread", "peppermint", "eggnog", "yule"]),
    _fixed("New Year's Eve", 12, 31, 21, ["new year", "champagne", "gold", "countdown"]),
]


# ── Per-market local events (HQ / multi-location) ────────────────────────────
# Recurring annual Chicago-area events tagged to a market cluster. They recur
# every year (rule-based dates), so they're seeded once and reused. Longer lead
# times give each market 2+ months to plan a themed special. There's no clean,
# cheap API for hyperlocal town events, so this is a curated, owner-editable
# calendar (data/local_events.json) — reliable, not scraped.
LOCAL_EVENTS_PATH = data_path("local_events.json")


def _fixed_local(name, cluster, month, day, lead, keywords):
    e = _fixed(name, month, day, lead, keywords)
    e["cluster"] = cluster
    return e


def _float_local(name, cluster, month, weekday, n, lead, keywords):
    e = _floating(name, month, weekday, n, lead, keywords)
    e["cluster"] = cluster
    return e


_DEFAULT_LOCAL_EVENTS = [
    # Downtown — Loop / Michigan Ave / Streeterville / South Loop
    _fixed_local("Taste of Chicago", "downtown", 9, 5, 45, ["taste of chicago", "food festival", "summer"]),
    _float_local("Chicago Air & Water Show", "downtown", 8, 5, 3, 30, ["air and water show", "lakefront", "summer"]),
    _float_local("Chicago Marathon", "downtown", 10, 6, 2, 45, ["marathon", "runners", "carb"]),
    _fixed_local("Mag Mile Lights Festival", "downtown", 11, 22, 45, ["mag mile", "lights festival", "tree lighting", "holiday"]),
    # Lincoln Park
    _fixed_local("DePaul Move-In / Welcome Week", "lincoln_park", 9, 2, 30, ["depaul", "students", "back to school", "move in"]),
    _fixed_local("Green City Market Opening", "lincoln_park", 5, 3, 21, ["farmers market", "green city", "local", "spring"]),
    # Suburban Malls — Skokie / Norridge / Lombard
    _fixed_local("Skokie Festival of Cultures", "suburban_malls", 5, 18, 30, ["festival of cultures", "skokie", "family"]),
    _fixed_local("Skokie Backlot Bash", "suburban_malls", 8, 29, 30, ["backlot bash", "skokie", "end of summer", "family"]),
    _fixed_local("Mall Holiday Shopping Kickoff", "suburban_malls", 11, 1, 45, ["holiday shopping", "gifts", "black friday", "family"]),
    # Rosemont Outlet
    _fixed_local("Rosemont Summer Concert Series", "rosemont_outlet", 7, 3, 21, ["rosemont", "concert", "summer", "parkway bank"]),
    _fixed_local("Fashion Outlets Holiday Shopping", "rosemont_outlet", 11, 1, 45, ["holiday shopping", "outlet", "gifts", "travelers"]),
]


def _load_local_calendar() -> list[dict]:
    """Owner-editable per-market event calendar, seeding defaults on first use."""
    if LOCAL_EVENTS_PATH.exists():
        try:
            cal = json.loads(LOCAL_EVENTS_PATH.read_text(encoding="utf-8"))
            if isinstance(cal, list) and cal:
                return cal
        except (ValueError, OSError):
            pass
    LOCAL_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_EVENTS_PATH.write_text(json.dumps(_DEFAULT_LOCAL_EVENTS, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
    return list(_DEFAULT_LOCAL_EVENTS)


def _load_calendar() -> list[dict]:
    """Load the owner-editable calendar, seeding defaults on first use."""
    if EVENTS_PATH.exists():
        try:
            cal = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
            if isinstance(cal, list) and cal:
                return cal
        except (ValueError, OSError):
            pass
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_PATH.write_text(json.dumps(_DEFAULT_EVENTS, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    return list(_DEFAULT_EVENTS)


def _resolve_date(rule: dict, year: int) -> date | None:
    try:
        t = rule.get("type")
        if t == "fixed":
            return date(year, int(rule["month"]), int(rule["day"]))
        if t == "nth_weekday":
            return _nth_weekday(year, int(rule["month"]), int(rule["weekday"]), int(rule["n"]))
        if t == "easter":
            return _easter(year)
    except (KeyError, ValueError, TypeError):
        return None
    return None


def upcoming_events(window_days: int = DEFAULT_WINDOW_DAYS,
                    today: date | None = None, cluster: str | None = None) -> list[dict]:
    """Events inside the window, soonest first, each with real planning math:
    days_until, the decide-by date (event minus lead), and a status —
    'act_now' once the decide-by date is within 7 days (or passed but the
    event hasn't), else 'upcoming'.

    cluster=None returns the national calendar; a cluster key returns that
    market's local events. Local events use a wider default window so a market
    sees them 2+ months out with time to plan."""
    today = today or datetime.now(timezone.utc).date()
    if cluster:
        calendar = [e for e in _load_local_calendar() if e.get("cluster") == cluster]
        if window_days == DEFAULT_WINDOW_DAYS:
            window_days = 90  # give local events a longer planning runway
    else:
        calendar = _load_calendar()
    out = []
    for ev in calendar:
        for year in (today.year, today.year + 1):
            d = _resolve_date(ev.get("rule") or {}, year)
            if not d:
                continue
            days_until = (d - today).days
            if 0 <= days_until <= window_days:
                lead = int(ev.get("lead_days", DEFAULT_LEAD_DAYS))
                decide_by = d - timedelta(days=lead)
                status = "act_now" if (decide_by - today).days <= 7 else "upcoming"
                out.append({
                    "name": ev["name"],
                    "date": d.isoformat(),
                    "days_until": days_until,
                    "lead_days": lead,
                    "decide_by": decide_by.isoformat(),
                    "status": status,
                    "keywords": list(ev.get("keywords") or []),
                    "cluster": ev.get("cluster"),
                })
                break  # matched this event once; don't add next year's too
    out.sort(key=lambda e: e["days_until"])
    return out


# ── Occasion buzz (live demand signal) ───────────────────────────────────────
# The calendar above says WHEN a dated moment lands. Occasion buzz is the other
# half of "looking for events": it reads what people are actually posting about
# right now and tells the owner which CAKE-ORDER occasion is heating up in the
# feeds — a demand nudge, not a dated event. Counts are real mention tallies
# from the social scans; nothing is invented. An occasion posting in its
# peak-season month is flagged in_season so a seasonal spike sorts to the top.
_OCCASION_BUZZ = [
    {"label": "Graduation",
     "variants": {"graduation", "grad", "gradparty", "gradcap", "classof", "gradseason", "gradcake"},
     "months": {5, 6}, "note": "Grad-cap toppers and class-of designs — stock them while the season peaks."},
    {"label": "Wedding & bridal",
     "variants": {"wedding", "bridal", "bride", "bridalshower", "weddingcake", "engagement"},
     "months": {5, 6, 7, 8, 9, 10}, "note": "Wedding & bridal-shower season — push tiered cakes and tasting boxes."},
    {"label": "Baby shower / gender reveal",
     "variants": {"babyshower", "genderreveal", "genderrevealcake", "newbaby", "itsagirl", "itsaboy"},
     "months": set(range(1, 13)), "note": "Reveal cupcakes and pastel sets for baby-shower and gender-reveal orders."},
    {"label": "Birthday",
     "variants": {"birthday", "bday", "birthdaycake", "birthdayparty", "birthdaygirl", "birthdayboy"},
     "months": set(range(1, 13)), "note": "Your steady core — keep custom birthday options front and center."},
    {"label": "Anniversary",
     "variants": {"anniversary", "anniversarycake", "anniversaryparty"},
     "months": set(range(1, 13)), "note": "Elegant two-person cakes and dessert boxes for anniversary orders."},
]


def _norm_occ(s) -> str:
    """Lowercase, strip to bare word/hashtag token for occasion matching."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _occasion_counts(src: dict | None) -> Counter:
    """Pull (term -> mention count) from a social scan's caption words and
    co-hashtags, tolerant of the small shape differences between scrapers."""
    counts: Counter = Counter()
    if not isinstance(src, dict):
        return counts
    for w in (src.get("trending_words") or []):
        t = _norm_occ(w.get("word"))
        if t:
            counts[t] += int(w.get("count") or 0)
    for key in ("related_tags", "hashtags", "trending_hashtags"):
        for item in (src.get(key) or []):
            t = _norm_occ(item.get("tag") or item.get("hashtag") or item.get("name"))
            if t:
                counts[t] += int(item.get("count") or item.get("post_count") or 1)
    return counts


def occasion_buzz(instagram: dict | None, tiktok: dict | None = None,
                  today: date | None = None, min_mentions: int = 3) -> list[dict]:
    """Which cake-order OCCASIONS are trending in the social feeds right now.

    Reads Instagram (and TikTok, if given) caption words + co-hashtags, tallies
    mentions per occasion, and returns those clearing `min_mentions`. Sorted
    in-season first, then by mention volume, so a real seasonal spike leads.
    This is the demand-side companion to the fixed event calendar."""
    today = today or datetime.now(timezone.utc).date()
    counts = _occasion_counts(instagram)
    counts.update(_occasion_counts(tiktok))

    out = []
    for occ in _OCCASION_BUZZ:
        hits = {v: counts[v] for v in occ["variants"] if counts.get(v)}
        total = sum(hits.values())
        if total >= min_mentions:
            # A narrow-window occasion (graduation, wedding) currently in its
            # window is a real SEASONAL SPIKE. Year-round occasions (birthday,
            # anniversary) are always "in season" — that's steady core demand,
            # not a spike — so they don't earn the peak badge or the top slot.
            seasonal = len(occ["months"]) < 12
            in_season = seasonal and today.month in occ["months"]
            out.append({
                "occasion": occ["label"],
                "mentions": total,
                "terms": sorted(hits, key=lambda x: -hits[x]),
                "seasonal": seasonal,
                "in_season": in_season,
                "note": occ["note"],
            })
    out.sort(key=lambda o: (not o["in_season"], -o["mentions"]))
    return out


def event_tie_ins(events: list[dict], scored: list[dict]) -> list[dict]:
    """Attach currently-trending terms to each event by keyword match.
    Only rising/peaking terms qualify, and each tie-in carries that term's
    REAL direction/confidence/evidence — the suggestion is 'this event is
    coming AND this matching term is measurably moving', nothing more."""
    active = [c for c in scored if c.get("direction") in ("rising", "peaking")]
    out = []
    for ev in events:
        kws = [k.lower() for k in ev.get("keywords") or []]
        ties = []
        for c in active:
            term = (c.get("term") or "").lower()
            if any(k in term or term in k for k in kws):
                ties.append({
                    "term": c["term"],
                    "direction": c["direction"],
                    "confidence": c.get("confidence", "low"),
                    "category": c.get("category", ""),
                    "evidence": list(c.get("evidence") or [])[:2],
                })
        out.append({**ev, "tie_ins": ties})
    return out
