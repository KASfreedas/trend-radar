# Trend Radar — Full Technical Architecture

## What this is

A trend-intelligence and decision-support tool for a single bakery business (demo: Buttercup Bakery, a multi-location Chicago bakery). It scrapes external signals (Google search interest, Instagram, TikTok, Pinterest, Reddit, food-media editorial content), scores them for genuine momentum and corroboration, cross-references against the owner's actual menu and real sales, watches specific competitor Instagram accounts for standout posts, and produces a monthly "Specials Board Briefing" — live on a dashboard and emailed as HTML — recommending what to launch, watch, skip, or retire. Everything is scoped to one business, single-tenant, no database — flat JSON files on disk.

**Non-negotiable design rule threaded through every module**: never cite a number that isn't real and observed. Deterministic code paths only restate scraped evidence; the one optional LLM path is guardrailed to strip any invented figure after the fact. When there isn't enough signal, the system says so explicitly ("quiet month," empty states) rather than padding.

## Directory structure

```
trend-scraper/
  app.py                        Flask app — all routes, in-memory cache, threading
  scheduler.py                  Optional APScheduler cron, off by default
  requirements.txt
  .env / .env.example           Secrets — never commit .env

  scrapers/
    google_trends.py            pytrends wrapper + adaptive re-query + rising-query discovery
    instagram.py                 Apify hashtag scraper — posting-volume ranking
    tiktok.py                    Apify video scraper — engagement-velocity ranking
    pinterest.py                  Apify board-search scraper — board-interest ranking
    reddit.py                     RSS (default) or praw (optional) — recency-weighted mentions
    food_media.py                  RSS editorial scraper (Bon Appétit, Food52, Serious Eats, etc.)
    competitor_accounts.py          Apify Instagram profile scraper — paid, explicit-trigger only
    _config.py                      data/config.json read/write helpers
    _reliability.py                  run_with_fallback(): last-good cache + operator alerts + snapshots
    _history.py                       Per-tag snapshot history (sparklines, Hashtag Growth)
    _discovery.py                      Competitor-name denylist + owner-dismissed-term filter
    _engagement.py                      Shared engagement-score / posting-rate math

  briefing/
    score.py                     Direction/confidence/gap_score — the "is this trending" engine
    gaps.py                       Menu-gap diff (trending + not on menu = opportunity)
    dna.py                         Brand DNA: risk-tolerance filter + dietary exclusions + LLM voice
    sales.py                        Manual sales tracker + sales-informed suggestions
    competitors.py                   Competitor-move detection (baseline vs. outlier post)
    outcomes.py                       Proof loop: logs picks, tracks resolution, hit-rate sentence
    synthesize.py                      LLM-optional recommendation bucketing
    render.py                           HTML briefing renderer (email-safe, inline-styled)
    send.py                              Resend email delivery, dry-run fallback
    run.py                                CLI orchestrator: python -m briefing.run [--send]

  templates/
    index.html                   The entire UI — one file, ~2700+ lines, no build step
    login.html                    Optional password-gate page

  data/
    menu.json, config.json, competitors.json, competitor_scan_cache.json
    cache/            last_good_<source>.json, history_<source>.json
    history/           briefing_<YYYY-MM>.html, sales.json, outcomes.json
```

## Runtime architecture

- Single Flask process, single Jinja2 template. "Views" (Dashboard / Settings / Menu & Gaps / Suggestions) are DOM siblings toggled via JS `display:none/block` — there is no client-side router and no page reload between them.
- `_cache` (a plain dict in `app.py`) holds the latest result per source (`google`, `reddit`, `food_media`, `instagram`, `tiktok`, `pinterest`) plus `last_full_refresh`/`is_refreshing` flags. Refreshes run scrapers in parallel threads, guarded by a `threading.Lock`.
- Two refresh paths: `POST /api/refresh` (full watch lists, real scale) and `POST /api/refresh-light` (small subsets, for cheap testing). Both now route every source through `scrapers._reliability.run_with_fallback()` — this was NOT always true; refresh-light originally bypassed it via a bare try/except, found and fixed mid-project.
- No database. All state is flat JSON under `data/`, read at call-time (not cached at import), so Settings edits apply on the next refresh with no restart — except scheduler/schedule-related settings, which need a restart.

## The scoring engine — `briefing/score.py`

For every Google-tracked keyword (flavor/packaging/design):

