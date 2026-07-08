"""Tests for scheduler.py — proves the unattended runner is wired correctly:
the right jobs/triggers register, APScheduler actually fires a job on its own,
and a crashing job alerts the operator instead of dying silently.

No Apify spend: the refresh/briefing targets are monkeypatched."""

import threading
import time

import pytest

import scheduler as sched_mod


class TestTriggerRegistration:
    def test_registers_weekly_and_biweekly_jobs(self, monkeypatch):
        monkeypatch.setattr(sched_mod, "_schedule_config", lambda: {
            "refresh_day": "mon", "refresh_hour": 5,
            "send_day_of_month": 1, "send_hour": 8,
        })
        sched = sched_mod.start()
        try:
            ids = {j.id for j in sched.get_jobs()}
            assert "weekly_refresh" in ids
            assert "biweekly_briefing" in ids
            biweekly = sched.get_job("biweekly_briefing")
            # Two sends: the configured day and 14 days later.
            assert "day='1,15'" in str(biweekly.trigger)
        finally:
            sched.shutdown(wait=False)

    def test_send_day_offset_and_cap(self, monkeypatch):
        # send_day 20 → second send at min(34,28)=28, not day 34 (doesn't exist).
        monkeypatch.setattr(sched_mod, "_schedule_config", lambda: {
            "refresh_day": "fri", "refresh_hour": 6,
            "send_day_of_month": 20, "send_hour": 9,
        })
        sched = sched_mod.start()
        try:
            trig = str(sched.get_job("biweekly_briefing").trigger)
            assert "day='20,28'" in trig
        finally:
            sched.shutdown(wait=False)


class TestUnattendedFiring:
    def test_apscheduler_fires_a_job_on_its_own(self):
        """Confidence check: a started BackgroundScheduler executes a job on its
        trigger with nobody calling it — the core promise of 'runs unattended'."""
        from apscheduler.schedulers.background import BackgroundScheduler
        from datetime import datetime, timedelta

        fired = threading.Event()
        s = BackgroundScheduler()
        s.add_job(fired.set, "date", run_date=datetime.now() + timedelta(seconds=0.5))
        s.start()
        try:
            assert fired.wait(timeout=4), "scheduled job did not fire unattended"
        finally:
            s.shutdown(wait=False)


class TestFailureAlerting:
    def test_briefing_job_alerts_operator_on_crash(self, monkeypatch):
        import briefing.run as run_mod
        import briefing.send as send_mod

        monkeypatch.setattr(run_mod, "run", lambda **k: (_ for _ in ()).throw(RuntimeError("kaboom")))
        alerts = []
        monkeypatch.setattr(send_mod, "send_operator_alert",
                            lambda subject, body: alerts.append(subject))

        # Must not raise, and must fire exactly one operator alert.
        sched_mod._monthly_briefing_job()
        assert len(alerts) == 1
        assert "briefing" in alerts[0].lower()
