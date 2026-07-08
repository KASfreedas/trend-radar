"""
Shared keyword-discovery denylist — scrapers/_discovery.py

A real end-to-end test (2026-07-01) found Google's rising-query discovery
suggesting things that aren't useful new watch-list candidates: a competitor's
own brand name ("crumbl", "crumbl cookie" — already a tracked competitor, not
a menu opportunity) and pure noise from an unrelated viral topic that happened
to co-occur in Google's related searches ("labubu", a collectible toy).

Two mechanisms, deliberately kept separate:
  - competitor_denylist(): deterministic, real data — anything matching a
    tracked competitor's name/handle/tag never surfaces as a "new keyword."
  - dismissed_terms(): no heuristic can reliably tell food from noise (there's
    no LLM call in this pipeline to ask), so the owner can permanently hide a
    one-off bad suggestion once seen. Persisted in data/config.json, same
    pattern as every other owner-editable list in this app.
"""

from __future__ import annotations


def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def competitor_denylist() -> set[str]:
    names: set[str] = set()
    try:
        from briefing.competitors import load_competitors
        for c in load_competitors():
            names.add(_norm(c.get("name", "")))
            names.add(_norm(c.get("instagram", "")))
    except Exception:
        pass
    try:
        from scrapers import instagram as ig_mod
        for t in (ig_mod.LOCAL_COMP_TAGS + ig_mod.NATIONAL_TAGS):
            names.add(_norm(t))
    except Exception:
        pass
    try:
        from scrapers import tiktok as tt_mod
        for t in tt_mod.COMPETITOR_TAGS:
            names.add(_norm(t))
    except Exception:
        pass
    names.discard("")
    return names


def dismissed_terms() -> set[str]:
    from scrapers._config import get_list
    return {t.lower().strip() for t in get_list("discovery", "dismissed", [])}


def is_denylisted(term: str, denylist: set[str] | None = None, dismissed: set[str] | None = None) -> bool:
    denylist = competitor_denylist() if denylist is None else denylist
    dismissed = dismissed_terms() if dismissed is None else dismissed
    if term.lower().strip() in dismissed:
        return True
    q = _norm(term)
    if not q:
        return False
    return any(q == d or (len(d) > 2 and (q in d or d in q)) for d in denylist)


def dismiss(term: str) -> None:
    from scrapers._config import load_config, save_config
    cfg = load_config()
    lst = cfg.setdefault("discovery", {}).setdefault("dismissed", [])
    t = term.lower().strip()
    if t and t not in lst:
        lst.append(t)
    save_config(cfg)
