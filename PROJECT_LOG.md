# Buttercup Bakery — Trend Radar: Build Log

## Overview

A live social media trend intelligence dashboard built for **Buttercup Bakery** (Chicago) to monitor baking trends across flavors, packaging, and design aesthetics. The system scrapes six data sources in parallel and presents them through a branded web dashboard.

---

## What Was Built

### Backend — `app.py`

Flask server running on port 5050. Six scrapers run in parallel threads on startup, with results cached in memory. Four API routes:

| Route | Purpose |
|---|---|
| `GET /` | Serves the dashboard HTML |
| `GET /api/data` | Returns all cached scraper results as JSON |
| `POST /api/refresh` | Triggers a background re-scrape of all sources |
| `GET /api/status` | Shows per-source readiness and last refresh time |

### Scrapers

#### 1. Google Trends — `scrapers/google_trends.py`
Uses `pytrends` (unofficial Google Trends API). Queries three keyword groups:
- **Flavors**: dubai chocolate, matcha, pistachio, ube, croissant, bento cake, etc.
- **Packaging**: custom cake box, bakery box design, eco bakery packaging, etc.
- **Design**: coquette cake, cottagecore baking, Y2K cake, Korean minimalist cake, etc.

**Key issue fixed**: `pytrends` broke with `urllib3` 2.x when passed `retries=2`. Removed that parameter entirely.

#### 2. Reddit — `scrapers/reddit.py`
Pulls from public Atom RSS feeds (`/r/<sub>/hot/.rss`) — no OAuth required. Scores posts by keyword relevance.

**Subreddits** (expanded from 6 → 14):
`Baking`, `cakedecorating`, `pastry`, `Cupcakes`, `bakersofreddit`, `ArtisanBread`, `DessertPorn`, `FoodPorn`, `Breadit`, `cookies`, `chocolate`, `foodphotography`, `PastryChefs`, `veganbaking`

**Why RSS**: Reddit's JSON API returns 403 for unauthenticated requests.

#### 3. Food Media — `scrapers/food_media.py`
Parses RSS feeds from editorial publications:
- Bon Appétit, Food52, Serious Eats, The Kitchn, Epicurious, King Arthur Baking

Returns top articles ranked by keyword relevance to baking trends.

#### 4. Instagram — `scrapers/instagram.py`
Uses Apify actor `apify~instagram-hashtag-scraper`. Scrapes 15 baking hashtags and extracts:
- **Top posts** (image, caption, likes, comments, owner)
- **Hashtag engagement** (total + avg per post)
- **Trending caption words** (NLP word frequency, stop-words filtered)
- **Co-occurring hashtags** (what creators pair with each tag)

**Why Apify**: Meta Graph API was abandoned after extensive troubleshooting (app platform config, Facebook Page creation, Business account switching, token expiry every 2 hours). Apify provides equivalent data with a single long-lived API token.

#### 5. TikTok — `scrapers/tiktok.py`
Uses Apify actor `clockworks~free-tiktok-scraper`. Searches 12 baking hashtags and returns:
- Top videos by play count (cover image, description, author, plays, likes)
- Hashtag aggregate stats (total plays, video count)

#### 6. Pinterest — `scrapers/pinterest.py`
Uses Apify actor `emastra~pinterest-scraper`. Searches baking Pinterest queries via URL format and returns:
- Top pins (image, title, save count, source query)
- Trending topics by pin volume

