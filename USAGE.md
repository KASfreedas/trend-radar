# Trend Radar — Usage Guide

How to actually use this tool well, month to month. `ARCHITECTURE.md` explains
how it's built; this explains how to run it and — more importantly — how to
get real decisions out of it without being fooled by weak signal.

There are two roles, and this guide is split to match:

- **Owner** — the bakery decision-maker. Reads the briefing, works the
  dashboard, makes the launch/retire calls, logs what actually happened.
- **Operator** — whoever runs the software (you). Triggers refreshes, keeps
  the watch lists sane, manages deployment and cost.

If one person does both, read the whole thing. If you're handing the Owner
role to a non-technical client, the "For the Owner" sections stand alone.

---

## The 30-second mental model

The Radar watches six outside signals — Google search interest, Instagram,
TikTok, Pinterest, Reddit, and food-media articles — and **every two weeks** it
tells you what to **launch, watch, skip, or retire** on your specials board,
plus which **calendar events** are close enough to start planning for.

Two things make it different from just scrolling TikTok yourself:

1. **It scores for real momentum and corroboration, not vibes.** A flavor
   only earns "high confidence" when several independent sources agree, each
   with a real minimum amount of activity behind it. One viral post doesn't
   count as a trend.
2. **It never makes up a number.** Every claim in a briefing restates
   something actually scraped. When the signal is thin, it says "quiet month"
   instead of inventing excitement. That honesty is the point — it's what
   makes the confident months worth acting on.

The single most important habit: **treat it as a shortlist generator, not an
oracle.** It narrows the whole internet down to a handful of candidates worth
your judgment. You still bring the judgment.

---

## The rhythm — how it's actually used

| Cadence | Who | What |
|---|---|---|
| **Weekly** | Operator | Trigger a data refresh (or let the scheduler do it). Glance at the dashboard for anything spiking. |
| **Bi-weekly** (1st & 15th) | System | A "Specials Board Briefing" generates and emails automatically — twice a month. |
| **Bi-weekly** | Owner | Read the briefing. Decide what to try. **Mark last cycle's picks** as sold-well / didn't take off / never launched. |
| **As needed** | Owner | Enter sales numbers; run a competitor scan; adjust the menu. |

The briefing is the product. Everything else — the dashboard, the settings —
exists to make those emails trustworthy and tailored. The bi-weekly cadence
(cycles labeled "Early July" / "Late July") means twice the touchpoints and
twice the trend history, at **zero extra scraping cost** — both briefings
render from the same weekly scrape data.

---

## Starting it up (Operator)

The dashboard is an **operator console** — a tool for whoever runs the Radar.
The *client's* product is the email briefing; a bakery owner never has to log
into anything. That framing matters for how you run it:

**Local (the recommended default):**

```
py app.py
```

Opens on `http://127.0.0.1:5050`. No password needed on localhost. Nothing
scrapes on startup (that would cost money every restart) — data loads from the
last saved results on disk, and you refresh on demand. Running it on your own
machine (or a private box only you reach) keeps the whole security surface
tiny: there's no customer data, and the only secrets live in `.env`, never in
the browser.

**Always-on (so the scheduler can run unattended):** the one reason to keep it
running beyond your own sessions is the bi-weekly auto-send. Run it as a
single always-on process — on a locked-down VPS you control, or a always-on
home box — with a persistent `data/` volume and `ENABLE_SCHEDULER=1`. If that
box is ever reachable from the public internet, set `APP_PASSWORD` (the app
refuses to bind to a public host without one). See `DEPLOYMENT.md`.

**Multiple bakeries:** run one instance per business (each with its own
`TENANT_ID`, data volume, and — if exposed — password). See "Onboarding" below.
Note that a single shared password is fine for a private operator console but
is **not** strong enough for a public, client-facing multi-tenant login — see
`SCORECARD.md` §6 for the security trade-offs before exposing it that way.

---

## The four views

The UI is one page with four views, switched from the left sidebar. No page
reloads.

### 1. Trends (dashboard) — *the daily glance*
Top to bottom:
- **The briefing hero** — your latest Specials Board Briefing, front and
  center, with "Open briefing" and "Generate now" buttons.
