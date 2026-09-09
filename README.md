# Trend Radar

A trend-intelligence tool for a bakery. It scrapes six sources (Google Trends,
Instagram, TikTok, Pinterest, Reddit, food media), scores them for real
momentum and cross-source corroboration, cross-references them against the
owner's actual menu and sales, watches competitors, tracks upcoming calendar
events, and produces a **bi-weekly "Specials Board Briefing"** — live on a dark
dashboard and delivered by email — recommending what to launch, watch, skip, or
retire.

**One rule threaded through everything: never cite a number that isn't real and
observed.** When the signal is thin, the briefing says "quiet cycle" rather than
inventing excitement. That honesty is the product's credibility — and it's
enforced in code, not just intended: minimum-evidence floors in the scorer, and
a guardrail that strips any figure a language model tries to invent.

## What it does

- **Six-source scraping with graceful failure.** Google Trends, Instagram,
  TikTok, Pinterest, Reddit, and food-media RSS run in parallel. Every source is
  wrapped so a failure falls back to the last good result (tagged stale) and
  fires one operator alert — one broken source never blanks a cycle.
- **Honest scoring.** Direction (rising / peaking / fading) comes from a
  12-month series; confidence (high / medium / low) comes from cross-source
  corroboration with minimum-evidence floors, so a single stray post can't fake
  a trend. Pinterest is deliberately excluded from confidence.
- **The bi-weekly briefing.** Buckets every candidate into Launch / Watch /
  Skip / Retire with a one-line "why" that restates only real evidence. Renders
  to a dark dashboard hero and an HTML email. Narrative wording is
  deterministic by default, or optionally written by a language model
  (Anthropic API **or** a local Ollama model) — with a guardrail that reverts
  any sentence citing a number absent from the evidence.
- **Per-market pages** (`/market/<key>`). The owner runs multiple locations
  grouped into market clusters; each market gets its own page — a live
  local-buzz trend line, launch picks routed to that market's risk profile,
  its local event calendar with decide-by dates, live occasion demand, and
  neighborhood hashtag movers. An HQ rollup summarizes all markets.
- **Menu-gap analysis.** Trends *not* on the menu surface as opportunities;
  trends already on the menu show as covered; fading menu items show as retire
  candidates.
- **Discovery.** Auto-surfaces emerging flavor keywords from cross-source
  corroboration, with owner-editable rules (blocklist, classic-flavor list,
  sensitivity thresholds) so noise can be tuned out without touching code.
- **Occasion demand.** Reads which cake-order occasions (graduation, wedding,
  birthday…) are heating up in the social feeds, flagging genuine seasonal
  spikes separately from year-round steady demand.
- **"Became viral this week" ranking.** Top posts are ranked by engagement
  *gained since the last scan* — a measured delta — not merely by what was
  posted recently, so an older post that just blew up is caught honestly.
- **Competitor watch + events.** Tracks competitor accounts for standout posts,
  and keeps a curated recurring calendar (national + per-market) with lead-time
  math so a special can be planned weeks ahead.
- **Multi-tenant.** One instance per bakery via `TENANT_ID`; a demo tenant
  ships generic so the codebase can be shown publicly without exposing a client.

## How it works

```
sources ──▶ scrapers/ ──▶ briefing/score.py ──▶ briefing/synthesize.py ──▶ output
(6 APIs/    (per-source    (direction +          (bucket + "why",           ├─ dashboard (Flask + Jinja)
 RSS)        + fallback)    confidence floors)     guardrailed narrative)     └─ email (bi-weekly briefing)
                                   ▲
                    menu / sales / clusters / events / DNA
                    (owner-editable flat JSON under data/)
```

Scraped data is cached in memory and on disk; scoring, gap analysis, and
rendering all read that cache, so the dashboard and briefing never trigger a
paid scrape on their own. Refreshes are on-demand or scheduled.

## Quickstart

```bash
pip install -r requirements.txt      # first time
py app.py                            # → http://127.0.0.1:5050
py -m pytest tests -q                # run the 151-test suite
```

Nothing scrapes on startup (that would cost Apify credits) — data loads from the
last saved results on disk; refresh on demand from the dashboard. Real scraping
needs `APIFY_TOKEN` in `.env` (copy `.env.example`). Email delivery needs
`EMAIL_API_KEY`; without it, briefings are saved to disk instead of sent.
Optional LLM narrative: set `LLM_PROVIDER=ollama` for a local model, or
`LLM_API_KEY` for the Anthropic API — either way the never-invent-numbers
guardrail still applies.

