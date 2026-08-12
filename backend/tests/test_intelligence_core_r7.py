from __future__ import annotations
from pathlib import Path

from services.intelligence_core.entity_resolution import EntityResolver
from services.intelligence_core.service import _point_in_polygon
from services.intelligence_core.storage import IntelligenceStore


def test_r7_schema_spatial_geofence_and_identifiers(tmp_path: Path) -> None:
    store = IntelligenceStore(tmp_path / "r7.db")
    assert store.schema_info()["schema_version"] >= 9
    assert store.storage_features()["fts5"] in {True, False}
    assert store.storage_features()["rtree"] in {True, False}

    store.record_observation({
        "id": "obs-r7",
        "kind": "observed",
        "event_type": "aviation",
        "summary": "Aircraft observed",
        "entity_id": "aircraft-r7",
        "location": {"lat": 41.0, "lng": 29.0},
        "source": {"source_id": "test", "provider": "Test", "reliability": 0.9},
        "confidence": 0.9,
        "attributes": {},
        "provenance": [],
    })
    assert [x["id"] for x in store.observations_in_bbox(28.0, 40.0, 30.0, 42.0, 10)] == ["obs-r7"]

    fence = store.create_geofence({
        "name": "Istanbul test",
        "polygon": [
            {"lat": 40.5, "lng": 28.5}, {"lat": 41.5, "lng": 28.5},
            {"lat": 41.5, "lng": 29.5}, {"lat": 40.5, "lng": 29.5},
        ],
        "severity": "watch", "entity_types": ["aircraft"], "cooldown_seconds": 30, "metadata": {},
    })
    assert store.candidate_geofences(41.0, 29.0)[0]["id"] == fence["id"]
    assert _point_in_polygon(41.0, 29.0, fence["polygon"])
    assert not _point_in_polygon(42.0, 29.0, fence["polygon"])

    resolver = EntityResolver(store)
    store.upsert_identifier("aircraft", "icao24", "ABC123", "TC-R7", 1.0, "test")
    resolved = resolver.resolve("aircraft", "Unknown label", identifiers={"icao24": "abc123"})
    assert resolved["method"] == "exact_identifier"
    assert resolved["canonical"] == "TC-R7"


def test_r7_full_snapshot_and_evidence_v2(tmp_path: Path) -> None:
    store = IntelligenceStore(tmp_path / "r7.db")
    case = store.create_case({"title": "R7", "description": "", "case_type": "investigation", "priority": "normal", "tags": []})
    evidence = store.add_evidence({
        "case_id": case["id"], "title": "Capture", "source_uri": "local://r7",
        "content_text": "immutable evidence", "content_mime": "text/plain",
        "capture_method": "unit-test", "captured_by": "pytest", "source_headers": {"etag": "r7"}, "metadata": {},
    })
    assert evidence["hash_version"] == 2
    assert store.verify_evidence(evidence["id"])["integrity_ok"] is True
    snap = store.create_full_snapshot("pytest")
    assert any(x["id"] == snap["id"] and x["available"] for x in store.list_full_snapshots())


def test_r7_offline_source_gate_never_calls_network(tmp_path: Path) -> None:
    import asyncio
    from services.intelligence_core.source_health import SourceHealthRegistry

    store = IntelligenceStore(tmp_path / "r7-offline.db")
    store.set_setting("runtime_preferences", {"offline_mode": True})
    sources = SourceHealthRegistry(store)
    called = False

    async def run() -> None:
        nonlocal called

        def should_not_run():
            nonlocal called
            called = True
            return {"unexpected": True}

        try:
            await sources.call("offline-test", "Offline Test", should_not_run)
        except RuntimeError as exc:
            assert str(exc) == "source_offline_mode:offline-test"
        else:
            raise AssertionError("offline source gate did not block the call")

    asyncio.run(run())
    assert called is False
    row = next(x for x in store.list_source_health() if x["source_id"] == "offline-test")
    assert row["state"] == "disabled"
    assert row["last_error"] == "runtime_offline_mode"


