"""Vertical onboarding presets — presets.py (Tier 1)

A new tenant should be scanning sensible trends within minutes, not after a
consulting session. Each vertical bundles Google keyword groups, social
watch lists, subreddits, and a starter menu skeleton. `city` localizes the
social lists (e.g. "chicago" -> #chicagofood, #chicagobakery).

These are starting points the owner edits in Settings, not ceilings — the
same config.json override mechanism applies afterward.
"""

from __future__ import annotations

# Generic engagement/trend words every vertical wants on Reddit.
_REDDIT_BASE_KEYWORDS = [
    "trend", "trending", "new", "viral", "obsessed", "recipe",
    "aesthetic", "packaging", "seasonal", "limited",
]

VERTICALS: dict[str, dict] = {
    "cupcakes": {
        "label": "Cupcake / cake bakery",
        "google": {
            "flavor": ["matcha cupcake", "bento cake", "dubai chocolate",
                       "pistachio pastry", "ube dessert", "tres leches",
                       "biscoff dessert", "tiramisu cake", "earl grey cake",
                       "tahini cookie", "black sesame dessert"],
            "packaging": ["bakery box design", "cupcake packaging trend",
                          "eco bakery packaging", "custom cake box"],
            "design": ["coquette cake", "bento cake design", "vintage lambeth cake",
                       "korean minimalist cake", "piping cake design"],
        },
        "instagram": ["cakedecorating", "buttercream", "dripcake", "cupcakebouquet",
                      "desserttable", "viralcupcakes", "trendingdessert", "koreanbakery"],
        "tiktok": ["cupcake", "viralcake", "cakedecorating", "bentocake",
                   "dubaichocolate", "matcha", "pistachio", "dessert"],
        "pinterest": ["cupcake design", "bento cake", "matcha dessert",
                      "korean cake", "dubai chocolate"],
        "reddit_subs": ["Baking", "cakedecorating", "Cupcakes", "pastry",
                        "DessertPorn", "bakersofreddit"],
        "reddit_keywords": ["cupcake", "frosting", "buttercream", "filling",
                            "matcha", "pistachio", "bento", "lambeth"],
        "menu_formats": ["cupcake", "layer cake", "mini cupcake", "cake jar"],
    },
    "cookies": {
        "label": "Cookie shop",
        "google": {
            "flavor": ["stuffed cookie", "crinkle cookies", "brown butter cookie",
                       "miso cookie", "tahini cookie", "biscoff cookie",
                       "matcha cookie", "red velvet cookie", "smores cookie"],
            "packaging": ["cookie box design", "cookie packaging", "eco bakery packaging"],
            "design": ["giant cookie", "cookie cake design", "stuffed cookie trend"],
        },
        "instagram": ["cookiesofinstagram", "stuffedcookies", "cookiedecorating",
                      "gourmetcookies", "cookiebox", "viralcookies"],
        "tiktok": ["cookie", "stuffedcookies", "cookierecipe", "crumbl",
                   "gourmetcookies", "bakingtiktok"],
        "pinterest": ["gourmet cookies", "stuffed cookies", "cookie box",
                      "cookie decorating"],
        "reddit_subs": ["cookies", "Baking", "bakersofreddit", "DessertPorn"],
        "reddit_keywords": ["cookie", "stuffed", "gooey", "brown butter",
                            "miso", "tahini", "crinkle"],
        "menu_formats": ["cookie", "stuffed cookie", "cookie sandwich", "cookie cake"],
    },
    "donuts": {
        "label": "Donut shop",
        "google": {
            "flavor": ["mochi donut", "filled donut", "croissant donut", "ube donut",
                       "matcha donut", "creme brulee donut", "biscoff donut"],
            "packaging": ["donut box design", "bakery box design", "eco bakery packaging"],
            "design": ["donut wall", "donut tower", "mini donut trend"],
        },
        "instagram": ["donutsofinstagram", "mochidonuts", "gourmetdonuts",
                      "donutworthy", "vegandonuts"],
        "tiktok": ["donut", "mochidonut", "donutshop", "filleddonut", "bakingtiktok"],
        "pinterest": ["gourmet donuts", "mochi donut", "donut wall", "donut box"],
        "reddit_subs": ["donuts", "Baking", "bakersofreddit", "DessertPorn"],
        "reddit_keywords": ["donut", "doughnut", "mochi", "filled", "glaze", "yeast"],
        "menu_formats": ["yeast donut", "cake donut", "mochi donut", "donut hole"],
    },
    "coffee_shop": {
        "label": "Coffee shop / café",
        "google": {
            "flavor": ["pistachio latte", "ube latte", "brown sugar shaken espresso",
                       "lavender matcha", "maple oat latte", "spanish latte",
                       "einspanner", "hojicha latte"],
            "packaging": ["coffee cup design", "cafe cup sleeve", "eco coffee packaging"],
            "design": ["latte art trend", "cafe aesthetic", "korean cafe design"],
        },
        "instagram": ["coffeeshopvibes", "latteart", "specialtycoffee", "cafehopping",
                      "matchalatte", "coffeetrends"],
        "tiktok": ["coffeetok", "latte", "matcha", "espresso", "cafevlog",
                   "coffeerecipe"],
        "pinterest": ["latte art", "cafe aesthetic", "coffee bar", "matcha latte"],
        "reddit_subs": ["Coffee", "espresso", "barista", "cafe"],
        "reddit_keywords": ["latte", "espresso", "syrup", "matcha", "cold brew",
                            "seasonal", "signature drink"],
        "menu_formats": ["latte", "cold brew", "espresso drink", "seasonal drink"],
    },
    "ice_cream": {
        "label": "Ice cream / gelato shop",
        "google": {
            "flavor": ["ube ice cream", "black sesame ice cream", "pistachio gelato",
                       "brown butter ice cream", "miso caramel", "halo halo",
                       "soft serve trend"],
            "packaging": ["ice cream cup design", "gelato packaging", "pint packaging"],
            "design": ["soft serve swirl", "croissant ice cream sandwich",
                       "taiyaki cone"],
        },
        "instagram": ["icecreamlover", "softserve", "gelatoart", "icecreamshop",
                      "taiyaki"],
        "tiktok": ["icecream", "softserve", "gelato", "icecreamrecipe", "desserttok"],
        "pinterest": ["soft serve", "ice cream shop", "gelato flavors",
                      "ice cream sandwich"],
        "reddit_subs": ["icecreamery", "DessertPorn", "FoodPorn"],
        "reddit_keywords": ["ice cream", "gelato", "soft serve", "swirl", "cone",
                            "sundae"],
        "menu_formats": ["scoop", "soft serve", "sundae", "ice cream sandwich", "pint"],
    },
}


