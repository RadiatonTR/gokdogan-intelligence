from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_usb_distribution_scripts_are_release_wired():
    one_click = (ROOT / "WINDOWS-DESKTOP-ONE-CLICK.ps1").read_text(encoding="utf-8")
    prep = (ROOT / "GOKDOGAN-USB-DAGITIM-HAZIRLA.ps1").read_text(encoding="utf-8")
    install = (ROOT / "GOKDOGAN-USB-KUR.ps1").read_text(encoding="utf-8")
    assert "GOKDOGAN-USB-DAGITIM" in one_click
    assert "Gokdogan-Intelligence-v1.0.0-OFFLINE-USB.zip" in one_click
    assert "GOKDOGAN-USB-DAGITIM-HAZIRLA.ps1" in one_click
    assert "BuildReportsDir" not in one_click.split("Write-Stage 9", 1)[1].split("Write-Stage 10", 1)[0]
    assert "Gokdogan-Intelligence-v1.0.0-Setup.exe" in prep
    assert "SHA256SUMS.txt" in prep
    assert "--self-test" in install
    assert "Get-FileHash" in install


def test_authorized_public_camera_catalog_requires_explicit_public_marker():
    from services.cctv_pipeline import _camera_rows_from_authorized_catalog

    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [29.0, 41.0]},
                "properties": {
                    "id": "public-1",
                    "name": "Resmi kamu kamerası",
                    "source_agency": "Official Open Data",
                    "public_access_confirmed": True,
                    "image_url": "https://example.org/camera.jpg",
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [30.0, 40.0]},
                "properties": {
                    "id": "private-1",
                    "name": "No explicit public marker",
                    "image_url": "https://example.org/private.jpg",
                },
            },
        ],
    }
    rows = _camera_rows_from_authorized_catalog(payload, catalog_url="https://catalog.example.org/cameras.geojson")
    assert len(rows) == 1
    assert rows[0]["source_agency"] == "Official Open Data"
    assert rows[0]["lat"] == 41.0
    assert rows[0]["lon"] == 29.0
    assert rows[0]["media_url"].startswith("https://")


def test_public_camera_catalog_url_needs_explicit_host_allowlist(monkeypatch):
    from services import cctv_pipeline as mod

    monkeypatch.setenv("GOKDOGAN_PUBLIC_CAMERA_CATALOG_HOSTS", "catalog.example.org")
    monkeypatch.setattr(mod, "_hostname_resolves_only_public_addresses", lambda host: host == "catalog.example.org")
    assert mod._public_camera_catalog_url_allowed("https://catalog.example.org/cameras.json") is True
    assert mod._public_camera_catalog_url_allowed("http://catalog.example.org/cameras.json") is False
    assert mod._public_camera_catalog_url_allowed("https://other.example.org/cameras.json") is False


def test_dynamic_cctv_proxy_hosts_require_public_network_resolution(monkeypatch):
    from services import cctv_public_policy as mod

    monkeypatch.setenv("GOKDOGAN_PUBLIC_CAMERA_MEDIA_HOSTS", "media.example.org")
    monkeypatch.setattr(mod, "host_resolves_only_public_addresses", lambda host: host == "media.example.org")
    assert mod.configured_public_camera_media_host_allowed("media.example.org") is True
    assert mod.configured_public_camera_media_host_allowed("sub.media.example.org") is False
    assert mod.configured_public_camera_media_host_allowed("localhost") is False


def test_registry_credentials_are_persistable_by_windows_vault():
    import ast
    import re

    api_source = (ROOT / "backend" / "services" / "api_settings.py").read_text(encoding="utf-8")
    tree = ast.parse(api_source)
    registry = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "API_REGISTRY" for t in node.targets):
            registry = ast.literal_eval(node.value)
            break
    env_keys = {row["env_key"] for row in registry if row.get("env_key")}
    rust = (ROOT / "desktop-shell" / "tauri-skeleton" / "src-tauri" / "src" / "backend_runtime.rs").read_text(encoding="utf-8")
    block = rust.split("fn backend_vault_secret_allowed", 1)[1].split("\n}", 1)[0]
    allowed = set(re.findall(r'"([A-Z][A-Z0-9_]+)"', block))
    assert env_keys.issubset(allowed)
    for key in {
        "GOKDOGAN_PUBLIC_CAMERA_CATALOG_URLS",
        "GOKDOGAN_PUBLIC_CAMERA_CATALOG_HOSTS",
        "GOKDOGAN_PUBLIC_CAMERA_MEDIA_HOSTS",
        "ABUSEIPDB_API_KEY",
    }:
        assert key in env_keys
        assert key in allowed


def test_abuseipdb_enrichment_is_passive_and_server_side(monkeypatch):
    from services.osint import lookups as mod

    monkeypatch.setenv("ABUSEIPDB_API_KEY", "server-side-test-key")

    class _TorResponse:
        status_code = 200
        text = ""

    monkeypatch.setattr(mod, "fetch_with_curl", lambda *args, **kwargs: _TorResponse())

    def fake_json(url: str, *, timeout=8.0, headers=None):
        if "abuseipdb.com/api/v2/check" in url:
            assert headers == {"Accept": "application/json", "Key": "server-side-test-key"}
            return {
                "data": {
                    "abuseConfidenceScore": 88,
                    "totalReports": 17,
                    "countryCode": "US",
                    "usageType": "Data Center/Web Hosting/Transit",
                    "isp": "Example ISP",
                    "domain": "example.net",
                    "lastReportedAt": "2026-08-10T00:00:00+00:00",
                    "isTor": False,
                }
            }
        if "alienvault.com" in url:
            return {"pulse_info": {"count": 0}}
        return None

    monkeypatch.setattr(mod, "_json_get", fake_json)
    result = mod.lookup_threats("8.8.8.8")
    assert result["abuseipdb"]["abuse_confidence_score"] == 88
    assert result["abuseipdb"]["total_reports"] == 17
    assert result["threat_level"] == "HIGH"
