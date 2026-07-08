"""Tests for briefing/dna.py — risk-tolerance confidence floors and dietary
exclusions. These filters decide what the client is told to act on."""

import json

import scrapers._config as config_mod
from briefing.dna import apply_filters, load_dna


def _c(term, confidence):
    return {"term": term, "confidence": confidence}


CANDIDATES = [
    _c("high pick", "high"),
    _c("medium pick", "medium"),
    _c("low pick", "low"),
]


class TestRiskFloor:
    def test_conservative_keeps_only_high(self):
        dna = {"risk_tolerance": "conservative", "dietary_exclusions": ""}
        assert [c["term"] for c in apply_filters(CANDIDATES, dna)] == ["high pick"]

    def test_balanced_keeps_high_and_medium(self):
        dna = {"risk_tolerance": "balanced", "dietary_exclusions": ""}
        assert [c["term"] for c in apply_filters(CANDIDATES, dna)] == [
            "high pick", "medium pick"]

    def test_adventurous_keeps_everything(self):
        dna = {"risk_tolerance": "adventurous", "dietary_exclusions": ""}
        assert len(apply_filters(CANDIDATES, dna)) == 3


class TestDietaryExclusions:
    def test_excluded_term_removed(self):
        dna = {"risk_tolerance": "adventurous", "dietary_exclusions": "matcha, tahini"}
        cands = [_c("matcha cupcake", "high"), _c("tahini cookie", "high"),
                 _c("chocolate babka", "high")]
        assert [c["term"] for c in apply_filters(cands, dna)] == ["chocolate babka"]

    def test_empty_exclusions_removes_nothing(self):
        dna = {"risk_tolerance": "adventurous", "dietary_exclusions": ""}
        assert len(apply_filters(CANDIDATES, dna)) == 3


class TestLoadDnaDefaults:
    def test_bad_config_values_fall_back(self, tmp_path, monkeypatch):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"dna": {
            "risk_tolerance": "yolo",
            "max_new_items_per_month": "not a number",
        }}), encoding="utf-8")
        monkeypatch.setattr(config_mod, "CONFIG_PATH", p)
        dna = load_dna()
        assert dna["risk_tolerance"] == "balanced"
        assert dna["max_new_items_per_month"] == 3

    def test_missing_config_gives_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "nope.json")
        dna = load_dna()
        assert dna["risk_tolerance"] == "balanced"
        assert dna["dietary_exclusions"] == ""
