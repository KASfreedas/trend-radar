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
inventing excitement. That honesty is the product's credibility.

## Quickstart

```bash
pip install -r requirements.txt      # first time
py app.py                            # → http://127.0.0.1:5050
py -m pytest tests -q                # run the 91-test suite
```

Nothing scrapes on startup (that would cost Apify credits) — data loads from the
last saved results on disk; refresh on demand from the dashboard. Real scraping
needs `APIFY_TOKEN` in `.env` (copy `.env.example`). Email delivery needs
`EMAIL_API_KEY`; without it, briefings are saved to disk instead of sent.

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

## Facts worth knowing up front

- **Stack:** Flask + one Jinja2 template (`templates/index.html`, the whole UI),
  in-memory cache, flat JSON under `data/`. No database. Chart.js + Lenis on the
  frontend. pytest for the money-path tests.
- **Cost:** Apify is pay-per-use (~$5–20/mo per bakery). Google, Reddit,
  editorial, email (Resend free tier) are effectively free.
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
