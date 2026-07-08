# Trend Radar — working notes for Claude

A trend-intelligence tool for a bakery. Flask backend, a single Jinja2 template
(`templates/index.html`) that holds the entire UI, in-memory cache, flat JSON in
`data/`. See `ARCHITECTURE.md` (how it's built), `USAGE.md` (how it's used),
`PRODUCT-READINESS.md` (what's left to sell it).

## Design system — "dark intelligence terminal"

Near-black surfaces, warm off-white ink, mono-forward type, one warm accent.
Everything is token-driven; **use the tokens, never raw hex/px**.

- **Tokens** live in the `:root` block at the top of `templates/index.html`
  (and a mirrored copy in `login.html`). There's ALSO a set of JS color
  constants (`const ESPRESSO`, `CREAM`, `LINE`, `CINNAMON`… around line ~1405)
  used by the Chart.js configs — if you change a color, change it in BOTH places.
- **Palette**: `--paper #0B0A09` (base) · `--cream #16130F` (cards) ·
  `--oat #201B16` (inputs) · ink `--espresso #F1E9DE` / `--cocoa` / `--mocha` /
  `--latte` (muted) · `--cinnamon #C85E33` (the one warm accent — keep it) ·
  `--line #2C2620` (borders). Semantic trend colors are dark-tint + light-ink.
- **Type**: `--font-display` = Fraunces (warm serif, for hero + card titles only),
  `--font-body` and `--font-mono` = Space Mono (everything else). Mono-forward.
- **Motion** (premium layer — treat as part of the design):
  - Lenis smooth scroll (CDN), inited at the bottom of the script, guarded by
    `prefers-reduced-motion`.
  - Scroll-reveal: `.section-label`s get `.reveal-el` and are revealed by an
    IntersectionObserver (`armReveals()`, called in `_showView` + on init).
  - Card hover = cinnamon glow (`.card:hover`). Hero has a radial cinnamon glow.
  - Keep new animation easing/duration consistent with these; don't invent a
    different motion style.
- **Components to reuse** (don't invent new looks): `.card`, `.section-label`,
  `.badge`, `.btn-primary` / `.btn-secondary` / `.btn-refresh`, the labeled
  sidebar rail (collapses to icon rail ≤1024px), the `.hero` band.

## Making a design change — do this

1. **Read the tokens first** (`:root` + the JS color constants). Match the
   existing type scale, spacing, radii, and motion. New UI must look native.
2. **Use tokens, not raw values.** If you change a token, update every place it
   lives (CSS `:root`, the `login.html` copy, and the JS constants) — leave no
   orphaned old values.
3. Restructuring a section is fine — this is a living app, not a locked template
   — but keep it inside the token system and verify nothing else broke.
4. **Verify before claiming done.** Two traps specific to this app:
   - Flask caches templates in `debug=False`: a template edit does NOT show on
     reload. You must fully **stop and restart the dev server** (`preview_start`).
   - Screenshots time out on the dashboard (external Instagram images). Use
     `preview_eval` DOM measurement as the source of truth; screenshot the
     **Settings view** (no external images) for a clean visual check.
   Then confirm: no horizontal overflow at 375px AND desktop; all four views
   (Trends / Suggestions / Menu & Gaps / Settings) switch with the right title
   and active state; charts stay legible on dark (Chart.js colors come from the
   JS constants); no console errors; and `py -m pytest tests -q` still passes
   (60 tests — a template change must never break the backend).
5. Report what changed, where, and how to see it.

## Other repo conventions

- Never echo/commit secrets — they live only in `.env` (`APIFY_TOKEN`, email keys).
- Real Apify spend costs money; don't trigger `/api/refresh` casually. Replaying
  `data/cache/last_good_*.json` through the pipeline verifies logic for free.
- Multi-tenant: paths route through `tenancy.py` (`data_path()`); default tenant
  == legacy `data/`. Don't build raw `data/...` paths.
