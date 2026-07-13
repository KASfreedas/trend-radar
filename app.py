import os
import re
import json
import secrets
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, Response, request, session, redirect, url_for

from scrapers import google_trends, reddit, food_media, instagram, tiktok, pinterest, competitor_accounts
from tenancy import data_path

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "").strip() or secrets.token_hex(32)

# ── Login gate (Phase 4) ─────────────────────────────────────────────────────
# Off by default (local dev). Set APP_PASSWORD in .env before deploying
# anywhere reachable off localhost — every route except /login gets gated.
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
_PUBLIC_PATHS = {"/login"}


@app.before_request
def _require_login():
    if not APP_PASSWORD:
        return
    if request.path in _PUBLIC_PATHS or request.path.startswith("/static"):
        return
    if not session.get("authed"):
        return redirect(url_for("login", next=request.path))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        submitted = request.form.get("password", "")
        if APP_PASSWORD and secrets.compare_digest(submitted, APP_PASSWORD):
            session["authed"] = True
            return redirect(request.args.get("next") or url_for("index"))
        error = "Incorrect password."
    return render_template("login.html", error=error, bakery_name=_bakery_name())


@app.route("/logout")
def logout():
    session.pop("authed", None)
    return redirect(url_for("login"))

_cache: dict = {
    "google":     None,
    "reddit":     None,
    "food_media": None,
    "instagram":  None,
    "tiktok":     None,
    "pinterest":  None,
    "last_full_refresh": None,
    "is_refreshing": False,
}
_lock = threading.Lock()

SOURCES = ("google", "reddit", "food_media", "instagram", "tiktok", "pinterest")


def _hydrate_cache_from_disk() -> None:
    """Load each source's persisted last-good result into the in-memory cache
    at boot. Without this, a restart right before a scheduled briefing send
    would email the client an empty 'quiet month' even though real data sits
    on disk (found the hard way, 2026-07-05: /briefing/run after a restart
    produced a 0/6-sources briefing and overwrote the month's archive)."""
    from scrapers._reliability import load_last_good
    for name in SOURCES:
        data = load_last_good(name)
        if data is not None:
            _cache[name] = data


_hydrate_cache_from_disk()
_SCRAPERS = {
    "google":     google_trends.run_full_scan,
    "reddit":     reddit.run_full_scan,
    "food_media": food_media.run_full_scan,
    "instagram":  instagram.run_full_scan,
    "tiktok":     tiktok.run_full_scan,
    "pinterest":  pinterest.run_full_scan,
}


def _run(name):
    from scrapers._reliability import run_with_fallback
    result = run_with_fallback(name, _SCRAPERS[name])
    with _lock:
        _cache[name] = result


def refresh_all(background=False):
    def _do():
        with _lock:
            _cache["is_refreshing"] = True
        threads = [threading.Thread(target=_run, args=(name,)) for name in SOURCES]
        for t in threads: t.start()
        for t in threads: t.join()
        with _lock:
            _cache["last_full_refresh"] = datetime.utcnow().isoformat()
            _cache["is_refreshing"] = False

    if background:
        threading.Thread(target=_do, daemon=True).start()
    else:
        _do()


def _bakery_name() -> str:
    """Configured business name (Settings-editable); demo default ships generic."""
    from scrapers._config import get_value
    return get_value("business", "name", "Buttercup Bakery")


@app.route("/")
def index():
    return render_template("index.html", app_password_set=bool(APP_PASSWORD),
                           bakery_name=_bakery_name())

@app.route("/api/data")
def api_data():
    with _lock:
        return jsonify({k: _cache[k] for k in _cache})

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    with _lock:
        if _cache["is_refreshing"]:
            return jsonify({"status": "already_running"})
    refresh_all(background=True)
    return jsonify({"status": "started"})

@app.route("/api/refresh-light", methods=["POST"])
def api_refresh_light():
    """Modest end-to-end scrape — small tag subsets + low limits to conserve
    free Apify credits and reduce Google rate-limit risk. Populates the same
    cache the dashboard and briefing read.

    Runs every source through scrapers._reliability.run_with_fallback(), same
    as the full refresh — a failure here falls back to last-good data and
    fires an operator alert, and a success feeds the snapshot history that
    powers the IG/TikTok sparklines. (A real test on 2026-07-01 found this
    route previously bypassed that layer entirely via a bare try/except —
    fixed here.)"""
    with _lock:
        if _cache["is_refreshing"]:
            return jsonify({"status": "already_running"})

    def _light_google():
        from scrapers import google_trends as gt
        flavor, rising_raw = gt.get_trends(gt.FLAVOR_KEYWORDS[:5])
        return {
            "source": "Google Trends", "scanned_at": datetime.utcnow().isoformat(),
            "flavor_trends": flavor, "packaging_trends": [], "design_trends": [],
            "rising_queries": gt._aggregate_rising(rising_raw, gt.FLAVOR_KEYWORDS[:5]),
            "keyword_count": 5,
        }

    def _do():
        from scrapers._reliability import run_with_fallback
        with _lock:
            _cache["is_refreshing"] = True
        out = {
            "google":     run_with_fallback("google", _light_google),
            "reddit":     run_with_fallback("reddit", reddit.run_full_scan),
            "food_media": run_with_fallback("food_media", food_media.run_full_scan),
            "instagram":  run_with_fallback(
                "instagram", lambda: instagram.run_full_scan(hashtags=instagram.ALL_TAGS[:8], results_limit=6)),
            "tiktok":     run_with_fallback(
                "tiktok", lambda: tiktok.run_full_scan(hashtags=tiktok.ALL_TAGS[:6], results_per_page=3)),
            "pinterest":  run_with_fallback(
                "pinterest", lambda: pinterest.run_full_scan(queries=pinterest.SEARCH_QUERIES[:3])),
        }
        with _lock:
            for k, v in out.items():
                _cache[k] = v
            _cache["last_full_refresh"] = datetime.utcnow().isoformat()
            _cache["is_refreshing"] = False

    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"status": "started", "mode": "light"})

def _source_status(v):
    if not v:
        return "pending"
    if v.get("stale"):
        return "stale"
    if v.get("error"):
        return "error"
    return "ready"


@app.route("/api/status")
def api_status():
    with _lock:
        return jsonify({
            "is_refreshing": _cache["is_refreshing"],
            "last_full_refresh": _cache["last_full_refresh"],
            "sources": {k: _source_status(_cache[k]) for k in SOURCES},
        })


BRIEFING_DIR = data_path("history")

@app.route("/briefing/latest")
def briefing_latest():
    """Render the most recent saved briefing in-browser."""
    # Newest by generation time (filename order breaks across the legacy
    # monthly ids and the bi-weekly cycle ids, e.g. 2026-07 vs 2026-07-a).
    files = (sorted(BRIEFING_DIR.glob("briefing_*.html"), key=lambda f: f.stat().st_mtime, reverse=True)
             if BRIEFING_DIR.exists() else [])
    if not files:
        return Response(
            "<h2 style='font-family:Georgia;padding:40px;color:#4B3422'>"
            "No briefing generated yet.<br><br>"
            "Run <code>python -m briefing.run</code> to generate one.</h2>",
            content_type="text/html"
        )
    return Response(files[0].read_text(encoding="utf-8"), content_type="text/html")

