"""Tests for briefing/outcomes.py — the proof loop. hit_rate_sentence is the
renewal argument; it must never claim credit early or report a 0% month."""

import briefing.outcomes as outcomes_mod
from briefing.outcomes import record_picks, set_status, list_outcomes, hit_rate_sentence


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(outcomes_mod, "OUTCOMES_PATH", tmp_path / "outcomes.json")


def _log(month, terms):
    record_picks({"launch": [{"term": t, "category": "flavor"} for t in terms],
                  "gaps": []}, month)


class TestRecordPicks:
    def test_records_launch_and_gap_terms(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        record_picks({"launch": [{"term": "a", "category": "flavor"}],
                      "gaps": [{"term": "b", "category": "flavor"}]}, "July 2026")
        assert {i["term"] for i in list_outcomes()} == {"a", "b"}
        assert all(i["status"] == "not_yet" for i in list_outcomes())

    def test_idempotent_per_month_and_term(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        _log("July 2026", ["a"])
        _log("July 2026", ["a"])
        assert len(list_outcomes()) == 1
        # Same term in a NEW month is a new row.
        _log("August 2026", ["a"])
        assert len(list_outcomes()) == 2


class TestSetStatus:
    def test_valid_status_updates(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        _log("July 2026", ["a"])
        assert set_status("July 2026", "a", "selling_well") is True
        assert list_outcomes()[0]["status"] == "selling_well"

    def test_invalid_status_rejected(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        _log("July 2026", ["a"])
        assert set_status("July 2026", "a", "went_viral") is False

    def test_unknown_term_returns_false(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        assert set_status("July 2026", "nope", "selling_well") is False


class TestHitRateSentence:
    def test_silent_when_nothing_resolved(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        _log("July 2026", ["a"])
        assert hit_rate_sentence("August 2026") is None

    def test_silent_when_zero_wins(self, tmp_path, monkeypatch):
        # Exists to build trust, not report failures.
        _isolate(tmp_path, monkeypatch)
        _log("July 2026", ["a"])
        set_status("July 2026", "a", "underperformed")
        assert hit_rate_sentence("August 2026") is None

    def test_never_counts_current_month(self, tmp_path, monkeypatch):
        # Marking the CURRENT month's own pick resolved must not produce a claim.
        _isolate(tmp_path, monkeypatch)
        _log("August 2026", ["a"])
        set_status("August 2026", "a", "selling_well")
        assert hit_rate_sentence("August 2026") is None

    def test_singular_win_names_the_item(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        _log("July 2026", ["tahini cookie"])
        set_status("July 2026", "tahini cookie", "selling_well")
        assert hit_rate_sentence("August 2026") == \
            "The item we flagged last cycle — tahini cookie — is now a top seller."

    def test_multi_win_counts_and_names(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        _log("July 2026", ["tahini cookie", "matcha cupcake", "c"])
        set_status("July 2026", "tahini cookie", "selling_well")
        set_status("July 2026", "matcha cupcake", "selling_well")
        set_status("July 2026", "c", "underperformed")
        assert hit_rate_sentence("August 2026") == \
            "2 of the 3 items we flagged last cycle are now top sellers: " \
            "tahini cookie, matcha cupcake."
