"""Tests for briefing/dataset.py — the ML-ready observation log.

Proves features are captured at decision time, the log is idempotent per cycle,
and observations join cleanly with outcomes + feedback into a labeled table."""

import json

import briefing.dataset as ds
import briefing.outcomes as outcomes_mod
import briefing.feedback as fb_mod


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "OBSERVATIONS_PATH", tmp_path / "observations.json")
    monkeypatch.setattr(outcomes_mod, "OUTCOMES_PATH", tmp_path / "outcomes.json")
    monkeypatch.setattr(fb_mod, "FEEDBACK_PATH", tmp_path / "feedback.json")


def _scored():
    return [
        {"term": "tahini cookie", "category": "flavor", "direction": "rising",
         "delta": 0.4, "current_interest": 62, "confidence": "medium",
         "sources_agreeing": 1, "evidence": ["x"]},
        {"term": "dubai chocolate", "category": "flavor", "direction": "fading",
         "delta": -0.2, "current_interest": 30, "confidence": "high",
         "sources_agreeing": 3, "evidence": ["y"]},
    ]


def _synth():
    return {"launch": [{"term": "tahini cookie"}], "watch": [], "skip": [],
            "gaps": [{"term": "tahini cookie"}], "retire": [{"term": "dubai chocolate"}]}


def _gaps():
    return {"gaps": [{"term": "tahini cookie"}], "covered": [],
            "retire": [{"term": "dubai chocolate"}]}


class TestRecordObservations:
    def test_captures_feature_vector_and_decision(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        n = ds.record_observations(_scored(), _gaps(), _synth(), "2026-07-a", "Early July 2026")
        assert n == 2
        rows = {r["term"]: r for r in ds.list_observations()}
        tc = rows["tahini cookie"]
        assert tc["cycle_id"] == "2026-07-a"
        assert tc["features"] == {"direction": "rising", "delta": 0.4,
                                  "current_interest": 62, "confidence": "medium",
                                  "sources_agreeing": 1}
        assert tc["decision"] == "launch"          # launch wins over gap
        assert tc["menu_status"] == "off_menu"
        assert rows["dubai chocolate"]["decision"] == "retire"
        assert rows["dubai chocolate"]["menu_status"] == "on_menu"

    def test_idempotent_per_cycle(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        ds.record_observations(_scored(), _gaps(), _synth(), "2026-07-a", "Early July 2026")
        ds.record_observations(_scored(), _gaps(), _synth(), "2026-07-a", "Early July 2026")
        # Same cycle re-run replaces, not duplicates.
        assert len(ds.list_observations()) == 2

    def test_different_cycles_accumulate(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        ds.record_observations(_scored(), _gaps(), _synth(), "2026-07-a", "Early July 2026")
        ds.record_observations(_scored(), _gaps(), _synth(), "2026-07-b", "Late July 2026")
        assert len(ds.list_observations()) == 4


class TestTrainingTable:
    def test_joins_outcome_label_by_cycle_and_term(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        ds.record_observations(_scored(), _gaps(), _synth(), "2026-07-a", "Early July 2026")
        # Log the pick and resolve it as sold_well.
        outcomes_mod.record_picks(_synth(), "Early July 2026")
        outcomes_mod.set_status("Early July 2026", "tahini cookie", "selling_well")
        table = {r["term"]: r for r in ds.build_training_table()}
        assert table["tahini cookie"]["outcome"] == "selling_well"
        assert table["dubai chocolate"]["outcome"] is None  # unresolved

    def test_joins_term_feedback(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        ds.record_observations(_scored(), _gaps(), _synth(), "2026-07-a", "Early July 2026")
        fb_mod.record_feedback(rating=5, note="loved it", term="tahini cookie")
        table = {r["term"]: r for r in ds.build_training_table()}
        assert table["tahini cookie"]["feedback"]["avg"] == 5.0

    def test_csv_export_has_flat_feature_columns(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        ds.record_observations(_scored(), _gaps(), _synth(), "2026-07-a", "Early July 2026")
        csv_text = ds.to_csv()
        header = csv_text.splitlines()[0]
        assert "feat_delta" in header and "feat_confidence" in header
        assert "outcome" in header
        assert "tahini cookie" in csv_text

    def test_coverage_counts_labeled(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        ds.record_observations(_scored(), _gaps(), _synth(), "2026-07-a", "Early July 2026")
        outcomes_mod.record_picks(_synth(), "Early July 2026")
        outcomes_mod.set_status("Early July 2026", "tahini cookie", "selling_well")
        cov = ds.coverage()
        assert cov["observations"] == 2
        assert cov["labeled_outcomes"] == 1
        assert cov["cycles_recorded"] == 1
