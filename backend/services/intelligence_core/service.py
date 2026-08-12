from __future__ import annotations

import threading
from typing import Any

from .adapters import AdapterMetadata, AdapterRegistry, CallableAdapter
from .confidence import evaluate_calibration, score_confidence
from .delta import MetricRule, compare_snapshots
from .diagnostics import diagnostics_snapshot
from .entity_resolution import EntityResolver, normalize_text
from .entity_enrichment import EntityEnrichmentService
from .fusion import fuse_observations
from .local_ai import LocalAIService
from .legacy_bridge import ingest_legacy_layer as bridge_legacy_layer
from .opencti import OpenCTIConnector
from .passive_sources import PassiveSourceHub
from .rules import rule_matches
from .source_health import SourceHealthRegistry, SourcePolicy
from .storage import IntelligenceStore
from .task_queue import IntelligenceTaskQueue


def _point_in_polygon(lat: float, lng: float, polygon: list[dict[str, Any]]) -> bool:
    """Ray-casting containment for local alert geofences. Coordinates are WGS84 degrees."""
    pts = [
        (float(p.get("lat")), float(p.get("lng")))
        for p in polygon
        if isinstance(p, dict) and p.get("lat") is not None and p.get("lng") is not None
    ]
    if len(pts) < 3:
        return False
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        yi, xi = pts[i]
        yj, xj = pts[j]
        crosses = ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi
        )
        if crosses:
            inside = not inside
        j = i
    return inside