- **Radar stats strip** — live proof numbers (sources live, terms scored,
  rising / peaking / fading, menu gaps) — the same counts the briefing cites.
- **Live pulse** — the single hottest signal across sources right now.
- **Planning Intelligence** — two cards:
  - **Coming Up** — calendar events inside the 60-day window, each with a
    *decide-by date* (so you have lead time) and any trending terms that match
    them. An orange "decide by" pill means act now.
  - **Hashtag Movers** — the biggest posting-rate changes between your last two
    scans, with real ▲/▼ percentages.
- **Google Trends** 12-month flavor chart, then **Instagram / TikTok /
  Pinterest / Reddit / editorial** intelligence.
- **Briefing Archive** — past briefings, searchable, at the bottom.

The **REFRESH ALL** button (top right) pulls fresh data. On Instagram and
TikTok, the "Top Posts" cards always show the most-engaged real content, and
tag genuinely viral posts (cleared the high like/comment bar) with a **"✓ Viral"
badge** — so the card is never empty, and the truly-big ones still stand out.

Use it to: spot something spiking mid-cycle, see what's coming on the calendar,
sanity-check that sources are current, and open past briefings.

### 2. Menu & Gaps — *the opportunity map*
Cross-references what's trending against **your actual menu**:
- **Gaps** — trending and *not* on your menu → the opportunity list.
- **Covered** — trending and already on your menu → you're on it, promote it.
- **Retire candidates** — fading and *on* your menu → consider cutting.

This is only as good as your menu data. Keep `Settings → Menu` accurate.

### 3. Suggestions — *the "act on this now" shortlist*
The gaps list, already filtered by your Brand DNA (see below) and capped to a
sensible number of moves per month, so it's a short, do-able list rather than
a firehose.

### 4. Settings — *configuration* (four tabs, below)

### Market pages — `/market/<key>` *(multi-location)*
Each market cluster gets its own page: a poster-style header with that
market's real local-buzz trend line drawn under its name, the launch picks
routed to that market's risk profile, its local event calendar with
decide-by dates, live occasion demand, neighborhood hashtag activity with
scan-over-scan movers, and its tracked competitors. Open them from the
**HQ Rollup** view ("View market page →" on each market card); prev/next
links at the bottom cycle through all markets. Same honesty rule as the
briefing: every number restates a scraped value, and a quiet market says
so plainly instead of dressing it up.

---

## Reading the outputs — the trust ladder

This is the part people get wrong, so the briefing itself prints it. Not every
number deserves the same weight. From most to least trustworthy:

1. **Your own sales data** (Sales Tracker). Real units you actually sold. This
   beats any scraped signal — nothing is more real than your own register.
2. **High-confidence picks.** Google search momentum backed by 3+ independent
   sources clearing their evidence floors. Safe to act on.
3. **Competitor Watch.** A specific real post that genuinely overperformed a
   competitor's own baseline. Concrete, but narrow — one post, one moment.
4. **Medium/low-confidence gaps and "On The Radar" discoveries.** Early
   signal. Worth watching, *not* worth betting the specials board on yet.

Rule of thumb: **launch off tier 1–2, experiment off tier 3, just monitor
tier 4.** If something sits at low confidence, that's the tool telling you it
hasn't earned a decision yet — not that it's hiding a sure thing.

A **"quiet month" is a real answer, not a failure.** It means no flavor
cleared the bar this cycle. Holding your menu steady on a quiet month is the
system working correctly.

---

## Configuring it (Settings)

Settings has four tabs. You set these up once, then touch them occasionally.

### Content
- **Menu** ("Current Menu") — your real flavors, formats, toppings,
  seasonal items. Drives the entire gap analysis. Keep it current; a stale
  menu produces false gaps and false retire suggestions.
- **Sales Tracker** ("Monthly Unit Sales") — enter roughly how many of each
  item sold this month. After 2+ months are logged, the tool blends your real
  sales with live trend data (the most trustworthy signal it has — see the
  trust ladder).

### Discovery & Trends
- **Watch Lists** ("Scraper Watch Lists") — the Google keywords, hashtags,
  subreddits, and Pinterest queries each source tracks. Sensible defaults ship
  built-in. Edits apply on the next refresh, no restart. **Bigger lists cost
  more** on the paid sources (Instagram/TikTok/Pinterest) — see cost, below.
