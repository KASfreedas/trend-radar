"""Tests for Pinterest retry-on-zero (scrapers/pinterest.py).

Pinterest returns wildly inconsistent counts run-to-run; a zero is more likely
a transient blip than a true empty, so it retries once. These tests use a fake
_search — no real Apify runs."""

import scrapers.pinterest as pin


class TestRetryOnZero:
    def test_no_retry_when_first_call_has_results(self, monkeypatch):
        calls = {"n": 0}
        def fake(q, l):
            calls["n"] += 1
            return [{"pinCount": 100}]
        monkeypatch.setattr(pin, "_search", fake)
        items, retried = pin._search_resilient("matcha dessert", 20)
        assert items and calls["n"] == 1 and retried is False

    def test_retries_once_on_zero_then_succeeds(self, monkeypatch):
        seq = [[], [{"pinCount": 827}]]  # first empty (blip), second real
        monkeypatch.setattr(pin, "_search", lambda q, l: seq.pop(0))
        items, retried = pin._search_resilient("pistachio cake", 20)
        assert retried is True
        assert items == [{"pinCount": 827}]

    def test_retry_bounded_to_one(self, monkeypatch):
        calls = {"n": 0}
        def always_empty(q, l):
            calls["n"] += 1
            return []
        monkeypatch.setattr(pin, "_search", always_empty)
        items, retried = pin._search_resilient("dubai chocolate", 20)
        # Exactly one retry — never an unbounded loop of paid runs.
        assert calls["n"] == 2 and items == [] and retried is True
