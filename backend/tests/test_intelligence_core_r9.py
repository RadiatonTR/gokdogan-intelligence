from __future__ import annotations

from pathlib import Path

from services.intelligence_core.storage import IntelligenceStore, SCHEMA_VERSION
from services.intelligence_core.source_health import SourceHealthRegistry, SourcePolicy


def test_r9_schema_quarantine_and_maintenance(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "r9.db")
    assert SCHEMA_VERSION >= 11
    assert store.schema_info()["schema_version"] == SCHEMA_VERSION
    q = store.quarantine_source("adapter:test", "Test", "schema drift", quarantine_kind="schema-drift", duration_seconds=3600)
    assert q["source_id"] == "adapter:test"
    assert store.get_source_quarantine("adapter:test") is not None
    assert store.list_source_quarantine()
    assert store.clear_source_quarantine("adapter:test") is True
    assert store.get_source_quarantine("adapter:test") is None
    run = store.run_database_maintenance(rebuild_search=True)
    assert run["ok"] is True
    assert store.list_maintenance_runs(1)[0]["action"] == "database-maintenance"
    integrity = store.integrity_report()
    assert integrity["ok"] is True


def test_r9_source_registry_respects_quarantine(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "r9-health.db")
    health = SourceHealthRegistry(store)
    health.register("src", "Source", SourcePolicy(max_failures=2, cooldown_seconds=60))
    assert health.can_call("src") is True
    health.quarantine("src", "Source", "manual review", manual=True, duration_seconds=60)
    assert health.can_call("src") is False
    snap = {x["source_id"]: x for x in health.snapshot()}
    assert snap["src"]["quarantined"] is True
    assert snap["src"]["state"] == "disabled"
    assert health.clear_quarantine("src") is True
    assert health.can_call("src") is True


def test_r9_backup_v2_round_trip_geofence_workspace_and_alert(tmp_path: Path):
    source = IntelligenceStore(tmp_path / "source.db")
    source.create_geofence({
        "name": "Test Fence",
        "polygon": [{"lat": 40.0, "lng": 28.0}, {"lat": 40.2, "lng": 28.0}, {"lat": 40.1, "lng": 28.2}],
        "severity": "priority",
        "enabled": True,
        "entity_types": ["aircraft"],
        "cooldown_seconds": 300,
        "metadata": {"test": True},
    })
    source.save_workspace("Analyst", {"preferred_tab": "sources"}, is_default=True)
    source.set_setting("runtime_preferences", {"profile": "balanced", "offline_mode": False})
    alert = source.create_alert({"title": "Backup Alert", "detail": "test", "severity": "priority", "metadata": {"x": 1}})
    source.update_alert_status(alert["id"], "acknowledged")
    payload = source.export_state()
    assert payload["format"] == "shadowbroker-intelligence-core-backup-v2"

    target = IntelligenceStore(tmp_path / "target.db")
    counts = target.import_state(payload)
    assert counts["geofences"] == 1
    assert counts["workspaces"] == 1
    assert counts["alerts"] == 1
    assert counts["settings"] == 1
    assert target.list_geofences()[0]["name"] == "Test Fence"
    assert target.list_workspaces()[0]["name"] == "Analyst"
    assert target.list_alerts(10)[0]["status"] == "acknowledged"