## Start here, by role

- **Running or using it?** → [USAGE.md](USAGE.md) — the operator + owner guide:
  the bi-weekly rhythm, the four dashboard views, the trust ladder, Settings,
  cost, onboarding a new bakery.
- **Modifying the code or design?** → [CLAUDE.md](CLAUDE.md) (design tokens,
  the dark theme, the change-and-verify workflow) and
  [ARCHITECTURE.md](ARCHITECTURE.md) (full technical architecture — modules,
  scoring engine, API surface, per-source scraper details).
- **Deploying it?** → [DEPLOYMENT.md](DEPLOYMENT.md) — Docker/gunicorn, hosting
  options, required env vars, the single-worker rule.
- **Deciding what to fix or whether to sell it?** →
  [SCORECARD.md](SCORECARD.md) (a graded report card + prioritized fix list) and
  [PRODUCT-READINESS.md](PRODUCT-READINESS.md) (the gap between this prototype
  and a sellable product, with pricing reality).

## The docs, in one line each

| Doc | What it's for |
|-----|---------------|
| [USAGE.md](USAGE.md) | How to run and use it well (operator + owner). |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How it's built — modules, data flow, API surface. |
| [CLAUDE.md](CLAUDE.md) | Design system + working notes for anyone (or any agent) changing the code. |
| [DEPLOYMENT.md](DEPLOYMENT.md) | How to deploy it (or run it as a private always-on console). |
| [SCORECARD.md](SCORECARD.md) | Graded product report card + what to fix, in priority order. |
| [PRODUCT-READINESS.md](PRODUCT-READINESS.md) | Prototype → sellable-product gap analysis + pricing. |
| [PROJECT_LOG.md](PROJECT_LOG.md) | Historical build log (older; superseded by the above). |

## Repo map

```
app.py                  Flask app — routes, cache, refresh orchestration, /api/*
tenancy.py              per-tenant path routing (data_path); default == legacy data/
clusters.py             market clusters (multi-location): grouping, launch routing
presets.py              onboarding presets for a new bakery/vertical
scheduler.py            bi-weekly refresh + send cron (opt-in, ENABLE_SCHEDULER)
wsgi.py                 gunicorn entry point

scrapers/               one module per source + shared infra
  google_trends.py  instagram.py  tiktok.py  pinterest.py  reddit.py  food_media.py
  _reliability.py       last-good fallback wrapper + operator alerts
  _history.py           rolling snapshot history (sparklines, viral-gain deltas)
  _config.py            owner-editable watch lists + thresholds (data/config.json)
  _engagement.py  _discovery.py  competitor_accounts.py

briefing/               the intelligence layer
  score.py              direction + cross-source confidence (the scoring engine)
  gaps.py               menu-gap analysis          synthesize.py  bucketing + LLM veneer + guardrail
  render.py             HTML briefing + dashboard fragments
  events.py             calendar + occasion-buzz    cycle.py       bi-weekly cadence
  dna.py                brand-fit filter            sales.py       real-sales tracker
  outcomes.py           past-picks / proof loop     feedback.py    client feedback
  dataset.py            ML-ready observation log     run.py send.py competitors.py

templates/              index.html (whole dashboard UI) · market.html · hq.html
                        · portal.html · login.html
tests/                  151 tests over the money paths + honesty guarantees
data/                   flat JSON: menu, sales, clusters, config, cache (gitignored)
```

## Facts worth knowing up front

- **Stack:** Flask + one Jinja2 template (`templates/index.html`, the whole UI),
  in-memory cache, flat JSON under `data/`. No database. Chart.js + Lenis on the
  frontend. pytest for the money-path tests.
- **Cost:** Apify is pay-per-use (~$5–20/mo per bakery). Google, Reddit,
  editorial, email (Resend free tier), and the local-Ollama LLM path are
  effectively free.
- **How it's run:** the dashboard is an **operator console**; the client's
  product is the email. Run it privately (local or a locked-down box) — see
  USAGE "Starting it up" and SCORECARD §6 for the security reasoning.
- **Multi-tenant:** one instance per bakery via `TENANT_ID`; `py tenancy.py new
  <id> --preset cupcakes --city chicago` scaffolds a new one.

## License

Source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md):
you may read, run, and experiment with this code for any noncommercial
purpose. **Commercial use — including running it for a business — requires a
separate commercial license.** Contact the copyright holder.
