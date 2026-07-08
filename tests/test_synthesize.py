"""Tests for briefing/synthesize.py — the number-invention guardrail.

This is the safety-critical path: when an LLM writes the 'why' sentences, any
figure it cites that isn't in the item's real evidence MUST be stripped and
replaced with the deterministic, evidence-only sentence. These tests prove the
guardrail catches a fabricated statistic without needing a live API key."""

import briefing.synthesize as syn
from briefing.synthesize import (
    _why_is_grounded, _enforce_guardrails, _deterministic_synthesis, synthesize,
)


EVIDENCE = ["Google Trends: 62/100 (+40% vs prior period)",
            "Reddit: \"tahini cookie\" mentioned 4x in hot posts"]


class TestGroundedness:
    def test_why_with_only_real_numbers_is_grounded(self):
        # Numbers restated from evidence (no comma directly after a digit — the
        # guardrail regex treats trailing commas as thousands separators).
        assert _why_is_grounded("Rising to 62/100 and 40% up with 4x mentions", EVIDENCE)

    def test_why_with_invented_number_is_not_grounded(self):
        # 9000 appears nowhere in the evidence — fabrication.
        assert not _why_is_grounded("Exploding — 9000 searches last week", EVIDENCE)

    def test_number_free_why_is_grounded(self):
        assert _why_is_grounded("Rising momentum with medium confidence", EVIDENCE)


class TestEnforceGuardrails:
    def _synth_with_why(self, why):
        return {
            "launch": [{"term": "tahini cookie", "evidence": EVIDENCE, "why": why}],
            "watch": [], "skip": [], "gaps": [], "retire": [],
            "texture_tip": None,
        }

    def _det(self):
        return {
            "launch": [{"term": "tahini cookie", "evidence": EVIDENCE,
                        "why": "Rising momentum with medium confidence — "
                               + "; ".join(EVIDENCE) + "."}],
            "watch": [], "skip": [], "gaps": [], "retire": [],
        }

    def test_fabricated_why_replaced_with_deterministic(self):
        synth = self._synth_with_why("Massive — 9000 searches, +500% overnight")
        out = _enforce_guardrails(synth, self._det())
        assert "9000" not in out["launch"][0]["why"]
        assert "Rising momentum" in out["launch"][0]["why"]

    def test_grounded_why_is_kept(self):
        good = "Worth launching — Google Trends: 62/100 (+40% vs prior period)"
        out = _enforce_guardrails(self._synth_with_why(good), self._det())
        assert out["launch"][0]["why"] == good

    def test_texture_tip_with_numbers_is_stripped(self):
        synth = self._synth_with_why("ok")
        synth["texture_tip"] = "Sales jumped 300% after launch"
        out = _enforce_guardrails(synth, self._det())
        assert out["texture_tip"] is None

    def test_qualitative_texture_tip_survives(self):
        synth = self._synth_with_why("ok")
        synth["texture_tip"] = "Lean into nutty, toasty flavor notes this season"
        out = _enforce_guardrails(synth, self._det())
        assert out["texture_tip"] == "Lean into nutty, toasty flavor notes this season"


def _scored(term="tahini cookie", direction="rising", confidence="medium"):
    return [{"term": term, "category": "flavor", "direction": direction,
             "confidence": confidence, "current_interest": 62, "delta": 0.4,
             "on_menu": False, "evidence": EVIDENCE}]


class TestSynthesizeFallback:
    def test_no_key_uses_deterministic(self, monkeypatch):
        monkeypatch.setattr(syn, "LLM_API_KEY", "")
        out = synthesize(_scored(), {"gaps": [], "retire": []})
        assert out["source"] == "deterministic"

    def test_llm_failure_falls_back(self, monkeypatch):
        monkeypatch.setattr(syn, "LLM_API_KEY", "test-key")
        monkeypatch.setattr(syn, "_call_llm", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        out = synthesize(_scored(), {"gaps": [{"term": "x", "confidence": "high",
                                               "direction": "rising", "evidence": []}], "retire": []})
        assert out["source"] == "deterministic"

    def test_llm_fabrication_is_caught_end_to_end(self, monkeypatch):
        # A mocked LLM invents "+9000%" — synthesize() must strip it.
        monkeypatch.setattr(syn, "LLM_API_KEY", "test-key")
        def fake_llm(payload, voice=""):
            return {"quiet_month": False, "headline": "Big month",
                    "launch": [{"term": "tahini cookie", "why": "Up +9000% — buy now"}],
                    "watch": [], "skip": [], "gaps": [], "texture_tip": None}
        monkeypatch.setattr(syn, "_call_llm", fake_llm)
        out = synthesize(_scored(), {"gaps": [], "retire": []})
        # Non-quiet so the LLM path runs, but the fabricated number is gone.
        assert out["source"] == "llm"
        assert "9000" not in out["launch"][0]["why"]

    def test_quiet_month_never_calls_llm(self, monkeypatch):
        monkeypatch.setattr(syn, "LLM_API_KEY", "test-key")
        called = {"n": 0}
        monkeypatch.setattr(syn, "_call_llm", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
        # No launch + no gaps → quiet → must short-circuit before any API call.
        out = synthesize(_scored(direction="flat"), {"gaps": [], "retire": []})
        assert called["n"] == 0
        assert out["source"] == "deterministic"
