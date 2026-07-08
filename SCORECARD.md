# Product Scorecard — Trend Radar

A brutally honest report card. Each dimension is graded on its own merits, with
what's good, what's holding the grade down, and the specific fix to raise it.
Last updated 2026-07-05.

**One-line verdict:** engineering is a strong B+/A-. Business validation is an F.
The distance between those two grades *is* the whole story — the product is far
more built than it is proven.

| # | Dimension | Grade | The fix to raise it |
|---|-----------|:-----:|---------------------|
| 1 | Core scraping & pipeline | A– | Reddit official API; Pinterest reliability |
| 2 | Scoring & rigor | B+ | More/deeper social data (real ceiling, not a bug) |
| 3 | Briefing generation & delivery | A– | Verify a real domain sender; exercise LLM path |
| 4 | Automated tests | B+ | Integration/e2e + some UI coverage |
| 5 | Reliability / unattended run | B– | Run a real multi-week scheduler cycle |
| 6 | Security | C  | Depends entirely on operating model (see below) |
| 7 | Deployment readiness | B  | Actually deploy it once |
| 8 | UX / UI | A– | Card-rhythm consistency; real mobile nav |
| 9 | Multi-tenancy | C+ | Shared DB + per-request tenant isolation (phase 2) |
| 10 | **Business validation** | **F** | **One real bakery, one real cycle, one receipt** |
| 11 | Documentation | A– | (README index now added — mostly resolved) |
| 12 | Cost model | A  | (already lean — nothing to fix) |

---