@app.route("/api/briefings")
def api_briefings():
    """List saved briefings (newest first) for the dashboard history browser."""
    files = (sorted(BRIEFING_DIR.glob("briefing_*.html"), key=lambda f: f.stat().st_mtime, reverse=True)
             if BRIEFING_DIR.exists() else [])
    out = []
    from briefing.cycle import label_for_id
    for f in files:
        stem = f.stem.replace("briefing_", "")  # "2026-07-a" (cycle) or legacy "2026-06"
        label = label_for_id(stem)
        st = f.stat()
        out.append({
            "name": f.name,
            "id": stem,
            "label": label,
            "generated": datetime.utcfromtimestamp(st.st_mtime).isoformat(),
            "size": st.st_size,
        })
    return jsonify({"briefings": out, "count": len(out)})

@app.route("/briefing/view/<bid>")
def briefing_view(bid):
    """Render a specific saved briefing by id (e.g. /briefing/view/2026-06)."""
    # Guard against path traversal — only allow our known filename shape.
    safe = "".join(ch for ch in bid if ch.isalnum() or ch in "-_")
    target = BRIEFING_DIR / f"briefing_{safe}.html"
    if not target.exists():
        return Response("<h2 style='font-family:Georgia;padding:40px'>Briefing not found.</h2>",
                        status=404, content_type="text/html")
    return Response(target.read_text(encoding="utf-8"), content_type="text/html")

@app.route("/briefing/run", methods=["POST"])
def briefing_run():
    """Generate a new briefing from current cached data (runs in background).

    Pass ?send=1 to also email it (falls back to a dry run if no email key)."""
    send = request.args.get("send") in ("1", "true", "yes")

    def _do():
        from datetime import datetime as _dt
        from briefing.score import score_all
        from briefing.gaps import compute_gaps
        from briefing.synthesize import synthesize
        from briefing.render import build_html, save_briefing
        from briefing.competitors import load_competitors, compute_competitor_move
        from briefing.outcomes import record_picks, hit_rate_sentence
        with _lock:
            data = {k: _cache[k] for k in _cache}
        scored = score_all(data)
        gap_result = compute_gaps(scored)
        synthesis = synthesize(scored, gap_result)
        discoveries = (data.get("google") or {}).get("rising_queries") or []

        # Competitor move: reuses the last EXPLICIT scan (never re-scrapes here —
        # that costs Apify credits and is its own opt-in action).
        scan = _competitor_state.get("last_result")
        competitor_move = compute_competitor_move(scan, load_competitors()) if scan else None

        from briefing.cycle import cycle_label, cycle_id
        month_label = cycle_label()  # bi-weekly cycle, e.g. "Early July 2026"
        cid = cycle_id()
        hit_rate = hit_rate_sentence(month_label)

        html = build_html(scored, gap_result, month_label=month_label, synthesis=synthesis,
                          discoveries=discoveries, competitor_move=competitor_move, hit_rate=hit_rate,
                          data=data)
        save_briefing(html)
        record_picks(synthesis, month_label)
        # Snapshot the feature vectors + decisions for future ML (can't backfill).
        from briefing.dataset import record_observations
        record_observations(scored, gap_result, synthesis, cid, month_label)
        if send:
            from briefing.send import send_briefing
            send_briefing(html)
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"status": "generating", "send": send, "check": "/briefing/latest"})

MENU_PATH = data_path("menu.json")
MENU_CATEGORIES = ("flavors", "formats", "toppings", "seasonal")
_MENU_DEFAULT = {k: [] for k in MENU_CATEGORIES}


def _clean_list(value, cap=100, maxlen=60):
    """Trim, lowercase, de-dupe, drop blanks; cap counts so a fat-finger can't
    bloat the menu (and downstream the scrape cost)."""
    if not isinstance(value, list):
        return []
    seen, out = set(), []
    for item in value:
        s = str(item).strip().lower()
        if s and len(s) <= maxlen and s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= cap:
            break
    return out