- **Flavor Chart** ("Which Lines Show on the Dashboard Chart") — pick which
  lines show on the dashboard trend chart (auto top-5, or pin up to 5).
- **Top Post Thresholds** ("What Counts As A Top Post") — the **"✓ Viral" bar**:
  last N days plus minimum views/likes/comments (defaults 10 days, 10k views,
  10k likes, 1k comments). The Top Posts cards always show the most-engaged real
  posts regardless; clearing this bar just adds the viral badge. If almost
  nothing ever earns the badge on your local tags, lower these numbers to match
  the scale of the accounts you track.
- **Discovery Rules** ("What Shows Up as a Suggestion") — the same idea as Top
  Post Thresholds, but for the *flavor-discovery / hashtag feed* on the
  Suggestions page. Four controls, all applied immediately (no refresh needed):
  - **Blocklist** — terms you never want suggested (a name that keeps
    resurfacing, a location, a competitor). Type one per line; they vanish from
    suggestions for good.
  - **Classic flavors** — your menu staples (chocolate, vanilla, red velvet…).
    These are hidden because you already make them, but a *specific twist*
    ("dubai chocolate", "black sesame") still comes through. Edit to match your
    menu; "Reset to defaults" restores the built-in list.
  - **Min sources to surface** — how corroborated a term must be before it
    shows. Lower = more ideas (noisier); higher = only strongly-cross-confirmed
    ones. Google rising queries always show regardless.
  - **Min mentions for occasion buzz** — how many social mentions before an
    occasion (graduation, wedding…) is flagged as heating up in "Coming Up."
- **Hashtag Growth** ("Track Any Hashtag's Growth") — any watched hashtag's
  post-volume over time. Needs at least two refreshes before it can draw a line.

