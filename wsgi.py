"""Production entrypoint — wsgi.py

Run with:  gunicorn --workers 1 --threads 8 --bind 0.0.0.0:5050 wsgi:app

app.py's `if __name__ == "__main__"` block never executes under a WSGI
server, so the deploy-time concerns live here instead:
  - refuse to serve without APP_PASSWORD (a WSGI deploy is by definition
    not localhost-only)
  - start the scheduler if ENABLE_SCHEDULER=1

Worker model note: the app keeps its scrape cache in process memory
(app._cache) — it MUST run as exactly one worker process (threads are
fine). More workers means each has its own cache and a refresh in one is
invisible to the others.
"""

import os

from app import app, APP_PASSWORD

if not APP_PASSWORD:
    raise SystemExit(
        "Refusing to start under WSGI: APP_PASSWORD is not set. "
        "A WSGI deploy is network-reachable — set APP_PASSWORD in the environment."
    )

if not os.getenv("FLASK_SECRET_KEY", "").strip():
    # Not fatal, but every restart logs all users out and (with >1 replica)
    # sessions won't stick. Loud warning instead of silent weirdness.
    print("WARNING: FLASK_SECRET_KEY is not set — sessions reset on every restart.")

if os.getenv("ENABLE_SCHEDULER") == "1":
    import scheduler
    scheduler.start()
