"""Tests for briefing/gaps.py — menu matching, and the 2026-07-05 category
fix: only flavor terms may be matched against the menu. Packaging/design
terms were never menu items, so they can never be 'covered' or 'retire'."""

import json

import briefing.gaps as gaps_mod
from briefing.gaps import compute_gaps


def _candidate(term, direction, category="flavor", confidence="medium"):
    return {"term": term, "direction": direction, "category": category,
            "confidence": confidence, "current_interest": 50, "delta": 0.2}


def _write_menu(tmp_path, monkeypatch):
    menu = {"flavors": ["chocolate", "vanilla bean"],
            "formats": ["cake", "cupcake"],
            "toppings": [], "seasonal": []}
    p = tmp_path / "menu.json"
    p.write_text(json.dumps(menu), encoding="utf-8")
    monkeypatch.setattr(gaps_mod, "MENU_PATH", p)


class TestFlavorMatching:
    def test_rising_flavor_not_on_menu_is_gap(self, tmp_path, monkeypatch):
        _write_menu(tmp_path, monkeypatch)
        result = compute_gaps([_candidate("tahini cookie", "rising")])
        assert [g["term"] for g in result["gaps"]] == ["tahini cookie"]
        assert result["gaps"][0]["on_menu"] is False

    def test_rising_flavor_on_menu_is_covered(self, tmp_path, monkeypatch):
        _write_menu(tmp_path, monkeypatch)
        result = compute_gaps([_candidate("chocolate babka", "rising")])
        assert [c["term"] for c in result["covered"]] == ["chocolate babka"]
        assert result["gaps"] == []

    def test_fading_flavor_on_menu_is_retire(self, tmp_path, monkeypatch):
        _write_menu(tmp_path, monkeypatch)
        result = compute_gaps([_candidate("matcha cupcake", "fading")])
        assert [r["term"] for r in result["retire"]] == ["matcha cupcake"]

    def test_flat_terms_ignored(self, tmp_path, monkeypatch):
        _write_menu(tmp_path, monkeypatch)
        result = compute_gaps([_candidate("chocolate", "flat")])
        assert result["gaps"] == result["covered"] == result["retire"] == []


class TestCategoryScoping:
    """Regression tests for the packaging false-positive bug found in the
    2026-07-05 full-scale test: 'Clear Cake Container' appeared as a retire
    candidate because it shares the word 'cake' with a menu format item."""

    def test_fading_packaging_term_is_never_retire(self, tmp_path, monkeypatch):
        _write_menu(tmp_path, monkeypatch)
        result = compute_gaps(
            [_candidate("clear cake container", "fading", category="packaging")])
        assert result["retire"] == []

    def test_fading_design_term_is_never_retire(self, tmp_path, monkeypatch):
        _write_menu(tmp_path, monkeypatch)
        result = compute_gaps(
            [_candidate("vintage cake piping", "fading", category="design")])
        assert result["retire"] == []

    def test_rising_packaging_term_is_gap_not_covered(self, tmp_path, monkeypatch):
        # Shares "cake" with the menu, but packaging can't be "covered".
        _write_menu(tmp_path, monkeypatch)
        result = compute_gaps(
            [_candidate("custom cake box", "rising", category="packaging")])
        assert [g["term"] for g in result["gaps"]] == ["custom cake box"]
        assert result["covered"] == []


class TestSorting:
    def test_gaps_sorted_by_confidence_rank(self, tmp_path, monkeypatch):
        _write_menu(tmp_path, monkeypatch)
        result = compute_gaps([
            _candidate("term low", "rising", confidence="low"),
            _candidate("term high", "rising", confidence="high"),
            _candidate("term med", "rising", confidence="medium"),
        ])
        assert [g["confidence"] for g in result["gaps"]] == ["high", "medium", "low"]