- **`direction`** (`rising` / `peaking` / `fading` / `flat`): real 12-month pytrends time series, compares avg(last ~30d) vs avg(prior ~90d). >15% up → rising, >15% down → fading, sitting near its own historical peak → peaking.
- **`confidence`** (`high` / `medium` / `low`): counts how many *other* sources also surface the term — but only if each source clears a real minimum-sample floor: `MIN_REDDIT_MENTIONS=2`, `MIN_IG_POSTS=3` (checks the real `post_count` field), `MIN_IG_WORD_MENTIONS=3`, `MIN_TIKTOK_VIDEOS=3`. A single stray post does not count as corroboration — this floor was added after real testing showed some Instagram tags at 0.2–0.5 posts/day, which would otherwise register as "confirmed." Food media is exempt from any floor (a single editorial mention is real signal on its own). **Pinterest is excluded from this count entirely** — not because of sample size but because real testing found the *same query* returning wildly different board counts on different days; a floor can't fix an inconsistent source.
- **`gap_score`** (0–100, display-only): `current_interest` + a confidence bonus (+20/+8/0) + a direction bonus (+10 rising/+5 peaking) + a corroboration bonus (+5/source, capped) — a composite of fields that already exist, not a new measurement.

## Menu gaps — `briefing/gaps.py`

Reads `data/menu.json` (fixed categories: `flavors`/`formats`/`toppings`/`seasonal`, each a flat list of lowercase strings). For each scored candidate: rising/peaking + not on menu (exact or partial word-overlap match, words >3 chars) → **gap**. Rising/peaking + on menu → **covered**. Fading + on menu → **retire candidate**. The word-overlap matching is deliberately loose and has a known false-positive mode (e.g. "bento cake" can match a generic "cake" menu item) — not fixed, documented.

## Brand DNA — `briefing/dna.py`

- `voice` (free text): fed only into the LLM synthesis prompt as context. Zero effect on deterministic synthesis (no LLM key configured currently). Cannot override the never-invent-numbers guardrail.
- `risk_tolerance`: conservative (high-confidence only) / balanced (high+medium) / adventurous (everything) — a hard floor applied in `apply_filters()`.
- `dietary_exclusions`: comma list, substring-blocks gap terms.
- `max_new_items_per_month`: caps how many gaps count as "act on this now" — applied only on the Suggestions page, never on the full Menu & Gaps browse list.
- Applied server-side inside `GET /api/menu-gaps`, so every consumer (dashboard chart legend, Menu & Gaps page, Suggestions page) sees identically-filtered data from one source of truth.

## Sales Tracker — `briefing/sales.py`

Owner manually enters unit counts per menu item per month (Settings). `compute_suggestions()` requires ≥2 real months per item before generating anything — a single data point has no trend. Correlates the real month-over-month delta against the same scored candidates (same matching logic as gaps.py). Three outcomes: `retire_candidate` (sales down, no trend support), `lean_in` (sales up + trend support), `underperforming_despite_trend` (sales flat/down *despite* a supporting trend — an execution/marketing signal, distinct from a trend signal).

## Competitor Watch — `briefing/competitors.py` + `scrapers/competitor_accounts.py`

`data/competitors.json`: owner-managed name/handle/tier list, capped at 15. Scanning (`POST /api/competitors/scan`) is the *only* trigger for `apify~instagram-profile-scraper` — never automatic — result cached to `data/competitor_scan_cache.json` so a server restart never silently re-triggers a paid scan. `compute_competitor_move()`: baseline = median engagement (likes + 6×comments) of a competitor's own recent posts; flags the single post, across all tracked competitors, with the highest multiple over *its own account's* baseline (not cross-competitor comparison) — needs ≥1.2x and ≥3 posts for a valid baseline. The profile-scraper's field extraction (`_extract_posts`/`_post_engagement_fields`) is written defensively against multiple possible field-name variants, with a `raw_post_keys` debug field for fast verification — validated correct on the first real scan.

## Proof loop — `briefing/outcomes.py`

Every "Launch Next"/"Menu Gap" term is logged automatically when a briefing generates (idempotent per month+term). Owner marks status later via Settings. `hit_rate_sentence()` opens the *next* briefing with a real hit-rate line once prior-month items resolve — never claims credit for the current month's own picks, and stays silent rather than ever opening with a 0%-win report.

## Synthesis + rendering — `synthesize.py`, `render.py`, `send.py`, `run.py`

- **synthesize.py**: works with or without `LLM_API_KEY`. Deterministic path (always available, zero cost) = mechanical bucketing + evidence-only "why" sentences. LLM path (currently unused — no key configured) makes one Anthropic Messages call for headline/phrasing only; a post-hoc guardrail strips any LLM sentence citing a number absent from that item's real evidence, replacing it with the deterministic version. Structure and numbers always come from the deterministic pass; the LLM only ever contributes prose.
- **render.py**: single email-safe HTML document, Daybreak Bakery design tokens hardcoded as Python constants (inline styles throughout, for email-client compatibility). Section order: header (+ hit-rate pill) → stats bar ("This Month at a Glance," real counts only) → "How To Read This" trust-tier note (static) → quiet-month/headline banner → competitor-move card → Launch Next / Hold & Watch / Skip / Menu Gaps / Consider Retiring → On The Radar (rising discoveries) → texture tip (LLM-only, currently always empty) → footer.
- **send.py**: Resend HTTP API. No key or no recipient → dry-run (HTML saved to `data/history/`, never crashes). Recipient resolves from Settings at send-time, `.env` `CLIENT_EMAIL` as fallback.
- **run.py**: `python -m briefing.run [--send]` — standalone CLI orchestrator, fully independent of the Flask process (usable from a cron/scheduler).