## 1. Core scraping & pipeline — A–
**Good:** Six real sources (Google, Instagram, TikTok, Pinterest, Reddit, food
media) run in parallel with a last-good-fallback wrapper so one broken source
never blanks a cycle. Verified end-to-end twice with real Apify spend.
**Holding it down:** Reddit runs on throttled public RSS (official API blocked
by Reddit's own captcha); Pinterest is genuinely inconsistent run-to-run.
**Fix:** Reddit OAuth creds when obtainable (code already supports it);
Pinterest now retries-on-zero — monitor whether that's enough or drop it.

## 2. Scoring & rigor — B+
**Good:** Real direction math + cross-source confidence with minimum-evidence
floors (a single stray post can't fake corroboration). Pinterest correctly
excluded from confidence. Never fabricates a number.
**Holding it down:** Social platforms give thin local signal (0.2–0.5 posts/day
on niche tags) — a real statistical ceiling no formula can fix.
**Fix:** Not a code fix. Raise TikTok's per-tag pull (a cost dial), and accept
that Google + editorial are the trustworthy backbone; social is corroboration.

## 3. Briefing generation & delivery — A–
**Good:** Deterministic + optional-LLM synthesis, real Resend email sends
confirmed, bi-weekly cadence, events section, proof-loop receipts. Degrades
gracefully (dry-run to disk with no email key).
**Holding it down:** Sends from a Resend sandbox sender; LLM path only tested
with mocks, never a live key.
**Fix:** Verify a real sending domain; run one real LLM synthesis to confirm.

## 4. Automated tests — B+
**Good:** 91 pytest tests covering the money paths — scoring floors, gap
category scoping, DNA filters, proof loop, events/cycle math, the LLM
number-stripping guardrail, scheduler wiring, Pinterest retry.
**Holding it down:** No integration/e2e test (full refresh→score→render→send),
and the UI is verified manually, not by automation.
**Fix:** One `test_client` integration test of the whole pipeline on fixture
data; optionally a Playwright smoke test of the four views.

## 5. Reliability / unattended operation — B–
**Good:** Fallback cache + edge-triggered operator alerts (built and tested);
the scheduler is proven to fire jobs unattended and to alert on a job crash.
**Holding it down:** It has never actually run a real multi-week cycle — the
core promise ("the briefing arrives without anyone touching it") is proven in
tests, not in the wild.
**Fix:** Deploy, turn `ENABLE_SCHEDULER=1` on, and let it run for a month.

## 6. Security — C (model-dependent)
This is the dimension you flagged, and you're right to. The grade swings hard
based on how it's operated:
- **As a public multi-tenant SaaS clients log into: C–.** A single shared
  password over HTTPS is genuinely weak — no per-user accounts, no rate
  limiting, no audit log, no session hardening beyond Flask defaults.
- **As an operator console you run privately (not publicly exposed): B+.** The
  threat surface nearly vanishes. There's no customer PII, no payment data — the
  only secrets (Apify token, Resend key) live in `.env` on your machine, never
  in the UI. The client only ever receives an email.
**Mitigating facts regardless of model:** the app *refuses* to bind to a public
host without a password; secrets are never exposed to the browser; no user data
is stored beyond the bakery's own menu and public trend data.
**Fix (if you go public SaaS):** real per-tenant accounts (or an auth provider
like Auth0/Clerk), HTTPS-only cookies, rate limiting, and a secrets manager.
**Fix (if operator console):** basically done — keep it off the public internet.

## 7. Deployment readiness — B
**Good:** Dockerfile, `wsgi.py`, `.dockerignore`, `DEPLOYMENT.md`, auth guard,
boot-time cache hydration — the kit is complete and single-worker-safe.
**Holding it down:** It has never actually been deployed anywhere.
**Fix:** One real deploy to Railway/Render/Fly, or a locked-down VPS/local box.

## 8. UX / UI — A–
**Good:** Dark "intelligence terminal" redesign, token-driven, responsive-
verified at 375/730/1360px, premium motion, the briefing surfaced as the hero,
never-empty social cards with viral badges.
**Holding it down:** Card padding/heading rhythm isn't fully unified; mobile
keeps a persistent icon rail instead of a native nav pattern.
**Fix:** A consistency pass across all cards; a bottom-tab or slide-over nav on
phones.

## 9. Multi-tenancy — C+
**Good:** Phase-1 tenant-per-process (`tenancy.py`) with onboarding presets;
default tenant is byte-compatible with the legacy layout.
**Holding it down:** It's one-tenant-per-deployment, flat JSON — no shared
database, no per-request tenant resolution, no cross-tenant admin.
**Fix (only if going self-serve SaaS):** Postgres, per-request tenant scoping,
a tenant admin surface. Don't build this until a paying customer needs it.

## 10. Business validation — F
**Good:** Nothing to grade yet — that's the point.
**Holding it down:** Zero real customers. Zero proof-loop receipts. Pricing is
an estimate, not a validated number. The single most important feature (the
"we called it, you sold it" receipt) has never fired because it needs elapsed
real time, which no build substitutes for.
**Fix:** One real bakery (even the pilot bakery itself) through one or two real bi-weekly
cycles, marking Past Picks. This is the highest-leverage action available and
it's been deferred every session in favor of more building.

## 11. Documentation — B+
**Good:** ARCHITECTURE, USAGE, DEPLOYMENT, PRODUCT-READINESS, CLAUDE.md, and now
this — thorough and honest.
**Holding it down:** Six docs, no index; a newcomer doesn't know where to start.
**Fix:** A short README that routes to each doc in one paragraph.

## 12. Cost model — A
Pay-per-use Apify (~$5–20/mo per bakery), free Google/Reddit/editorial, Resend
free tier, ~$5–10/mo hosting. Margin works even at a low price. Nothing to fix.

---

## What to fix, in priority order
1. **Decide the operating model** (public SaaS vs. operator console vs. local).
   It resolves the security grade and half the roadmap. See the security section.
2. **Get one real bakery through one real cycle.** Raises the F. Nothing else
   moves the needle as much.
3. **Deploy + run the scheduler unattended for real** (privately if that's the
   model). Raises reliability and deployment from B-range to A-range.
4. **Verify a real email sending domain** so briefings can reach any recipient.
5. Everything else (integration tests, card rhythm, Reddit API, phase-2
   tenancy) is genuine polish that should wait behind 1–4.
