from __future__ import annotations

import os
import threading


def test_integration_readiness_never_exposes_secret_values(monkeypatch):
    monkeypatch.setenv("OPENSKY_CLIENT_ID", "client-id-secret-looking")
    monkeypatch.setenv("OPENSKY_CLIENT_SECRET", "client-secret-secret-looking")
    monkeypatch.setenv("AIS_API_KEY", "ais-secret-looking")
    from services.integration_readiness import integration_readiness_snapshot

    snapshot = integration_readiness_snapshot()
    assert snapshot["ok"] is True
    rendered = repr(snapshot)
    assert "client-id-secret-looking" not in rendered
    assert "client-secret-secret-looking" not in rendered
    assert "ais-secret-looking" not in rendered
    rows = {row["id"]: row for row in snapshot["integrations"]}
    assert rows["opensky_client_id"]["configured"] is True
    assert rows["ais_api_key"]["configured"] is True


def test_paired_credentials_report_partial_configuration(monkeypatch):
    monkeypatch.setenv("OPENSKY_CLIENT_ID", "set")
    monkeypatch.delenv("OPENSKY_CLIENT_SECRET", raising=False)
    from services.integration_readiness import integration_readiness_snapshot

    rows = {row["id"]: row for row in integration_readiness_snapshot()["integrations"]}
    assert rows["opensky_client_id"]["state"] == "partial_config"
    assert rows["opensky_client_secret"]["state"] == "partial_config"


def test_missing_key_blocks_refresh_without_network(monkeypatch):
    monkeypatch.delenv("GFW_API_TOKEN", raising=False)
    from services.integration_readiness import request_integration_refresh

    result = request_integration_refresh("gfw_api_token")
    assert result["ok"] is False
    assert result["detail"] == "optional_key"


def test_refresh_runs_background_callable(monkeypatch):
    from services import integration_readiness as mod

    done = threading.Event()
    monkeypatch.setattr(mod, "_refresh_callable", lambda group: lambda: done.set())
    result = mod.request_integration_refresh("usgs_earthquakes")
    assert result["ok"] is True
    assert result["group"] == "earthquakes"
    assert done.wait(2.0)


def test_layer_enable_refresh_covers_opt_in_operational_layers():
    from services import layer_enable_refresh as mod

    expected = {
        "cctv", "firms", "psk_reporter", "fishing_activity", "crowdthreat",
        "malware_c2", "cyber_threats", "scm_suppliers", "viirs_nightlights",
        "road_corridor_trends",
    }
    assert expected.issubset(mod._SLOW_LAYER_KEYS)


def test_experimental_and_hardware_capabilities_are_honest():
    from services.integration_readiness import integration_readiness_snapshot

    caps = {row["id"]: row for row in integration_readiness_snapshot()["capabilities"]}
    assert caps["infonet_privacy"]["state"] == "experimental"
    assert caps["meshtastic_hardware"]["state"] == "hardware_required"
    assert caps["host_shell"]["state"] == "disabled_by_design"
    assert caps["active_recon"]["state"] == "disabled_by_design"
