# Product Readiness — Honest Assessment (2026-07-05)

> **Status update (same day):** Tier 0 items 1 (code side), 3, 4, and 5 are
> now done — 60-test pytest suite (`tests/`), operator alerting verified
> already built (`scrapers/_reliability.py`), public-bind auth guard
> (`app.py` + `wsgi.py`), Dockerfile/DEPLOYMENT.md, boot-time cache
> hydration (empty-briefing-after-restart bug found and fixed). Tier 1
> items 6 (phase-1: tenant-per-process via `tenancy.py`), 9 (`presets.py` +
> `/api/presets`), and 10 (receipts now name the winning items) are started
> or done. Still open: actually deploying to a host, a real unattended
> scheduler cycle, phase-2 shared-instance tenancy, billing, and the pilot.

Companion to `ARCHITECTURE.md`. That file describes what exists; this one
describes the distance between what exists and a product a brick-and-mortar
business pays $500/month for. Written to be brutally honest, not to sell.

## Verdict up front

- **What exists today**: a working, real-data-validated, single-tenant
  prototype. It genuinely scrapes, scores, filters, and emails. It is a good
  demo and a legitimate pilot tool. It is **not yet a product**.
- **Is $500/mo realistic?** Not for a single-location bakery — realistic
  single-location willingness-to-pay is $50–150/mo. $500/mo is defensible
  **only at franchise/multi-location HQ level** (e.g., 10 locations ×
  $50/location of value), and only after Tier 0 + Tier 1 below are done.
- **Website or native app?** Web + email. Building a native app would be a
  mistake at this stage — see the last section.

## Why $500/mo is a stretch today (the uncomfortable part)

1. **The data has a proven ceiling.** The first real full-scale month
   produced an honest "quiet month": 30 terms scored, 1 rising, and that one
   at low confidence with zero corroborating sources — correctly suppressed
   by Brand DNA. That honesty is the system working, but a $500/mo customer
   expects actionable output most months. Local bakery content runs
   0.2–0.5 posts/day per hashtag; Pinterest has returned inconsistent counts
   in two separate real tests. No pricing tier fixes thin source data.
2. **The competitive squeeze.** Above this product sit enterprise
   food-trend platforms (Tastewise, Spoonshot — $1k+/mo, CPG-grade data
   pipelines). Below it sits a shift manager spending one paid hour a week
   on TikTok. $500/mo has to beat the manager decisively and be honest that
   it isn't the enterprise tier. Per-location cost of ~$50 across a
   franchise is where that math actually closes.
3. **The retention feature is unproven.** The thing that keeps a paying
   customer past month 3 is the Sales Tracker proof loop — "we flagged X on
   [date], you launched it [date], it sold N units." The code exists
   (`briefing/outcomes.py`, `briefing/sales.py`) but has never run a real
   multi-month cycle. Until it produces one real receipt, the sales pitch
   is a promise, not evidence.

## The discrepancy list, organized

### Tier 0 — blockers to selling to even ONE customer

1. **Hosting + HTTPS + auth on by default.** Still localhost; `APP_PASSWORD`
   unset by default. Nothing else matters until this is a URL a customer
   can log into.
2. **Scheduler hardening.** `scheduler.py` (APScheduler) exists but has
   never run a real unattended multi-week cycle. A paid product's core
   promise is "the briefing arrives without anyone touching it."
3. **Failure alerting to the operator.** The reliability layer falls back
   to last-good data silently. Fine for a demo; for a paid product, a
   source failing for 3 weeks straight while briefings quietly reuse stale
   data is a churn event. Operator email on source failure is table stakes.
4. **An automated test suite for the money paths.** Zero pytest files
   exist. Scoring (`score.py`), gap logic (`gaps.py` — which had a real
   category bug found only by reading a real briefing), DNA filters, and
   render must have tests before any refactor for multi-tenancy, or that
   refactor will silently break the outputs customers pay for.
5. **Secrets handling.** One `.env` on one box is fine today; it does not
   extend to N customers or a real deploy pipeline.

