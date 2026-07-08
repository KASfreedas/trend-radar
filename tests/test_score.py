"""Tests for briefing/score.py — trajectory math, cross-source evidence
floors, confidence mapping, and category assignment. These encode the
behaviors the briefing's numbers depend on; a regression here means the
email lies to the client."""

from briefing.score import (
    _trajectory,
    _cross_source_score,
    _confidence,
    score_all,
    MIN_REDDIT_MENTIONS,
    MIN_IG_POSTS,
    MIN_TIKTOK_VIDEOS,
)


def _series(values):
    return [{"date": f"2026-01-{i+1:02d}", "value": v} for i, v in enumerate(values)]


class TestTrajectory:
    def test_rising(self):
        direction, delta = _trajectory(_series([20] * 12 + [40] * 4))
        assert direction == "rising"
        assert delta == 1.0

    def test_fading(self):
        direction, delta = _trajectory(_series([40] * 12 + [10] * 4))
        assert direction == "fading"
        assert delta == -0.75

    def test_peaking_flat_delta_near_peak(self):
        direction, delta = _trajectory(_series([50] * 16))
        assert direction == "peaking"
        assert delta == 0.0

    def test_flat_when_small_delta_and_off_peak(self):
        # One old spike sets the peak; recent values are well below it.
        direction, _ = _trajectory(_series([60] + [30] * 15))
        assert direction == "flat"

    def test_short_series_is_flat(self):
        assert _trajectory(_series([10, 20, 30])) == ("flat", 0.0)
        assert _trajectory([]) == ("flat", 0.0)

    def test_zero_prior_period_gives_zero_delta(self):
        # avg(prior) < 1 must not divide — delta pinned to 0.
        _, delta = _trajectory(_series([0] * 12 + [50] * 4))
        assert delta == 0.0


class TestCrossSourceFloors:
    def test_reddit_below_floor_does_not_count(self):
        data = {"reddit": {"trending_keywords": [
            {"keyword": "tahini cookie", "count": MIN_REDDIT_MENTIONS - 1}]}}
        count, evidence = _cross_source_score("tahini cookie", data)
        assert count == 0 and evidence == []

    def test_reddit_at_floor_counts(self):
        data = {"reddit": {"trending_keywords": [
            {"keyword": "tahini cookie", "count": MIN_REDDIT_MENTIONS}]}}
        count, evidence = _cross_source_score("tahini cookie", data)
        assert count == 1
        assert "Reddit" in evidence[0]

    def test_instagram_post_floor(self):
        below = {"instagram": {"hashtag_trends": [
            {"hashtag": "tahinicookie", "post_count": MIN_IG_POSTS - 1,
             "engagement_display": "1.2K"}]}}
        at = {"instagram": {"hashtag_trends": [
            {"hashtag": "tahinicookie", "post_count": MIN_IG_POSTS,
             "engagement_display": "1.2K"}]}}
        assert _cross_source_score("tahini cookie", below)[0] == 0
        assert _cross_source_score("tahini cookie", at)[0] == 1

    def test_tiktok_video_floor(self):
        below = {"tiktok": {"hashtag_trends": [
            {"hashtag": "tahinicookie", "video_count": MIN_TIKTOK_VIDEOS - 1,
             "plays_display": "10K"}]}}
        at = {"tiktok": {"hashtag_trends": [
            {"hashtag": "tahinicookie", "video_count": MIN_TIKTOK_VIDEOS,
             "plays_display": "10K"}]}}
        assert _cross_source_score("tahini cookie", below)[0] == 0
        assert _cross_source_score("tahini cookie", at)[0] == 1

    def test_pinterest_never_contributes(self):
        # Deliberately excluded after two real tests showed inconsistent counts.
        data = {"pinterest": {"query_trends": [
            {"query": "tahini cookie", "total_pins": 9999, "board_count": 500}]}}
        assert _cross_source_score("tahini cookie", data)[0] == 0

    def test_food_media_has_no_floor(self):
        data = {"food_media": {"top_articles": [
            {"title": "Tahini Cookie mania sweeps bakeries", "source": "NYT"}]}}
        count, evidence = _cross_source_score("tahini cookie", data)
        assert count == 1
        assert "Editorial" in evidence[0]


class TestConfidence:
    def test_mapping(self):
        assert _confidence(0) == "low"
        assert _confidence(1) == "medium"
        assert _confidence(2) == "medium"
        assert _confidence(3) == "high"
        assert _confidence(5) == "high"


class TestScoreAll:
    def test_categories_assigned_from_google_groups(self):
        data = {"google": {
            "flavor_trends": [{"keyword": "tahini cookie",
                               "time_series": _series([20] * 12 + [40] * 4),
                               "current_interest": 40}],
            "packaging_trends": [{"keyword": "clear cake container",
                                  "time_series": _series([40] * 12 + [10] * 4),
                                  "current_interest": 10}],
            "design_trends": [{"keyword": "vintage cake",
                               "time_series": _series([50] * 16),
                               "current_interest": 50}],
        }}
        scored = {c["term"]: c for c in score_all(data)}
        assert scored["tahini cookie"]["category"] == "flavor"
        assert scored["clear cake container"]["category"] == "packaging"
        assert scored["vintage cake"]["category"] == "design"

    def test_empty_keyword_skipped(self):
        data = {"google": {"flavor_trends": [{"keyword": "", "time_series": []}]}}
        assert score_all(data) == []

    def test_no_sources_is_low_confidence(self):
        data = {"google": {"flavor_trends": [{"keyword": "tahini cookie",
                                              "time_series": _series([20] * 12 + [40] * 4),
                                              "current_interest": 40}]}}
        (c,) = score_all(data)
        assert c["confidence"] == "low"
        assert c["sources_agreeing"] == 0