@app.route("/api/menu")
def api_menu_get():
    """Return the current menu for the Settings editor."""
    if MENU_PATH.exists():
        try:
            data = json.loads(MENU_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
    else:
        data = {}
    return jsonify({k: data.get(k, []) for k in MENU_CATEGORIES})


@app.route("/api/menu", methods=["POST"])
def api_menu_save():
    """Validate and persist an edited menu (drives the briefing's gap analysis)."""
    body = request.get_json(silent=True) or {}
    cleaned = {k: _clean_list(body.get(k, [])) for k in MENU_CATEGORIES}
    MENU_PATH.parent.mkdir(parents=True, exist_ok=True)
    MENU_PATH.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(len(v) for v in cleaned.values())
    return jsonify({"status": "saved", "menu": cleaned, "item_count": total})


# ── Onboarding presets (Tier 1) ──────────────────────────────────────────────
@app.route("/api/presets")
def api_presets():
    """List vertical presets a new tenant can start from."""
    from presets import list_verticals
    import tenancy
    return jsonify({"verticals": list_verticals(),
                    "tenant": tenancy.current_tenant()})


@app.route("/api/presets/apply", methods=["POST"])
def api_presets_apply():
    """Apply a vertical preset to the current tenant: replaces all watch-list
    config sections and merges the preset's starter formats into the menu.
    Destructive for watch lists, so it requires an explicit confirm flag."""
    from presets import VERTICALS, build_config_sections, build_starter_menu
    body = request.get_json(silent=True) or {}
    vertical = (body.get("vertical") or "").strip().lower()
    city = (body.get("city") or "").strip() or None
    if vertical not in VERTICALS:
        return jsonify({"error": f"Unknown vertical: {vertical!r}",
                        "available": sorted(VERTICALS)}), 400
    if body.get("confirm") is not True:
        return jsonify({"error": "This replaces every watch list for this tenant. "
                                 "Re-send with \"confirm\": true."}), 400

    from scrapers._config import load_config, save_config
    cfg = load_config()
    cfg.update(build_config_sections(vertical, city=city))
    save_config(cfg)

    # Merge starter formats into the menu without touching what's there.
    menu = _MENU_DEFAULT.copy()
    if MENU_PATH.exists():
        try:
            existing = json.loads(MENU_PATH.read_text(encoding="utf-8"))
            menu = {k: existing.get(k, []) for k in MENU_CATEGORIES}
        except (ValueError, OSError):
            pass
    starter = build_starter_menu(vertical)
    merged_formats = _clean_list(list(menu.get("formats", [])) + starter["formats"])
    menu["formats"] = merged_formats
    MENU_PATH.parent.mkdir(parents=True, exist_ok=True)
    MENU_PATH.write_text(json.dumps(menu, indent=2, ensure_ascii=False), encoding="utf-8")

    return jsonify({"status": "applied", "vertical": vertical, "city": city,
                    "menu_formats": merged_formats})


# ── Editable scraper watch lists (Settings → Watch Lists) ───────────────────
# (section, key, label, group, kind, default-list)
CONFIG_SCHEMA = [
    ("google",    "flavor",     "Flavor keywords",   "Google Trends", "phrase",    google_trends.FLAVOR_KEYWORDS),
    ("google",    "packaging",  "Packaging keywords", "Google Trends", "phrase",   google_trends.PACKAGING_KEYWORDS),
    ("google",    "design",     "Design keywords",   "Google Trends", "phrase",    google_trends.DESIGN_KEYWORDS),
    ("instagram", "hashtags",   "Hashtags",          "Instagram",     "hashtag",   instagram.ALL_TAGS),
    ("tiktok",    "hashtags",   "Hashtags",          "TikTok",        "hashtag",   tiktok.ALL_TAGS),
    ("pinterest", "queries",    "Search queries",    "Pinterest",     "phrase",    pinterest.SEARCH_QUERIES),
    ("reddit",    "subreddits", "Subreddits",        "Reddit",        "subreddit", reddit.SUBREDDITS),
    ("reddit",    "keywords",   "Trend keywords",    "Reddit",        "phrase",    reddit.TREND_KEYWORDS),
]
# Sources that cost Apify credits per scrape (for the UI cost nudge).
_PAID_SECTIONS = {"instagram", "tiktok", "pinterest"}


def _clean_config_item(item, kind):
    s = str(item).strip()
    if kind == "hashtag":
        s = re.sub(r"[^a-z0-9]", "", s.lower().lstrip("#"))
    elif kind == "subreddit":
        s = re.sub(r"^/?r/", "", s, flags=re.I).strip("/").strip()
        s = re.sub(r"[^A-Za-z0-9_]", "", s)
    else:  # free-text phrase / keyword
        s = s.lower()
    return s


def _clean_config_list(items, kind, cap=80, maxlen=80):
    if not isinstance(items, list):
        return []
    seen, out = set(), []
    for it in items:
        s = _clean_config_item(it, kind)
        low = s.lower()
        if s and len(s) <= maxlen and low not in seen:
            seen.add(low)
            out.append(s)
        if len(out) >= cap:
            break
    return out


def _config_sections():
    from scrapers._config import get_list
    out = []
    for section, key, label, group, kind, default in CONFIG_SCHEMA:
        out.append({
            "section": section, "key": key, "label": label, "group": group,
            "kind": kind, "paid": section in _PAID_SECTIONS,
            "items": get_list(section, key, default),
            "default": default,
        })
    return out


@app.route("/api/config")
def api_config_get():
    """Effective watch lists (config overrides merged over scraper defaults)."""
    return jsonify({"sections": _config_sections()})


@app.route("/api/config", methods=["POST"])
def api_config_save():
    """Validate and persist edited watch lists to data/config.json."""
    from scrapers._config import load_config, save_config
    body = request.get_json(silent=True) or {}
    cfg = load_config()
    for section, key, label, group, kind, default in CONFIG_SCHEMA:
        submitted = (body.get(section) or {}).get(key)
        if submitted is None:
            continue  # not in payload → leave existing override untouched
        cfg.setdefault(section, {})[key] = _clean_config_list(submitted, kind)
    save_config(cfg)
    sections = _config_sections()
    paid_count = sum(len(s["items"]) for s in sections if s["paid"])
    return jsonify({"status": "saved", "sections": sections, "paid_target_count": paid_count})


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.route("/api/delivery")
def api_delivery_get():
    """Briefing recipient (Settings-editable; NOT a secret). The send API key
    stays in .env and is never exposed here."""
    from scrapers._config import get_value
    from briefing.send import CLIENT_EMAIL_DEFAULT
    email = get_value("delivery", "client_email", CLIENT_EMAIL_DEFAULT)
    return jsonify({"client_email": email})


@app.route("/api/delivery", methods=["POST"])
def api_delivery_save():
    from scrapers._config import set_value
    body = request.get_json(silent=True) or {}
    email = str(body.get("client_email", "")).strip()
    if email and not _EMAIL_RE.match(email):
        return jsonify({"status": "error", "message": "That doesn't look like a valid email address."}), 400
    set_value("delivery", "client_email", email)
    return jsonify({"status": "saved", "client_email": email})


# ── Schedule (Phase 4 §4) ───────────────────────────────────────────────────
_SCHEDULE_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@app.route("/api/schedule")
def api_schedule_get():
    from scrapers._config import get_value
    return jsonify({
        "refresh_day": get_value("schedule", "refresh_day", "mon"),
        "refresh_hour": get_value("schedule", "refresh_hour", "5"),
        "send_day_of_month": get_value("schedule", "send_day_of_month", "1"),
        "send_hour": get_value("schedule", "send_hour", "8"),
        "scheduler_enabled": os.getenv("ENABLE_SCHEDULER") == "1",
    })


@app.route("/api/schedule", methods=["POST"])
def api_schedule_save():
    from scrapers._config import set_value
    body = request.get_json(silent=True) or {}

    day = str(body.get("refresh_day", "mon")).strip().lower()
    if day not in _SCHEDULE_DAYS:
        return jsonify({"status": "error", "message": "Invalid refresh day."}), 400
    try:
        refresh_hour = int(body.get("refresh_hour", 5))
        send_dom = int(body.get("send_day_of_month", 1))
        send_hour = int(body.get("send_hour", 8))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Hours/day must be numbers."}), 400
    if not (0 <= refresh_hour <= 23) or not (0 <= send_hour <= 23):
        return jsonify({"status": "error", "message": "Hour must be 0-23."}), 400
    if not (1 <= send_dom <= 28):
        return jsonify({"status": "error",
                        "message": "Send day must be 1-28 (28 keeps it valid in every month)."}), 400

    set_value("schedule", "refresh_day", day)
    set_value("schedule", "refresh_hour", str(refresh_hour))
    set_value("schedule", "send_day_of_month", str(send_dom))
    set_value("schedule", "send_hour", str(send_hour))
    return jsonify({"status": "saved", "note": "Takes effect on next server restart."})


# ── Competitor tracking (Phase 3 §C) ────────────────────────────────────────
# Account scraping costs real Apify credits, so a scan is NEVER triggered
# automatically — only via an explicit POST /api/competitors/scan click.
_competitor_state = {"is_scanning": False}
_competitor_state["last_result"] = competitor_accounts.load_cached_scan()  # survives restarts

_IG_USERNAME_RE = re.compile(r"[^a-z0-9_.]")
MAX_COMPETITORS = 15  # hard cap — each one costs a profile-scrape credit


def _clean_competitors(items):
    if not isinstance(items, list):
        return []
    out, seen = [], set()
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()[:60]
        handle = _IG_USERNAME_RE.sub("", str(it.get("instagram", "")).strip().lower().lstrip("@"))
        tier = str(it.get("tier", "local")).strip().lower()
        if tier not in ("local", "national", "asian_bakery"):
            tier = "local"
        if not name or not handle or handle in seen:
            continue
        seen.add(handle)
        out.append({"name": name, "instagram": handle, "tier": tier})
        if len(out) >= MAX_COMPETITORS:
            break
    return out


@app.route("/api/competitors")
def api_competitors_get():
    from briefing.competitors import load_competitors
    last = _competitor_state.get("last_result")
    return jsonify({
        "competitors": load_competitors(),
        "last_scanned_at": (last or {}).get("scanned_at"),
        "last_scan_profiles": len((last or {}).get("profiles", [])),
    })


@app.route("/api/competitors", methods=["POST"])
def api_competitors_save():
    from briefing.competitors import save_competitors
    body = request.get_json(silent=True) or {}
    cleaned = _clean_competitors(body.get("competitors", []))
    save_competitors(cleaned)
    return jsonify({"status": "saved", "competitors": cleaned})


@app.route("/api/competitors/scan", methods=["POST"])
def api_competitors_scan():
    """Explicit, paid action: scrape every tracked competitor's Instagram
    profile. Never runs automatically."""
    from briefing.competitors import load_competitors
    if _competitor_state["is_scanning"]:
        return jsonify({"status": "already_running"})
    competitors = load_competitors()
    handles = [c["instagram"] for c in competitors if c.get("instagram")]
    if not handles:
        return jsonify({"status": "error", "message": "No competitors configured yet."}), 400

    def _do():
        _competitor_state["is_scanning"] = True
        try:
            result = competitor_accounts.run_full_scan(handles)
            competitor_accounts.save_scan_cache(result)
            _competitor_state["last_result"] = result
        finally:
            _competitor_state["is_scanning"] = False

    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"status": "started", "handles": handles, "note": "this costs Apify credits"})


