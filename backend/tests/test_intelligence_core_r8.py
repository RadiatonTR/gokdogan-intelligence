from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

from services.intelligence_core.local_ai import LocalAIService
from services.intelligence_core.service import IntelligenceCore
from services.intelligence_core.storage import IntelligenceStore, SCHEMA_VERSION


def _core_with_store(store: IntelligenceStore) -> IntelligenceCore:
    core = object.__new__(IntelligenceCore)
    core.store = store
    core.local_ai = LocalAIService()
    return core


def test_r8_integrity_report_and_snapshot_validation(tmp_path: Path) -> None:
    store = IntelligenceStore(tmp_path / "intelligence-core.db")
    report = store.integrity_report()
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["quick_check"] == ["ok"]
    assert report["missing_tables"] == []
    assert report["missing_virtual_tables"] == []
    assert report["ok"] is True

    snapshot = store.create_full_snapshot("r8-integrity")
    check = store.validate_full_snapshot(snapshot["id"])
    assert check["ok"] is True
    assert check["schema_version"] == SCHEMA_VERSION
    assert check["sha256"] == snapshot["database_sha256"]
    assert store.validate_full_snapshot("../escape")["error"] == "invalid_snapshot_id"


def test_r8_tampered_snapshot_is_rejected(tmp_path: Path) -> None:
    store = IntelligenceStore(tmp_path / "intelligence-core.db")
    snapshot = store.create_full_snapshot("r8-tamper")
    snap_dir = store.db_path.parent / "intelligence-snapshots"
    snap_db = snap_dir / snapshot["database_file"]
    with snap_db.open("ab") as handle:
        handle.write(b"R8-TAMPER")
    result = store.validate_full_snapshot(snapshot["id"])
    assert result["ok"] is False
    assert result["error"] == "snapshot_integrity_failed"


def test_r8_hybrid_semantic_search_preserves_lexical_exact_match(tmp_path: Path) -> None:
    store = IntelligenceStore(tmp_path / "intelligence-core.db")
    case = store.create_case({
        "title": "Black Sea maritime anomaly",
        "description": "Vessel ALPHA-778 changed course near the monitored corridor.",
        "case_type": "investigation",
        "priority": "normal",
        "tags": ["maritime"],
    })
    core = _core_with_store(store)
    result = asyncio.run(core.semantic_search("ALPHA-778", limit=10))
    assert result["ranking"] == "hybrid-local-v1"
    assert result["vector_engine"] in {"python", "numpy-batched"}
    assert result["count"] >= 1
    ids = [str(item["id"]) for item in result["results"]]
    assert case["id"] in ids
    hit = next(item for item in result["results"] if str(item["id"]) == case["id"])
    assert hit["lexical_score"] > 0
    assert hit["hybrid_score"] > 0


def test_r8_recovery_helper_restores_latest_valid_snapshot(tmp_path: Path) -> None:
    # Import the stdlib-only Windows recovery helper by file path so it remains
    # independently executable outside the backend package.
    helper_path = Path(__file__).resolve().parents[2] / "scripts" / "windows" / "recover_intelligence_database.py"
    spec = importlib.util.spec_from_file_location("r8_recovery_helper", helper_path)
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "intelligence-core.db"
    store = IntelligenceStore(db_path)
    case = store.create_case({"title": "Snapshot state", "description": "", "case_type": "investigation", "priority": "normal", "tags": []})
    snapshot = store.create_full_snapshot("r8-recovery")

    # Mutate the live database after the snapshot.
    store.create_case({"title": "Later state", "description": "", "case_type": "investigation", "priority": "normal", "tags": []})
    valid = helper.list_valid_snapshots(data_dir)
    assert valid and valid[0]["meta"]["id"] == snapshot["id"]
    restored = helper.restore_snapshot(db_path, Path(valid[0]["database"]), data_dir)
    assert restored["ok"] is True
    assert restored["check"]["quick_check"] == ["ok"]

    reopened = IntelligenceStore(db_path)
    cases = reopened.list_cases(20)
    assert [item["title"] for item in cases] == ["Snapshot state"]
    assert reopened.get_case(case["id"]) is not None


def test_r8_schema_v9_upgrade_backfills_geofence_rtree(tmp_path: Path) -> None:
    db_path = tmp_path / "upgrade.db"
    store = IntelligenceStore(db_path)
    fence = store.create_geofence({
        "name": "Upgrade fence",
        "polygon": [
            {"lat": 40.0, "lng": 28.0}, {"lat": 42.0, "lng": 28.0},
            {"lat": 42.0, "lng": 30.0}, {"lat": 40.0, "lng": 30.0},
        ],
        "severity": "watch", "entity_types": [], "cooldown_seconds": 60, "metadata": {},
    })
    with store.connect() as con:
        con.execute("DROP TABLE IF EXISTS geofence_geo")
        con.execute("UPDATE schema_meta SET value='9' WHERE key='schema_version'")
    upgraded = IntelligenceStore(db_path)
    assert upgraded.schema_info()["schema_version"] == SCHEMA_VERSION
    assert SCHEMA_VERSION >= 10
    assert upgraded.storage_features()["geofence_rtree"] is True
    candidates = upgraded.candidate_geofences(41.0, 29.0)
    assert [item["id"] for item in candidates] == [fence["id"]]
