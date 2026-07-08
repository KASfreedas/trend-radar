# Deployment

The app is a single Flask process with an in-memory scrape cache and all
persistent state in `data/` (flat JSON). That gives two hard rules:

1. **Exactly one worker process.** Threads for concurrency are fine
   (`--threads 8`), but a second worker gets its own empty cache and its own
   scheduler. The Dockerfile already enforces this.
2. **`data/` must be a persistent volume.** Config, menu, briefing history,
   hashtag snapshots, and outcome tracking all live there. Lose it and the
   proof loop starts over.

## Required environment

| Var | Why |
|---|---|
| `APP_PASSWORD` | `wsgi.py` refuses to start without it — a WSGI deploy is network-reachable. |
| `FLASK_SECRET_KEY` | Stable session signing. Generate once: `python -c "import secrets;print(secrets.token_hex(32))"` |
| `APIFY_TOKEN` | Social scraping (pay-per-use). |
| `EMAIL_API_KEY`, `CLIENT_EMAIL`, `OPERATOR_EMAIL` | Briefing delivery + failure alerts. |
| `ENABLE_SCHEDULER=1` | Weekly refresh + monthly send. Only enable on the deployed instance — never on a laptop copy, or two schedulers will both scrape and both email. |

Full list with explanations: `.env.example`.

## Host options (in order of least effort)

- **Railway / Render / Fly.io** — Dockerfile detected automatically; attach
  a volume at `/app/data`; set env vars in the dashboard; TLS is provided.
  ~$5–10/mo. This is the right choice for the pilot.
- **A $6/mo VPS** (Hetzner/DigitalOcean) — `docker run` with a volume and a
  Caddy reverse proxy for TLS. Cheapest, most manual.
- **Not** shared PHP-style hosting or serverless — the scheduler and the
  in-memory cache both need one long-lived process.

## Docker quickstart

```bash
docker build -t trend-radar .
docker run -d --name trend-radar \
  -p 5050:5050 \
  -v trendradar_data:/app/data \
  --env-file .env \
  -e HOST=0.0.0.0 -e ENABLE_SCHEDULER=1 \
  trend-radar
```

First boot on an empty volume starts with no scrape data — either trigger a
refresh from the dashboard or copy an existing `data/` directory into the
volume.

## Local dev (unchanged)

`py app.py` — binds 127.0.0.1:5050, no password needed, scheduler off.
Binding any other `HOST` without `APP_PASSWORD` exits with an error.

## Verifying a deploy

1. `/login` prompts and rejects a wrong password.
2. Dashboard loads after login; sources show cached/empty state.
3. `POST /briefing/run` (without `send=1`) generates a briefing from cache.
4. Check gunicorn logs for the scheduler start line if `ENABLE_SCHEDULER=1`.
5. Confirm `OPERATOR_EMAIL` receives the alert if you temporarily break a
   source (e.g., wrong `APIFY_TOKEN`) and refresh — this is the alerting
   path that protects a paying customer.