@app.route("/api/competitors/scan")
def api_competitors_scan_status():
    last = _competitor_state.get("last_result") or {}
    return jsonify({
        "is_scanning": _competitor_state["is_scanning"],
        "scanned_at": last.get("scanned_at"),
        "profiles_scraped": len(last.get("profiles", [])),
        "error": last.get("error"),
    })


# ── Proof loop (Phase 3 §F, manual v2) ──────────────────────────────────────
@app.route("/api/competitor-move")
def api_competitor_move():
    """Exposes the computed best competitor move from the last cached scan —
    never triggers a new scan (that's the explicit, paid /api/competitors/scan
    action). Returns {"move": null} until a scan has actually been run."""
    from briefing.competitors import load_competitors, compute_competitor_move
    scan = _competitor_state.get("last_result")
    move = compute_competitor_move(scan, load_competitors()) if scan else None
    return jsonify({"move": move})


@app.route("/api/outcomes")
def api_outcomes_get():
    from briefing.outcomes import list_outcomes, STATUS_LABELS
    return jsonify({"outcomes": list_outcomes(), "labels": STATUS_LABELS})


@app.route("/api/outcomes", methods=["POST"])
def api_outcomes_set():
    from briefing.outcomes import set_status
    body = request.get_json(silent=True) or {}
    ok = set_status(body.get("month", ""), body.get("term", ""), body.get("status", ""))
    if not ok:
        return jsonify({"status": "error", "message": "Outcome not found or invalid status"}), 400
    return jsonify({"status": "saved"})


def _gap_score(c: dict) -> int:
    """Single 0-100 display number for the Menu & Gaps gauge — a deterministic
    function of fields score_all() already computed from real scraped data
    (current_interest, confidence, direction, sources_agreeing). Not a new
    measurement, just a combined view of ones that already exist."""
    bonus = {"high": 20, "medium": 8, "low": 0}.get(c.get("confidence"), 0)
    bonus += 10 if c.get("direction") == "rising" else 5
    bonus += min(c.get("sources_agreeing", 0) * 5, 15)
    return min(100, round(c.get("current_interest", 0) + bonus))


@app.route("/api/sales")
def api_sales_get():
    """Sales history + sales-informed suggestions for items already on the
    menu (complements /api/menu-gaps, which only covers items NOT on it)."""
    from briefing.sales import load_sales, compute_suggestions, item_history
    from briefing.score import score_all
    data = load_sales()
    with _lock:
        cache_data = {k: _cache[k] for k in _cache}
    scored = score_all(cache_data)
    menu = json.loads(MENU_PATH.read_text(encoding="utf-8")) if MENU_PATH.exists() else _MENU_DEFAULT
    suggestions = compute_suggestions(menu, scored)
    all_items = [it for cat in MENU_CATEGORIES for it in menu.get(cat, [])]
    history = {it: [u for _, u in item_history(it)] for it in all_items}
    history = {k: v for k, v in history.items() if len(v) >= 2}
    return jsonify({"months": data.get("months", {}), "suggestions": suggestions, "history": history})


@app.route("/api/sales", methods=["POST"])
def api_sales_save():
    from briefing.sales import save_month
    body = request.get_json(silent=True) or {}
    month = str(body.get("month", "")).strip()
    entries = body.get("entries", {})
    if not month:
        return jsonify({"status": "error", "message": "Missing month."}), 400
    if not isinstance(entries, dict):
        return jsonify({"status": "error", "message": "Invalid entries."}), 400
    cleaned = {}
    for item, units in entries.items():
        try:
            u = int(units)
        except (TypeError, ValueError):
            continue
        if u < 0:
            continue
        cleaned[str(item).strip().lower()] = u
    save_month(month, cleaned)
    return jsonify({"status": "saved", "month": month, "item_count": len(cleaned)})


_THRESHOLD_DEFAULTS = {
    "top_post_window_days": "7",
    "tiktok_min_views": "10000", "tiktok_min_likes": "10000", "tiktok_min_comments": "1000",
    "instagram_min_likes": "10000", "instagram_min_comments": "1000",
}


@app.route("/api/thresholds")
def api_thresholds_get():
    from scrapers._config import get_value
    return jsonify({k: get_value("thresholds", k, v) for k, v in _THRESHOLD_DEFAULTS.items()})


@app.route("/api/thresholds", methods=["POST"])
def api_thresholds_save():
    from scrapers._config import set_value
    body = request.get_json(silent=True) or {}
    saved = {}
    for key, default in _THRESHOLD_DEFAULTS.items():
        try:
            val = int(float(body.get(key, default)))
            if val < 0:
                val = 0
        except (TypeError, ValueError):
            val = int(default)
        set_value("thresholds", key, str(val))
        saved[key] = val
    return jsonify({"status": "saved", **saved})


@app.route("/api/discovery-rules")
def api_discovery_rules_get():
    """Owner-editable rules for the flavor-discovery / hashtag feed — the
    analog of Top Post Thresholds, but for what SUGGESTIONS surface. Lists
    default to the built-in sets; scalars to _DISCOVERY_RULE_DEFAULTS."""
    from scrapers._config import get_list, get_value
    return jsonify({
        "blocklist": get_list("discovery", "blocklist", []),
        "classic_flavors": get_list("discovery", "classic_flavors", sorted(_CLASSIC_FLAVORS)),
        "min_corroboration": _discovery_int("min_corroboration"),
        "occasion_min_mentions": _discovery_int("occasion_min_mentions"),
        "classic_default": sorted(_CLASSIC_FLAVORS),
    })


