"""Smoke + integration tests for briefing/render.py. The render layer's core
promise is 'never fabricate a number' — these tests check that what goes in
is what appears, and that the real cached pipeline stays consistent."""

import json
from pathlib import Path

import pytest

from briefing.render import build_html
from briefing.score import score_all
from briefing.gaps import compute_gaps

ROOT = Path(__file__).parent.parent
CACHE = ROOT / "data" / "cache"
SOURCES = ["google", "reddit", "food_media", "instagram", "tiktok", "pinterest"]


def _scored(term="tahini cookie", direction="rising", category="flavor"):
    return {"term": term, "direction": direction, "category": category,
            "confidence": "medium", "sources_agreeing": 1, "delta": 0.4,
            "current_interest": 62,
            "evidence": ["Google Trends: 62/100 (+40% vs prior period)"]}


class TestBuildHtmlSmoke:
    def test_minimal_inputs_render(self):
        html = build_html([_scored()], {"gaps": [], "covered": [], "retire": []})
        assert isinstance(html, str) and len(html) > 500
        assert "tahini cookie" in html.lower()

    def test_month_label_appears(self):
        html = build_html([], {"gaps": [], "covered": [], "retire": []},
                          month_label="July 2026")
        assert "July 2026" in html

    def test_trust_tiers_always_present(self):
        html = build_html([], {"gaps": [], "covered": [], "retire": []})
        assert "Most trustworthy" in html

    def test_hit_rate_line_included_when_given(self):
        line = "2 of the 3 items we flagged last cycle are now top sellers."
        html = build_html([], {"gaps": [], "covered": [], "retire": []},
                          hit_rate=line)
        assert line in html

    def test_evidence_strings_pass_through_verbatim(self):
        # Evidence is pre-built from real numbers; render must not alter it.
        c = _scored()
        html = build_html([c], {"gaps": [c], "covered": [], "retire": []})
        assert "Google Trends: 62/100 (+40% vs prior period)" in html


@pytest.mark.skipif(
    not all((CACHE / f"last_good_{s}.json").exists() for s in SOURCES),
    reason="real cached scrape data not present",
)
class TestRealDataRegression:
    """Replays the last real full-scale scrape through the pipeline.
    Guards the 2026-07-05 finding: no packaging/design term may ever be a
    retire candidate."""

    def _data(self):
        return {s: json.loads((CACHE / f"last_good_{s}.json").read_text(encoding="utf-8"))
                for s in SOURCES}

    def test_retire_candidates_are_flavor_only(self):
        result = compute_gaps(score_all(self._data()))
        assert all(r.get("category") == "flavor" for r in result["retire"])

    def test_pipeline_produces_scored_terms_and_html(self):
        data = self._data()
        scored = score_all(data)
        assert len(scored) > 0
        html = build_html(scored, compute_gaps(scored), data=data)
        assert len(html) > 2000
        assert "clear cake container" not in html.lower()
