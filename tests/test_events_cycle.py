"""Tests for briefing/cycle.py (bi-weekly briefing identity) and
briefing/events.py (upcoming-events engine + trend tie-ins)."""

import json
from datetime import date, datetime, timezone

import pytest

import briefing.events as events_mod
from briefing.cycle import cycle_id, cycle_label, label_for_id, cycle_half
from briefing.events import (upcoming_events, event_tie_ins, occasion_buzz,
                             _nth_weekday, _easter)


def _dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


class TestCycle:
    def test_first_half_is_a(self):
        assert cycle_half(_dt(2026, 7, 1)) == "a"
        assert cycle_half(_dt(2026, 7, 14)) == "a"

    def test_second_half_is_b(self):
        assert cycle_half(_dt(2026, 7, 15)) == "b"
        assert cycle_half(_dt(2026, 7, 31)) == "b"

    def test_ids_never_collide_within_month(self):
        assert cycle_id(_dt(2026, 7, 3)) == "2026-07-a"
        assert cycle_id(_dt(2026, 7, 20)) == "2026-07-b"

    def test_labels(self):
        assert cycle_label(_dt(2026, 7, 3)) == "Early July 2026"
        assert cycle_label(_dt(2026, 7, 20)) == "Late July 2026"

    def test_label_for_id_new_and_legacy(self):
        assert label_for_id("2026-07-a") == "Early July 2026"
        assert label_for_id("2026-07-b") == "Late July 2026"
        assert label_for_id("2026-06") == "June 2026"      # legacy monthly file
        assert label_for_id("garbage") == "garbage"        # graceful fallback


class TestDateRules:
    def test_nth_weekday(self):
        # 2nd Sunday of May 2026 (Mother's Day) = May 10
        assert _nth_weekday(2026, 5, 6, 2) == date(2026, 5, 10)
        # 4th Thursday of Nov 2026 (Thanksgiving) = Nov 26
        assert _nth_weekday(2026, 11, 3, 4) == date(2026, 11, 26)

    def test_easter_known_years(self):
        assert _easter(2026) == date(2026, 4, 5)
        assert _easter(2027) == date(2027, 3, 28)


