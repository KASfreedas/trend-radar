"""Tests for the per-market pages: /api/market/<key> assembly and the
/market/<key> route. The endpoint must stay honest at every data level —
fresh install (no snapshots), sparse market (Rosemont), and full data."""

import pytest

import app as app_mod


@pytest.fixture
def client():
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c


MARKET_KEYS = ["downtown", "lincoln_park", "suburban_malls", "rosemont_outlet"]
TOP_FIELDS = ["market", "bakery", "pulse", "launch_picks", "events",
              "occasion_buzz", "local_buzz", "movers", "nav", "scanned_at"]


class TestMarketApi:
    def test_shape_all_four_markets(self, client):
        for key in MARKET_KEYS:
            j = client.get(f"/api/market/{key}").get_json()
            for f in TOP_FIELDS:
                assert f in j, f"{key} missing {f}"
            assert j["market"]["key"] == key
            assert j["market"]["profile_label"]
            assert isinstance(j["pulse"]["points"], list)
            assert j["pulse"]["snapshots"] == len(j["pulse"]["points"])

    def test_unknown_key_404(self, client):
        r = client.get("/api/market/nowhere")
        assert r.status_code == 404
        assert "error" in r.get_json()

    def test_rosemont_sparse_market_no_crash(self, client):
        """Rosemont: 1 geo tag, possibly 0 competitors/picks — the empty-state
        gauntlet. Everything must be a well-typed empty, never an error."""
        j = client.get("/api/market/rosemont_outlet").get_json()
        assert isinstance(j["launch_picks"], list)
        assert isinstance(j["local_buzz"]["instagram"], list)
        assert isinstance(j["movers"], list)
        assert isinstance(j["market"]["competitors"], list)

    def test_picks_carry_real_evidence_only(self, client):
        """Evidence lines must come verbatim from the scored data — the page
        never invents a stat."""
        from briefing.score import score_all
        with app_mod._lock:
            data = {k: app_mod._cache[k] for k in app_mod._cache}
        real_evidence = {e for c in score_all(data) for e in (c.get("evidence") or [])}
        for key in MARKET_KEYS:
            for p in client.get(f"/api/market/{key}").get_json()["launch_picks"]:
                for line in p.get("evidence") or []:
                    assert line in real_evidence

    def test_movers_only_this_markets_geo_tags(self, client):
        for key in MARKET_KEYS:
            j = client.get(f"/api/market/{key}").get_json()
            geo = {t.lower() for t in j["market"]["geo_hashtags"]}
            for m in j["movers"]:
                assert m["tag"] in geo

    def test_events_scoped_to_cluster(self, client):
        j = client.get("/api/market/downtown").get_json()
        for ev in j["events"]:
            assert ev.get("cluster") == "downtown"

    def test_nav_cycles_all_markets(self, client):
        seen = set()
        key = "downtown"
        for _ in range(len(MARKET_KEYS)):
            seen.add(key)
            key = client.get(f"/api/market/{key}").get_json()["nav"]["next"]["key"]
        assert seen == set(MARKET_KEYS)


class TestMarketPulse:
    def test_pulse_sums_only_market_geo_tags(self, monkeypatch):
        import scrapers._history as hist
        snaps = [
            {"at": "2026-07-01T00:00:00", "metrics": {"chicagoloop": 3.0, "skokie": 9.0}},
            {"at": "2026-07-08T00:00:00", "metrics": {"chicagoloop": 5.5, "skokie": 1.0}},
        ]
        monkeypatch.setattr(hist, "load_history", lambda source: snaps)
        p = app_mod._market_pulse({"chicagoloop"})
        assert p["snapshots"] == 2
        assert [pt["v"] for pt in p["points"]] == [3.0, 5.5]  # skokie excluded

    def test_pulse_empty_history_is_safe(self, monkeypatch):
        import scrapers._history as hist
        monkeypatch.setattr(hist, "load_history", lambda source: [])
        p = app_mod._market_pulse({"chicagoloop"})
        assert p["points"] == [] and p["snapshots"] == 0


class TestMarketRoute:
    def test_route_renders_each_market(self, client):
        for key in MARKET_KEYS:
            r = client.get(f"/market/{key}")
            assert r.status_code == 200
            assert key.encode() in r.data  # data-market attribute

    def test_route_unknown_key_404(self, client):
        assert client.get("/market/nowhere").status_code == 404
