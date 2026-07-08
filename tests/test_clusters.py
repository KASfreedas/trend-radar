"""Tests for clusters.py — the market-cluster grouping (HQ rollup layer)."""

import json

import clusters as cl


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "CLUSTERS_PATH", tmp_path / "clusters.json")


class TestSeeding:
    def test_seeds_four_default_clusters(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        cs = cl.load_clusters()
        keys = {c["key"] for c in cs}
        assert keys == {"downtown", "lincoln_park", "suburban_malls", "rosemont_outlet"}
        # 8 locations total across the clusters.
        assert sum(len(c["locations"]) for c in cs) == 8
        assert (tmp_path / "clusters.json").exists()

    def test_edits_persist(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        cs = cl.load_clusters()
        cs[0]["competitors"].append("newrival")
        cl.save_clusters(cs)
        assert "newrival" in cl.load_clusters()[0]["competitors"]


class TestGeoHashtags:
    def test_all_geo_hashtags_deduped(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        tags = cl.all_geo_hashtags()
        assert "michiganave" in tags and "skokie" in tags and "rosemont" in tags
        assert len(tags) == len(set(tags))  # no dupes


class TestGrouping:
    def test_groups_scanned_tags_into_right_cluster(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        ig = {"hashtag_trends": [
            {"hashtag": "michiganave", "posts_per_day": 12},   # downtown
            {"hashtag": "skokie", "posts_per_day": 4},          # suburban
            {"hashtag": "dubaichocolate", "posts_per_day": 30}, # national, no cluster
        ]}
        tt = {"hashtag_trends": [{"hashtag": "lincolnpark", "videos_per_day": 3}]}
        grouped = cl.group_by_cluster(ig, tt)
        assert [t["hashtag"] for t in grouped["downtown"]["local_ig"]] == ["michiganave"]
        assert [t["hashtag"] for t in grouped["suburban_malls"]["local_ig"]] == ["skokie"]
        assert [t["hashtag"] for t in grouped["lincoln_park"]["local_tt"]] == ["lincolnpark"]
        # Non-neighborhood national tag lands in no cluster.
        for k, g in grouped.items():
            assert "dubaichocolate" not in [t["hashtag"] for t in g["local_ig"]]

    def test_empty_scan_gives_empty_clusters_not_error(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        grouped = cl.group_by_cluster(None, None)
        assert all(g["local_ig"] == [] and g["local_tt"] == [] for g in grouped.values())


class TestLaunchRouting:
    """Per-market launch routing by confidence + profile."""

    def _scored(self):
        return [
            {"term": "dubai chocolate", "direction": "rising", "confidence": "low", "delta": 0.35},
            {"term": "matcha cupcake", "direction": "rising", "confidence": "medium", "delta": 0.66},
            {"term": "tiramisu cake", "direction": "peaking", "confidence": "high", "delta": 0.05},
            {"term": "old flavor", "direction": "fading", "confidence": "high", "delta": -0.3},
        ]

    def test_trend_forward_gets_low_confidence_early_bets(self):
        c = {"profile": "trend_forward"}
        terms = [p["term"] for p in cl.launch_picks_for_cluster(c, self._scored())]
        assert "dubai chocolate" in terms and "matcha cupcake" in terms  # low + medium allowed
        assert "old flavor" not in terms                                 # fading excluded

    def test_classic_gets_only_high_confidence(self):
        c = {"profile": "classic"}
        terms = [p["term"] for p in cl.launch_picks_for_cluster(c, self._scored())]
        assert terms == ["tiramisu cake"]   # only the high-confidence one

    def test_balanced_excludes_low(self):
        c = {"profile": "balanced"}
        terms = [p["term"] for p in cl.launch_picks_for_cluster(c, self._scored())]
        assert "dubai chocolate" not in terms          # low excluded
        assert "matcha cupcake" in terms and "tiramisu cake" in terms

    def test_ranked_by_momentum(self):
        c = {"profile": "trend_forward"}
        picks = cl.launch_picks_for_cluster(c, self._scored())
        deltas = [p["delta"] for p in picks]
        assert deltas == sorted(deltas, reverse=True)  # highest momentum first


class TestBriefingSection:
    """The 'By Market' section in the emailed briefing (briefing/render.py)."""

    def test_renders_by_market_with_local_buzz(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        from briefing.render import _clusters_html
        data = {"instagram": {"hashtag_trends": [
            {"hashtag": "michiganave", "posts_per_day": 20}]}, "tiktok": None}
        html = _clusters_html(data)
        assert "By Market" in html
        assert "Downtown" in html and "Lincoln Park" in html
        assert "#michiganave" in html            # real local buzz shown for downtown

    def test_single_cluster_omits_section(self, monkeypatch):
        from briefing import render
        monkeypatch.setattr(render, "_clusters_html", render._clusters_html)  # keep real fn
        import clusters as cl2
        monkeypatch.setattr(cl2, "load_clusters", lambda: [{"key": "only", "name": "Only",
                            "locations": ["A"], "geo_hashtags": [], "competitors": []}])
        assert render._clusters_html({}) == ""   # one market → no breakdown