### Tier 1 — required before charging $500/mo

6. **Multi-tenancy.** The current design is single-tenant *by
   construction*: one in-memory `_cache`, one `config.json`, one
   `menu.json`, flat JSON history files. Product version needs a real
   database (Postgres; SQLite-per-tenant acceptable to start) with
   tenant-scoped config, menu, DNA, watch lists, history, and briefings.
   This is the single largest engineering item on this list.
7. **Multi-location model.** The $500/mo buyer is a franchise HQ:
   per-market watch lists (Chicago ≠ Nashville), per-location menus,
   per-location briefings plus an HQ rollup. Without this, the price point
   has no buyer.
8. **Billing + budget caps.** Stripe subscriptions, and a per-tenant Apify
   spend cap so one tenant's aggressive watch list can't burn the margin.
9. **Onboarding templates.** Configuring watch lists/menu/DNA well
   currently requires expertise. Vertical presets (cupcakes, cookies,
   coffee, pizza…) that a new customer can adopt in 15 minutes are what
   make the product sellable without a services engagement per customer.
10. **Automatic ROI receipts.** The outcomes loop should self-generate
    "we flagged this N weeks before it peaked" lines in the briefing. This
    is the renewal argument, automated.

### Tier 2 — result-quality optimizations (cheap, parallel)

11. **Term clustering/dedup** — near-duplicate terms ("dubai chocolate" /
    "ghirardelli dubai style chocolate") currently count separately.
12. **TikTok results-per-tag 5 → 25** — the biggest data-quality lever per
    dollar; deliberately deferred to control spend, revisit when a
    customer is paying.
13. **Pinterest: fix or drop.** Inconsistent in two independent real tests
    (same query, wildly different counts; one query returning 0). Either
    add retry-on-zero or remove the source — a paid product should not
    ship a known-flaky signal, even display-only.
14. **Reddit official API** when credentials become obtainable (RSS works
    but is shallower).
15. **LLM synthesis path**: exercise with a real key or delete the code
    path — untested paid paths are liabilities.
16. **Remaining gaps.py fuzziness**: the packaging/design category bug is
    fixed (2026-07-05), but word-overlap within flavors can still
    false-positive (e.g., any two terms sharing "cake").

## Per-tenant cost model (grounded in the real full-scale run)

- One full refresh: ~900 paid Apify results (772 Instagram + 105 TikTok +
  Pinterest), ~7 minutes wall clock. At pay-per-result actor pricing this
  is on the order of **single dollars per run**.
- Weekly cadence → roughly **$5–20/mo Apify per tenant** depending on watch
  list size. Hosting ~$10–20/mo total across all tenants at small scale.
  Resend free tier covers email (100/day).
- Realistic COGS: **$15–40/mo per tenant**. Margin works even at $99/mo.
  **Price is constrained by demonstrated value, not by cost** — which is
  why the proof loop (item 10) matters more than any scraper improvement.

## Website or native app — the direct answer

Stay web + email. Reasons:

- **The email is the product.** A bakery owner's decision cadence is
  weekly/monthly. An inbox briefing meets them where they already are; an
  app asks them to build a new habit.
- A native app adds app-store review friction, a second codebase, and
  push notifications — which add nothing over email at this cadence.
- The dashboard's job is configuration and verification, which is a
  responsive web page (mobile layout was audited and fixed 2026-07).
- If customers ever want urgency, add **SMS alerts** (Twilio) for
  high-confidence spikes long before considering an app.

## Honest sequencing recommendation

1. Tier 0 (roughly 2–3 weeks of focused work) →
2. **Pilot with 2–3 real bakeries at $99/mo** — this validates the value
   story and generates real proof-loop data, which no amount of building
   can substitute for →
3. Tier 1 built against pilot feedback →
4. Raise to $500/mo at franchise-HQ level once the briefing can show at
   least one real "we called it" receipt.

Skipping step 2 and going straight to a $500 price with no receipts is the
most likely way this fails commercially despite working technically.