@app.route("/api/discovery-rules", methods=["POST"])
def api_discovery_rules_save():
    from scrapers._config import load_config, save_config
    body = request.get_json(silent=True) or {}

    def _as_list(v):
        if isinstance(v, str):
            v = re.split(r"[,\n]", v)
        return v if isinstance(v, list) else []

    cfg = load_config()
    sect = cfg.setdefault("discovery", {})
    sect["blocklist"] = _clean_list(_as_list(body.get("blocklist", [])), cap=300, maxlen=50)
    sect["classic_flavors"] = _clean_list(_as_list(body.get("classic_flavors", [])), cap=300, maxlen=50)
    for key, default in _DISCOVERY_RULE_DEFAULTS.items():
        try:
            val = max(1, min(int(float(body.get(key, default))), 10))
        except (TypeError, ValueError):
            val = int(default)
        sect[key] = str(val)
    save_config(cfg)
    return jsonify({"status": "saved", **sect})


@app.route("/api/chart-prefs")
def api_chart_prefs_get():
    """Which flavor keywords the dashboard chart should feature. Empty list =
    auto mode (top 5 by current Google Trends interest, the existing default)."""
    from scrapers._config import get_list
    return jsonify({"selected": get_list("dashboard", "chart_keywords", [])})


@app.route("/api/chart-prefs", methods=["POST"])
def api_chart_prefs_save():
    from scrapers._config import load_config, save_config
    body = request.get_json(silent=True) or {}
    selected = body.get("selected", [])
    if not isinstance(selected, list):
        return jsonify({"status": "error", "message": "Invalid selection."}), 400
    cleaned = []
    seen = set()
    for x in selected:
        s = str(x).strip().lower()
        if s and s not in seen:
            seen.add(s)
            cleaned.append(s)
        if len(cleaned) >= 5:
            break
    cfg = load_config()
    cfg.setdefault("dashboard", {})["chart_keywords"] = cleaned
    save_config(cfg)
    return jsonify({"status": "saved", "selected": cleaned})


# Generic/obvious words we never want to surface as a "new flavor" discovery.
_DISCOVERY_STOP = {
    "chicago", "cake", "cakes", "cupcake", "cupcakes", "chocolate", "dessert",
    "desserts", "bakery", "bakeries", "food", "foodie", "sweet", "sweets",
    "baking", "baker", "recipe", "recipes", "new", "viral", "trending", "yummy",
    "delicious", "instagood", "love", "photooftheday", "chicagorealestate",
}

# Classic flavors are staples, not discoveries. Matched EXACTLY (whole term) so a
# specific twist like "dubai chocolate" or "black sesame" still surfaces — only
# the plain classic ("chocolate", "red velvet") is filtered out.
_CLASSIC_FLAVORS = {
    "chocolate", "vanilla", "strawberry", "lemon", "caramel", "cinnamon",
    "coffee", "mocha", "mint", "banana", "blueberry", "raspberry", "blackberry",
    "coconut", "carrot", "pumpkin", "apple", "cherry", "orange", "hazelnut",
    "almond", "pistachio", "peanut butter", "red velvet", "cookies and cream",
    "salted caramel", "oreo", "smores", "smore", "funfetti", "birthday cake",
    "cheesecake", "tiramisu", "cannoli", "espresso", "matcha",
}

# Occasions belong to the events engine, not flavor discovery. A term that is
# purely an occasion ("birthday", "wedding") is routed out of flavor keywords.
_OCCASION_WORDS = {
    "birthday", "wedding", "anniversary", "graduation", "party", "babyshower",
    "baby shower", "engagement", "retirement", "holiday", "celebration",
    "shower", "reunion", "quinceanera", "communion", "gender reveal",
}


def _disc_norm(s: str) -> str:
    return " ".join("".join(c for c in (s or "").lower() if c.isalnum() or c == " ").split())


# Owner-editable discovery rules (Settings → Discovery Rules), backed by
# config.json like the post-filter thresholds. The hardcoded sets above are the
# DEFAULTS; these getters let the owner tune what surfaces without code edits.
_DISCOVERY_RULE_DEFAULTS = {"min_corroboration": "2", "occasion_min_mentions": "3"}


def _discovery_classics() -> set[str]:
    """Normalized classic-flavor list — owner-editable, defaults to _CLASSIC_FLAVORS."""
    from scrapers._config import get_list
    return {_disc_norm(x) for x in get_list("discovery", "classic_flavors", sorted(_CLASSIC_FLAVORS)) if x}


def _discovery_blocklist() -> set[str]:
    """Normalized never-suggest terms the owner has added (empty by default)."""
    from scrapers._config import get_list
    return {_disc_norm(x) for x in get_list("discovery", "blocklist", []) if x}


def _discovery_int(key: str) -> int:
    """A discovery sensitivity dial as an int, clamped sane, config-backed."""
    from scrapers._config import get_value
    default = _DISCOVERY_RULE_DEFAULTS.get(key, "0")
    try:
        return max(1, min(int(float(get_value("discovery", key, default))), 10))
    except (TypeError, ValueError):
        return int(default)


