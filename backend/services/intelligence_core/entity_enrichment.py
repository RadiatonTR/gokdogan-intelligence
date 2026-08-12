from __future__ import annotations

import asyncio
import time
from typing import Any

from .source_health import SourceHealthRegistry


class EntityEnrichmentService:
    """Bridge the existing OSIRIS-derived resolver into Intelligence Core.

    The underlying resolver performs passive lookups only (Wikidata,
    OpenSanctions, RIPE/ip-api and current local telemetry). Active scanning is
    deliberately outside this service.
    """

    def __init__(self, sources: SourceHealthRegistry) -> None:
        self.sources = sources

    async def resolve(self, entity_type: str, value: str, properties: dict[str, Any] | None = None) -> dict[str, Any]:
        from services.osint_intel.resolve import resolve_entity

        started = time.perf_counter()
        try:
            result = await asyncio.to_thread(resolve_entity, entity_type, value, properties or {})
            latency = (time.perf_counter() - started) * 1000
            nodes = list(result.get("nodes") or []) if isinstance(result, dict) else []
            self.sources.record_success("entity_enrichment", "Entity Enrichment", latency_ms=latency, record_count=len(nodes), metadata={"entity_type": entity_type})
            return {"entity_type": entity_type, "value": value, **(result or {})}
        except Exception as exc:
            self.sources.record_failure("entity_enrichment", "Entity Enrichment", str(exc))
            raise