### Business Rules
- **Brand DNA** ("What Counts As A Good Fit") — the tailoring that makes it
  yours:
  - **Risk tolerance** — Conservative (high confidence only) / Balanced
    (high + medium) / Adventurous (include early breakouts). A hard filter on
    what reaches your action list.
  - **Dietary / ingredient exclusions** — a comma list that blocks any gap
    containing those words.
  - **Max new items / month** — caps how many gaps land on the Suggestions
    page, so you're never handed 20 "must-try" flavors.
  - **Brand voice** — free-text personality. Only affects wording *if* an LLM
    key is configured (it isn't by default); it can never override the
    never-invent-a-number rule.
  - Set risk tolerance honestly: Conservative suits a business that can't
    afford flops; Adventurous is for when you *want* early bets.
- **Competitors** ("Tracked Competitors") — the competitor Instagram accounts
  the scan checks. Managed here; the scan itself is a button (see Competitor
  Watch / cost, below).
- **Past Picks** ("Did They Sell?") — where you mark what happened to prior
  briefing picks. This is the proof loop — see its section below.

### Delivery & Schedule
- **Delivery** ("Briefing Recipient") — where the briefing is emailed.
- **Schedule** ("Refresh & Send Timing") — the weekly-refresh day/hour and the
  send day. The briefing goes out on that day **and again ~14 days later**
  (bi-weekly). Schedule changes need a restart to take effect (everything else
  is live).

> **Note on noise:** to permanently silence a junk discovery term, use the
> **dismiss control on the Suggestions page** (not a Settings card) — it hides
> that term from future keyword discovery.

---

## The bi-weekly briefing (Owner)

Arrives twice a month (cycles labeled "Early July" / "Late July"). Top to bottom:

- **Hit-rate line** (when earned) — "2 of the 3 items we flagged last cycle
  are now top sellers: …". Only appears once you've marked prior picks. This
  is the receipt that proves the tool is working.
- **This Cycle at a Glance** — real counts: sources scanned, terms scored,
  rising / peaking / fading, gaps, retire candidates.
- **How To Read This** — the trust ladder above, reprinted.
- **Headline / quiet-cycle banner.**
- **Coming Up** — calendar events close enough to plan for, with decide-by
  dates and any trending terms that tie into them.
- **Competitor Watch** — the single most notable competitor post this cycle.
- **Launch Next / Hold & Watch / Skip / Menu Gaps / Consider Retiring.**
- **On The Radar** — early rising discoveries, explicitly not yet proven.

Then do the one thing that compounds: go to **Settings → Past Picks and mark
what happened.** Which items you launched, which sold, which flopped.

---

## The proof loop — why month 6 beats month 1

This is the feature that makes the tool worth paying for, and it only works if
you feed it.

Every briefing logs its picks. When you later mark them
sold-well / didn't-take-off / never-launched, the *next* briefing can open
with a real, specific track record ("the item we flagged last cycle — tahini
cookie — is now a top seller"). It never claims credit for the current month's
own picks, and it stays silent rather than ever leading with a bad month.

Skip the marking step and you get a competent trend scraper. Do it every cycle
and you get a system that visibly proves its own hit rate over time — the
difference between a tool you tolerate and one you renew.

---

## Refreshing data & staying cost-aware (Operator)

Two ways to pull fresh data:

- **Refresh All** (`POST /api/refresh`) — full watch lists, real scale. This
  is the normal weekly pull. Sources run in parallel; a full run takes a few
  minutes.
- **Light refresh** (`POST /api/refresh-light`) — small subsets, for cheap
  testing when you're changing config and don't want to pay full price.

**What costs money:** Instagram, TikTok, and Pinterest run through Apify
(pay-per-result). Bigger hashtag/query lists = more results = more cost per
refresh. Google Trends, Reddit, food media, and everything else are free.

**Competitor scans are separate and manual.** They only run when you click
"Scan Competitors" — never automatically — and the result is cached so a
restart never silently re-charges you.

Rough cost: a full weekly refresh is on the order of single dollars; monthly
Apify spend per business lands around $5–20 depending on list sizes. Keep
watch lists focused and you keep the bill down.

**If a source breaks,** the Radar serves the last good data (marked stale) and
emails the Operator an alert instead of silently shipping an empty briefing.
Don't ignore those alerts — a source stale for weeks means decisions on old
data.

---

## Onboarding a new business or location (Operator, Tier 1)

The Radar can run for more than one bakery. Each business runs as its own
tenant (its own data, config, menu, and briefings), selected by a `TENANT_ID`.

Spin one up, pre-loaded for its vertical:

```
py tenancy.py new joes-donuts --preset donuts --city denver
py tenancy.py list
```

Presets ship for **cupcakes, cookies, donuts, coffee shops, and ice cream** —
each seeds sensible keywords, hashtags, subreddits, and a starter menu, with
`--city` adding localized food hashtags. From there the Owner tunes the menu
and Brand DNA. You can also apply a preset to the running tenant via
`Settings`/the `/api/presets` endpoints (it asks for confirmation first,
because it replaces the watch lists).

Run each tenant as its own deployment with its own `TENANT_ID`, password, and
data volume. The default tenant is the original pilot setup, unchanged.

---

## Quick troubleshooting

| Symptom | Almost always means |
|---|---|
| "Quiet month," no picks | Genuinely thin signal this cycle. Working as intended. Hold the menu. |
| A gap/retire that makes no sense | Menu is stale, or a loose word-overlap match. Update `Settings → Menu`. |
| Same noise term keeps appearing | **Dismiss it on the Suggestions page.** |
| No "✓ Viral" badges on Top Posts | Nothing cleared the high viral bar this window (normal for local tags). The cards still show the most-engaged posts. Lower the thresholds in Settings if you want the badge to appear more. |
| Pinterest numbers look erratic | Known: Pinterest is display-only and excluded from confidence scoring for exactly this reason. Don't make decisions on it alone. |
| Hashtag Growth / sparklines blank | Needs 2+ refreshes to have anything to chart. |
| Briefing looks empty right after a restart | Trigger a refresh before generating — though the cache now reloads from disk on boot, so fresh data is there if a recent refresh ran. |

---

## The one-paragraph version

Keep your menu and Brand DNA accurate, refresh weekly, read the briefing every
cycle (twice a month), act off the top of the trust ladder, ignore the "quiet
cycles," and — above all — **mark what actually happened to last cycle's
picks.** Do that and the Radar stops being a trend scraper and becomes a record
of decisions that paid off.