@app.route("/api/suggested-keywords")
def api_suggested_keywords():
    """Multi-source flavor-discovery feed, ranked by CROSS-SOURCE CORROBORATION.
    Generators (novel terms): Google rising queries + Instagram co-hashtags +
    Instagram caption words. Corroboration/food signals: Reddit trending
    keywords + food-media article titles. A term surfacing in several sources
    is far more likely a real emerging flavor than single-source noise (this is
    what let 'labubu' through before) — so corroboration count sorts the list,
    and a food-media hit flags it as genuinely food. Already-watched and
    denylisted/dismissed terms are dropped (we only surface what's NEW)."""
    from scrapers._discovery import is_denylisted, competitor_denylist, dismissed_terms
    from scrapers._config import get_list
    with _lock:
        google = _cache.get("google") or {}
        ig = _cache.get("instagram") or {}
        reddit = _cache.get("reddit") or {}
        food = _cache.get("food_media") or {}
    denylist, dismissed = competitor_denylist(), dismissed_terms()

    # Owner-editable discovery rules (Settings → Discovery Rules).
    classics = _discovery_classics()
    blocklist = _discovery_blocklist()
    min_corro = _discovery_int("min_corroboration")

    # Terms already on a watch list aren't "new" — exclude them.
    watched: set[str] = set()
    for key in ("flavor", "packaging", "design"):
        watched |= {t.lower().strip() for t in get_list("google", key, [])}

    # Geo/location terms are not flavors — exclude the neighborhood tags we scan
    # plus common location noise their co-hashtags drag in.
    geo_exclude: set[str] = set()
    try:
        from clusters import all_geo_hashtags
        geo_exclude = {g.lower() for g in all_geo_hashtags()}
    except Exception:
        pass
    _GEO_NOISE = ("chicago", "illinois", "realestate", "events", "downtown",
                  "uptown", "suburb", "neighborhood", "lagrange", "okazja")

    def _is_geo(n: str) -> bool:
        return n in geo_exclude or any(w in n for w in _GEO_NOISE)

    # Source term pools (for corroboration matching).
    pools = {
        "google": [r.get("query", "") for r in (google.get("rising_queries") or [])],
        "instagram": [w.get("word", "") for w in (ig.get("trending_words") or []) if w.get("count", 0) >= 3]
                     + [t.get("tag", "") for t in (ig.get("related_tags") or []) if t.get("count", 0) >= 3],
        "reddit": [k.get("keyword", "") for k in (reddit.get("trending_keywords") or [])],
    }
    pools_norm = {k: [_disc_norm(x) for x in v if x] for k, v in pools.items()}
    titles = " ".join(_disc_norm(a.get("title", "")) for a in (food.get("top_articles") or []))

    def _signals(term: str):
        n = _disc_norm(term)
        srcs = [name for name, lst in pools_norm.items()
                if any(n == x or (len(n) > 3 and (n in x or x in n)) for x in lst)]
        in_food = len(n) > 3 and n in titles
        return srcs, in_food

    cand: dict = {}

    def _add(term: str, source: str, extra: dict | None = None):
        t = (term or "").strip()
        n = t.lower()
        if not t or n in _DISCOVERY_STOP or n in watched or n in cand:
            return
        nn = _disc_norm(t)
        # Owner blocklist: terms she never wants suggested, dropped outright.
        if nn in blocklist:
            return
        # Exact-match filters: plain classic flavors (already on the menu) and
        # pure occasion words (the events engine's job) are not flavor discoveries.
        # Exact-only, so specific twists like "dubai chocolate" still pass.
        if nn in classics or nn in _OCCASION_WORDS:
            return
        if _is_geo(nn) or is_denylisted(t, denylist, dismissed):
            return
        srcs, in_food = _signals(t)
        corro = len(set(srcs)) + (1 if in_food else 0)
        cand[n] = {"query": t, "source": source, "sources": srcs,
                   "in_food_media": in_food, "corroboration": corro, **(extra or {})}

    for r in (google.get("rising_queries") or []):
        _add(r.get("query", ""), "google",
             {"breakout": r.get("breakout"), "value": r.get("value"),
              "seeds": r.get("seeds"), "seed_count": r.get("seed_count")})
    for t in (ig.get("related_tags") or []):
        if t.get("count", 0) >= 3:
            _add(t.get("tag", ""), "instagram_tag", {"count": t.get("count")})
    for w in (ig.get("trending_words") or []):
        if w.get("count", 0) >= 3:
            _add(w.get("word", ""), "instagram_caption", {"count": w.get("count")})

    # Pinpoint filter: a candidate qualifies only if it's a Google rising query
    # (novel + food-seeded = a strong signal on its own) OR it's corroborated
    # across 2+ sources. Single-source Instagram co-tags are too noisy to trust
    # alone (they drag in geo/foreign terms), so they surface only when another
    # source confirms them — which is exactly the "pinpoint" a real flavor gets.
    def _qualifies(c: dict) -> bool:
        return c["source"] == "google" or c["corroboration"] >= min_corro

    out = sorted(
        (c for c in cand.values() if _qualifies(c)),
        key=lambda c: (-c["corroboration"], 0 if c["in_food_media"] else 1,
                       -(c.get("value") or 0), -(c.get("count") or 0)),
    )[:20]
    return jsonify({"suggestions": out})


@app.route("/api/discovery/dismiss", methods=["POST"])
def api_discovery_dismiss():
    from scrapers._discovery import dismiss
    body = request.get_json(silent=True) or {}
    term = str(body.get("term", "")).strip()
    if not term:
        return jsonify({"status": "error", "message": "Missing term."}), 400
    dismiss(term)
    return jsonify({"status": "saved", "term": term.lower()})


@app.route("/api/history/<source>")
def api_history(source):
    """Rolling snapshot history for the sparkline UI (Instagram/TikTok top
    tags). Accumulates for free across whatever real refreshes already run —
    this route itself never triggers a scrape."""
    from scrapers._history import load_history
    if source not in ("instagram", "tiktok"):
        return jsonify({"error": "unknown source"}), 404
    return jsonify({"source": source, "snapshots": load_history(source)})


@app.route("/api/dna")
def api_dna_get():
    from briefing.dna import load_dna
    return jsonify(load_dna())


@app.route("/api/dna", methods=["POST"])
def api_dna_save():
    from briefing.dna import save_dna, RISK_LEVELS
    body = request.get_json(silent=True) or {}
    voice = str(body.get("voice", ""))[:2000]
    risk = str(body.get("risk_tolerance", "balanced")).strip().lower()
    if risk not in RISK_LEVELS:
        risk = "balanced"
    try:
        max_items = int(body.get("max_new_items_per_month", 3))
    except (TypeError, ValueError):
        max_items = 3
    max_items = max(0, min(max_items, 20))
    dietary = str(body.get("dietary_exclusions", ""))[:500]
    save_dna(voice, risk, max_items, dietary)
    return jsonify({"status": "saved"})


@app.route("/api/menu-gaps")
def api_menu_gaps():
    """Real menu-gap opportunities — same scoring/gap pipeline the briefing
    itself uses (briefing.score.score_all + briefing.gaps.compute_gaps),
    surfaced live for the Menu & Gaps dashboard view."""
    from briefing.score import score_all
    from briefing.gaps import compute_gaps
    from briefing.dna import apply_filters, load_dna
    with _lock:
        data = {k: _cache[k] for k in _cache}
    scored = score_all(data)
    result = compute_gaps(scored)
    dna = load_dna()
    result["gaps"] = apply_filters(result["gaps"], dna)
    for g in result["gaps"]:
        g["gap_score"] = _gap_score(g)
    result["dna_applied"] = dna
    return jsonify(result)


@app.route("/api/scores")
def api_scores():
    """Momentum scores for all trend candidates (feeds the dashboard)."""
    from briefing.score import score_all
    with _lock:
        data = {k: _cache[k] for k in _cache}
    scored = score_all(data)
    return jsonify({"scores": scored, "count": len(scored)})


@app.route("/api/events")
def api_events():
    """Upcoming bakery-relevant events inside the planning window, each with
    real lead-time math and trend tie-ins matched against the live scores."""
    from briefing.events import (upcoming_events, event_tie_ins, occasion_buzz,
                                  DEFAULT_WINDOW_DAYS)
    from briefing.score import score_all
    try:
        window = min(max(int(request.args.get("window", DEFAULT_WINDOW_DAYS)), 7), 120)
    except ValueError:
        window = DEFAULT_WINDOW_DAYS
    events = upcoming_events(window_days=window)
    with _lock:
        data = {k: _cache[k] for k in _cache}
    scored = score_all(data)
    return jsonify({"events": event_tie_ins(events, scored),
                    "occasion_buzz": occasion_buzz(data.get("instagram"), data.get("tiktok"),
                                                   min_mentions=_discovery_int("occasion_min_mentions")),
                    "window_days": window, "count": len(events)})