def test_r7_retention_prunes_operational_history_not_analyst_evidence(tmp_path: Path) -> None:
    store = IntelligenceStore(tmp_path / "r7-retention.db")
    case = store.create_case({"title": "Keep me", "description": "", "case_type": "investigation", "priority": "normal", "tags": []})
    evidence = store.add_evidence({
        "case_id": case["id"], "title": "Keep evidence", "source_uri": "local://retention",
        "content_text": "analyst evidence must survive pruning", "content_mime": "text/plain",
        "capture_method": "unit-test", "captured_by": "pytest", "source_headers": {}, "metadata": {},
    })
    store.record_observation({
        "id": "old-observation", "kind": "observed", "event_type": "test", "summary": "old",
        "entity_id": "entity-old", "observed_at": "2000-01-01T00:00:00+00:00",
        "location": {"lat": 41.0, "lng": 29.0},
        "source": {"source_id": "test", "provider": "Test", "reliability": 1.0},
        "confidence": 1.0, "attributes": {}, "provenance": [],
    })
    result = store.prune_history(keep_days=1)
    assert result["removed"]["observations"] >= 1
    assert store.get_case(case["id"]) is not None
    assert store.verify_evidence(evidence["id"])["integrity_ok"] is True


def test_r7_local_ai_model_manager_names_are_not_urls_or_paths() -> None:
    from services.intelligence_core.local_ai import LocalAIService

    assert LocalAIService.validate_model_name("gemma3:4b") == "gemma3:4b"
    assert LocalAIService.validate_model_name("org/model-name:Q4_K_M") == "org/model-name:Q4_K_M"
    for value in ("", "http://example.test/model", "../model", "model?token=x", "model name"):
        try:
            LocalAIService.validate_model_name(value)
        except ValueError as exc:
            assert str(exc) == "invalid_local_model_name"
        else:
            raise AssertionError(f"unsafe model name accepted: {value}")


def test_r7_workspace_presets_round_trip(tmp_path: Path) -> None:
    store = IntelligenceStore(tmp_path / "r7-workspace.db")
    saved = store.save_workspace(
        "Maritime analyst",
        {"runtime_preferences": {"profile": "balanced", "offline_mode": False}, "semantic_mode": True, "ai_model": "gemma3:4b", "preferred_tab": "search"},
        is_default=True,
    )
    listed = store.list_workspaces()
    assert listed and listed[0]["id"] == saved["id"]
    assert listed[0]["is_default"] is True
    assert listed[0]["layout"]["preferred_tab"] == "search"
    replacement = store.save_workspace(
        "Crisis analyst",
        {"runtime_preferences": {"profile": "performance"}, "semantic_mode": False, "preferred_tab": "incidents"},
        is_default=True,
    )
    listed = store.list_workspaces()
    defaults = [item for item in listed if item["is_default"]]
    assert [item["id"] for item in defaults] == [replacement["id"]]
    assert store.delete_workspace(saved["id"]) is True
    assert all(item["id"] != saved["id"] for item in store.list_workspaces())
    assert store.delete_workspace("missing") is False


def test_r7_adapter_sdk_rejects_active_collection_and_normalizes_passive() -> None:
    from services.intelligence_core.adapters import AdapterMetadata, AdapterRegistry, CallableAdapter
    import asyncio

    async def passive_fetch(**kwargs):
        return {"items": [{"id": "one"}, "ignore", {"id": "two"}]}

    passive = CallableAdapter(
        AdapterMetadata(id="test-passive", name="Test Passive", category="test", active_collection=False),
        passive_fetch,
    )
    registry = AdapterRegistry()
    registry.register(passive)
    assert registry.get("test-passive") is passive
    assert passive.normalize(asyncio.run(passive.fetch())) == [{"id": "one"}, {"id": "two"}]

    active = CallableAdapter(
        AdapterMetadata(id="test-active", name="Test Active", category="test", active_collection=True),
        passive_fetch,
    )
    try:
        registry.register(active)
    except RuntimeError as exc:
        assert str(exc) == "active_adapter_requires_explicit_host_authorization:test-active"
    else:
        raise AssertionError("active adapter was accepted without authorization boundary")


def test_r7_task_queue_concurrency_reconfigures_live() -> None:
    from services.intelligence_core.task_queue import IntelligenceTaskQueue

    queue = IntelligenceTaskQueue(max_concurrency=4)
    assert queue.status()["max_concurrency"] == 4
    assert queue.set_max_concurrency(9) == 9
    assert queue.status()["max_concurrency"] == 9
    assert queue.set_max_concurrency(999) == 32
    assert queue.set_max_concurrency(0) == 1
