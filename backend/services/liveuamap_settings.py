"""LiveUAMap Playwright scraper opt-in (#348) — UI consent on Windows."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_OPT_IN_FILE = Path(__file__).resolve().parent.parent / "data" / "liveuamap_scraper_opt_in.json"
_OPT_IN_LOCK = threading.Lock()


def _env_flag(name: str) -> str:
    return str(os.getenv(name, "")).strip().lower()


def liveuamap_requires_ui_opt_in() -> bool:
    """Windows local installs need explicit consent before Playwright contacts LiveUAMap."""
    return os.name == "nt"


def get_liveuamap_ui_opt_in() -> bool:
    if not _OPT_IN_FILE.exists():
        return False
    try:
        payload = json.loads(_OPT_IN_FILE.read_text(encoding="utf-8"))
        return bool(payload.get("opted_in"))
    except (OSError, json.JSONDecodeError, TypeError) as e:
        logger.warning("LiveUAMap opt-in file unreadable: %s", e)
        return False


def set_liveuamap_ui_opt_in(opted_in: bool) -> None:
    _OPT_IN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _OPT_IN_LOCK:
        _OPT_IN_FILE.write_text(
            json.dumps({"opted_in": bool(opted_in)}, indent=2),
            encoding="utf-8",
        )


def liveuamap_scraper_enabled() -> bool:
    """Whether the Playwright LiveUAMap scraper may run on this backend."""
    setting = _env_flag("SHADOWBROKER_ENABLE_LIVEUAMAP_SCRAPER")
    if setting in {"1", "true", "yes", "on"}:
        return True
    if setting in {"0", "false", "no", "off"}:
        return False
    if not liveuamap_requires_ui_opt_in():
        return True
    return get_liveuamap_ui_opt_in()


def liveuamap_scraper_status() -> dict[str, Any]:
    setting = _env_flag("SHADOWBROKER_ENABLE_LIVEUAMAP_SCRAPER")
    env_override = None
    if setting in {"1", "true", "yes", "on"}:
        env_override = "on"
    elif setting in {"0", "false", "no", "off"}:
        env_override = "off"
    ui_opted_in = get_liveuamap_ui_opt_in()
    requires = liveuamap_requires_ui_opt_in()
    return {
        "platform_requires_opt_in": requires,
        "ui_opted_in": ui_opted_in,
        "scraper_enabled": liveuamap_scraper_enabled(),
        "env_override": env_override,
    }