@app.route("/api/feedback", methods=["GET", "POST"])
def api_feedback():
    """Client feedback on a briefing — a 1-5 rating and/or free-text detail,
    optionally tied to a specific term. GET returns everything for the operator
    plus a summary."""
    from briefing.feedback import record_feedback, list_feedback, summary
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        # Also accept query params so a one-click link in an email can record.
        rating = body.get("rating", request.args.get("rating"))
        note = body.get("note", request.args.get("note", ""))
        cycle = body.get("cycle", request.args.get("cycle", ""))
        term = body.get("term", request.args.get("term", ""))
        entry = record_feedback(rating=rating, note=note, cycle=cycle, term=term)
        if entry is None:
            return jsonify({"error": "Provide a rating (1-5) and/or a note."}), 400
        # Email the operator so no feedback is missed. Best-effort — a failed
        # email must never break recording the feedback.
        try:
            from briefing.send import send_operator_alert
            r = entry.get("rating")
            lines = [
                f"Rating: {r}/5" if r is not None else "Rating: (none)",
                f"Cycle: {entry.get('cycle') or '(unspecified)'}",
                f"About term: {entry.get('term')}" if entry.get("term") else "",
                "",
                (entry.get("note") or "(no written note)"),
                "",
                f"Received: {entry.get('at')}",
            ]
            send_operator_alert(
                subject=f"[Trend Radar] New client feedback"
                        + (f" — {r}/5" if r is not None else ""),
                body="\n".join(l for l in lines if l != "" or True),
            )
        except Exception:
            pass
        return jsonify({"status": "recorded", "entry": entry})
    return jsonify({"feedback": list_feedback(), "summary": summary()})


@app.route("/portal")
def portal():
    """Client-facing portal — a stripped, read-mostly view for the bakery owner.
    No config, no scraping controls; just their briefing, what's coming, their
    track record, and a place to respond."""
    return render_template("portal.html")


@app.route("/api/portal")
def api_portal():
    """Consolidated client-safe read model for the portal (one fetch)."""
    from scrapers._config import get_value
    from briefing.cycle import cycle_label, label_for_id
    from briefing.events import upcoming_events, event_tie_ins
    from briefing.outcomes import list_outcomes, hit_rate_sentence, STATUS_LABELS
    from briefing.score import score_all
    from briefing.feedback import summary as fb_summary

    files = (sorted(BRIEFING_DIR.glob("briefing_*.html"), key=lambda f: f.stat().st_mtime, reverse=True)
             if BRIEFING_DIR.exists() else [])
    latest = None
    if files:
        st = files[0].stat()
        stem = files[0].stem.replace("briefing_", "")
        latest = {"id": stem, "label": label_for_id(stem),
                  "generated": datetime.utcfromtimestamp(st.st_mtime).isoformat()}

    with _lock:
        data = {k: _cache[k] for k in _cache}
    scored = score_all(data)
    events = event_tie_ins(upcoming_events(), scored)[:5]

    outcomes = list_outcomes()
    resolved = [o for o in outcomes if o.get("status") in ("selling_well", "underperformed")]
    wins = sum(1 for o in resolved if o["status"] == "selling_well")

    return jsonify({
        "bakery": get_value("business", "name", "Buttercup Bakery"),
        "cycle": latest,
        "hit_rate": hit_rate_sentence(cycle_label()),
        "events": events,
        "track_record": {"outcomes": outcomes, "labels": STATUS_LABELS,
                         "wins": wins, "resolved": len(resolved)},
        "feedback": fb_summary(),
    })


@app.route("/hq")
def hq():
    """HQ multi-location rollup — for the owner of the chain. Shows shared
    national trends + per-market-cluster local activity across all locations."""
    return render_template("hq.html")


@app.route("/api/hq")
def api_hq():
    """Rollup across market clusters: shared national trends (scanned once) +
    per-cluster local hashtag activity (grouped) + per-cluster competitors."""
    from clusters import load_clusters, group_by_cluster, launch_picks_for_cluster, profile_rationale
    from briefing.score import score_all
    from briefing.events import occasion_buzz
    from scrapers._config import get_value
    with _lock:
        data = {k: _cache[k] for k in _cache}
    scored = score_all(data)
    national = [c for c in scored if c.get("direction") in ("rising", "peaking")][:6]
    grouped = group_by_cluster(data.get("instagram"), data.get("tiktok"))
    clusters = load_clusters()
    out_clusters = []
    for c in clusters:
        g = grouped.get(c["key"], {})
        local_ig = sorted(g.get("local_ig", []), key=lambda t: -(t.get("posts_per_day", 0)))[:5]
        local_tt = sorted(g.get("local_tt", []), key=lambda t: -(t.get("videos_per_day", 0)))[:5]
        picks = [{"term": p["term"], "delta": p.get("delta"), "confidence": p.get("confidence")}
                 for p in launch_picks_for_cluster(c, scored)]
        out_clusters.append({**c, "local_ig": local_ig, "local_tt": local_tt,
                             "has_local": bool(local_ig or local_tt),
                             "launch_picks": picks, "profile_note": profile_rationale(c)})
    return jsonify({
        "bakery": get_value("business", "name", "Buttercup Bakery"),
        "national": [{"term": c["term"], "category": c.get("category"),
                      "direction": c["direction"], "confidence": c.get("confidence"),
                      "current_interest": c.get("current_interest")} for c in national],
        "clusters": out_clusters,
        "occasion_buzz": occasion_buzz(data.get("instagram"), data.get("tiktok"),
                                       min_mentions=_discovery_int("occasion_min_mentions")),
        "location_count": sum(len(c.get("locations", [])) for c in clusters),
        "cluster_count": len(clusters),
    })


@app.route("/api/clusters", methods=["GET", "POST"])
def api_clusters():
    """Market clusters the owner can edit — locations, local geo-hashtags, and
    local competitors per cluster. Menu/DNA stay shared (one brand)."""
    from clusters import load_clusters, save_clusters
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        incoming = body.get("clusters")
        if not isinstance(incoming, list) or not incoming:
            return jsonify({"error": "Expected a non-empty clusters list."}), 400
        cleaned = []
        for c in incoming:
            if not isinstance(c, dict):
                continue
            key = "".join(ch for ch in str(c.get("key", "")).lower() if ch.isalnum() or ch == "_")[:40]
            name = str(c.get("name", "")).strip()[:60]
            if not key or not name:
                continue
            profile = str(c.get("profile", "balanced"))
            if profile not in ("trend_forward", "balanced", "classic"):
                profile = "balanced"
            cleaned.append({
                "key": key,
                "name": name,
                "profile": profile,
                "blurb": str(c.get("blurb", "")).strip()[:200],
                "locations": _clean_list(c.get("locations", []), cap=20, maxlen=60),
                "geo_hashtags": [t.lower() for t in _clean_list(c.get("geo_hashtags", []), cap=20, maxlen=40)],
                "competitors": [t.lower() for t in _clean_list(c.get("competitors", []), cap=20, maxlen=40)],
            })
        if not cleaned:
            return jsonify({"error": "No valid clusters after cleaning."}), 400
        save_clusters(cleaned)
        return jsonify({"status": "saved", "count": len(cleaned)})
    return jsonify({"clusters": load_clusters()})


_PROFILE_LABEL = {"trend_forward": "Trend-forward market",
                  "balanced": "Balanced market",
                  "classic": "Classics-first market"}