class TestUpcomingEvents:
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(events_mod, "EVENTS_PATH", tmp_path / "events.json")

    def test_window_and_ordering(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        evs = upcoming_events(window_days=60, today=date(2026, 7, 1))
        names = [e["name"] for e in evs]
        assert "Independence Day" in names            # Jul 4 — 3 days out
        assert "Back to School" in names              # Aug 15 — 45 days out
        assert "Halloween" not in names               # Oct 31 — outside window
        assert evs == sorted(evs, key=lambda e: e["days_until"])

    def test_act_now_status_uses_lead_time(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        evs = upcoming_events(window_days=60, today=date(2026, 7, 1))
        by_name = {e["name"]: e for e in evs}
        # July 4 with 21-day lead: decide-by long past → act_now
        assert by_name["Independence Day"]["status"] == "act_now"
        # Back to School (Aug 15, 21-day lead → decide by Jul 25): 24 days away → upcoming
        assert by_name["Back to School"]["status"] == "upcoming"

    def test_year_rollover(self, tmp_path, monkeypatch):
        # In late December, next year's Valentine's must NOT appear in a
        # 60-day window, but New Year's Eve (this year) must.
        self._isolate(tmp_path, monkeypatch)
        evs = upcoming_events(window_days=45, today=date(2026, 12, 20))
        names = [e["name"] for e in evs]
        assert "New Year's Eve" in names
        assert "Christmas" in names
        assert "Valentine's Day" not in names

    def test_seeds_editable_calendar_file(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        upcoming_events(today=date(2026, 7, 1))
        seeded = json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))
        assert any(e["name"] == "Halloween" for e in seeded)


class TestTieIns:
    def test_only_rising_or_peaking_terms_attach(self):
        events = [{"name": "Halloween", "date": "2026-10-31", "days_until": 30,
                   "lead_days": 28, "decide_by": "2026-10-03", "status": "upcoming",
                   "keywords": ["pumpkin", "spooky"]}]
        scored = [
            {"term": "pumpkin spice cupcake", "direction": "rising",
             "confidence": "medium", "category": "flavor",
             "evidence": ["Google Trends: 60/100 (+40% vs prior period)"]},
            {"term": "pumpkin bread", "direction": "fading",
             "confidence": "high", "category": "flavor", "evidence": []},
        ]
        out = event_tie_ins(events, scored)
        ties = out[0]["tie_ins"]
        assert [t["term"] for t in ties] == ["pumpkin spice cupcake"]
        # Evidence passes through verbatim — the stat is real, not invented.
        assert ties[0]["evidence"] == ["Google Trends: 60/100 (+40% vs prior period)"]

    def test_placeholder(self):
        pass


class TestLocalEvents:
    """Per-market recurring local events (HQ multi-location layer)."""

    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(events_mod, "EVENTS_PATH", tmp_path / "events.json")
        monkeypatch.setattr(events_mod, "LOCAL_EVENTS_PATH", tmp_path / "local_events.json")

    def test_cluster_filter_returns_only_that_market(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        # Wide window so seasonal events land regardless of test date.
        dt = date(2026, 8, 1)
        downtown = upcoming_events(window_days=120, today=dt, cluster="downtown")
        assert downtown, "expected some downtown events in a 120-day window"
        assert all(e["cluster"] == "downtown" for e in downtown)
        # Taste of Chicago (Sept 5) should be in a downtown Aug-1 window.
        assert any("Taste of Chicago" in e["name"] for e in downtown)

    def test_national_query_excludes_local_events(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        national = upcoming_events(window_days=120, today=date(2026, 8, 1))
        assert all(e.get("cluster") is None for e in national)

    def test_local_events_recur_annually(self, tmp_path, monkeypatch):
        # A rule-based event resolves in consecutive years (reusable, not one-off).
        self._isolate(tmp_path, monkeypatch)
        this_year = upcoming_events(window_days=120, today=date(2026, 8, 1), cluster="downtown")
        next_year = upcoming_events(window_days=120, today=date(2027, 8, 1), cluster="downtown")
        assert {e["name"] for e in this_year} == {e["name"] for e in next_year}

    def test_seeds_editable_local_file(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        upcoming_events(today=date(2026, 8, 1), cluster="suburban_malls")
        seeded = json.loads((tmp_path / "local_events.json").read_text(encoding="utf-8"))
        assert any(e["name"] == "Skokie Backlot Bash" for e in seeded)


class TestOccasionBuzz:
    """Live occasion-demand signal read from social caption words + co-hashtags."""

    def _ig(self):
        return {
            "trending_words": [
                {"word": "graduation", "count": 20},
                {"word": "grad", "count": 8},
                {"word": "birthday", "count": 40},
            ],
            "related_tags": [{"tag": "weddingcake", "count": 5}],
        }

    def test_counts_are_real_tallies(self):
        buzz = occasion_buzz(self._ig(), None, today=date(2026, 6, 1))
        by = {b["occasion"]: b for b in buzz}
        assert by["Graduation"]["mentions"] == 28   # 20 + 8, summed from variants
        assert by["Birthday"]["mentions"] == 40

    def test_seasonal_spike_sorts_above_year_round(self):
        # June: graduation is a narrow-window spike; birthday is year-round core.
        buzz = occasion_buzz(self._ig(), None, today=date(2026, 6, 1))
        assert buzz[0]["occasion"] == "Graduation"
        assert buzz[0]["in_season"] is True
        birthday = next(b for b in buzz if b["occasion"] == "Birthday")
        assert birthday["in_season"] is False       # year-round ≠ "peak season"
        assert birthday["seasonal"] is False

    def test_off_season_drops_the_peak_flag(self):
        # January: graduation still counted, but not flagged in-season.
        buzz = occasion_buzz(self._ig(), None, today=date(2026, 1, 15))
        grad = next(b for b in buzz if b["occasion"] == "Graduation")
        assert grad["in_season"] is False

    def test_min_mentions_floor_filters_noise(self):
        thin = {"trending_words": [{"word": "graduation", "count": 1}]}
        assert occasion_buzz(thin, None, today=date(2026, 6, 1)) == []

    def test_empty_and_missing_sources_are_safe(self):
        assert occasion_buzz(None, None) == []
        assert occasion_buzz({}, {}) == []

    def test_tiktok_source_contributes(self):
        tt = {"trending_words": [{"word": "graduation", "count": 5}]}
        buzz = occasion_buzz(None, tt, today=date(2026, 6, 1))
        assert any(b["occasion"] == "Graduation" and b["mentions"] == 5 for b in buzz)


class TestTieInsExtra:
    def test_no_match_keeps_event_with_empty_tie_ins(self):
        events = [{"name": "National Donut Day", "date": "2026-06-05",
                   "days_until": 10, "lead_days": 14, "decide_by": "2026-05-22",
                   "status": "act_now", "keywords": ["donut"]}]
        out = event_tie_ins(events, [{"term": "matcha cake", "direction": "rising",
                                      "confidence": "low", "category": "flavor",
                                      "evidence": []}])
        assert out[0]["tie_ins"] == []
