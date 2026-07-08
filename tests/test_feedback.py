"""Tests for briefing/feedback.py — client feedback capture (rating + detail)."""

import briefing.feedback as fb


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(fb, "FEEDBACK_PATH", tmp_path / "feedback.json")


class TestRecord:
    def test_rating_only(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        e = fb.record_feedback(rating=4)
        assert e["rating"] == 4 and e["note"] == ""

    def test_note_only(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        e = fb.record_feedback(note="more Chicago-specific trends please")
        assert e["rating"] is None and "Chicago" in e["note"]

    def test_rating_clamped_and_coerced(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        assert fb.record_feedback(rating="9")["rating"] == 5   # clamp high
        assert fb.record_feedback(rating=0)["rating"] == 1     # clamp low
        assert fb.record_feedback(rating="bad", note="x")["rating"] is None

    def test_empty_feedback_rejected(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        assert fb.record_feedback() is None
        assert fb.record_feedback(rating="", note="   ") is None

    def test_note_length_capped(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        e = fb.record_feedback(note="x" * 5000)
        assert len(e["note"]) == 2000


class TestAggregate:
    def test_feedback_by_term_averages(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        fb.record_feedback(rating=5, term="tahini cookie")
        fb.record_feedback(rating=3, term="tahini cookie", note="too niche")
        fb.record_feedback(rating=4, term="matcha cake")
        by_term = fb.feedback_by_term()
        assert by_term["tahini cookie"]["avg"] == 4.0
        assert by_term["tahini cookie"]["count"] == 2
        assert "too niche" in by_term["tahini cookie"]["notes"]

    def test_summary(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        fb.record_feedback(rating=5)
        fb.record_feedback(rating=3, note="ok")
        s = fb.summary()
        assert s["total"] == 2 and s["avg_rating"] == 4.0 and s["with_notes"] == 1

    def test_list_newest_first(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        fb.record_feedback(rating=1, note="first")
        fb.record_feedback(rating=5, note="second")
        items = fb.list_feedback()
        assert items[0]["note"] == "second"
