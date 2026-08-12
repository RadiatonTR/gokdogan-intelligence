from __future__ import annotations

from pathlib import Path

from services.intelligence_core.confidence import score_confidence
from services.intelligence_core.delta import MetricRule, compare_snapshots
from services.intelligence_core.entity_resolution import EntityResolver
from services.intelligence_core.source_health import SourceHealthRegistry, SourcePolicy
from services.intelligence_core.storage import IntelligenceStore


def test_store_case_evidence_and_audit(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "intel.db")
    case = store.create_case({"title": "Test case", "description": "x", "tags": ["demo"]})
    evidence = store.add_evidence({"case_id": case["id"], "title": "Snapshot", "content_text": "immutable evidence", "metadata": {"kind": "test"}})
    assert len(evidence["sha256"]) == 64
    loaded = store.get_case(case["id"])
    assert loaded and loaded["evidence"][0]["sha256"] == evidence["sha256"]
    assert store.list_audit(10)


def test_source_health_circuit_breaker(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "intel.db")
    sources = SourceHealthRegistry(store)
    policy = SourcePolicy(max_failures=2, cooldown_seconds=60, reliability=0.9)
    sources.register("demo", "Demo", policy)
    sources.record_failure("demo", "Demo", "one")
    assert sources.can_call("demo")
    sources.record_failure("demo", "Demo", "two")
    assert not sources.can_call("demo")
    sources.record_success("demo", "Demo", 12.0, 3)
    assert sources.can_call("demo")
    assert sources.snapshot()[0]["state"] == "live"


def test_delta_and_confidence():
    previous = {"air": {"count": 10}, "ships": [{"mmsi": "1"}]}
    current = {"air": {"count": 20}, "ships": [{"mmsi": "1"}, {"mmsi": "2"}]}
    delta = compare_snapshots(current, previous, [MetricRule("air.count", threshold=25, percent=True)])
    assert delta["summary"]["total_changes"] >= 2
    assert delta["signals"]["escalated"][0]["metric_change"] == 100.0
    score = score_confidence({"source_reliability": 1, "freshness": 1, "location_certainty": 1, "timestamp_certainty": 1, "independent_confirmation": 1, "source_independence": 1, "cross_source_agreement": 1})
    assert score["label"] == "very_high"


def test_entity_alias_resolution(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "intel.db")
    resolver = EntityResolver(store)
    result = resolver.resolve("country", "USA")
    assert result["canonical"] == "United States"
    result2 = resolver.resolve("country", "USA")
    assert result2["method"] == "alias_store"