def _market_pulse(geo_tags: set[str]) -> dict:
    """Per-scan local activity series for a market: the sum of its geo-tags'
    Instagram posting rates in each recorded history snapshot. Real recorded
    numbers only — needs 2+ snapshots before a line can honestly be drawn."""
    from scrapers._history import load_history
    points = []
    for snap in load_history("instagram"):
        total = sum(v for t, v in (snap.get("metrics") or {}).items() if t in geo_tags)
        points.append({"t": (snap.get("at") or "")[:10], "v": round(total, 1)})
    return {"points": points, "snapshots": len(points),
            "metric": "sum of this market's geo-tag posts/day per scan"}


@app.route("/market/<key>")
def market_page(key):
    from clusters import load_clusters
    if not any(c["key"] == key for c in load_clusters()):
        return render_template("market.html", market_key="", bakery_name=_bakery_name()), 404
    return render_template("market.html", market_key=key, bakery_name=_bakery_name())


@app.route("/api/market/<key>")
def api_market(key):
    """Everything one market page needs in a single fetch. Same honesty rule as
    the briefing: every number here restates a scraped value — no composite
    'momentum scores', no projected revenue, nothing modeled."""
    from clusters import (load_clusters, group_by_cluster,
                          launch_picks_for_cluster, profile_rationale)
    from briefing.score import score_all
    from briefing.events import upcoming_events, occasion_buzz

    clusters = load_clusters()
    order = [c["key"] for c in clusters]
    cluster = next((c for c in clusters if c["key"] == key), None)
    if not cluster:
        return jsonify({"error": "No market with that key."}), 404

    with _lock:
        data = {k: _cache[k] for k in _cache}
    scored = score_all(data)

    # Launch picks, enriched with the scored candidate's real evidence lines.
    by_term = {c.get("term"): c for c in scored}
    picks = []
    for p in launch_picks_for_cluster(cluster, scored):
        src = by_term.get(p["term"], {})
        picks.append({**p, "direction": src.get("direction"),
                      "category": src.get("category"),
                      "evidence": list(src.get("evidence") or [])[:2]})

    geo = {g.lower() for g in (cluster.get("geo_hashtags") or [])}
    g = group_by_cluster(data.get("instagram"), data.get("tiktok")).get(key, {})
    local_ig = sorted(g.get("local_ig", []), key=lambda t: -(t.get("posts_per_day") or 0))[:8]
    local_tt = sorted(g.get("local_tt", []), key=lambda t: -(t.get("videos_per_day") or 0))[:8]

    # Movers restricted to this market's geo tags (real snapshot-to-snapshot).
    from scrapers._history import load_history, _METRIC_FIELD
    movers = []
    for source in _METRIC_FIELD:
        snaps = load_history(source)
        if len(snaps) < 2:
            continue
        prev, curr = snaps[-2]["metrics"], snaps[-1]["metrics"]
        for tag, now_v in curr.items():
            then_v = prev.get(tag)
            if tag in geo and then_v and then_v > 0:
                movers.append({"tag": tag, "source": source, "prev": then_v, "curr": now_v,
                               "change_pct": round((now_v - then_v) / then_v * 100, 1)})
    movers.sort(key=lambda m: -abs(m["change_pct"]))

    idx = order.index(key)
    neighbors = {"prev": order[idx - 1], "next": order[(idx + 1) % len(order)]}
    names = {c["key"]: c["name"] for c in clusters}

    return jsonify({
        "market": {**cluster,
                   "profile_label": _PROFILE_LABEL.get(cluster.get("profile"), "Balanced market"),
                   "profile_note": profile_rationale(cluster)},
        "bakery": _bakery_name(),
        "pulse": _market_pulse(geo),
        "launch_picks": picks,
        "events": upcoming_events(cluster=key)[:8],
        "occasion_buzz": occasion_buzz(data.get("instagram"), data.get("tiktok"),
                                       min_mentions=_discovery_int("occasion_min_mentions")),
        "local_buzz": {"instagram": local_ig, "tiktok": local_tt},
        "movers": movers[:6],
        "nav": {"prev": {"key": neighbors["prev"], "name": names[neighbors["prev"]]},
                "next": {"key": neighbors["next"], "name": names[neighbors["next"]]}},
        "scanned_at": (data.get("instagram") or {}).get("scanned_at") or "",
    })


@app.route("/api/training-data")
def api_training_data():
    """The joined, labeled observation table for future ML. `?format=csv` for
    the flat CSV an ML pipeline expects; otherwise JSON rows + coverage stats."""
    from briefing.dataset import build_training_table, to_csv, coverage
    if request.args.get("format") == "csv":
        return Response(to_csv(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=trend_training_data.csv"})
    return jsonify({"rows": build_training_table(), "coverage": coverage()})


@app.route("/api/hashtag-momentum")
def api_hashtag_momentum():
    """Biggest hashtag movers between the last two real scans, per source.
    Delta is computed from recorded snapshots (posts/day for Instagram, peak
    velocity for TikTok) — real observed numbers, nothing modeled."""
    from scrapers._history import load_history, _METRIC_FIELD
    out = {}
    for source in _METRIC_FIELD:
        snaps = load_history(source)
        if len(snaps) < 2:
            out[source] = {"movers": [], "snapshots": len(snaps)}
            continue
        prev, curr = snaps[-2]["metrics"], snaps[-1]["metrics"]
        movers = []
        for tag, now_v in curr.items():
            then_v = prev.get(tag)
            if then_v is None or then_v <= 0:
                continue
            change = (now_v - then_v) / then_v
            movers.append({"tag": tag, "prev": then_v, "curr": now_v,
                           "change_pct": round(change * 100, 1)})
        movers.sort(key=lambda m: -abs(m["change_pct"]))
        out[source] = {"movers": movers[:8], "snapshots": len(snaps),
                       "prev_at": snaps[-2]["at"], "curr_at": snaps[-1]["at"]}
    return jsonify(out)


if __name__ == "__main__":
    print("Starting Trend Radar...")
    # Don't auto-scrape on boot (avoids surprise Apify credit burn on every
    # restart). Set AUTO_REFRESH=1 to opt in; otherwise refresh on demand via
    # the dashboard button / /api/refresh / /api/refresh-light, or the scheduler.
    if os.getenv("AUTO_REFRESH") == "1":
        refresh_all(background=True)
    # Phase 4: weekly refresh + monthly briefing send, only once deployed
    # somewhere that stays up. Off by default — see scheduler.py.
    if os.getenv("ENABLE_SCHEDULER") == "1":
        import scheduler
        scheduler.start()
    # Auth-by-default for public exposure: binding beyond loopback without a
    # password would put every route (including refresh, which spends Apify
    # credits) on the open network.
    host = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host not in ("127.0.0.1", "localhost") and not APP_PASSWORD:
        raise SystemExit(
            f"Refusing to bind to {host}: APP_PASSWORD is not set. "
            "Set APP_PASSWORD in .env before exposing this app beyond localhost."
        )
    app.run(debug=False, host=host, port=int(os.getenv("PORT", "5050")), use_reloader=False)
