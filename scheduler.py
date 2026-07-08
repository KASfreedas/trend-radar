"""
scheduler.py — Phase 4: in-process cron (04_BUILD_PLAN.md Phase 4)

Two recurring jobs against the same cache/pipeline app.py serves:
  - weekly refresh_all()                (default: Monday 05:00 America/Chicago)
  - monthly generate + email briefing   (default: the 1st, 08:00 America/Chicago)

Disabled by default — set ENABLE_SCHEDULER=1 to opt in. This matches the
existing "explicit opt-in for automation/spend" pattern already used for
AUTO_REFRESH and the competitor scan button: nothing fires on its own until
you deliberately turn it on, which should only happen once this is deployed
somewhere that stays up (not a laptop that's asleep at 5am Monday).

Day/hour are Settings-editable (Schedule card -> data/config.json "schedule"
section; see scrapers/_config.py). A change takes effect on the next server
restart (the scheduler reads config once, at start()).
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

BAKERY_TZ = ZoneInfo("America/Chicago")
logger = logging.getLogger("scheduler")


def _schedule_config() -> dict:
    from scrapers._config import get_value
    return {
        "refresh_day": get_value("schedule", "refresh_day", "mon"),
        "refresh_hour": int(get_value("schedule", "refresh_hour", "5")),
        "send_day_of_month": int(get_value("schedule", "send_day_of_month", "1")),
        "send_hour": int(get_value("schedule", "send_hour", "8")),
    }


def _weekly_refresh_job():
    try:
        logger.info("weekly refresh starting")
        from app import refresh_all
        refresh_all(background=False)
        logger.info("weekly refresh done")
    except Exception as e:
        from briefing.send import send_operator_alert
        send_operator_alert(
            subject="[Trend Radar] Scheduled weekly refresh crashed",
            body=f"The weekly refresh job raised an unhandled error.\n\n"
                 f"Error: {e!r}\nTime: {datetime.now(timezone.utc).isoformat()}",
        )


def _monthly_briefing_job():
    try:
        logger.info("monthly briefing starting")
        from briefing.run import run as run_briefing
        run_briefing(send=True)
        logger.info("monthly briefing sent")
    except Exception as e:
        from briefing.send import send_operator_alert
        send_operator_alert(
            subject="[Trend Radar] Scheduled monthly briefing crashed",
            body=f"The monthly generate+send job raised an unhandled error — "
                 f"the client may NOT have received a briefing this month.\n\n"
                 f"Error: {e!r}\nTime: {datetime.now(timezone.utc).isoformat()}",
        )


def start() -> BackgroundScheduler:
    cfg = _schedule_config()
    sched = BackgroundScheduler(timezone=BAKERY_TZ)

    sched.add_job(
        _weekly_refresh_job,
        CronTrigger(day_of_week=cfg["refresh_day"], hour=cfg["refresh_hour"], minute=0, timezone=BAKERY_TZ),
        id="weekly_refresh", replace_existing=True,
    )
    # Bi-weekly: two sends per month — the configured day and 14 days later
    # (capped at 28 so it exists in February). Both render from the weekly
    # scrape cache, so the second send costs zero extra Apify credits.
    day1 = min(cfg["send_day_of_month"], 28)
    day2 = min(day1 + 14, 28)
    sched.add_job(
        _monthly_briefing_job,
        CronTrigger(day=f"{day1},{day2}", hour=cfg["send_hour"], minute=0, timezone=BAKERY_TZ),
        id="biweekly_briefing", replace_existing=True,
    )
    sched.start()
    logger.info(
        "started — weekly refresh %s@%02d:00, bi-weekly send days %d & %d @%02d:00 (America/Chicago)",
        cfg["refresh_day"], cfg["refresh_hour"], day1, day2, cfg["send_hour"],
    )
    return sched