## Reliability layer — `scrapers/_reliability.py`

`run_with_fallback(source, fn)` wraps every scraper call on both refresh paths. Success → persists to `data/cache/last_good_<source>.json`, clears alert state, records a snapshot. Failure → serves last-good data (marked `stale: true`) if one exists, else a plain error dict; fires an operator alert (edge-triggered on ok→error, then throttled to once/24h while broken).

## Snapshot history — `scrapers/_history.py`

Every successful Instagram/TikTok scan records `{hashtag: metric}` (`posts_per_day` for IG, `peak_velocity` for TikTok) to a rolling list capped at 8, in `data/cache/history_<source>.json`. Feeds dashboard sparklines (top-3 chips) and the Settings "Hashtag Growth" lookup (any watched hashtag, full history). Needs ≥2 real refreshes to show anything — unlike Google Trends, which gets a full 12-month history instantly on first scan.

## Discovery filtering — `scrapers/_discovery.py`

`competitor_denylist()` pulls real identifiers from `data/competitors.json` plus curated brand-tag lists already in `instagram.py`/`tiktok.py` — a competitor's own name never gets suggested as a "new keyword." `dismissed_terms()` is an owner-permanent-dismiss list for one-off noise no rule can predict. Wired into `google_trends.py`'s rising-query aggregation and the merged `GET /api/suggested-keywords` (which also folds in Instagram caption-word discovery, not just Google).

## Per-source scraper specifics — each one is *deliberately* different, verified empirically, not accidentally inconsistent

| Source | Apify actor | What it actually returns | Ranking used |
|---|---|---|---|
| Google Trends | pytrends (not Apify) | Real 12-month time series | Trajectory (direction math above) |
| Instagram | `apify~instagram-hashtag-scraper` | Recency firehose (posts from minutes ago) | Posting volume (posts/day) |
| TikTok | `clockworks~free-tiktok-scraper` | Real top videos spanning a range of ages | Engagement velocity (plays ÷ age) |
| Pinterest | `easyapi~pinterest-search-scraper` | Boards, not pins (old actor `emastra~pinterest-scraper` is dead, 404) | Board interest (total pin count) — proven inconsistent run-to-run |
| Reddit | Public RSS (default) or praw if `REDDIT_CLIENT_ID/SECRET` set | Posts from `/hot` + `/rising` | Recency-weighted mentions, boosted by native `/rising` |
| Food media | RSS (Bon Appétit, Food52, Serious Eats, The Kitchn, Epicurious, King Arthur) | Editorial articles | Keyword match, no confidence floor (trusted source) |
| Competitor accounts | `apify~instagram-profile-scraper` | Profile + recent posts | Median-baseline outlier detection |

Google Trends has an adaptive re-query mechanism worth knowing about: Google normalizes 0–100 *within each API payload*, so a breakout term crushes niche chunk-mates to near-zero. `get_trends()` detects all-zero non-error results and re-queries just those together in a smaller cohort (recursion capped at depth 2), flagging rescued entries `cohort_normalized: True` — their absolute value is cohort-relative, direction is still valid.

"Top posts" (separate from the ranking above) is a Settings-editable strict filter: last N days + minimum views/likes/comments. TikTok checks all three (it has real view counts). Instagram checks only likes+comments — there is no public view-count field on regular IG posts via this scraper, so that threshold simply doesn't apply there; an empty "top posts" result is treated as correct, not broken.

## Frontend — `templates/index.html`, one file, no build step

