"""Tenant-scoped data paths — tenancy.py (Tier 1 foundation)

Phase 1 multi-tenancy model: **one tenant per process**, selected by the
TENANT_ID environment variable at startup. Deploy one container per customer
(each with its own TENANT_ID, APP_PASSWORD, and data volume) — the standard
early-SaaS model that gets real customer isolation without per-request
tenant resolution, shared auth, or a database migration.

The default tenant maps to the legacy flat `data/` layout, so existing
single-tenant installs (and this repo's dev data) keep working unchanged.
Named tenants live under `data/tenants/<id>/` with the identical internal
structure (config.json, menu.json, history/, cache/).

Phase 2 (shared instance, per-request tenant resolution, real DB) swaps this
module's resolver without touching callers: every data file in the codebase
routes through data_path().

CLI:
  py tenancy.py new <id> [--preset cupcakes] [--city chicago]
  py tenancy.py list
"""

from __future__ import annotations
import json
import os
import re
from pathlib import Path

_ROOT = Path(__file__).parent
DATA_ROOT = _ROOT / "data"
TENANTS_ROOT = DATA_ROOT / "tenants"
DEFAULT_TENANT = "default"
_VALID_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def current_tenant() -> str:
    tid = os.getenv("TENANT_ID", "").strip().lower() or DEFAULT_TENANT
    if not _VALID_ID.match(tid):
        raise ValueError(
            f"Invalid TENANT_ID {tid!r}: lowercase letters, digits, '-', '_' only."
        )
    return tid


def tenant_root(tenant_id: str | None = None) -> Path:
    tid = tenant_id or current_tenant()
    if tid == DEFAULT_TENANT:
        return DATA_ROOT  # legacy layout, unchanged
    return TENANTS_ROOT / tid


def data_path(*parts: str, tenant_id: str | None = None) -> Path:
    """Resolve a tenant-scoped data file path. All persistent state in the
    codebase must go through here — never build a `data/...` path directly."""
    return tenant_root(tenant_id).joinpath(*parts)


def list_tenants() -> list[str]:
    out = [DEFAULT_TENANT]
    if TENANTS_ROOT.exists():
        out += sorted(p.name for p in TENANTS_ROOT.iterdir() if p.is_dir())
    return out


def create_tenant(tenant_id: str, preset: str | None = None,
                  city: str | None = None) -> Path:
    """Create a new tenant directory tree, optionally seeded from a vertical
    preset (see presets.py). Refuses to overwrite an existing tenant."""
    tid = tenant_id.strip().lower()
    if not _VALID_ID.match(tid):
        raise ValueError(f"Invalid tenant id {tid!r}.")
    if tid == DEFAULT_TENANT:
        raise ValueError("'default' is the legacy data/ tenant — it already exists.")
    root = TENANTS_ROOT / tid
    if root.exists():
        raise FileExistsError(f"Tenant {tid!r} already exists at {root}.")

    (root / "history").mkdir(parents=True)
    (root / "cache").mkdir(parents=True)

    config: dict = {
        "schedule": {"refresh_day": "mon", "refresh_hour": "5",
                     "send_day_of_month": "1", "send_hour": "8"},
        "dna": {"voice": "", "risk_tolerance": "balanced",
                "max_new_items_per_month": "3", "dietary_exclusions": ""},
    }
    menu: dict = {"flavors": [], "formats": [], "toppings": [], "seasonal": []}

    if preset:
        from presets import build_config_sections, build_starter_menu
        config.update(build_config_sections(preset, city=city))
        menu = build_starter_menu(preset)

    (root / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    (root / "menu.json").write_text(
        json.dumps(menu, indent=2, ensure_ascii=False), encoding="utf-8")
    return root


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tenant management")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new", help="create a tenant")
    p_new.add_argument("id")
    p_new.add_argument("--preset", default=None)
    p_new.add_argument("--city", default=None)
    sub.add_parser("list", help="list tenants")
    args = parser.parse_args()

    if args.cmd == "list":
        for t in list_tenants():
            print(t)
    elif args.cmd == "new":
        path = create_tenant(args.id, preset=args.preset, city=args.city)
        print(f"Created tenant {args.id!r} at {path}")
        print(f"Run it with:  TENANT_ID={args.id} (own APP_PASSWORD + volume per tenant)")
