from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]


def test_v1_public_release_identity_is_single_source_of_truth():
    release = json.loads((ROOT / "release-version.json").read_text(encoding="utf-8"))
    assert release["product"] == "Gökdoğan Intelligence"
    assert release["public_version"] == "1.0.0"
    assert release["distribution"] == "Gökdoğan Intelligence 1.0.0"
    assert release["technical_core_revision"] == "R24"
    assert release["technical_base_version"] == "0.10.3"


def test_v1_user_facing_artifact_names_are_final_not_hotfix():
    start = (ROOT / "START-HERE.bat").read_text(encoding="ascii", errors="replace")
    one_click = (ROOT / "WINDOWS-DESKTOP-ONE-CLICK.ps1").read_text(encoding="utf-8-sig")
    usb = (ROOT / "GOKDOGAN-USB-DAGITIM-HAZIRLA.ps1").read_text(encoding="utf-8-sig")
    assert "GOKDOGAN INTELLIGENCE v1.0.0" in start
    assert "Gokdogan-Intelligence-v1.0.0-Windows-Desktop-Bundle.zip" in one_click
    assert "Gokdogan-Intelligence-v1.0.0-OFFLINE-USB.zip" in one_click
    assert "Gokdogan-Intelligence-v1.0.0-Setup.exe" in usb
    assert "MATRIX" not in start.upper()


def test_v1_source_root_has_no_hotfix_narrative_clutter():
    forbidden = [
        "GD1-FINAL-R4-UYGULAMA-RAPORU.md",
        "GD1-FINAL-R4.1-CARGO-HOTFIX-TR.txt",
        "GD1-FINAL-R4.3-HATA-UYARI-HOTFIX-TR.txt",
        "GD1-FINAL-R4.4-API-RUNTIME-ACL-HOTFIX-TR.txt",
        "GD1-FINAL-R4.6-API-SYSTEM-STABILITY-HOTFIX-TR.txt",
        "GD1-FINAL-R4.7-RUNTIME-LOCK-STABILITY-HOTFIX-TR.txt",
        "GD1-FINAL-R4.8-USB-POWERSHELL-PARSER-HOTFIX-TR.txt",
        "GOKDOGAN-README-TR.md",
    ]
    assert not [name for name in forbidden if (ROOT / name).exists()]
    assert (ROOT / "README.md").exists()
    assert (ROOT / "CHANGELOG.md").exists()


def test_v1_github_assets_and_hygiene_exist():
    assert (ROOT / ".gitignore").exists()
    assert (ROOT / ".gitattributes").exists()
    assert (ROOT / "docs/screenshots/01-bolgesel-operasyon-haritasi.png").exists()
    assert (ROOT / "docs/screenshots/02-kuresel-operasyon-gorunumu.png").exists()
    workflow = (ROOT / ".github/workflows/desktop-release.yml").read_text(encoding="utf-8")
    assert '- "v*"' in workflow
    assert "gokdogan-intelligence-windows" in workflow


def test_v1_frontend_public_version_is_1_0_0_while_core_remains_r24():
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    assert frontend["version"] == "1.0.0"
    manifest = json.loads((ROOT / "R24-IMPLEMENTATION-MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["revision"] == "R24"
    assert manifest["base_version"] == "0.10.3"


def test_v1_known_user_facing_english_regressions_are_removed():
    targets = {
        "frontend/src/components/WorldviewLeftPanel.tsx": ["Catalog only (free)", "Alerts: sign up", "EDIT AOIs"],
        "frontend/src/components/SarModeChooserModal.tsx": ["SAR GROUND-CHANGE LAYER", "MODE A — Catalog only", "Activate Mode B"],
        "frontend/src/components/StartupWarmupModal.tsx": ["MASS DATA SYNTHESIS", "CONTINUE"],
        "frontend/src/components/ChangelogModal.tsx": ["WHAT&apos;S NEW", "NEW CAPABILITIES", "ACKNOWLEDGED"],
        "frontend/src/components/MaplibreViewer.tsx": ["UNKNOWN SATELLITE", "LORA SATELLITE"],
        "frontend/src/components/AIIntelPanel.tsx": ["SATELLITE IMAGERY"],
    }
    leftovers = []
    for rel, forbidden in targets.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        leftovers.extend(f"{rel}:{phrase}" for phrase in forbidden if phrase in text)
    assert not leftovers


def test_v1_ais_banner_is_turkish_and_has_startup_grace_period():
    text = (ROOT / "frontend/src/components/AisUpstreamBanner.tsx").read_text(encoding="utf-8")
    assert "90_000" in text
    assert "AIS canlı gemi akışı bekleniyor" in text
    assert "Diğer kullanılabilir deniz" in text


def test_v1_windows_builder_keeps_last_runtime_and_usb_regressions_in_release_gate():
    text = (ROOT / "WINDOWS-DESKTOP-ONE-CLICK.ps1").read_text(encoding="utf-8-sig")
    assert "test_gokdogan_r47_runtime_lock_cleanup.py" in text
    assert "test_gokdogan_r48_usb_powershell_parser.py" in text
    assert "test_gokdogan_v1_release_contract.py" in text