- Four views, DOM siblings, toggled via `_showView(id)`: `#dashboardMain`, `#settingsView`, `#menuGapsView`, `#suggestionsView`.
- Settings is internally tabbed (Content / Discovery & Trends / Business Rules / Delivery & Schedule) via `data-tab` attributes on each existing section — not physically reordered — with `showSettingsTab(tab)` showing/hiding by attribute match and lazy-loading only that tab's data (`_SETTINGS_TAB_LOADERS`), instead of ~14 loaders firing on every Settings visit.
- State is plain `let` globals, no framework: `_gapsCache`/`_coveredCache`/`_gapsDnaApplied` (shared across dashboard/Menu&Gaps/Suggestions via one `loadSharedGaps()`), `_chartKeywordPrefs`, `_historyCache`, `_menu`, `_cfg`/`_cfgMeta`, `_competitors`, `_salesData`, `_dna`. DOM updates via template-literal `innerHTML`, with an `esc()` HTML-escape helper used on any externally-sourced text.
- Dashboard polling: `loadData()` runs once on load, then via `setInterval(loadData, 3500)` only while `is_refreshing` is true, stopped on completion — derived caches (history/gaps/chart-prefs) only re-fetch on true initial load or right when a refresh finishes, not on every poll tick.
- Chart.js (CDN): the flavor trend line chart (auto top-5-by-current-interest, or a manual pin list via Settings, with a "Gap opportunity"/"On menu"/"New" badge legend cross-referencing menu-gap data), the Hashtag Growth chart, and a Trend Matrix bubble scatter (momentum × corroboration) that a concurrent/parallel Claude session built independently — worth reviewing fresh rather than assuming full context transfer on that one piece.
- Mobile: fixed and verified at 375px. Root cause of the original overflow was a classic flexbox gotcha — `.main-wrap` is a flex item of `body{display:flex}` (the sidebar is `position:fixed`, out of flow), and flex items default to `min-width:auto`, refusing to shrink below their content's intrinsic width. Fix was `.main-wrap{min-width:0}`, plus wrapping the header/settings-tabs rows and stacking `.mg-panels` at `max-width:680px`.

## Config system — `data/config.json` via `scrapers/_config.py`

Sections: `delivery`, `schedule`, `dna`, `discovery`, `dashboard` (chart_keywords), `thresholds`, plus per-scraper watch-list overrides (`google.flavor/packaging/design`, `instagram.hashtags`, `tiktok.hashtags`, `pinterest.queries`, `reddit.subreddits/keywords`). `get_list(section,key,default)` returns the override if present and non-empty, else the scraper module's hardcoded default — every scraper always has a sane built-in list even untouched. Everything is read at scan/request time, not cached at import.

## Full API surface

```
GET/POST /login          GET /logout
GET  /
GET  /api/data
POST /api/refresh                POST /api/refresh-light
GET  /api/status
GET  /briefing/latest            GET  /api/briefings              GET  /briefing/view/<bid>
POST /briefing/run
GET/POST /api/menu
GET/POST /api/config
GET/POST /api/delivery
GET/POST /api/schedule
GET/POST /api/competitors        POST /api/competitors/scan       GET /api/competitors/scan (status)
GET  /api/competitor-move
GET/POST /api/outcomes
GET/POST /api/sales
GET/POST /api/thresholds
GET/POST /api/chart-prefs
GET  /api/suggested-keywords     POST /api/discovery/dismiss
GET  /api/history/<source>
GET/POST /api/dna
GET  /api/menu-gaps
GET  /api/scores
```

## Cost model

- **Free**: Google Trends, Reddit (RSS or praw), food media, all config/Settings CRUD, all scoring/synthesis (deterministic), rendering, dry-run email.
- **Costs Apify credits**: Instagram/TikTok/Pinterest scans (bundled in both refresh routes), competitor account scans (separate, explicit-trigger only).
- **Costs LLM API**: only if `LLM_API_KEY` is set (currently not — untested path).
- **Email**: Resend free tier (100/day, 3000/month) — effectively free at this scale.

## Known gaps, for anyone modifying this

- Still on localhost — no hosting decided.
- `scheduler.py` exists (APScheduler) but is off by default and has never run a real multi-week cycle.
- LLM synthesis path has never been exercised with a real key — only deterministic synthesis is battle-tested.
- Menu-gap word-overlap matching is intentionally fuzzy and can false-positive.
  (2026-07-05: packaging/design-category terms are now excluded from menu
  matching entirely — only `category == "flavor"` terms can be covered/retire.
  Within-flavor word overlap can still false-positive.)
- See `PRODUCT-READINESS.md` for the full gap analysis between this prototype
  and a sellable multi-tenant product.
- Auth: `APP_PASSWORD` still optional for localhost dev, but `app.py`/`wsgi.py`
  now REFUSE to bind a non-loopback host without it (2026-07-05), so a public
  deploy can't accidentally ship unauthenticated.
- Automated tests now exist: `tests/` (pytest, ~60 tests) covers the scoring
  floors, trajectory math, gap category scoping, DNA filters, the proof loop,
  and briefing rendering, plus a real-cached-data regression test. Run with
  `py -m pytest tests -q`. UI/live behavior is still verified manually.
- Multi-tenancy (2026-07-05): `tenancy.py` routes every data path through a
  per-`TENANT_ID` root (default == legacy `data/`). Phase 1 is one tenant per
  process; a shared-instance/DB model is still future work.
- Mobile layout had a real, previously-uncaught bug (only found during a deliberate audit) — worth assuming other untested surfaces may have similar latent issues rather than assuming everything's been checked.
- See `USAGE.md` for the operator/owner day-to-day guide.
