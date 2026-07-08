"""
Menu-gap mapping — briefing/gaps.py

Diffs scored trend candidates against data/menu.json:
  gaps    : trending terms NOT on the menu (highest-value output)
  covered : trending terms already on the menu
  retire  : menu items whose trend direction is "fading"
"""

from __future__ import annotations
import json

from tenancy import data_path

MENU_PATH = data_path("menu.json")


def _load_menu() -> dict:
    if MENU_PATH.exists():
        return json.loads(MENU_PATH.read_text(encoding="utf-8"))
    return {"flavors": [], "formats": [], "toppings": [], "seasonal": []}


def _normalize(s: str) -> str:
    return s.lower().strip()


def _menu_terms(menu: dict) -> set[str]:
    """Flatten all menu items into a set of normalized strings."""
    terms: set[str] = set()
    for key in ("flavors", "formats", "toppings", "seasonal"):
        for item in menu.get(key, []):
            terms.add(_normalize(item))
            # also add individual words for partial matching
            for word in _normalize(item).split():
                if len(word) > 3:
                    terms.add(word)
    return terms


def _on_menu(term: str, menu_terms: set[str]) -> bool:
    t = _normalize(term)
    if t in menu_terms:
        return True
    # partial: any menu word appears in term or vice versa
    term_words = t.split()
    for word in term_words:
        if len(word) > 3 and word in menu_terms:
            return True
    return False


def compute_gaps(scored_candidates: list[dict]) -> dict:
    """
    Returns {"gaps": [...], "covered": [...], "retire": [...]}.
    Only includes candidates with direction != "flat" for gap/covered.
    Retire candidates are fading items found on menu.
    """
    menu = _load_menu()
    menu_terms = _menu_terms(menu)

    gaps = []
    covered = []
    retire = []

    for c in scored_candidates:
        term = c.get("term", "")
        direction = c.get("direction", "flat")
        category = c.get("category", "")
        # Packaging/design terms describe presentation, not products — they
        # were never "on the menu" to begin with, so only flavor terms can
        # be matched against actual menu items (covered/retire).
        on_menu = category == "flavor" and _on_menu(term, menu_terms)

        if direction == "fading" and on_menu:
            retire.append({**c, "on_menu": True})
        elif direction in ("rising", "peaking"):
            if on_menu:
                covered.append({**c, "on_menu": True})
            else:
                gaps.append({**c, "on_menu": False})

    # Sort gaps by confidence then current_interest
    conf_rank = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda c: (conf_rank.get(c["confidence"], 3), -c.get("current_interest", 0)))
    covered.sort(key=lambda c: -c.get("current_interest", 0))
    retire.sort(key=lambda c: c.get("delta", 0))

    return {
        "gaps": gaps,
        "covered": covered,
        "retire": retire,
        "menu_snapshot": {
            "flavors": menu.get("flavors", []),
            "formats": menu.get("formats", []),
        },
    }
