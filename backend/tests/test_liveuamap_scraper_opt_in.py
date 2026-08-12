"""LiveUAMap scraper UI opt-in on Windows (#348)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import liveuamap_settings as settings


@pytest.fixture
def opt_in_file(tmp_path, monkeypatch):
    path = tmp_path / "liveuamap_scraper_opt_in.json"
    monkeypatch.setattr(settings, "_OPT_IN_FILE", path)
    return path


def test_windows_defaults_off_without_opt_in(monkeypatch, opt_in_file):
    monkeypatch.setattr(settings.os, "name", "nt")
    monkeypatch.delenv("SHADOWBROKER_ENABLE_LIVEUAMAP_SCRAPER", raising=False)
    assert settings.liveuamap_scraper_enabled() is False
    assert settings.liveuamap_requires_ui_opt_in() is True


def test_windows_opt_in_enables_scraper(monkeypatch, opt_in_file):
    monkeypatch.setattr(settings.os, "name", "nt")
    monkeypatch.delenv("SHADOWBROKER_ENABLE_LIVEUAMAP_SCRAPER", raising=False)
    settings.set_liveuamap_ui_opt_in(True)
    assert settings.liveuamap_scraper_enabled() is True
    assert json.loads(opt_in_file.read_text())["opted_in"] is True


def test_linux_enabled_without_opt_in(monkeypatch, opt_in_file):
    monkeypatch.setattr(settings.os, "name", "posix")
    monkeypatch.delenv("SHADOWBROKER_ENABLE_LIVEUAMAP_SCRAPER", raising=False)
    assert settings.liveuamap_requires_ui_opt_in() is False
    assert settings.liveuamap_scraper_enabled() is True


def test_env_force_off_overrides_ui_opt_in(monkeypatch, opt_in_file):
    monkeypatch.setattr(settings.os, "name", "nt")
    monkeypatch.setenv("SHADOWBROKER_ENABLE_LIVEUAMAP_SCRAPER", "false")
    settings.set_liveuamap_ui_opt_in(True)
    assert settings.liveuamap_scraper_enabled() is False