class IntelligenceCore:
    def __init__(self) -> None:
        self.store = IntelligenceStore()
        self.sources = SourceHealthRegistry(self.store)
        self.entities = EntityResolver(self.store)
        self.enrichment = EntityEnrichmentService(self.sources)
        self.opencti = OpenCTIConnector()
        self.adapters = AdapterRegistry()
        runtime_prefs = self.store.get_setting("runtime_preferences", {}) or {}
        self.tasks = IntelligenceTaskQueue(
            max_concurrency=int(runtime_prefs.get("max_background_jobs", 4) or 4)
        )
        self.local_ai = LocalAIService()
        self._register_builtin_sources()
        self.passive = PassiveSourceHub(self.sources)
        self._register_passive_adapters()

    def _register_builtin_sources(self) -> None:
        for source_id, provider, reliability, stale in [
            ("opensky", "OpenSky", 0.88, 90),
            ("ais", "AIS", 0.82, 120),
            ("gdelt", "GDELT", 0.72, 900),
            ("nasa_firms", "NASA FIRMS", 0.92, 1800),
            ("sentinel", "Copernicus Sentinel", 0.95, 86400),
            ("opensanctions", "OpenSanctions", 0.90, 86400),
            ("wikidata", "Wikidata", 0.80, 86400),
            ("entity_enrichment", "Entity Enrichment", 0.84, 86400),
            ("cisa_kev", "CISA KEV", 0.98, 86400),
            ("reliefweb", "ReliefWeb", 0.90, 3600),
        ]:
            self.sources.register(
                source_id,
                provider,
                SourcePolicy(reliability=reliability, stale_after_seconds=stale),
                {"owner": "intelligence-core", "network_io": False},
            )

    def _register_passive_adapters(self) -> None:
        specs = [
            (
                "cisa-kev",
                "CISA Known Exploited Vulnerabilities",
                "cyber",
                "CISA",
                "Public domain / US Government",
                self.passive.cisa_kev,
                (),
                ("vulnerability", "kev"),
            ),
            (
                "who-outbreaks",
                "WHO Disease Outbreak News",
                "health",
                "World Health Organization",
                "WHO terms apply",
                self.passive.who_outbreaks,
                (),
                ("health", "outbreak"),
            ),
            (
                "humanitarian",
                "Humanitarian Reports",
                "emergency",
                "ReliefWeb / HDX",
                "Provider terms apply",
                self.passive.reliefweb,
                ("RELIEFWEB_APPNAME",),
                ("disaster", "humanitarian"),
            ),
            (
                "safecast",
                "Safecast Radiation",
                "radiation",
                "Safecast",
                "CC0 where supplied by Safecast",
                self.passive.safecast,
                (),
                ("radiation", "sensor"),
            ),
            (
                "epa-radnet",
                "EPA RadNet",
                "radiation",
                "US EPA",
                "Public US Government data",
                self.passive.epa_radnet,
                (),
                ("radiation", "sensor"),
            ),
            (
                "un-comtrade",
                "UN Comtrade",
                "economic",
                "United Nations",
                "UN Comtrade terms apply",
                self.passive.comtrade,
                (),
                ("trade", "supply-chain"),
            ),
            (
                "fred",
                "FRED",
                "economic",
                "Federal Reserve Bank of St. Louis",
                "FRED terms apply",
                self.passive.fred,
                ("FRED_API_KEY",),
                ("macro", "economic"),
            ),
            (
                "bls",
                "BLS Public Data",
                "economic",
                "US Bureau of Labor Statistics",
                "Public US Government data",
                self.passive.bls,
                ("BLS_API_KEY",),
                ("labor", "economic"),
            ),
            (
                "eia",
                "EIA Open Data",
                "energy",
                "US Energy Information Administration",
                "Public US Government data",
                self.passive.eia,
                ("EIA_API_KEY",),
                ("energy", "economic"),
            ),
            (
                "treasury",
                "US Treasury Fiscal Data",
                "economic",
                "US Treasury",
                "Public US Government data",
                self.passive.treasury,
                (),
                ("treasury", "economic"),
            ),
            (
                "usaspending",
                "USAspending",
                "economic",
                "USAspending.gov",
                "Public US Government data",
                self.passive.usaspending,
                (),
                ("spending", "economic"),
            ),
            (
                "gscpi",
                "Global Supply Chain Pressure Index",
                "supply-chain",
                "Federal Reserve Bank of New York",
                "Provider terms apply",
                self.passive.gscpi,
                (),
                ("supply-chain", "economic"),
            ),
        ]
        for (
            adapter_id,
            name,
            category,
            attribution,
            license_name,
            fetcher,
            config_keys,
            tags,
        ) in specs:
            self.adapters.register(
                CallableAdapter(
                    AdapterMetadata(
                        id=adapter_id,
                        name=name,
                        category=category,
                        attribution=attribution,
                        license=license_name,
                        config_keys=tuple(config_keys),
                        tags=tuple(tags),
                        active_collection=False,
                        permissions=("network:public-data",),
                    ),
                    fetcher,
                )
            )

    def status(self) -> dict[str, Any]:
        health = self.sources.snapshot()
        counts = {
            key: sum(1 for x in health if x.get("state") == key)
            for key in (
                "live",
                "stale",
                "degraded",
                "error",
                "rate_limited",
                "auth_required",
                "disabled",
                "unknown",
            )
        }
        return {
            "ok": True,
            "schema": self.store.schema_info(),
            "sources": {"total": len(health), "states": counts},
            "storage_features": self.store.storage_features(),
            "features": [
                "canonical-model",
                "sqlite-wal",
                "migrations",
                "source-health",
                "circuit-breaker",
                "delta",
                "confidence",
                "provenance",
                "entity-resolution",
                "cases",
                "evidence-hashing",
                "watchlists",
                "rules",
                "alerts",
                "audit-log",
                "opencti-probe",
                "passive-public-feeds",
                "fusion",
                "incident-workflow",
                "entity-enrichment",
                "backup-restore",
                "diagnostics-bundle",
                "adapter-sdk",
                "controlled-task-queue",
                "local-ai",
                "opencti-stix-push",
                "fts5-search",
                "rtree-spatial-index",
                "observation-ingest",
                "source-lineage",
                "per-target-alert-dedup",
                "geofence-alerts",
                "full-db-snapshots",
                "evidence-v2",
                "local-vector-search",
            ],
        }

    def compare_and_store(
        self,
        namespace: str,
        current: dict[str, Any],
        rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        prior = self.store.recent_snapshots(namespace, 1)
        parsed = [MetricRule(**r) for r in (rules or [])]
        result = compare_snapshots(
            current, prior[0]["payload"] if prior else None, parsed
        )
        snap = self.store.save_snapshot(namespace, current)
        return {"snapshot": snap, "delta": result}

    def confidence(self, factors: dict[str, Any]) -> dict[str, Any]:
        return score_confidence(factors)

    def confidence_calibration(
        self, samples: list[dict[str, Any]], bins: int = 10
    ) -> dict[str, Any]:
        return evaluate_calibration(samples, bins)

    def diagnostics(self) -> dict[str, Any]:
        return diagnostics_snapshot(self.store)

    def maintenance_report(self) -> dict[str, Any]:
        integrity = self.store.integrity_report()
        health = self.sources.snapshot()
        quarantines = self.store.list_source_quarantine()
        storage = self.store.storage_stats()
        counts: dict[str, int] = {}
        for item in health:
            state = str(item.get("state") or "unknown")
            counts[state] = counts.get(state, 0) + 1
        score = 100
        recommendations: list[dict[str, str]] = []
        if not integrity.get("ok"):
            score -= 45
            recommendations.append(
                {
                    "severity": "critical",
                    "action": "database_repair",
                    "detail": "Intelligence database integrity/schema check failed.",
                }
            )
        if counts.get("error", 0):
            score -= min(20, counts["error"] * 2)
            recommendations.append(
                {
                    "severity": "high",
                    "action": "review_sources",
                    "detail": f"{counts['error']} source(s) currently report errors.",
                }
            )
        if counts.get("stale", 0) or counts.get("degraded", 0):
            score -= min(15, counts.get("stale", 0) + counts.get("degraded", 0))
            recommendations.append(
                {
                    "severity": "medium",
                    "action": "review_freshness",
                    "detail": "One or more data sources are stale/degraded.",
                }
            )
        if quarantines:
            score -= min(15, len(quarantines) * 3)
            recommendations.append(
                {
                    "severity": "medium",
                    "action": "review_quarantine",
                    "detail": f"{len(quarantines)} source(s) are quarantined.",
                }
            )
        snapshots = self.store.list_full_snapshots()
        if not snapshots:
            score -= 5
            recommendations.append(
                {
                    "severity": "low",
                    "action": "create_snapshot",
                    "detail": "No full analyst-data recovery snapshot exists yet.",
                }
            )
        return {
            "ok": bool(integrity.get("ok")),
            "health_score": max(0, score),
            "integrity": integrity,
            "source_states": counts,
            "quarantines": quarantines,
            "storage": storage,
            "recent_maintenance": self.store.list_maintenance_runs(10),
            "recommendations": recommendations,
        }

    def fuse(
        self,
        observations: list[dict[str, Any]],
        *,
        radius_km: float = 75.0,
        window_minutes: int = 90,
        min_observations: int = 2,
        persist: bool = True,
    ) -> dict[str, Any]:
        candidates = fuse_observations(
            observations,
            radius_km=radius_km,
            window_minutes=window_minutes,
            min_observations=min_observations,
        )
        incidents = (
            [self.store.upsert_incident(item) for item in candidates]
            if persist
            else candidates
        )
        return {"count": len(incidents), "incidents": incidents}

    def evaluate_rules(self, event: dict[str, Any]) -> dict[str, Any]:
        triggered: list[dict[str, Any]] = []
        entity_key = str(
            event.get("entity_id")
            or event.get("correlation_key")
            or event.get("id")
            or "global"
        )[:200]
        incident_key = str(event.get("incident_id") or "")[:128]
        for rule in self.store.list_rules():
            if not rule.get("enabled") or not rule_matches(rule, event):
                continue
            cooldown = int(rule.get("cooldown_seconds") or 0)
            dedup_key = f"rule:{rule.get('id')}:{entity_key}:{incident_key}"
            alert = self.store.create_alert(
                {
                    "title": rule.get("name") or "Intelligence rule triggered",
                    "detail": rule.get("description")
                    or "Rule conditions matched a canonical intelligence event.",
                    "severity": rule.get("severity") or "watch",
                    "rule_id": rule.get("id"),
                    "incident_id": event.get("incident_id"),
                    "entity_id": event.get("entity_id"),
                    "dedup_key": dedup_key,
                    "metadata": {"event": event},
                },
                dedup_seconds=cooldown,
            )
            if alert.get("deduplicated"):
                continue
            self.store.mark_rule_triggered(str(rule["id"]))
            triggered.append(alert)
        return {"matched": len(triggered), "alerts": triggered}

    def ingest_legacy_layer(
        self, layer: str, items: list[Any], *, max_rule_items: int = 250
    ) -> dict[str, int]:
        return bridge_legacy_layer(self, layer, items, max_rule_items=max_rule_items)

    def ingest_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = dict(payload.get("source") or {})
        source_id = str(
            source.get("source_id") or payload.get("source_id") or "unknown"
        )
        source_family = (
            str(source.get("family") or payload.get("source_family") or "") or None
        )
        source_origin = str(
            source.get("origin_id")
            or payload.get("source_origin")
            or source_family
            or source_id
        )
        self.store.register_source_lineage(
            source_id, origin_id=source_origin, family=source_family
        )
        observation = self.store.record_observation(payload)
        rule_result = self.evaluate_rules(observation)

        watch_matches: list[dict[str, Any]] = []
        observed_value = normalize_text(
            str(
                payload.get("entity_value")
                or payload.get("entity_name")
                or payload.get("entity_id")
                or ""
            )
        )
        observed_type = str(payload.get("entity_type") or "").casefold()
        if observed_value:
            for watch in self.store.list_watch():
                if not watch.get("enabled"):
                    continue
                if (
                    observed_type
                    and str(watch.get("entity_type") or "").casefold() != observed_type
                ):
                    continue
                if normalize_text(str(watch.get("value") or "")) != observed_value:
                    continue
                dedup_key = f"watch:{watch.get('id')}:{observation.get('id')}"
                alert = self.store.create_alert(
                    {
                        "title": watch.get("label")
                        or f"Watchlist match: {watch.get('value')}",
                        "detail": observation.get("summary")
                        or "Watchlisted entity observed.",
                        "severity": str(
                            (watch.get("metadata") or {}).get("severity") or "watch"
                        ),
                        "entity_id": observation.get("entity_id"),
                        "dedup_key": dedup_key,
                        "metadata": {
                            "watchlist_id": watch.get("id"),
                            "observation_id": observation.get("id"),
                        },
                    },
                    dedup_seconds=300,
                )
                if not alert.get("deduplicated"):
                    watch_matches.append(alert)
        geofence_alerts: list[dict[str, Any]] = []
        location = observation.get("location") or {}
        lat, lng = location.get("lat"), location.get("lng")
        if lat is not None and lng is not None:
            for fence in self.store.candidate_geofences(float(lat), float(lng)):
                allowed_types = {
                    str(x).casefold()
                    for x in (fence.get("entity_types") or [])
                    if str(x).strip()
                }
                if (
                    allowed_types
                    and observed_type
                    and observed_type not in allowed_types
                ):
                    continue
                if not _point_in_polygon(
                    float(lat), float(lng), fence.get("polygon") or []
                ):
                    continue
                dedup_key = f"geofence:{fence.get('id')}:{str(observation.get('entity_id') or observed_value or observation.get('event_type') or 'point')[:200]}"
                alert = self.store.create_alert(
                    {
                        "title": f"Geofence match: {fence.get('name')}",
                        "detail": observation.get("summary")
                        or "An observation entered a monitored geofence.",
                        "severity": fence.get("severity") or "watch",
                        "entity_id": observation.get("entity_id"),
                        "dedup_key": dedup_key,
                        "metadata": {
                            "geofence_id": fence.get("id"),
                            "observation_id": observation.get("id"),
                            "location": location,
                        },
                    },
                    dedup_seconds=int(fence.get("cooldown_seconds") or 0),
                )
                if not alert.get("deduplicated"):
                    geofence_alerts.append(alert)
        return {
            "observation": observation,
            "rule_alerts": rule_result["alerts"],
            "watch_alerts": watch_matches,
            "geofence_alerts": geofence_alerts,
        }

    async def semantic_reindex(
        self, model: str | None = None, limit: int = 5000
    ) -> dict[str, Any]:
        docs = self.store.list_search_documents(limit)
        chosen_model = model or self.local_ai.HASHED_EMBED_MODEL
        indexed = 0
        provider = "deterministic-local"
        for doc in docs:
            text = f"{doc.get('title') or ''}\n{doc.get('body') or ''}"[:100_000]
            result = await self.local_ai.embed(text, model if model else None)
            vector = result.get("vector") or []
            actual_model = str(result.get("model") or chosen_model)
            provider = str(result.get("provider") or provider)
            if vector:
                self.store.save_semantic_vector(str(doc["id"]), actual_model, vector)
                indexed += 1
                chosen_model = actual_model
        return {"indexed": indexed, "model": chosen_model, "provider": provider}

    async def semantic_search(
        self, query: str, model: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        embedded = await self.local_ai.embed(query, model if model else None)
        chosen_model = str(embedded.get("model") or self.local_ai.HASHED_EMBED_MODEL)
        vector = [float(x) for x in (embedded.get("vector") or [])]
        rows = self.store.semantic_vectors(chosen_model, 50_000)
        semantic_scores: dict[str, float] = {}
        vector_engine = "python"

        # NumPy is already part of the packaged backend runtime. Use a batched
        # matrix path when all stored vectors have the same dimensions; this
        # keeps local semantic search responsive as the analyst index grows.
        if vector and rows:
            try:
                import numpy as np

                compatible = [
                    row for row in rows if len(row.get("vector") or []) == len(vector)
                ]
                if compatible:
                    matrix = np.asarray(
                        [row["vector"] for row in compatible], dtype=np.float32
                    )
                    query_vec = np.asarray(vector, dtype=np.float32)
                    qnorm = float(np.linalg.norm(query_vec))
                    norms = np.linalg.norm(matrix, axis=1)
                    if qnorm > 0:
                        raw = (matrix @ query_vec) / np.maximum(norms * qnorm, 1e-12)
                        for row, score in zip(compatible, raw.tolist()):
                            if score > 0:
                                semantic_scores[str(row["id"])] = max(
                                    -1.0, min(1.0, float(score))
                                )
                        vector_engine = "numpy-batched"
            except Exception:
                semantic_scores = {}

        if not semantic_scores:
            for row in rows:
                score = self.local_ai.cosine_similarity(vector, row.get("vector") or [])
                if score > 0:
                    semantic_scores[str(row["id"])] = score

        # Hybrid local ranking combines semantic similarity with FTS5 lexical
        # rank. This improves identifiers/names while retaining concept search.
        lexical = self.store.search_documents(query, limit=max(20, min(limit * 4, 500)))
        lexical_boost: dict[str, float] = {}
        for idx, row in enumerate(lexical):
            lexical_boost[str(row.get("id"))] = 1.0 / (1.0 + idx)

        row_by_id = {str(row["id"]): row for row in rows}
        candidates = set(semantic_scores) | set(lexical_boost)
        scored: list[dict[str, Any]] = []
        for doc_id in candidates:
            row = row_by_id.get(doc_id)
            if row is None:
                # A lexical result may not yet have a vector if reindexing is
                # incomplete. Preserve it rather than hiding an exact match.
                row = next(
                    (item for item in lexical if str(item.get("id")) == doc_id), None
                )
            if row is None:
                continue
            semantic = max(0.0, semantic_scores.get(doc_id, 0.0))
            lexical_score = lexical_boost.get(doc_id, 0.0)
            hybrid = (0.78 * semantic) + (0.22 * lexical_score)
            if hybrid <= 0:
                continue
            item = {k: v for k, v in row.items() if k != "vector"}
            item["similarity"] = round(semantic, 6)
            item["lexical_score"] = round(lexical_score, 6)
            item["hybrid_score"] = round(hybrid, 6)
            scored.append(item)
        scored.sort(key=lambda x: (x["hybrid_score"], x["similarity"]), reverse=True)
        cap = max(1, min(limit, 500))
        return {
            "query": query,
            "model": chosen_model,
            "provider": embedded.get("provider"),
            "vector_engine": vector_engine,
            "ranking": "hybrid-local-v1",
            "count": min(len(scored), cap),
            "results": scored[:cap],
        }


_lock = threading.Lock()
_instance: IntelligenceCore | None = None


def get_intelligence_core() -> IntelligenceCore:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = IntelligenceCore()
    return _instance