def list_verticals() -> list[dict]:
    return [{"slug": slug, "label": v["label"],
             "keyword_count": sum(len(g) for g in v["google"].values()),
             "hashtag_count": len(v["instagram"]) + len(v["tiktok"])}
            for slug, v in VERTICALS.items()]


def _localized(tags: list[str], city: str | None) -> list[str]:
    if not city:
        return list(tags)
    c = city.strip().lower().replace(" ", "")
    return list(tags) + [f"{c}food", f"{c}foodie", f"{c}desserts", f"{c}bakery"]


def build_config_sections(vertical: str, city: str | None = None) -> dict:
    """Watch-list config.json sections for a vertical. Raises KeyError on an
    unknown vertical slug."""
    v = VERTICALS[vertical]
    return {
        "google": {k: list(kw) for k, kw in v["google"].items()},
        "instagram": {"hashtags": _localized(v["instagram"], city)},
        "tiktok": {"hashtags": _localized(v["tiktok"], city)},
        "pinterest": {"queries": list(v["pinterest"])},
        "reddit": {"subreddits": list(v["reddit_subs"]),
                   "keywords": _REDDIT_BASE_KEYWORDS + list(v["reddit_keywords"])},
    }


def build_starter_menu(vertical: str) -> dict:
    v = VERTICALS[vertical]
    return {"flavors": [], "formats": list(v["menu_formats"]),
            "toppings": [], "seasonal": []}
