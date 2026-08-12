from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def _read_ps1(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_r48_usb_distribution_array_has_no_trailing_comma_before_close():
    source = _read_ps1(ROOT / "GOKDOGAN-USB-DAGITIM-HAZIRLA.ps1")
    assert "SHA256SUMS.txt" in source
    assert not re.search(r",\s*\r?\n\s*\)", source)


def test_r48_all_powershell_sources_reject_trailing_comma_before_closing_paren():
    offenders = []
    pattern = re.compile(r",\s*\r?\n\s*\)")
    for path in ROOT.rglob("*.ps1"):
        text = _read_ps1(path)
        if pattern.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_r48_release_identity_and_matrix_removal_are_preserved():
    release = (ROOT / "release-version.json").read_text(encoding="utf-8")
    start = (ROOT / "START-HERE.bat").read_text(encoding="utf-8-sig")
    one_click = _read_ps1(ROOT / "WINDOWS-DESKTOP-ONE-CLICK.ps1")
    assert '"package_revision": "1.0.0"' in release
    assert "GOKDOGAN INTELLIGENCE v1.0.0" in start
    assert "Gokdogan-Intelligence-v1.0.0-OFFLINE-USB.zip" in one_click
    assert not list(ROOT.glob("GOKDOGAN-*-KONSOLU.ps1"))
    assert not list(ROOT.glob("GOKDOGAN-*-KONSOLU.bat"))
