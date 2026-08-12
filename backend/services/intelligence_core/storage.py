from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import new_id, utc_now_iso
from services.runtime_paths import runtime_data_dir

SCHEMA_VERSION = 11


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _evidence_digest_v2(payload: dict[str, Any]) -> str:
    envelope = {
        "title": payload.get("title") or "",
        "source_uri": payload.get("source_uri") or "",
        "content_text": payload.get("content_text") or "",
        "content_mime": payload.get("content_mime") or "text/plain",
        "capture_method": payload.get("capture_method") or "manual",
        "captured_by": payload.get("captured_by") or "local-operator",
        "source_headers": payload.get("source_headers") or {},
        "metadata": payload.get("metadata") or {},
    }
    return hashlib.sha256(_json(envelope).encode("utf-8")).hexdigest()


class IntelligenceStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or runtime_data_dir() / "intelligence-core.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._backup_before_migration()
        self._initialize()

    def _backup_before_migration(self) -> None:
        """Create a consistent SQLite backup before an on-disk schema upgrade."""
        if not self.db_path.exists() or self.db_path.stat().st_size == 0:
            return
        source = None
        target = None
        try:
            source = sqlite3.connect(self.db_path, timeout=10)
            exists = source.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
            ).fetchone()
            current = 0
            if exists:
                row = source.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()
                current = int(row[0]) if row else 0
            if current >= SCHEMA_VERSION:
                return
            backup_path = self.db_path.with_name(
                f"{self.db_path.stem}.pre-v{current}-to-v{SCHEMA_VERSION}.sqlite.bak"
            )
            target = sqlite3.connect(backup_path)
            source.backup(target)
        except Exception:
            # Migration backup is defense in depth; the transactional migrations
            # below remain authoritative. Startup should not be bricked by an
            # inability to create the convenience backup.
            pass
        finally:
            if target is not None:
                target.close()
            if source is not None:
                source.close()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=10000")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _initialize(self) -> None:
        with self._lock, self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute(
                "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            current = con.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            version = int(current[0]) if current else 0
            if version < 1:
                self._migration_1(con)
                version = 1
            if version < 2:
                self._migration_2(con)
                version = 2
            if version < 3:
                self._migration_3(con)
                version = 3
            if version < 4:
                self._migration_4(con)
                version = 4
            if version < 5:
                self._migration_5(con)
                version = 5
            if version < 6:
                self._migration_6(con)
                version = 6
            if version < 7:
                self._migration_7(con)
                version = 7
            if version < 8:
                self._migration_8(con)
                version = 8
            if version < 9:
                self._migration_9(con)
                version = 9
            if version < 10:
                self._migration_10(con)
                version = 10
            if version < 11:
                self._migration_11(con)
                version = 11
            con.execute(
                "INSERT INTO schema_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _migration_1(con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS source_health (
          source_id TEXT PRIMARY KEY, provider TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'unknown',
          enabled INTEGER NOT NULL DEFAULT 1, last_success_at TEXT, last_failure_at TEXT,
          last_error TEXT, latency_ms REAL, record_count INTEGER NOT NULL DEFAULT 0,
          consecutive_failures INTEGER NOT NULL DEFAULT 0, cooldown_until REAL NOT NULL DEFAULT 0,
          cache_age_seconds REAL, reliability REAL NOT NULL DEFAULT 0.5, metadata_json TEXT NOT NULL DEFAULT '{}',
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cases (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          case_type TEXT NOT NULL DEFAULT 'investigation', priority TEXT NOT NULL DEFAULT 'normal',
          status TEXT NOT NULL DEFAULT 'open', tags_json TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evidence (
          id TEXT PRIMARY KEY, case_id TEXT NOT NULL, title TEXT NOT NULL, source_uri TEXT,
          content_text TEXT, sha256 TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
          captured_at TEXT NOT NULL, FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS watchlists (
          id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, value TEXT NOT NULL, label TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_watch_unique ON watchlists(entity_type, value);
        CREATE TABLE IF NOT EXISTS rules (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          severity TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, conditions_json TEXT NOT NULL DEFAULT '{}',
          cooldown_seconds INTEGER NOT NULL DEFAULT 300, last_triggered_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alerts (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', severity TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'new', rule_id TEXT, incident_id TEXT, entity_id TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)

    @staticmethod
    def _migration_2(con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
          id TEXT PRIMARY KEY, namespace TEXT NOT NULL, captured_at TEXT NOT NULL,
          payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_namespace_time ON snapshots(namespace, captured_at DESC);
        CREATE TABLE IF NOT EXISTS incidents (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', severity TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0.5, status TEXT NOT NULL DEFAULT 'open',
          location_json TEXT, observation_ids_json TEXT NOT NULL DEFAULT '[]', entity_ids_json TEXT NOT NULL DEFAULT '[]',
          source_ids_json TEXT NOT NULL DEFAULT '[]', tags_json TEXT NOT NULL DEFAULT '[]', assessment_json TEXT NOT NULL DEFAULT '{}',
          first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
        );
        """)

    @staticmethod
    def _migration_3(con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, actor TEXT NOT NULL DEFAULT 'local-operator',
          object_type TEXT, object_id TEXT, detail_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
        CREATE TABLE IF NOT EXISTS entity_aliases (
          alias_key TEXT NOT NULL, entity_type TEXT NOT NULL, canonical_value TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 1.0, source TEXT NOT NULL DEFAULT 'local', updated_at TEXT NOT NULL,
          PRIMARY KEY(alias_key, entity_type)
        );
        """)

    @staticmethod
    def _migration_4(con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS search_documents (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
          entity_id TEXT, source_id TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_search_kind ON search_documents(kind);
        CREATE INDEX IF NOT EXISTS idx_search_updated ON search_documents(updated_at DESC);
        """)

    @staticmethod
    def _migration_5(con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS kv_settings (
          key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workspaces (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, layout_json TEXT NOT NULL DEFAULT '{}',
          is_default INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)

    @staticmethod
    def _migration_6(con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS observations (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'observed', entity_id TEXT, event_type TEXT NOT NULL,
          summary TEXT NOT NULL DEFAULT '', lat REAL, lng REAL, uncertainty_km REAL,
          source_id TEXT NOT NULL, source_provider TEXT NOT NULL DEFAULT '', source_family TEXT, source_uri TEXT,
          source_reliability REAL NOT NULL DEFAULT 0.5, observed_at TEXT, received_at TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0.5, attributes_json TEXT NOT NULL DEFAULT '{}',
          provenance_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_observations_time ON observations(observed_at DESC, received_at DESC);
        CREATE INDEX IF NOT EXISTS idx_observations_entity ON observations(entity_id);
        CREATE INDEX IF NOT EXISTS idx_observations_source ON observations(source_id);
        CREATE TABLE IF NOT EXISTS source_lineage (
          source_id TEXT PRIMARY KEY, origin_id TEXT NOT NULL, parent_source_id TEXT, family TEXT,
          metadata_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS semantic_vectors (
          doc_id TEXT NOT NULL, model TEXT NOT NULL, dimensions INTEGER NOT NULL, vector_json TEXT NOT NULL,
          updated_at TEXT NOT NULL, PRIMARY KEY(doc_id, model)
        );
        """)
        # CPython's Windows SQLite normally ships FTS5/RTree. Keep startup
        # resilient if a custom SQLite build omits either extension. Feature
        # availability is exposed through storage_features().
        try:
            con.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(title, body, content='search_documents', content_rowid='rowid');
            CREATE TRIGGER IF NOT EXISTS search_documents_ai AFTER INSERT ON search_documents BEGIN
              INSERT INTO search_fts(rowid,title,body) VALUES (new.rowid,new.title,new.body);
            END;
            CREATE TRIGGER IF NOT EXISTS search_documents_ad AFTER DELETE ON search_documents BEGIN
              INSERT INTO search_fts(search_fts,rowid,title,body) VALUES('delete',old.rowid,old.title,old.body);
            END;
            CREATE TRIGGER IF NOT EXISTS search_documents_au AFTER UPDATE ON search_documents BEGIN
              INSERT INTO search_fts(search_fts,rowid,title,body) VALUES('delete',old.rowid,old.title,old.body);
              INSERT INTO search_fts(rowid,title,body) VALUES (new.rowid,new.title,new.body);
            END;
            INSERT INTO search_fts(search_fts) VALUES('rebuild');
            """)
        except sqlite3.OperationalError:
            pass
        try:
            con.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS observation_geo USING rtree(rowid, min_lat, max_lat, min_lng, max_lng)"
            )
        except sqlite3.OperationalError:
            pass

    @staticmethod
    def _migration_7(con: sqlite3.Connection) -> None:
        existing = {
            row[1] for row in con.execute("PRAGMA table_info(evidence)").fetchall()
        }
        additions = {
            "content_mime": "TEXT NOT NULL DEFAULT 'text/plain'",
            "capture_method": "TEXT NOT NULL DEFAULT 'manual'",
            "captured_by": "TEXT NOT NULL DEFAULT 'local-operator'",
            "source_headers_json": "TEXT NOT NULL DEFAULT '{}'",
            "hash_version": "INTEGER NOT NULL DEFAULT 1",
        }
        for name, ddl in additions.items():
            if name not in existing:
                con.execute(f"ALTER TABLE evidence ADD COLUMN {name} {ddl}")
        alert_existing = {
            row[1] for row in con.execute("PRAGMA table_info(alerts)").fetchall()
        }
        if "dedup_key" not in alert_existing:
            con.execute("ALTER TABLE alerts ADD COLUMN dedup_key TEXT")
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_rule_entity_time ON alerts(rule_id,entity_id,created_at DESC)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_dedup_time ON alerts(dedup_key,created_at DESC)"
        )

    @staticmethod
    def _migration_8(con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS geofences (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, polygon_json TEXT NOT NULL,
          min_lat REAL NOT NULL, max_lat REAL NOT NULL, min_lng REAL NOT NULL, max_lng REAL NOT NULL,
          severity TEXT NOT NULL DEFAULT 'watch', enabled INTEGER NOT NULL DEFAULT 1,
          entity_types_json TEXT NOT NULL DEFAULT '[]', cooldown_seconds INTEGER NOT NULL DEFAULT 300,
          metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_geofences_enabled ON geofences(enabled);
        CREATE INDEX IF NOT EXISTS idx_geofences_bbox ON geofences(min_lat,max_lat,min_lng,max_lng);
        """)

    @staticmethod
    def _migration_9(con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS entity_identifiers (
          identifier_type TEXT NOT NULL, identifier_value TEXT NOT NULL, entity_type TEXT NOT NULL,
          canonical_value TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0,
          source TEXT NOT NULL DEFAULT 'local', updated_at TEXT NOT NULL,
          PRIMARY KEY(identifier_type, identifier_value, entity_type)
        );
        CREATE INDEX IF NOT EXISTS idx_entity_identifier_canonical ON entity_identifiers(entity_type, canonical_value);
        """)

    @staticmethod
    def _migration_10(con: sqlite3.Connection) -> None:
        # Geofences use string public IDs, while SQLite RTree requires an
        # integer key. Index the owning geofences.rowid and backfill existing
        # rows so upgrades from schema v9 gain the same spatial index as fresh
        # installations. Custom SQLite builds without RTree remain supported.
        try:
            con.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS geofence_geo USING rtree(rowid, min_lat, max_lat, min_lng, max_lng)"
            )
            con.execute("DELETE FROM geofence_geo")
            con.execute(
                "INSERT INTO geofence_geo(rowid,min_lat,max_lat,min_lng,max_lng) "
                "SELECT rowid,min_lat,max_lat,min_lng,max_lng FROM geofences"
            )
        except sqlite3.OperationalError:
            pass

    @staticmethod
    def _migration_11(con: sqlite3.Connection) -> None:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS source_quarantine (
          source_id TEXT PRIMARY KEY, provider TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL,
          quarantine_kind TEXT NOT NULL DEFAULT 'contract', failure_count INTEGER NOT NULL DEFAULT 1,
          quarantined_at TEXT NOT NULL, until_epoch REAL NOT NULL DEFAULT 0, manual INTEGER NOT NULL DEFAULT 0,
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_source_quarantine_until ON source_quarantine(until_epoch);
        CREATE TABLE IF NOT EXISTS maintenance_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
          action TEXT NOT NULL, ok INTEGER NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_maintenance_runs_time ON maintenance_runs(id DESC);
        """)

    def schema_info(self) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            return {
                "schema_version": int(row[0]) if row else 0,
                "db_path": str(self.db_path),
            }

    def audit(
        self,
        event_type: str,
        object_type: str | None = None,
        object_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO audit_log(event_type,object_type,object_id,detail_json,created_at) VALUES(?,?,?,?,?)",
                (
                    event_type,
                    object_type,
                    object_id,
                    _json(detail or {}),
                    utc_now_iso(),
                ),
            )

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [{**dict(r), "detail": _loads(r["detail_json"], {})} for r in rows]

    def upsert_source_health(
        self, source_id: str, provider: str, **values: Any
    ) -> None:
        now = utc_now_iso()
        defaults = dict(
            state="unknown",
            enabled=1,
            record_count=0,
            consecutive_failures=0,
            cooldown_until=0.0,
            reliability=0.5,
            metadata_json="{}",
        )
        defaults.update(values)
        if "metadata" in defaults:
            defaults["metadata_json"] = _json(defaults.pop("metadata"))
        columns = ["source_id", "provider", *defaults.keys(), "updated_at"]
        params = [source_id, provider, *defaults.values(), now]
        update = ",".join(f"{c}=excluded.{c}" for c in columns[1:])
        with self._lock, self.connect() as con:
            con.execute(
                f"INSERT INTO source_health({','.join(columns)}) VALUES({','.join('?' for _ in columns)}) "
                f"ON CONFLICT(source_id) DO UPDATE SET {update}",
                params,
            )

    def list_source_health(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM source_health ORDER BY provider COLLATE NOCASE"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["enabled"] = bool(d["enabled"])
            d["metadata"] = _loads(d.pop("metadata_json", None), {})
            result.append(d)
        return result

    def quarantine_source(
        self,
        source_id: str,
        provider: str,
        reason: str,
        *,
        quarantine_kind: str = "contract",
        failure_count: int = 1,
        duration_seconds: int = 3600,
        manual: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_id = str(source_id or "").strip()[:128]
        if not source_id:
            raise ValueError("source_id_required")
        now = utc_now_iso()
        import time

        until_epoch = (
            0.0
            if manual and duration_seconds <= 0
            else time.time() + max(60, int(duration_seconds))
        )
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO source_quarantine(source_id,provider,reason,quarantine_kind,failure_count,quarantined_at,until_epoch,manual,metadata_json) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source_id) DO UPDATE SET provider=excluded.provider,reason=excluded.reason,quarantine_kind=excluded.quarantine_kind,failure_count=excluded.failure_count,quarantined_at=excluded.quarantined_at,until_epoch=excluded.until_epoch,manual=excluded.manual,metadata_json=excluded.metadata_json",
                (
                    source_id,
                    str(provider or source_id)[:160],
                    str(reason or "source_quarantined")[:1000],
                    str(quarantine_kind or "contract")[:64],
                    max(1, int(failure_count)),
                    now,
                    float(until_epoch),
                    1 if manual else 0,
                    _json(metadata or {}),
                ),
            )
        self.audit(
            "source.quarantined",
            "source",
            source_id,
            {
                "kind": quarantine_kind,
                "failure_count": failure_count,
                "until_epoch": until_epoch,
                "manual": manual,
            },
        )
        return self.get_source_quarantine(source_id) or {}

    def get_source_quarantine(self, source_id: str) -> dict[str, Any] | None:
        import time

        with self._lock, self.connect() as con:
            row = con.execute(
                "SELECT * FROM source_quarantine WHERE source_id=?", (source_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            if (
                not bool(d.get("manual"))
                and float(d.get("until_epoch") or 0) > 0
                and float(d.get("until_epoch") or 0) <= time.time()
            ):
                con.execute(
                    "DELETE FROM source_quarantine WHERE source_id=?", (source_id,)
                )
                return None
        d["manual"] = bool(d.get("manual"))
        d["metadata"] = _loads(d.pop("metadata_json", None), {})
        return d

    def list_source_quarantine(self) -> list[dict[str, Any]]:
        import time

        now = time.time()
        with self._lock, self.connect() as con:
            con.execute(
                "DELETE FROM source_quarantine WHERE manual=0 AND until_epoch>0 AND until_epoch<=?",
                (now,),
            )
            rows = con.execute(
                "SELECT * FROM source_quarantine ORDER BY quarantined_at DESC"
            ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["manual"] = bool(d.get("manual"))
            d["metadata"] = _loads(d.pop("metadata_json", None), {})
            out.append(d)
        return out

    def clear_source_quarantine(self, source_id: str) -> bool:
        with self._lock, self.connect() as con:
            cur = con.execute(
                "DELETE FROM source_quarantine WHERE source_id=?", (source_id,)
            )
            changed = cur.rowcount > 0
        if changed:
            self.audit("source.quarantine_cleared", "source", source_id, {})
        return changed

    def record_maintenance_run(
        self, action: str, ok: bool, detail: dict[str, Any]
    ) -> dict[str, Any]:
        started = str(detail.get("started_at") or utc_now_iso())
        finished = utc_now_iso()
        with self._lock, self.connect() as con:
            cur = con.execute(
                "INSERT INTO maintenance_runs(started_at,finished_at,action,ok,detail_json) VALUES(?,?,?,?,?)",
                (started, finished, str(action)[:100], 1 if ok else 0, _json(detail)),
            )
            run_id = int(cur.lastrowid)
        return {
            "id": run_id,
            "started_at": started,
            "finished_at": finished,
            "action": action,
            "ok": bool(ok),
            "detail": detail,
        }

    def list_maintenance_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM maintenance_runs ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [
            {**dict(r), "ok": bool(r["ok"]), "detail": _loads(r["detail_json"], {})}
            for r in rows
        ]

    def run_database_maintenance(
        self, *, rebuild_search: bool = False, analyze: bool = True
    ) -> dict[str, Any]:
        started = utc_now_iso()
        result = {
            "started_at": started,
            "rebuild_search": bool(rebuild_search),
            "analyze": bool(analyze),
            "actions": [],
        }
        try:
            with self._lock, self.connect() as con:
                checkpoint = con.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                result["wal_checkpoint"] = list(checkpoint) if checkpoint else []
                result["actions"].append("wal_checkpoint")
                if analyze:
                    con.execute("ANALYZE")
                    result["actions"].append("analyze")
                con.execute("PRAGMA optimize")
                result["actions"].append("pragma_optimize")
                if rebuild_search:
                    try:
                        con.execute(
                            "INSERT INTO search_fts(search_fts) VALUES('rebuild')"
                        )
                        result["actions"].append("fts5_rebuild")
                    except sqlite3.OperationalError:
                        result["fts5_rebuild"] = "unavailable"
            integrity = self.integrity_report()
            result["integrity"] = integrity
            result["ok"] = bool(integrity.get("ok"))
        except Exception as exc:
            result["ok"] = False
            result["error"] = f"maintenance_failed:{type(exc).__name__}"
        return self.record_maintenance_run(
            "database-maintenance", bool(result.get("ok")), result
        )

    def create_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        case_id, now = new_id("case"), utc_now_iso()
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO cases(id,title,description,case_type,priority,status,tags_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,'open',?,?,?)",
                (
                    case_id,
                    payload["title"],
                    payload.get("description", ""),
                    payload.get("case_type", "investigation"),
                    payload.get("priority", "normal"),
                    _json(payload.get("tags", [])),
                    now,
                    now,
                ),
            )
        self.audit("case.created", "case", case_id, {"title": payload["title"]})
        self.index_document(
            case_id,
            "case",
            payload["title"],
            payload.get("description", ""),
            metadata={
                "case_type": payload.get("case_type", "investigation"),
                "priority": payload.get("priority", "normal"),
            },
        )
        return self.get_case(case_id) or {}

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not row:
                return None
            ev = con.execute(
                "SELECT * FROM evidence WHERE case_id=? ORDER BY captured_at DESC",
                (case_id,),
            ).fetchall()
        d = dict(row)
        d["tags"] = _loads(d.pop("tags_json", None), [])
        d["evidence"] = [self._evidence_row(x) for x in ev]
        return d

    def list_cases(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM cases ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tags"] = _loads(d.pop("tags_json", None), [])
            out.append(d)
        return out

    def add_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        evidence_id, captured = new_id("evidence"), utc_now_iso()
        normalized = {
            **payload,
            "content_mime": str(payload.get("content_mime") or "text/plain")[:160],
            "capture_method": str(payload.get("capture_method") or "manual")[:80],
            "captured_by": str(payload.get("captured_by") or "local-operator")[:160],
            "source_headers": dict(payload.get("source_headers") or {}),
            "metadata": dict(payload.get("metadata") or {}),
        }
        digest = _evidence_digest_v2(normalized)
        with self._lock, self.connect() as con:
            if not con.execute(
                "SELECT 1 FROM cases WHERE id=?", (payload["case_id"],)
            ).fetchone():
                raise KeyError("case_not_found")
            con.execute(
                "INSERT INTO evidence(id,case_id,title,source_uri,content_text,sha256,metadata_json,captured_at,content_mime,capture_method,captured_by,source_headers_json,hash_version) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,2)",
                (
                    evidence_id,
                    payload["case_id"],
                    payload["title"],
                    payload.get("source_uri"),
                    payload.get("content_text"),
                    digest,
                    _json(normalized["metadata"]),
                    captured,
                    normalized["content_mime"],
                    normalized["capture_method"],
                    normalized["captured_by"],
                    _json(normalized["source_headers"]),
                ),
            )
            con.execute(
                "UPDATE cases SET updated_at=? WHERE id=?",
                (captured, payload["case_id"]),
            )
        self.audit(
            "evidence.captured",
            "evidence",
            evidence_id,
            {"case_id": payload["case_id"], "sha256": digest, "hash_version": 2},
        )
        self.index_document(
            evidence_id,
            "evidence",
            payload["title"],
            payload.get("content_text") or "",
            source_id=payload.get("source_uri"),
            metadata={
                "case_id": payload["case_id"],
                "sha256": digest,
                "content_mime": normalized["content_mime"],
                **normalized["metadata"],
            },
        )
        return {
            "id": evidence_id,
            **normalized,
            "sha256": digest,
            "hash_version": 2,
            "captured_at": captured,
        }

    @staticmethod
    def _evidence_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["metadata"] = _loads(d.pop("metadata_json", None), {})
        if "source_headers_json" in d:
            d["source_headers"] = _loads(d.pop("source_headers_json", None), {})
        return d

    def add_watch(self, payload: dict[str, Any]) -> dict[str, Any]:
        watch_id, now = new_id("watch"), utc_now_iso()
        with self._lock, self.connect() as con:
            existing = con.execute(
                "SELECT * FROM watchlists WHERE entity_type=? AND value=?",
                (payload["entity_type"], payload["value"]),
            ).fetchone()
            if existing:
                return self._watch_row(existing)
            con.execute(
                "INSERT INTO watchlists(id,entity_type,value,label,metadata_json,created_at,enabled) VALUES(?,?,?,?,?,?,1)",
                (
                    watch_id,
                    payload["entity_type"],
                    payload["value"],
                    payload.get("label"),
                    _json(payload.get("metadata", {})),
                    now,
                ),
            )
        self.audit("watchlist.added", "watchlist", watch_id, payload)
        return {"id": watch_id, **payload, "created_at": now, "enabled": True}

    @staticmethod
    def _watch_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["enabled"] = bool(d["enabled"])
        d["metadata"] = _loads(d.pop("metadata_json", None), {})
        return d

    def list_watch(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM watchlists ORDER BY created_at DESC"
            ).fetchall()
        return [self._watch_row(r) for r in rows]

    def create_geofence(self, payload: dict[str, Any]) -> dict[str, Any]:
        points = []
        for raw in payload.get("polygon") or []:
            if hasattr(raw, "model_dump"):
                raw = raw.model_dump()
            lat = raw.get("lat") if isinstance(raw, dict) else None
            lng = raw.get("lng") if isinstance(raw, dict) else None
            if lat is None or lng is None:
                continue
            points.append({"lat": float(lat), "lng": float(lng)})
        if len(points) < 3:
            raise ValueError("geofence_requires_three_points")
        lats = [p["lat"] for p in points]
        lngs = [p["lng"] for p in points]
        gid, now = new_id("geo"), utc_now_iso()
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO geofences(id,name,polygon_json,min_lat,max_lat,min_lng,max_lng,severity,enabled,entity_types_json,cooldown_seconds,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    gid,
                    payload["name"],
                    _json(points),
                    min(lats),
                    max(lats),
                    min(lngs),
                    max(lngs),
                    payload.get("severity", "watch"),
                    int(payload.get("enabled", True)),
                    _json(payload.get("entity_types", [])),
                    int(payload.get("cooldown_seconds", 300)),
                    _json(payload.get("metadata", {})),
                    now,
                    now,
                ),
            )
            try:
                row = con.execute(
                    "SELECT rowid,min_lat,max_lat,min_lng,max_lng FROM geofences WHERE id=?",
                    (gid,),
                ).fetchone()
                if row:
                    con.execute(
                        "INSERT OR REPLACE INTO geofence_geo(rowid,min_lat,max_lat,min_lng,max_lng) VALUES(?,?,?,?,?)",
                        (
                            row["rowid"],
                            row["min_lat"],
                            row["max_lat"],
                            row["min_lng"],
                            row["max_lng"],
                        ),
                    )
            except sqlite3.OperationalError:
                pass
        self.audit(
            "geofence.created",
            "geofence",
            gid,
            {"name": payload["name"], "points": len(points)},
        )
        return self.get_geofence(gid) or {"id": gid}

    @staticmethod
    def _geofence_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["enabled"] = bool(d["enabled"])
        d["polygon"] = _loads(d.pop("polygon_json", None), [])
        d["entity_types"] = _loads(d.pop("entity_types_json", None), [])
        d["metadata"] = _loads(d.pop("metadata_json", None), {})
        return d

    def get_geofence(self, geofence_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM geofences WHERE id=?", (geofence_id,)
            ).fetchone()
        return self._geofence_row(row) if row else None

    def list_geofences(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM geofences ORDER BY created_at DESC"
            ).fetchall()
        return [self._geofence_row(r) for r in rows]

    def candidate_geofences(self, lat: float, lng: float) -> list[dict[str, Any]]:
        with self.connect() as con:
            try:
                rows = con.execute(
                    "SELECT g.* FROM geofence_geo r JOIN geofences g ON g.rowid=r.rowid "
                    "WHERE g.enabled=1 AND r.min_lat<=? AND r.max_lat>=? AND r.min_lng<=? AND r.max_lng>=?",
                    (lat, lat, lng, lng),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = con.execute(
                    "SELECT * FROM geofences WHERE enabled=1 AND min_lat<=? AND max_lat>=? AND min_lng<=? AND max_lng>=?",
                    (lat, lat, lng, lng),
                ).fetchall()
        return [self._geofence_row(r) for r in rows]

    def create_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        rule_id, now = new_id("rule"), utc_now_iso()
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO rules(id,name,description,severity,enabled,conditions_json,cooldown_seconds,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    rule_id,
                    payload["name"],
                    payload.get("description", ""),
                    payload.get("severity", "watch"),
                    int(payload.get("enabled", True)),
                    _json(payload.get("conditions", {})),
                    int(payload.get("cooldown_seconds", 300)),
                    now,
                    now,
                ),
            )
        self.audit("rule.created", "rule", rule_id, {"name": payload["name"]})
        return {"id": rule_id, **payload, "created_at": now, "updated_at": now}

    def list_rules(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM rules ORDER BY created_at DESC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["enabled"] = bool(d["enabled"])
            d["conditions"] = _loads(d.pop("conditions_json", None), {})
            out.append(d)
        return out

    def mark_rule_triggered(self, rule_id: str) -> None:
        now = utc_now_iso()
        with self._lock, self.connect() as con:
            con.execute(
                "UPDATE rules SET last_triggered_at=?, updated_at=? WHERE id=?",
                (now, now, rule_id),
            )

    def create_alert(
        self, payload: dict[str, Any], *, dedup_seconds: int = 0
    ) -> dict[str, Any]:
        alert_id, now = new_id("alert"), utc_now_iso()
        dedup_key = str(payload.get("dedup_key") or "")[:500] or None
        if dedup_key and dedup_seconds > 0:
            existing = self.find_recent_alert(dedup_key, dedup_seconds)
            if existing:
                return {**existing, "deduplicated": True}
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO alerts(id,title,detail,severity,status,rule_id,incident_id,entity_id,metadata_json,created_at,updated_at,dedup_key) "
                "VALUES(?,?,?,?,'new',?,?,?,?,?,?,?)",
                (
                    alert_id,
                    payload["title"],
                    payload.get("detail", ""),
                    payload.get("severity", "watch"),
                    payload.get("rule_id"),
                    payload.get("incident_id"),
                    payload.get("entity_id"),
                    _json(payload.get("metadata", {})),
                    now,
                    now,
                    dedup_key,
                ),
            )
        self.audit(
            "alert.created",
            "alert",
            alert_id,
            {"severity": payload.get("severity", "watch"), "dedup_key": dedup_key},
        )
        return {
            "id": alert_id,
            **payload,
            "dedup_key": dedup_key,
            "status": "new",
            "created_at": now,
            "updated_at": now,
            "deduplicated": False,
        }

    def find_recent_alert(
        self, dedup_key: str, within_seconds: int
    ) -> dict[str, Any] | None:
        if not dedup_key:
            return None
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM alerts WHERE dedup_key=? AND status NOT IN ('resolved','false_positive') AND created_at >= datetime('now', ?) ORDER BY created_at DESC LIMIT 1",
                (dedup_key, f"-{max(1, int(within_seconds))} seconds"),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["metadata"] = _loads(d.pop("metadata_json", None), {})
        return d

    def list_alerts(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metadata"] = _loads(d.pop("metadata_json", None), {})
            out.append(d)
        return out

    def update_alert_status(self, alert_id: str, status: str) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._lock, self.connect() as con:
            con.execute(
                "UPDATE alerts SET status=?,updated_at=? WHERE id=?",
                (status, now, alert_id),
            )
            row = con.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            return None
        self.audit("alert.status", "alert", alert_id, {"status": status})
        d = dict(row)
        d["metadata"] = _loads(d.pop("metadata_json", None), {})
        return d

    def save_snapshot(self, namespace: str, payload: dict[str, Any]) -> dict[str, Any]:
        snapshot_id, captured = new_id("snap"), utc_now_iso()
        encoded = _json(payload)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO snapshots(id,namespace,captured_at,payload_json,payload_sha256) VALUES(?,?,?,?,?)",
                (snapshot_id, namespace, captured, encoded, digest),
            )
        return {
            "id": snapshot_id,
            "namespace": namespace,
            "captured_at": captured,
            "sha256": digest,
        }

    def recent_snapshots(self, namespace: str, limit: int = 2) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM snapshots WHERE namespace=? ORDER BY captured_at DESC LIMIT ?",
                (namespace, max(1, min(limit, 20))),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "namespace": r["namespace"],
                "captured_at": r["captured_at"],
                "payload": _loads(r["payload_json"], {}),
                "sha256": r["payload_sha256"],
            }
            for r in rows
        ]

    def list_evidence(
        self, case_id: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        with self.connect() as con:
            if case_id:
                rows = con.execute(
                    "SELECT * FROM evidence WHERE case_id=? ORDER BY captured_at DESC LIMIT ?",
                    (case_id, max(1, min(limit, 2000))),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM evidence ORDER BY captured_at DESC LIMIT ?",
                    (max(1, min(limit, 2000)),),
                ).fetchall()
        return [self._evidence_row(r) for r in rows]

    def verify_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM evidence WHERE id=?", (evidence_id,)
            ).fetchone()
        if not row:
            return None
        item = self._evidence_row(row)
        if int(item.get("hash_version") or 1) >= 2:
            expected = _evidence_digest_v2(item)
        else:
            expected = hashlib.sha256(
                (
                    (item.get("content_text") or "")
                    + "\n"
                    + (item.get("source_uri") or "")
                    + "\n"
                    + _json(item.get("metadata", {}))
                ).encode("utf-8")
            ).hexdigest()
        return {
            **item,
            "integrity_ok": expected == item.get("sha256"),
            "computed_sha256": expected,
        }

    def upsert_incident(self, payload: dict[str, Any]) -> dict[str, Any]:
        incident_id = str(payload.get("id") or new_id("incident"))
        now = utc_now_iso()
        first_seen = str(payload.get("first_seen") or now)
        last_seen = str(payload.get("last_seen") or now)
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO incidents(id,title,summary,severity,confidence,status,location_json,observation_ids_json,entity_ids_json,source_ids_json,tags_json,assessment_json,first_seen,last_seen) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title,summary=excluded.summary,severity=excluded.severity,confidence=excluded.confidence,status=excluded.status,location_json=excluded.location_json,observation_ids_json=excluded.observation_ids_json,entity_ids_json=excluded.entity_ids_json,source_ids_json=excluded.source_ids_json,tags_json=excluded.tags_json,assessment_json=excluded.assessment_json,last_seen=excluded.last_seen",
                (
                    incident_id,
                    payload.get("title") or "Untitled incident",
                    payload.get("summary") or "",
                    payload.get("severity") or "watch",
                    max(0.0, min(float(payload.get("confidence", 0.5)), 1.0)),
                    payload.get("status") or "open",
                    _json(payload.get("location"))
                    if payload.get("location") is not None
                    else None,
                    _json(payload.get("observation_ids", [])),
                    _json(payload.get("entity_ids", [])),
                    _json(payload.get("source_ids", [])),
                    _json(payload.get("tags", [])),
                    _json(payload.get("assessment", {})),
                    first_seen,
                    last_seen,
                ),
            )
        self.audit(
            "incident.upserted",
            "incident",
            incident_id,
            {
                "severity": payload.get("severity"),
                "confidence": payload.get("confidence"),
            },
        )
        self.index_document(
            incident_id,
            "incident",
            payload.get("title") or "Untitled incident",
            payload.get("summary") or "",
            metadata={
                "severity": payload.get("severity") or "watch",
                "confidence": payload.get("confidence", 0.5),
                "tags": payload.get("tags", []),
            },
        )
        return self.get_incident(incident_id) or {}

    @staticmethod
    def _incident_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["location"] = _loads(d.pop("location_json", None), None)
        d["observation_ids"] = _loads(d.pop("observation_ids_json", None), [])
        d["entity_ids"] = _loads(d.pop("entity_ids_json", None), [])
        d["source_ids"] = _loads(d.pop("source_ids_json", None), [])
        d["tags"] = _loads(d.pop("tags_json", None), [])
        d["assessment"] = _loads(d.pop("assessment_json", None), {})
        return d

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM incidents WHERE id=?", (incident_id,)
            ).fetchone()
        return self._incident_row(row) if row else None

    def list_incidents(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM incidents ORDER BY last_seen DESC LIMIT ?",
                (max(1, min(limit, 2000)),),
            ).fetchall()
        return [self._incident_row(r) for r in rows]

    def storage_stats(self) -> dict[str, Any]:
        with self.connect() as con:
            tables = [
                "source_health",
                "cases",
                "evidence",
                "watchlists",
                "rules",
                "alerts",
                "snapshots",
                "incidents",
                "audit_log",
                "entity_aliases",
                "entity_identifiers",
                "search_documents",
                "kv_settings",
                "workspaces",
                "observations",
                "source_lineage",
                "semantic_vectors",
                "geofences",
            ]
            counts = {
                table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }
            page_size = int(con.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(con.execute("PRAGMA page_count").fetchone()[0])
            freelist = int(con.execute("PRAGMA freelist_count").fetchone()[0])
        wal = Path(str(self.db_path) + "-wal")
        shm = Path(str(self.db_path) + "-shm")
        return {
            "db_path": str(self.db_path),
            "database_bytes": self.db_path.stat().st_size
            if self.db_path.exists()
            else 0,
            "wal_bytes": wal.stat().st_size if wal.exists() else 0,
            "shm_bytes": shm.stat().st_size if shm.exists() else 0,
            "logical_bytes": page_size * page_count,
            "free_bytes": page_size * freelist,
            "counts": counts,
        }

    def prune_snapshots(
        self, keep_days: int = 30, keep_per_namespace: int = 500
    ) -> dict[str, Any]:
        keep_days = max(1, min(int(keep_days), 3650))
        keep_per_namespace = max(2, min(int(keep_per_namespace), 100_000))
        before = self.storage_stats()["counts"]["snapshots"]
        with self._lock, self.connect() as con:
            con.execute(
                "DELETE FROM snapshots WHERE captured_at < datetime('now', ?)",
                (f"-{keep_days} days",),
            )
            namespaces = [
                r[0]
                for r in con.execute(
                    "SELECT DISTINCT namespace FROM snapshots"
                ).fetchall()
            ]
            for ns in namespaces:
                con.execute(
                    "DELETE FROM snapshots WHERE namespace=? AND id NOT IN (SELECT id FROM snapshots WHERE namespace=? ORDER BY captured_at DESC LIMIT ?)",
                    (ns, ns, keep_per_namespace),
                )
        after = self.storage_stats()["counts"]["snapshots"]
        self.audit(
            "storage.pruned",
            "snapshots",
            None,
            {
                "removed": before - after,
                "keep_days": keep_days,
                "keep_per_namespace": keep_per_namespace,
            },
        )
        return {
            "removed": before - after,
            "remaining": after,
            "keep_days": keep_days,
            "keep_per_namespace": keep_per_namespace,
        }

    def prune_history(
        self,
        keep_days: int = 30,
        keep_per_namespace: int = 500,
        resolved_alert_days: int = 90,
        audit_days: int = 180,
    ) -> dict[str, Any]:
        """Apply bounded local-retention policy without deleting analyst evidence/cases.

        High-frequency canonical observations, old delta snapshots, resolved
        alerts and old audit entries are disposable operational history. Cases,
        evidence, watchlists, rules, geofences, incidents and entity-resolution
        knowledge are deliberately preserved.
        """
        keep_days = max(1, min(int(keep_days), 3650))
        keep_per_namespace = max(2, min(int(keep_per_namespace), 100_000))
        resolved_alert_days = max(1, min(int(resolved_alert_days), 3650))
        audit_days = max(7, min(int(audit_days), 3650))
        before = self.storage_stats()["counts"]
        with self._lock, self.connect() as con:
            # Snapshots: age bound + per-namespace cap.
            con.execute(
                "DELETE FROM snapshots WHERE datetime(captured_at) < datetime('now', ?)",
                (f"-{keep_days} days",),
            )
            namespaces = [
                r[0]
                for r in con.execute(
                    "SELECT DISTINCT namespace FROM snapshots"
                ).fetchall()
            ]
            for ns in namespaces:
                con.execute(
                    "DELETE FROM snapshots WHERE namespace=? AND id NOT IN (SELECT id FROM snapshots WHERE namespace=? ORDER BY captured_at DESC LIMIT ?)",
                    (ns, ns, keep_per_namespace),
                )

            # Observation RTree rows must be removed before their SQLite rowids
            # disappear. FTS/search/vector derivatives are removed afterwards.
            stale_rowids = [
                r[0]
                for r in con.execute(
                    "SELECT rowid FROM observations WHERE datetime(COALESCE(observed_at,received_at,created_at)) < datetime('now', ?)",
                    (f"-{keep_days} days",),
                ).fetchall()
            ]
            if stale_rowids:
                try:
                    con.executemany(
                        "DELETE FROM observation_geo WHERE rowid=?",
                        [(rowid,) for rowid in stale_rowids],
                    )
                except sqlite3.OperationalError:
                    pass
            con.execute(
                "DELETE FROM observations WHERE datetime(COALESCE(observed_at,received_at,created_at)) < datetime('now', ?)",
                (f"-{keep_days} days",),
            )
            con.execute(
                "DELETE FROM alerts WHERE status IN ('resolved','false_positive') AND datetime(updated_at) < datetime('now', ?)",
                (f"-{resolved_alert_days} days",),
            )
            con.execute(
                "DELETE FROM audit_log WHERE datetime(created_at) < datetime('now', ?)",
                (f"-{audit_days} days",),
            )
            con.execute(
                "DELETE FROM search_documents WHERE kind='observation' AND id NOT IN (SELECT id FROM observations)"
            )
            con.execute(
                "DELETE FROM semantic_vectors WHERE doc_id NOT IN (SELECT id FROM search_documents)"
            )
            try:
                con.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except sqlite3.OperationalError:
                pass
        after = self.storage_stats()["counts"]
        removed = {
            key: max(0, int(before.get(key, 0)) - int(after.get(key, 0)))
            for key in (
                "snapshots",
                "observations",
                "alerts",
                "audit_log",
                "search_documents",
                "semantic_vectors",
            )
        }
        result = {
            "removed": removed,
            "keep_days": keep_days,
            "keep_per_namespace": keep_per_namespace,
            "resolved_alert_days": resolved_alert_days,
            "audit_days": audit_days,
            "remaining": {key: after.get(key, 0) for key in removed},
        }
        self.audit("storage.history_pruned", "database", None, result)
        return result

    def storage_features(self) -> dict[str, bool]:
        with self.connect() as con:
            tables = {
                row[0]
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                ).fetchall()
            }
        return {
            "fts5": "search_fts" in tables,
            "rtree": "observation_geo" in tables,
            "geofence_rtree": "geofence_geo" in tables,
        }

    def record_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        observation_id = str(payload.get("id") or new_id("obs"))
        source = dict(payload.get("source") or {})
        location = dict(payload.get("location") or {})
        now = utc_now_iso()
        received_at = str(payload.get("received_at") or now)
        lat = location.get("lat")
        lng = location.get("lng", location.get("lon"))
        values = (
            observation_id,
            str(payload.get("kind") or "observed"),
            payload.get("entity_id"),
            str(payload.get("event_type") or "observation")[:128],
            str(payload.get("summary") or "")[:5000],
            float(lat) if lat is not None else None,
            float(lng) if lng is not None else None,
            float(location.get("uncertainty_km"))
            if location.get("uncertainty_km") is not None
            else None,
            str(source.get("source_id") or payload.get("source_id") or "unknown")[:128],
            str(source.get("provider") or payload.get("source_provider") or "")[:160],
            str(source.get("family") or payload.get("source_family") or "")[:160]
            or None,
            source.get("uri") or payload.get("source_uri"),
            max(
                0.0,
                min(
                    float(
                        source.get(
                            "reliability", payload.get("source_reliability", 0.5)
                        )
                    ),
                    1.0,
                ),
            ),
            payload.get("observed_at"),
            received_at,
            max(0.0, min(float(payload.get("confidence", 0.5)), 1.0)),
            _json(payload.get("attributes", {})),
            _json(payload.get("provenance", [])),
            now,
        )
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO observations(id,kind,entity_id,event_type,summary,lat,lng,uncertainty_km,source_id,source_provider,source_family,source_uri,source_reliability,observed_at,received_at,confidence,attributes_json,provenance_json,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,entity_id=excluded.entity_id,event_type=excluded.event_type,summary=excluded.summary,lat=excluded.lat,lng=excluded.lng,uncertainty_km=excluded.uncertainty_km,source_id=excluded.source_id,source_provider=excluded.source_provider,source_family=excluded.source_family,source_uri=excluded.source_uri,source_reliability=excluded.source_reliability,observed_at=excluded.observed_at,received_at=excluded.received_at,confidence=excluded.confidence,attributes_json=excluded.attributes_json,provenance_json=excluded.provenance_json",
                values,
            )
            row = con.execute(
                "SELECT rowid,* FROM observations WHERE id=?", (observation_id,)
            ).fetchone()
            if row and lat is not None and lng is not None:
                try:
                    con.execute(
                        "DELETE FROM observation_geo WHERE rowid=?", (row["rowid"],)
                    )
                    con.execute(
                        "INSERT INTO observation_geo(rowid,min_lat,max_lat,min_lng,max_lng) VALUES(?,?,?,?,?)",
                        (row["rowid"], float(lat), float(lat), float(lng), float(lng)),
                    )
                except sqlite3.OperationalError:
                    pass
        result = self.get_observation(observation_id) or {}
        self.index_document(
            observation_id,
            "observation",
            result.get("event_type") or "Observation",
            result.get("summary") or "",
            entity_id=result.get("entity_id"),
            source_id=result.get("source_id"),
            metadata={
                "observed_at": result.get("observed_at"),
                "confidence": result.get("confidence"),
            },
        )
        return result

    @staticmethod
    def _observation_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d.pop("rowid", None)
        d["attributes"] = _loads(d.pop("attributes_json", None), {})
        d["provenance"] = _loads(d.pop("provenance_json", None), [])
        if d.get("lat") is not None and d.get("lng") is not None:
            d["location"] = {
                "lat": d.pop("lat"),
                "lng": d.pop("lng"),
                "uncertainty_km": d.pop("uncertainty_km", None),
            }
        else:
            d.pop("lat", None)
            d.pop("lng", None)
            d.pop("uncertainty_km", None)
            d["location"] = None
        return d

    def get_observation(self, observation_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT rowid,* FROM observations WHERE id=?", (observation_id,)
            ).fetchone()
        return self._observation_row(row) if row else None

    def list_observations(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT rowid,* FROM observations ORDER BY COALESCE(observed_at,received_at) DESC LIMIT ?",
                (max(1, min(int(limit), 5000)),),
            ).fetchall()
        return [self._observation_row(r) for r in rows]

    def observations_in_bbox(
        self, west: float, south: float, east: float, north: float, limit: int = 2000
    ) -> list[dict[str, Any]]:
        with self.connect() as con:
            try:
                rows = con.execute(
                    "SELECT o.rowid,o.* FROM observation_geo g JOIN observations o ON o.rowid=g.rowid WHERE g.max_lng>=? AND g.min_lng<=? AND g.max_lat>=? AND g.min_lat<=? ORDER BY COALESCE(o.observed_at,o.received_at) DESC LIMIT ?",
                    (west, east, south, north, max(1, min(int(limit), 10000))),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = con.execute(
                    "SELECT rowid,* FROM observations WHERE lng BETWEEN ? AND ? AND lat BETWEEN ? AND ? ORDER BY COALESCE(observed_at,received_at) DESC LIMIT ?",
                    (west, east, south, north, max(1, min(int(limit), 10000))),
                ).fetchall()
        return [self._observation_row(r) for r in rows]

    def register_source_lineage(
        self,
        source_id: str,
        *,
        origin_id: str | None = None,
        parent_source_id: str | None = None,
        family: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now_iso()
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO source_lineage(source_id,origin_id,parent_source_id,family,metadata_json,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET origin_id=excluded.origin_id,parent_source_id=excluded.parent_source_id,family=excluded.family,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at",
                (
                    source_id,
                    origin_id or source_id,
                    parent_source_id,
                    family,
                    _json(metadata or {}),
                    now,
                ),
            )

    def independent_source_count(self, source_ids: list[str]) -> dict[str, Any]:
        cleaned = sorted({str(x) for x in source_ids if x})
        if not cleaned:
            return {"source_count": 0, "independent_count": 0, "origins": []}
        placeholders = ",".join("?" for _ in cleaned)
        with self.connect() as con:
            rows = con.execute(
                f"SELECT source_id,origin_id,family FROM source_lineage WHERE source_id IN ({placeholders})",
                cleaned,
            ).fetchall()
        mapping = {
            r["source_id"]: (r["origin_id"] or r["family"] or r["source_id"])
            for r in rows
        }
        origins = sorted({mapping.get(x, x) for x in cleaned})
        return {
            "source_count": len(cleaned),
            "independent_count": len(origins),
            "origins": origins,
        }

    def save_semantic_vector(
        self, doc_id: str, model: str, vector: list[float]
    ) -> None:
        now = utc_now_iso()
        safe = [float(x) for x in vector[:4096]]
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO semantic_vectors(doc_id,model,dimensions,vector_json,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(doc_id,model) DO UPDATE SET dimensions=excluded.dimensions,vector_json=excluded.vector_json,updated_at=excluded.updated_at",
                (doc_id, model[:200], len(safe), _json(safe), now),
            )

    def semantic_vectors(self, model: str, limit: int = 10000) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT v.doc_id,v.vector_json,d.kind,d.title,d.body,d.metadata_json FROM semantic_vectors v JOIN search_documents d ON d.id=v.doc_id WHERE v.model=? LIMIT ?",
                (model, max(1, min(limit, 50000))),
            ).fetchall()
        return [
            {
                "id": r["doc_id"],
                "vector": _loads(r["vector_json"], []),
                "kind": r["kind"],
                "title": r["title"],
                "body": r["body"],
                "metadata": _loads(r["metadata_json"], {}),
            }
            for r in rows
        ]

    def create_full_snapshot(self, label: str = "manual") -> dict[str, Any]:
        snap_dir = self.db_path.parent / "intelligence-snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        stamp = utc_now_iso().replace(":", "").replace("+", "_")
        snap_id = f"snapshot-{stamp}-{hashlib.sha256(label.encode()).hexdigest()[:8]}"
        db_copy = snap_dir / f"{snap_id}.sqlite"
        manifest = snap_dir / f"{snap_id}.json"
        with self._lock:
            src = sqlite3.connect(self.db_path, timeout=10)
            dst = sqlite3.connect(db_copy)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        digest = hashlib.sha256(db_copy.read_bytes()).hexdigest()
        meta = {
            "id": snap_id,
            "label": label[:200],
            "created_at": utc_now_iso(),
            "schema_version": SCHEMA_VERSION,
            "database_sha256": digest,
            "database_file": db_copy.name,
        }
        manifest.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.audit(
            "snapshot.created",
            "database",
            snap_id,
            {"sha256": digest, "label": label[:200]},
        )
        return meta

    def list_full_snapshots(self) -> list[dict[str, Any]]:
        snap_dir = self.db_path.parent / "intelligence-snapshots"
        if not snap_dir.exists():
            return []
        out = []
        for p in sorted(snap_dir.glob("snapshot-*.json"), reverse=True):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                db = snap_dir / d["database_file"]
                d["available"] = db.exists()
                out.append(d)
            except Exception:
                continue
        return out[:100]

    def validate_full_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        if not snapshot_id.startswith("snapshot-") or any(
            x in snapshot_id for x in ("/", "\\", "..")
        ):
            return {"ok": False, "id": snapshot_id, "error": "invalid_snapshot_id"}
        snap_dir = self.db_path.parent / "intelligence-snapshots"
        manifest = snap_dir / f"{snapshot_id}.json"
        if not manifest.exists():
            return {"ok": False, "id": snapshot_id, "error": "snapshot_not_found"}
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
            source_path = snap_dir / str(meta.get("database_file") or "")
            if not source_path.exists():
                return {
                    "ok": False,
                    "id": snapshot_id,
                    "error": "snapshot_database_missing",
                }
            actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if actual != meta.get("database_sha256"):
                return {
                    "ok": False,
                    "id": snapshot_id,
                    "error": "snapshot_integrity_failed",
                    "sha256": actual,
                }
            con = sqlite3.connect(source_path, timeout=10)
            try:
                quick = [
                    str(r[0]) for r in con.execute("PRAGMA quick_check").fetchall()
                ]
                row = con.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()
                version = int(row[0]) if row else 0
            finally:
                con.close()
            if quick != ["ok"]:
                return {
                    "ok": False,
                    "id": snapshot_id,
                    "error": "snapshot_sqlite_check_failed",
                    "quick_check": quick[:20],
                }
            if version > SCHEMA_VERSION:
                return {
                    "ok": False,
                    "id": snapshot_id,
                    "error": "snapshot_schema_newer_than_application",
                    "schema_version": version,
                }
            return {
                "ok": True,
                "id": snapshot_id,
                "schema_version": version,
                "sha256": actual,
                "database_file": source_path.name,
            }
        except Exception as exc:
            return {
                "ok": False,
                "id": snapshot_id,
                "error": f"snapshot_validation_failed:{type(exc).__name__}",
            }

    def integrity_report(self) -> dict[str, Any]:
        required_tables = {
            "schema_meta",
            "cases",
            "evidence",
            "watchlists",
            "rules",
            "alerts",
            "incidents",
            "observations",
            "source_health",
            "search_documents",
            "semantic_vectors",
            "geofences",
            "entity_identifiers",
            "source_quarantine",
            "maintenance_runs",
        }
        required_virtual = {"search_fts", "observation_geo", "geofence_geo"}
        try:
            with self.connect() as con:
                quick = [
                    str(r[0]) for r in con.execute("PRAGMA quick_check").fetchall()
                ]
                row = con.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()
                version = int(row[0]) if row else 0
                names = {
                    str(r[0])
                    for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                    ).fetchall()
                }
                counts = {}
                for table in (
                    "cases",
                    "evidence",
                    "incidents",
                    "observations",
                    "alerts",
                ):
                    try:
                        counts[table] = int(
                            con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        )
                    except sqlite3.Error:
                        counts[table] = -1
            missing_tables = sorted(required_tables - names)
            # FTS5/RTree are deliberately optional in _migration_6/_migration_10:
            # custom/portable SQLite builds may omit those extensions and the
            # intelligence store has SQL fallbacks for that case. Treat their
            # absence as a degraded optional capability, not database corruption.
            missing_virtual = sorted(required_virtual - names)
            snapshots = self.list_full_snapshots()[:3]
            snapshot_checks = [
                self.validate_full_snapshot(str(item.get("id") or ""))
                for item in snapshots
            ]
            ok = (
                quick == ["ok"]
                and version == SCHEMA_VERSION
                and not missing_tables
            )
            return {
                "ok": ok,
                "schema_version": version,
                "expected_schema_version": SCHEMA_VERSION,
                "quick_check": quick[:20],
                "missing_tables": missing_tables,
                "missing_virtual_tables": missing_virtual,
                "optional_storage_degraded": bool(missing_virtual),
                "database_path": str(self.db_path),
                "database_size_bytes": self.db_path.stat().st_size
                if self.db_path.exists()
                else 0,
                "counts": counts,
                "recent_snapshot_checks": snapshot_checks,
            }
        except Exception as exc:
            return {
                "ok": False,
                "schema_version": None,
                "expected_schema_version": SCHEMA_VERSION,
                "quick_check": [],
                "missing_tables": [],
                "missing_virtual_tables": [],
                "database_path": str(self.db_path),
                "database_size_bytes": self.db_path.stat().st_size
                if self.db_path.exists()
                else 0,
                "error": f"database_integrity_check_failed:{type(exc).__name__}",
            }

    def restore_full_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        if not snapshot_id.startswith("snapshot-") or any(
            x in snapshot_id for x in ("/", "\\", "..")
        ):
            raise ValueError("invalid_snapshot_id")
        snap_dir = self.db_path.parent / "intelligence-snapshots"
        manifest = snap_dir / f"{snapshot_id}.json"
        if not manifest.exists():
            raise FileNotFoundError("snapshot_not_found")
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        source_path = snap_dir / str(meta.get("database_file") or "")
        if not source_path.exists():
            raise FileNotFoundError("snapshot_database_missing")
        actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if actual != meta.get("database_sha256"):
            raise ValueError("snapshot_integrity_failed")
        src_check = sqlite3.connect(source_path)
        try:
            row = src_check.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            snap_version = int(row[0]) if row else 0
        finally:
            src_check.close()
        if snap_version > SCHEMA_VERSION:
            raise ValueError("snapshot_schema_newer_than_application")
        safety = self.create_full_snapshot("automatic-pre-restore")
        with self._lock:
            src = sqlite3.connect(source_path, timeout=10)
            dst = sqlite3.connect(self.db_path, timeout=10)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        self._initialize()
        self.audit(
            "snapshot.restored",
            "database",
            snapshot_id,
            {"safety_snapshot": safety["id"]},
        )
        return {
            "ok": True,
            "restored": snapshot_id,
            "safety_snapshot": safety["id"],
            "schema_version": snap_version,
        }

    def export_state(self) -> dict[str, Any]:
        with self.connect() as con:
            aliases = [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM entity_aliases ORDER BY entity_type,alias_key"
                ).fetchall()
            ]
        return {
            "format": "shadowbroker-intelligence-core-backup-v2",
            "exported_at": utc_now_iso(),
            "schema_version": SCHEMA_VERSION,
            "cases": [self.get_case(x["id"]) for x in self.list_cases(10_000)],
            "watchlists": self.list_watch(),
            "geofences": self.list_geofences(),
            "rules": self.list_rules(),
            "alerts": self.list_alerts(10_000),
            "incidents": self.list_incidents(10_000),
            "entity_aliases": aliases,
            "workspaces": self.list_workspaces(),
            "runtime_preferences": self.get_setting("runtime_preferences", {}),
        }

    def import_state(self, payload: dict[str, Any]) -> dict[str, int]:
        if payload.get("format") not in {
            "shadowbroker-intelligence-core-backup-v1",
            "shadowbroker-intelligence-core-backup-v2",
        }:
            raise ValueError("unsupported_backup_format")
        counts = {
            "cases": 0,
            "evidence": 0,
            "watchlists": 0,
            "geofences": 0,
            "rules": 0,
            "alerts": 0,
            "incidents": 0,
            "aliases": 0,
            "workspaces": 0,
            "settings": 0,
        }
        # Restore intentionally creates fresh local IDs for workflow objects to
        # avoid colliding with current state; content hashes preserve evidence identity.
        for case in list(payload.get("cases") or [])[:10_000]:
            created = self.create_case(
                {
                    "title": str(case.get("title") or "Restored case")[:300],
                    "description": str(case.get("description") or "")[:20_000],
                    "case_type": str(case.get("case_type") or "investigation")[:64],
                    "priority": str(case.get("priority") or "normal")[:32],
                    "tags": list(case.get("tags") or [])[:100],
                }
            )
            counts["cases"] += 1
            for ev in list(case.get("evidence") or [])[:5000]:
                self.add_evidence(
                    {
                        "case_id": created["id"],
                        "title": str(ev.get("title") or "Restored evidence")[:300],
                        "source_uri": ev.get("source_uri"),
                        "content_text": ev.get("content_text"),
                        "metadata": ev.get("metadata") or {},
                    }
                )
                counts["evidence"] += 1
        for watch in list(payload.get("watchlists") or [])[:10_000]:
            self.add_watch(
                {
                    "entity_type": str(watch.get("entity_type") or "unknown")[:64],
                    "value": str(watch.get("value") or "")[:1000],
                    "label": watch.get("label"),
                    "metadata": watch.get("metadata") or {},
                }
            )
            counts["watchlists"] += 1
        for geofence in list(payload.get("geofences") or [])[:5000]:
            polygon = list(geofence.get("polygon") or [])[:5000]
            if len(polygon) >= 3:
                self.create_geofence(
                    {
                        "name": str(geofence.get("name") or "Restored geofence")[:200],
                        "polygon": polygon,
                        "severity": str(geofence.get("severity") or "watch"),
                        "enabled": bool(geofence.get("enabled", True)),
                        "entity_types": list(geofence.get("entity_types") or [])[:100],
                        "cooldown_seconds": int(
                            geofence.get("cooldown_seconds") or 300
                        ),
                        "metadata": geofence.get("metadata") or {},
                    }
                )
                counts["geofences"] += 1
        for rule in list(payload.get("rules") or [])[:5000]:
            self.create_rule(
                {
                    "name": str(rule.get("name") or "Restored rule")[:200],
                    "description": str(rule.get("description") or "")[:5000],
                    "severity": str(rule.get("severity") or "watch"),
                    "enabled": bool(rule.get("enabled", True)),
                    "conditions": rule.get("conditions") or {},
                    "cooldown_seconds": int(rule.get("cooldown_seconds") or 300),
                }
            )
            counts["rules"] += 1
        for alert in list(payload.get("alerts") or [])[:10_000]:
            created = self.create_alert(
                {
                    "title": str(alert.get("title") or "Restored alert")[:500],
                    "detail": str(alert.get("detail") or "")[:20_000],
                    "severity": str(alert.get("severity") or "watch")[:32],
                    "rule_id": None,
                    "incident_id": None,
                    "entity_id": alert.get("entity_id"),
                    "metadata": {
                        **(alert.get("metadata") or {}),
                        "restored_from_backup": True,
                    },
                }
            )
            status = str(alert.get("status") or "new")
            if (
                status
                in {
                    "new",
                    "acknowledged",
                    "investigating",
                    "resolved",
                    "false_positive",
                }
                and status != "new"
            ):
                self.update_alert_status(created["id"], status)
            counts["alerts"] += 1
        for incident in list(payload.get("incidents") or [])[:10_000]:
            copy = dict(incident)
            copy.pop("id", None)
            self.upsert_incident(copy)
            counts["incidents"] += 1
        for alias in list(payload.get("entity_aliases") or [])[:50_000]:
            self.upsert_alias(
                str(alias.get("entity_type") or "unknown"),
                str(alias.get("alias_key") or ""),
                str(alias.get("canonical_value") or ""),
                float(alias.get("confidence") or 1.0),
                str(alias.get("source") or "restore"),
            )
            counts["aliases"] += 1
        for workspace in list(payload.get("workspaces") or [])[:1000]:
            self.save_workspace(
                str(workspace.get("name") or "Restored workspace")[:200],
                workspace.get("layout") or {},
                is_default=False,
            )
            counts["workspaces"] += 1
        if payload.get(
            "format"
        ) == "shadowbroker-intelligence-core-backup-v2" and isinstance(
            payload.get("runtime_preferences"), dict
        ):
            self.set_setting(
                "runtime_preferences", payload.get("runtime_preferences") or {}
            )
            counts["settings"] += 1
        self.audit("backup.restored", "database", None, counts)
        return counts

    def index_document(
        self,
        doc_id: str,
        kind: str,
        title: str,
        body: str = "",
        *,
        entity_id: str | None = None,
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO search_documents(id,kind,title,body,entity_id,source_id,metadata_json,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,title=excluded.title,body=excluded.body,entity_id=excluded.entity_id,source_id=excluded.source_id,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at",
                (
                    doc_id,
                    kind[:64],
                    title[:500],
                    body[:200_000],
                    entity_id,
                    source_id,
                    _json(metadata or {}),
                    now,
                ),
            )
        return {"id": doc_id, "kind": kind, "title": title, "updated_at": now}

    @staticmethod
    def _search_tokens(value: str) -> set[str]:
        import re

        return {
            x
            for x in re.findall(r"[\w.-]{2,}", value.casefold(), flags=re.UNICODE)
            if len(x) >= 2
        }

    def list_search_documents(self, limit: int = 5000) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM search_documents ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 50000)),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metadata"] = _loads(d.pop("metadata_json", None), {})
            out.append(d)
        return out

    def search_documents(
        self, query: str, *, kinds: list[str] | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        clean = " ".join(str(query or "").strip().split())
        if not clean:
            return []
        limit = max(1, min(int(limit), 500))
        rows = []
        with self.connect() as con:
            has_fts = bool(
                con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='search_fts'"
                ).fetchone()
            )
            if has_fts:
                # Quote user tokens; never expose raw FTS query syntax from the API.
                tokens = [
                    x.replace('"', "") for x in clean.split() if x.replace('"', "")
                ][:32]
                match = " AND ".join(f'"{x}"*' for x in tokens)
                if match:
                    sql = "SELECT d.*, bm25(search_fts,4.0,1.0) AS rank FROM search_fts JOIN search_documents d ON d.rowid=search_fts.rowid WHERE search_fts MATCH ?"
                    params = [match]
                    if kinds:
                        safe_kinds = [str(x)[:64] for x in kinds[:50]]
                        sql += (
                            " AND d.kind IN (" + ",".join("?" for _ in safe_kinds) + ")"
                        )
                        params.extend(safe_kinds)
                    sql += " ORDER BY rank ASC, d.updated_at DESC LIMIT ?"
                    params.append(limit)
                    try:
                        rows = con.execute(sql, params).fetchall()
                    except sqlite3.OperationalError:
                        rows = []
            if not rows:
                like = f"%{clean.casefold()}%"
                sql = "SELECT *, 0.0 AS rank FROM search_documents WHERE (lower(title) LIKE ? OR lower(body) LIKE ?)"
                params = [like, like]
                if kinds:
                    safe_kinds = [str(x)[:64] for x in kinds[:50]]
                    sql += " AND kind IN (" + ",".join("?" for _ in safe_kinds) + ")"
                    params.extend(safe_kinds)
                sql += " ORDER BY updated_at DESC LIMIT ?"
                params.append(limit)
                rows = con.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metadata"] = _loads(d.pop("metadata_json", None), {})
            out.append(d)
        return out

    def rebuild_search_index(self) -> dict[str, int]:
        with self._lock, self.connect() as con:
            con.execute("DELETE FROM search_documents")
        counts = {"cases": 0, "evidence": 0, "incidents": 0}
        for case in self.list_cases(10_000):
            self.index_document(
                case["id"],
                "case",
                case.get("title") or "Untitled case",
                case.get("description") or "",
                metadata={
                    "case_type": case.get("case_type"),
                    "priority": case.get("priority"),
                },
            )
            counts["cases"] += 1
        for item in self.list_evidence(limit=50_000):
            self.index_document(
                item["id"],
                "evidence",
                item.get("title") or "Evidence",
                item.get("content_text") or "",
                source_id=item.get("source_uri"),
                metadata={
                    "case_id": item.get("case_id"),
                    "sha256": item.get("sha256"),
                    **(item.get("metadata") or {}),
                },
            )
            counts["evidence"] += 1
        for incident in self.list_incidents(10_000):
            self.index_document(
                incident["id"],
                "incident",
                incident.get("title") or "Untitled incident",
                incident.get("summary") or "",
                metadata={
                    "severity": incident.get("severity"),
                    "confidence": incident.get("confidence"),
                    "tags": incident.get("tags", []),
                },
            )
            counts["incidents"] += 1
        self.audit("search.reindexed", "database", None, counts)
        return counts

    def set_setting(self, key: str, value: Any) -> dict[str, Any]:
        now = utc_now_iso()
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO kv_settings(key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                (key[:160], _json(value), now),
            )
        self.audit("setting.updated", "setting", key[:160], {})
        return {"key": key[:160], "value": value, "updated_at": now}

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as con:
            row = con.execute(
                "SELECT value_json FROM kv_settings WHERE key=?", (key[:160],)
            ).fetchone()
        return _loads(row[0], default) if row else default

    def list_settings(self) -> dict[str, Any]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT key,value_json,updated_at FROM kv_settings ORDER BY key"
            ).fetchall()
        return {
            r["key"]: {
                "value": _loads(r["value_json"], None),
                "updated_at": r["updated_at"],
            }
            for r in rows
        }

    def save_workspace(
        self,
        name: str,
        layout: dict[str, Any],
        workspace_id: str | None = None,
        is_default: bool = False,
    ) -> dict[str, Any]:
        wid, now = workspace_id or new_id("workspace"), utc_now_iso()
        with self._lock, self.connect() as con:
            if is_default:
                con.execute("UPDATE workspaces SET is_default=0")
            existing = con.execute(
                "SELECT created_at FROM workspaces WHERE id=?", (wid,)
            ).fetchone()
            created = existing[0] if existing else now
            con.execute(
                "INSERT INTO workspaces(id,name,layout_json,is_default,created_at,updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name,layout_json=excluded.layout_json,is_default=excluded.is_default,updated_at=excluded.updated_at",
                (wid, name[:200], _json(layout), int(is_default), created, now),
            )
        return {
            "id": wid,
            "name": name[:200],
            "layout": layout,
            "is_default": bool(is_default),
            "created_at": created,
            "updated_at": now,
        }

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM workspaces ORDER BY is_default DESC,updated_at DESC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["layout"] = _loads(d.pop("layout_json", None), {})
            d["is_default"] = bool(d["is_default"])
            out.append(d)
        return out

    def delete_workspace(self, workspace_id: str) -> bool:
        with self._lock, self.connect() as con:
            cur = con.execute(
                "DELETE FROM workspaces WHERE id=?", (workspace_id[:128],)
            )
            return cur.rowcount > 0

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        return "".join(str(value).strip().casefold().split())[:500]

    def upsert_identifier(
        self,
        entity_type: str,
        identifier_type: str,
        identifier_value: str,
        canonical: str,
        confidence: float = 1.0,
        source: str = "local",
    ) -> None:
        ident_type = str(identifier_type).strip().casefold()[:80]
        ident_value = self._normalize_identifier(identifier_value)
        if not ident_type or not ident_value:
            return
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO entity_identifiers(identifier_type,identifier_value,entity_type,canonical_value,confidence,source,updated_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(identifier_type,identifier_value,entity_type) DO UPDATE SET canonical_value=excluded.canonical_value,confidence=excluded.confidence,source=excluded.source,updated_at=excluded.updated_at",
                (
                    ident_type,
                    ident_value,
                    entity_type[:64],
                    canonical[:500],
                    max(0.0, min(float(confidence), 1.0)),
                    source[:80],
                    utc_now_iso(),
                ),
            )

    def resolve_identifier(
        self, entity_type: str, identifiers: dict[str, str]
    ) -> dict[str, Any] | None:
        with self.connect() as con:
            for identifier_type, raw in identifiers.items():
                ident_type = str(identifier_type).strip().casefold()[:80]
                ident_value = self._normalize_identifier(raw)
                if not ident_type or not ident_value:
                    continue
                row = con.execute(
                    "SELECT * FROM entity_identifiers WHERE identifier_type=? AND identifier_value=? AND entity_type=?",
                    (ident_type, ident_value, entity_type[:64]),
                ).fetchone()
                if row:
                    return dict(row)
        return None

    def upsert_alias(
        self,
        entity_type: str,
        alias: str,
        canonical: str,
        confidence: float = 1.0,
        source: str = "local",
    ) -> None:
        key = " ".join(alias.casefold().split())
        with self._lock, self.connect() as con:
            con.execute(
                "INSERT INTO entity_aliases(alias_key,entity_type,canonical_value,confidence,source,updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(alias_key,entity_type) DO UPDATE SET canonical_value=excluded.canonical_value,confidence=excluded.confidence,source=excluded.source,updated_at=excluded.updated_at",
                (key, entity_type, canonical, float(confidence), source, utc_now_iso()),
            )

    def resolve_alias(self, entity_type: str, value: str) -> dict[str, Any] | None:
        key = " ".join(value.casefold().split())
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM entity_aliases WHERE alias_key=? AND entity_type=?",
                (key, entity_type),
            ).fetchone()
        return dict(row) if row else None