**Note**: The originally specified actor `apify~pinterest-scraper` returned 404 (doesn't exist). Switched to `emastra~pinterest-scraper` with URL-based search input.

---

## Environment Setup

```
trend-scraper/
├── app.py
├── .env                  ← APIFY_TOKEN=<token>
├── requirements.txt
├── scrapers/
│   ├── google_trends.py
│   ├── reddit.py
│   ├── food_media.py
│   ├── instagram.py
│   ├── tiktok.py
│   └── pinterest.py
└── templates/
    └── index.html
```

`.env` must be UTF-8 **without BOM**. Windows Notepad saves UTF-16 by default which breaks `python-dotenv`. Use VS Code or PowerShell to write the file. All scrapers load it with:
```python
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", encoding="utf-8-sig")
```

---

## Dashboard — `templates/index.html`

Single-page app with Chicago editorial branding. Polls `/api/data` on load and populates all sections via JavaScript.

### Typography Stack

| Role | Font | Source |
|---|---|---|
| Brand logo | **Pacifico** | Google Fonts — cursive, signature bakery feel |
| Card headings | **Cormorant Garamond** | Google Fonts — elegant editorial serif |
| Section dividers | **Abril Fatface** | Google Fonts — bold display, high contrast |
| Body / UI | **Nunito** | Google Fonts — round, friendly, readable |
| Stats / numbers | **Space Grotesk** | Google Fonts — clean geometric monospace feel |

### Color Palette

| Variable | Hex | Use |
|---|---|---|
| `--cream` | `#FFF8EC` | Page background |
| `--red` | `#E31837` | Chicago red — primary accent, headings |
| `--blue` | `#9BD7F4` | Chicago blue — secondary tags, chips |
| `--navy` | `#1A202C` | Body text |
| `--gray` | `#4A5568` | Muted labels |

### Layout

- **64px fixed sidebar** with SVG icon buttons (Trends, Social, Analytics, Settings)
- **72px sticky header** with logo, source status badges, Refresh All button
- **Insight bar** — single-line summary of top finding from each source
- **Main content** scrolls independently

### Sections

1. **Google Trends** — Chart.js line chart for flavor keywords + ranked tables for packaging & design
2. **Instagram Intelligence** — 9-post image grid, caption word cloud, hashtag engagement table, related tags
3. **TikTok** — Video cards with play counts and cover images; hashtag leaderboard
4. **Pinterest** — Pin grid with save counts
5. **Editorial & Community** — Reddit hot posts + food media article cards
6. **Top Flavors** — Summary score bar at bottom

### Decorative elements

- Chicago skyline SVG path as page watermark (4% opacity, `#E31837`)
- All icons are inline SVG — no emoji used as UI elements

---

## Key Problems Encountered

### Meta Graph API (abandoned)
Spent significant time trying to connect Instagram via the official Meta API:
- Required creating a Facebook Page (account had none)
- Required switching Instagram to a Professional (Business) account
- Short-lived access tokens expired every ~2 hours
- `ig_hashtag_search` returned "nonexisting field" errors on personal accounts

**Resolution**: Replaced entirely with Apify. Single token, no expiry issues, richer data.

### pytrends urllib3 incompatibility
`TrendReq(retries=2)` raised `TypeError: Retry.__init__() got an unexpected keyword argument 'method_whitelist'` with urllib3 2.x.

**Fix**: Remove `retries=2`.

### Reddit 403 on JSON API
`/r/<sub>.json` returns 403 without OAuth. Public RSS feeds (`/r/<sub>/hot/.rss`) remain open.

### Windows UTF-16 BOM in .env
Notepad saved the `.env` as UTF-16 LE with BOM (`0xFF 0xFE`), causing `UnicodeDecodeError` on load.

**Fix**: Strip BOM with PowerShell, use `encoding="utf-8-sig"` in `load_dotenv()`.

### Flask template caching
Flask with `debug=False` serves Jinja2 templates from disk per-request but the preview tool reused the running process. Needed full server restart (stop + start) to pick up template changes.

---

## Running the App

```bash
cd "C:\Users\ianby\Claude Code\trend-scraper"
python app.py
```

Then open `http://localhost:5050`. Initial scrape runs in the background — data appears within 30–60 seconds for Google/Reddit/Food Media, up to 3 minutes for Apify sources (Instagram, TikTok, Pinterest).

Click **Refresh All** in the header to trigger a fresh scrape at any time.
