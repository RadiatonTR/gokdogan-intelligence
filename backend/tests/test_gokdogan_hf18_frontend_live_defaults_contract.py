from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_live_defaults_and_vitest_contract_stay_aligned():
    prefs = (ROOT / "frontend" / "src" / "lib" / "layerPreferences.ts").read_text(encoding="utf-8")
    test = (ROOT / "frontend" / "src" / "__tests__" / "lib" / "layerPreferences.test.ts").read_text(encoding="utf-8")

    for layer in ("firms", "cctv", "crowdthreat"):
        assert f"{layer}: true" in prefs
        assert f"expect(defaults.{layer}).toBe(true);" in test
        assert f"expect(defaults.{layer}).toBe(false);" not in test


def test_hf18_contract_is_in_windows_release_regression_lane():
    ps1 = (ROOT / "WINDOWS-DESKTOP-ONE-CLICK.ps1").read_text(encoding="utf-8")
    assert "backend\\tests\\test_gokdogan_hf18_frontend_live_defaults_contract.py" in ps1
