"""
Runtime config for editable scraper targets — scrapers/_config.py

The watch lists (keywords, hashtags, queries, subreddits) used to live as Python
constants in each scraper. They now live in data/config.json so the owner can
edit them from the Settings page without touching code. Each scraper keeps its
original list as the DEFAULT; config.json only holds overrides. Reads happen at
scan time, so an edit takes effect on the next scrape with no restart.
"""

from __future__ import annotations
import json

from tenancy import data_path

CONFIG_PATH = data_path("config.json")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def get_list(section: str, key: str, default: list[str]) -> list[str]:
    """Return the configured list for section.key, or `default` if unset/empty."""
    cfg = load_config()
    value = (cfg.get(section) or {}).get(key)
    if isinstance(value, list):
        cleaned = [str(x).strip() for x in value if str(x).strip()]
        if cleaned:
            return cleaned
    return default


def get_value(section: str, key: str, default: str = "") -> str:
    """Return a single configured scalar (e.g. delivery.client_email), or `default`."""
    cfg = load_config()
    value = (cfg.get(section) or {}).get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def set_value(section: str, key: str, value: str) -> None:
    cfg = load_config()
    cfg.setdefault(section, {})[key] = value.strip()
    save_config(cfg)
