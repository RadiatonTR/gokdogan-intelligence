#!/usr/bin/env python3
"""Offline regression validation for the ShadowBroker Intelligence Core."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def async_checks() -> None:
    from services.intelligence_core.adapters import AdapterMetadata, AdapterRegistry, CallableAdapter
    from services.intelligence_core.local_ai import LocalAIService
    from services.intelligence_core.task_queue import IntelligenceTaskQueue

    async def fetcher(**kwargs):
        return {"items": [{"ok": True, **kwargs}]}

    registry = AdapterRegistry()
    registry.register(CallableAdapter(AdapterMetadata(id="test-passive", name="Test Passive", category="test"), fetcher))
    check(len(registry.list()) == 1, "adapter registry failed")
    check((await registry.get("test-passive").fetch(value=7))["items"][0]["value"] == 7, "adapter fetch failed")

    queue = IntelligenceTaskQueue(max_concurrency=2)
    async def job():
        await asyncio.sleep(0)
        return {"done": True}
    submitted = queue.submit("self-test", job)
    for _ in range(50):
        state = queue.get(submitted["id"])
        if state and state["state"] in {"succeeded", "failed", "cancelled"}:
            break
        await asyncio.sleep(0.01)
    state = queue.get(submitted["id"])
    check(state and state["state"] == "succeeded" and state["result"]["done"], "controlled task queue failed")

    summary = LocalAIService.extractive_summary("Alpha changed. Bravo stayed stable. Alpha changed again. Charlie is unrelated.", 2)
    check(bool(summary) and len(summary) < 200, "local heuristic summarizer failed")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sb-intel-core-") as tmp:
        os.environ["SB_DATA_DIR"] = tmp
        from services.intelligence_core.storage import IntelligenceStore
        from services.intelligence_core.source_health import SourceHealthRegistry, SourcePolicy
        from services.intelligence_core.delta import MetricRule, compare_snapshots
        from services.intelligence_core.confidence import score_confidence
        from services.intelligence_core.fusion import fuse_observations
        from services.intelligence_core.rules import rule_matches

        store = IntelligenceStore(Path(tmp) / "self-test.db")
        check(store.schema_info()["schema_version"] >= 9, "schema migration failed")

        case = store.create_case({"title": "Self-test case", "description": "Local validation", "case_type": "investigation", "priority": "normal", "tags": ["self-test"]})
        evidence = store.add_evidence({"case_id": case["id"], "title": "Evidence", "source_uri": "local://self-test", "content_text": "Observed fact", "metadata": {"kind": "self-test"}})
        check(store.verify_evidence(evidence["id"])["integrity_ok"], "evidence hash verification failed")

        health = SourceHealthRegistry(store)
        health.register("self-test", "Self Test", SourcePolicy(reliability=0.9, stale_after_seconds=60), {"network_io": False})
        health.record_success("self-test", "Self Test", latency_ms=3.0, record_count=1, metadata={})
        check(any(x["source_id"] == "self-test" for x in health.snapshot()), "source health failed")

        delta = compare_snapshots({"metric": 20}, {"metric": 10}, [MetricRule(path="metric", threshold=5)])
        check(delta["signals"]["escalated"] and delta["summary"]["total_changes"] >= 1, "delta engine failed")

        conf = score_confidence({"source_reliability": 0.9, "freshness": 0.9, "independent_confirmation": 0.8})
        check(0.0 <= conf["score"] <= 1.0, "confidence engine failed")

        fused = fuse_observations([
            {"id": "o1", "title": "Signal A", "observed_at": "2026-08-10T00:00:00Z", "latitude": 41.0, "longitude": 29.0, "source_id": "a", "entity_id": "e1"},
            {"id": "o2", "title": "Signal B", "observed_at": "2026-08-10T00:10:00Z", "latitude": 41.05, "longitude": 29.05, "source_id": "b", "entity_id": "e1"},
        ], radius_km=20, window_minutes=30, min_observations=2)
        check(len(fused) == 1, "fusion engine failed")

        check(rule_matches({"conditions": {"mode": "all", "items": [{"kind": "field", "path": "severity", "op": "eq", "value": "high"}]}}, {"severity": "high"}), "rule engine failed")

        indexed = store.rebuild_search_index()
        check(indexed["cases"] >= 1 and indexed["evidence"] >= 1, "search reindex failed")
        check(store.search_documents("Self-test"), "local search failed")

        # R7 persistent observation + RTree spatial index.
        obs = store.record_observation({
            "id": "obs-self-test", "kind": "observed", "event_type": "aviation", "summary": "Test aircraft",
            "entity_id": "aircraft-test", "location": {"lat": 41.0, "lng": 29.0},
            "source": {"source_id": "self-test", "provider": "Self Test", "reliability": 0.9},
            "confidence": 0.9, "attributes": {}, "provenance": [],
        })
        check(obs["id"] == "obs-self-test", "observation persistence failed")
        check(any(x["id"] == "obs-self-test" for x in store.observations_in_bbox(28.5, 40.5, 29.5, 41.5, 50)), "RTree/bbox observation lookup failed")

        # R7 retention applies to disposable operational history without
        # deleting analyst cases/evidence.
        store.record_observation({
            "id": "obs-expired", "kind": "observed", "event_type": "test.old", "summary": "Expired telemetry",
            "location": {"lat": 40.0, "lng": 28.0}, "source": {"source_id": "self-test", "provider": "Self Test"},
            "observed_at": "2020-01-01T00:00:00Z", "confidence": 0.5, "attributes": {}, "provenance": [],
        })
        prune = store.prune_history(keep_days=30, keep_per_namespace=500)
        check(prune["removed"]["observations"] >= 1 and store.get_observation("obs-expired") is None, "history retention prune failed")
        check(store.list_cases(10) and store.list_evidence(case["id"]), "history prune removed analyst evidence")

        # R7 geofence persistence and candidate lookup.
        fence = store.create_geofence({"name": "Test Fence", "polygon": [{"lat": 40.5, "lng": 28.5}, {"lat": 41.5, "lng": 28.5}, {"lat": 41.5, "lng": 29.5}, {"lat": 40.5, "lng": 29.5}], "severity": "watch", "entity_types": ["aircraft"], "cooldown_seconds": 300, "metadata": {}})
        check(any(x["id"] == fence["id"] for x in store.candidate_geofences(41.0, 29.0)), "geofence candidate lookup failed")

        # R7 exact identifier resolution foundation.
        store.upsert_identifier("aircraft", "icao24", "ABC123", "TEST-AIRCRAFT", 1.0, "self-test")
        check(store.resolve_identifier("aircraft", {"icao24": "abc123"})["canonical_value"] == "TEST-AIRCRAFT", "entity identifier resolution failed")

        # R7 atomic full snapshot / restore.
        snap = store.create_full_snapshot("self-test")
        check(snap.get("id") and any(x.get("id") == snap["id"] and x.get("available") for x in store.list_full_snapshots()), "full snapshot creation failed")

        backup = store.export_state()
        check(backup["format"] == "shadowbroker-intelligence-core-backup-v2", "backup export failed")

        # R7 legacy bridge: with monitoring configured, a legacy aircraft row
        # becomes a canonical observation and can trigger the watchlist path
        # without network I/O.  Use a real IntelligenceCore so the bridge is
        # tested against the same persistence/rule path used by the application.
        from services.intelligence_core.service import IntelligenceCore
        core = IntelligenceCore()
        core.store.add_watch({
            "entity_type": "aircraft",
            "value": "abc123",
            "label": "Legacy bridge watch",
            "metadata": {},
        })
        legacy_result = core.ingest_legacy_layer(
            "military_flights",
            [{"icao24": "abc123", "callsign": "TEST123", "lat": 40.0, "lng": 29.0}],
            max_rule_items=5,
        )
        check(legacy_result["ingested"] >= 1, "legacy Intelligence Core bridge failed")

    asyncio.run(async_checks())
    print("Intelligence Core offline validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
