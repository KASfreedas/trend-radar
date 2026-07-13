"""Tests for the 'became viral this window' top-post selection
(scrapers.instagram.select_top_posts) and the per-post history layer."""

from scrapers.instagram import select_top_posts
import scrapers._history as hist


def _post(url, engagement, age_hours, likes=0, comments=0):
    return {"post_url": url, "engagement": engagement, "age_hours": age_hours,
            "likes": likes, "comments": comments}


class TestBecameViralSelection:
    def test_measured_gainer_beats_bigger_static_post(self):
        """An old post that GAINED 5k this window outranks a huge post that
        gained nothing — 'became viral' is about the delta, not the total."""
        prev = {"a": 10000.0, "b": 200.0}
        posts = [
            _post("a", 10050, age_hours=500),   # huge but static (+50)
            _post("b", 5200, age_hours=500),    # smaller but exploded (+5000)
        ]
        top = select_top_posts(posts, prev, window_days=7,
                               min_likes=10000, min_comments=1000)
        assert top[0]["post_url"] == "b"
        assert top[0]["gained"] == 5000.0
        assert top[0]["gained_display"].startswith("+5.0K")

    def test_old_post_without_history_is_excluded(self):
        """A 3-week-old post never seen before: we can't know when its
        engagement arrived, so it must not be claimed as 'this week'."""
        posts = [
            _post("old", 99999, age_hours=21 * 24),
            _post("new", 100, age_hours=24),
        ]
        top = select_top_posts(posts, {}, 7, 10000, 1000)
        assert [p["post_url"] for p in top] == ["new"]

    def test_new_post_counts_full_engagement_as_gained(self):
        posts = [_post("fresh", 800, age_hours=48)]
        top = select_top_posts(posts, {}, 7, 10000, 1000)
        assert top[0]["gained"] == 800
        assert "gained_display" not in top[0]  # not a measured delta

    def test_never_empty_fallback(self):
        """Only old unhistoried posts exist → still show something, ranked by
        engagement, with gained=0 (no false recency claims)."""
        posts = [_post("x", 500, age_hours=600), _post("y", 900, age_hours=700)]
        top = select_top_posts(posts, {}, 7, 10000, 1000)
        assert [p["post_url"] for p in top] == ["y", "x"]
        assert all(p["gained"] == 0 for p in top)

    def test_viral_badge_still_absolute(self):
        posts = [_post("v", 50000, age_hours=24, likes=20000, comments=2000),
                 _post("n", 60000, age_hours=24, likes=9000, comments=500)]
        top = select_top_posts(posts, {}, 7, 10000, 1000)
        by = {p["post_url"]: p for p in top}
        assert by["v"]["viral"] is True
        assert by["n"]["viral"] is False

    def test_negative_delta_clamps_to_zero(self):
        """Engagement can drop (deleted likes); gained never goes negative."""
        top = select_top_posts([_post("d", 900, age_hours=100)], {"d": 1200.0},
                               7, 10000, 1000)
        assert top[0]["gained"] == 0.0


class TestPostHistory:
    def test_roundtrip_and_rolling_cap(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hist, "HISTORY_DIR", tmp_path)
        for i in range(hist.MAX_POST_SNAPSHOTS + 3):
            hist.record_post_snapshot("instagram",
                                      {"post_engagements": {"u": float(i)}})
        snaps = hist.load_post_history("instagram")
        assert len(snaps) == hist.MAX_POST_SNAPSHOTS
        assert hist.previous_post_engagements("instagram") == {"u": float(
            hist.MAX_POST_SNAPSHOTS + 2)}

    def test_empty_result_records_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hist, "HISTORY_DIR", tmp_path)
        hist.record_post_snapshot("instagram", {"top_posts": []})
        assert hist.load_post_history("instagram") == []
        assert hist.previous_post_engagements("instagram") == {}
