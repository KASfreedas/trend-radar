"""Tests for tenancy.py + presets.py — tenant path resolution must keep the
default tenant byte-compatible with the legacy data/ layout, and tenant
creation must produce a valid, isolated starting state."""

import json

import pytest

import tenancy
import presets
from tenancy import data_path, current_tenant, create_tenant, DATA_ROOT


class TestPathResolution:
    def test_default_tenant_maps_to_legacy_layout(self, monkeypatch):
        monkeypatch.delenv("TENANT_ID", raising=False)
        assert current_tenant() == "default"
        assert data_path("menu.json") == DATA_ROOT / "menu.json"
        assert data_path("history", "outcomes.json") == \
            DATA_ROOT / "history" / "outcomes.json"

    def test_named_tenant_gets_own_tree(self, monkeypatch):
        monkeypatch.setenv("TENANT_ID", "sweet-shop")
        assert current_tenant() == "sweet-shop"
        assert data_path("menu.json") == \
            DATA_ROOT / "tenants" / "sweet-shop" / "menu.json"

    def test_explicit_tenant_id_overrides_env(self, monkeypatch):
        monkeypatch.setenv("TENANT_ID", "sweet-shop")
        assert data_path("menu.json", tenant_id="other") == \
            DATA_ROOT / "tenants" / "other" / "menu.json"

    def test_invalid_tenant_id_rejected(self, monkeypatch):
        monkeypatch.setenv("TENANT_ID", "../escape")
        with pytest.raises(ValueError):
            current_tenant()


class TestCreateTenant:
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tenancy, "TENANTS_ROOT", tmp_path / "tenants")

    def test_creates_directory_tree_and_files(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        root = create_tenant("new-bakery")
        assert (root / "history").is_dir()
        assert (root / "cache").is_dir()
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        assert cfg["dna"]["risk_tolerance"] == "balanced"
        menu = json.loads((root / "menu.json").read_text(encoding="utf-8"))
        assert menu == {"flavors": [], "formats": [], "toppings": [], "seasonal": []}

    def test_preset_seeds_watch_lists_and_menu(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        root = create_tenant("cookie-co", preset="cookies", city="denver")
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        assert "stuffed cookie" in cfg["google"]["flavor"]
        assert "denverfood" in cfg["instagram"]["hashtags"]
        menu = json.loads((root / "menu.json").read_text(encoding="utf-8"))
        assert "stuffed cookie" in menu["formats"]

    def test_refuses_duplicate_and_default(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        create_tenant("dup")
        with pytest.raises(FileExistsError):
            create_tenant("dup")
        with pytest.raises(ValueError):
            create_tenant("default")

    def test_refuses_invalid_id(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        with pytest.raises(ValueError):
            create_tenant("Bad Name!")


class TestPresets:
    def test_all_verticals_build_valid_sections(self):
        for slug in presets.VERTICALS:
            cfg = presets.build_config_sections(slug)
            # Every section the scrapers read must be present and non-empty.
            assert cfg["google"]["flavor"]
            assert cfg["instagram"]["hashtags"]
            assert cfg["tiktok"]["hashtags"]
            assert cfg["pinterest"]["queries"]
            assert cfg["reddit"]["subreddits"]
            assert cfg["reddit"]["keywords"]

    def test_city_localizes_social_tags(self):
        cfg = presets.build_config_sections("cupcakes", city="Chicago")
        assert "chicagobakery" in cfg["instagram"]["hashtags"]
        assert "chicagofood" in cfg["tiktok"]["hashtags"]

    def test_unknown_vertical_raises(self):
        with pytest.raises(KeyError):
            presets.build_config_sections("hardware_store")

    def test_list_verticals_shape(self):
        rows = presets.list_verticals()
        assert {"slug", "label", "keyword_count", "hashtag_count"} <= set(rows[0])
        assert len(rows) == len(presets.VERTICALS)
