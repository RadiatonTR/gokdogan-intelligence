"""Unified desktop intelligence-core APIs.

This router is intentionally passive/defensive. It manages local intelligence
state, source health, delta/confidence calculations, cases/evidence, watchlists,
alerts, and CTI interoperability. It does not perform active network scanning.
"""
from __future__ import annotations

from typing import Any
import asyncio
import io
import json
import zipfile

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import require_local_operator
from limiter import limiter
from services.intelligence_core import get_intelligence_core
from services.intelligence_core.stix_case import case_to_stix
from services.intelligence_core.models import (
    AlertCreate,
    AlertStatus,
    CaseCreate,
    EvidenceCreate,
    GeofenceCreate,
    ObservationRecord,
    RuleCreate,
    SourceState,
    WatchlistCreate,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence-core"])


class DeltaRequest(BaseModel):
    namespace: str = Field(min_length=1, max_length=128)
    current: dict[str, Any]
    rules: list[dict[str, Any]] = Field(default_factory=list, max_length=128)


class ConfidenceRequest(BaseModel):
    factors: dict[str, float]


class ConfidenceCalibrationRequest(BaseModel):
    samples: list[dict[str, Any]] = Field(default_factory=list, max_length=100000)
    bins: int = Field(default=10, ge=2, le=50)


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)
    model: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=50, ge=1, le=500)


class SemanticReindexRequest(BaseModel):
    model: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=5000, ge=1, le=50000)


class SnapshotCreateRequest(BaseModel):
    label: str = Field(default="manual", max_length=200)


class EntityResolveRequest(BaseModel):
    entity_type: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=500)
    candidates: list[str] = Field(default_factory=list, max_length=1000)
    identifiers: dict[str, str] = Field(default_factory=dict)


class RuleEvaluateRequest(BaseModel):
    event: dict[str, Any]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    kinds: list[str] = Field(default_factory=list, max_length=50)
    limit: int = Field(default=50, ge=1, le=500)


class RuntimePreferences(BaseModel):
    profile: str = Field(default="balanced", pattern="^(low|balanced|performance|maximum)$")
    offline_mode: bool = False
    metered_network: bool = False
    max_background_jobs: int = Field(default=4, ge=1, le=32)
    map_marker_budget: int = Field(default=25000, ge=1000, le=250000)
    history_retention_days: int = Field(default=30, ge=1, le=3650)


class WorkspacePayload(BaseModel):
    id: str | None = Field(default=None, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    layout: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class FusionRequest(BaseModel):
    observations: list[dict[str, Any]] = Field(default_factory=list, max_length=10000)
    radius_km: float = Field(default=75.0, gt=0, le=5000)
    window_minutes: int = Field(default=90, ge=1, le=10080)
    min_observations: int = Field(default=2, ge=1, le=100)
    persist: bool = True


class AdapterFetchRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class LocalSummaryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    model: str | None = Field(default=None, max_length=200)
    max_sentences: int = Field(default=5, ge=1, le=20)


class LocalModelRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    allow_metered: bool = False


class SourceQuarantineRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    duration_seconds: int = Field(default=3600, ge=0, le=604800)
    manual: bool = False


class SourceReport(BaseModel):
    source_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=160)
    ok: bool
    latency_ms: float | None = Field(default=None, ge=0)
    record_count: int = Field(default=0, ge=0)
    state: SourceState | None = None
    error: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/status")
@limiter.limit("60/minute")
async def intelligence_status(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().status()


@router.get("/diagnostics")
@limiter.limit("30/minute")
async def intelligence_diagnostics(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().diagnostics()


@router.get("/integrity")
@limiter.limit("12/minute")
async def intelligence_integrity(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await asyncio.to_thread(get_intelligence_core().store.integrity_report)


@router.get("/sources")
@limiter.limit("60/minute")
async def intelligence_sources(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"sources": get_intelligence_core().sources.snapshot()}


@router.get("/sources/quarantine")
@limiter.limit("30/minute")
async def intelligence_source_quarantine(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"quarantines": get_intelligence_core().store.list_source_quarantine()}


@router.post("/sources/{source_id}/quarantine")
@limiter.limit("20/minute")
async def intelligence_quarantine_source(source_id: str, payload: SourceQuarantineRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    core = get_intelligence_core()
    provider = next((str(x.get("provider") or source_id) for x in core.sources.snapshot() if x.get("source_id") == source_id), source_id)
    item = core.sources.quarantine(source_id, provider, payload.reason, quarantine_kind="manual", duration_seconds=payload.duration_seconds, manual=payload.manual, metadata={"operator_requested": True})
    return {"ok": True, "quarantine": item}


@router.delete("/sources/{source_id}/quarantine")
@limiter.limit("20/minute")
async def intelligence_clear_source_quarantine(source_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"ok": get_intelligence_core().sources.clear_quarantine(source_id), "source_id": source_id}


@router.get("/maintenance/report")
@limiter.limit("20/minute")
async def intelligence_maintenance_report(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await asyncio.to_thread(get_intelligence_core().maintenance_report)


@router.post("/maintenance/run")
@limiter.limit("5/minute")
async def intelligence_maintenance_run(request: Request, rebuild_search: bool = Query(default=False), analyze: bool = Query(default=True), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await asyncio.to_thread(get_intelligence_core().store.run_database_maintenance, rebuild_search=rebuild_search, analyze=analyze)


@router.post("/sources/report")
@limiter.limit("120/minute")
async def report_source_health(payload: SourceReport, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    core = get_intelligence_core()
    if payload.ok:
        core.sources.record_success(payload.source_id, payload.provider, payload.latency_ms, payload.record_count, payload.metadata)
    else:
        core.sources.record_failure(payload.source_id, payload.provider, payload.error or "source_failed", state=payload.state or SourceState.ERROR, metadata=payload.metadata)
    return {"ok": True, "source": next((x for x in core.sources.snapshot() if x["source_id"] == payload.source_id), None)}


@router.post("/delta")
@limiter.limit("60/minute")
async def intelligence_delta(payload: DeltaRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    try:
        return get_intelligence_core().compare_and_store(payload.namespace, payload.current, payload.rules)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fusion")
@limiter.limit("30/minute")
async def intelligence_fusion(payload: FusionRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().fuse(payload.observations, radius_km=payload.radius_km, window_minutes=payload.window_minutes, min_observations=payload.min_observations, persist=payload.persist)


@router.post("/confidence")
@limiter.limit("120/minute")
async def intelligence_confidence(payload: ConfidenceRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().confidence(payload.factors)


@router.post("/confidence/calibration")
@limiter.limit("10/minute")
async def intelligence_confidence_calibration(payload: ConfidenceCalibrationRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().confidence_calibration(payload.samples, payload.bins)


@router.post("/observations")
@limiter.limit("240/minute")
async def intelligence_observation_ingest(payload: ObservationRecord, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().ingest_observation(payload.model_dump(mode="json"))


@router.get("/observations")
@limiter.limit("60/minute")
async def intelligence_observations(request: Request, limit: int = Query(default=500, ge=1, le=5000), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"observations": get_intelligence_core().store.list_observations(limit)}


@router.get("/observations/bbox")
@limiter.limit("60/minute")
async def intelligence_observations_bbox(request: Request, west: float = Query(ge=-180, le=180), south: float = Query(ge=-90, le=90), east: float = Query(ge=-180, le=180), north: float = Query(ge=-90, le=90), limit: int = Query(default=2000, ge=1, le=10000), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    if west > east or south > north:
        raise HTTPException(status_code=400, detail="invalid_bbox")
    return {"observations": get_intelligence_core().store.observations_in_bbox(west, south, east, north, limit)}


@router.post("/entities/resolve")
@limiter.limit("120/minute")
async def intelligence_entity_resolve(payload: EntityResolveRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().entities.resolve(payload.entity_type, payload.value, payload.candidates, payload.identifiers)


@router.post("/entities/enrich")
@limiter.limit("30/minute")
async def intelligence_entity_enrich(payload: EntityResolveRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    try:
        return await get_intelligence_core().enrichment.resolve(payload.entity_type, payload.value, {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"entity_enrichment_failed:{type(exc).__name__}") from exc


@router.get("/cases")
@limiter.limit("60/minute")
async def list_cases(request: Request, limit: int = Query(default=100, ge=1, le=500), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"cases": get_intelligence_core().store.list_cases(limit)}


@router.post("/cases")
@limiter.limit("30/minute")
async def create_case(payload: CaseCreate, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().store.create_case(payload.model_dump(mode="json"))


@router.get("/cases/{case_id}")
@limiter.limit("60/minute")
async def get_case(case_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    case = get_intelligence_core().store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case_not_found")
    return case


@router.post("/evidence")
@limiter.limit("30/minute")
async def capture_evidence(payload: EvidenceCreate, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    try:
        return get_intelligence_core().store.add_evidence(payload.model_dump(mode="json"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="case_not_found") from exc


@router.get("/watchlists")
@limiter.limit("60/minute")
async def list_watchlists(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"watchlists": get_intelligence_core().store.list_watch()}


@router.post("/watchlists")
@limiter.limit("60/minute")
async def add_watchlist(payload: WatchlistCreate, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().store.add_watch(payload.model_dump(mode="json"))


@router.get("/geofences")
@limiter.limit("60/minute")
async def list_geofences(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"geofences": get_intelligence_core().store.list_geofences()}


@router.post("/geofences")
@limiter.limit("30/minute")
async def create_geofence(payload: GeofenceCreate, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    data = payload.model_dump(mode="json")
    data["severity"] = payload.severity.value
    try:
        return get_intelligence_core().store.create_geofence(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/rules")
@limiter.limit("60/minute")
async def list_rules(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"rules": get_intelligence_core().store.list_rules()}


@router.post("/rules")
@limiter.limit("30/minute")
async def create_rule(payload: RuleCreate, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    data = payload.model_dump(mode="json")
    data["severity"] = payload.severity.value
    return get_intelligence_core().store.create_rule(data)


@router.post("/rules/evaluate")
@limiter.limit("120/minute")
async def evaluate_rules(payload: RuleEvaluateRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().evaluate_rules(payload.event)


@router.get("/alerts")
@limiter.limit("60/minute")
async def list_alerts(request: Request, limit: int = Query(default=200, ge=1, le=1000), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"alerts": get_intelligence_core().store.list_alerts(limit)}


@router.post("/alerts")
@limiter.limit("60/minute")
async def create_alert(payload: AlertCreate, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    data = payload.model_dump(mode="json")
    data["severity"] = payload.severity.value
    return get_intelligence_core().store.create_alert(data)


@router.patch("/alerts/{alert_id}/status/{status}")
@limiter.limit("60/minute")
async def set_alert_status(alert_id: str, status: AlertStatus, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    result = get_intelligence_core().store.update_alert_status(alert_id, status.value)
    if not result:
        raise HTTPException(status_code=404, detail="alert_not_found")
    return result


@router.get("/audit")
@limiter.limit("30/minute")
async def intelligence_audit(request: Request, limit: int = Query(default=100, ge=1, le=500), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"events": get_intelligence_core().store.list_audit(limit)}


@router.post("/integrations/opencti/test")
@limiter.limit("10/minute")
async def opencti_test(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().opencti.test()


@router.post("/search")
@limiter.limit("120/minute")
async def intelligence_search(payload: SearchRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"query": payload.query, "results": get_intelligence_core().store.search_documents(payload.query, kinds=payload.kinds or None, limit=payload.limit)}


@router.get("/settings/runtime")
@limiter.limit("60/minute")
async def runtime_preferences_get(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    defaults = RuntimePreferences().model_dump(mode="json")
    stored = get_intelligence_core().store.get_setting("runtime_preferences", {}) or {}
    return {**defaults, **stored}


@router.put("/settings/runtime")
@limiter.limit("30/minute")
async def runtime_preferences_set(payload: RuntimePreferences, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    value = payload.model_dump(mode="json")
    core = get_intelligence_core()
    core.store.set_setting("runtime_preferences", value)
    core.tasks.set_max_concurrency(payload.max_background_jobs)
    return {**value, "effective_max_background_jobs": core.tasks.max_concurrency}


@router.get("/settings")
@limiter.limit("30/minute")
async def intelligence_settings(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"settings": get_intelligence_core().store.list_settings()}


@router.get("/workspaces")
@limiter.limit("60/minute")
async def intelligence_workspaces(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"workspaces": get_intelligence_core().store.list_workspaces()}


@router.post("/workspaces")
@limiter.limit("30/minute")
async def intelligence_workspace_save(payload: WorkspacePayload, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().store.save_workspace(payload.name, payload.layout, payload.id, payload.is_default)

@router.delete("/workspaces/{workspace_id}")
@limiter.limit("30/minute")
async def intelligence_workspace_delete(workspace_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    deleted = get_intelligence_core().store.delete_workspace(workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    return {"ok": True, "deleted": workspace_id}


@router.get("/incidents")
@limiter.limit("60/minute")
async def list_incidents(request: Request, limit: int = Query(default=200, ge=1, le=2000), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"incidents": get_intelligence_core().store.list_incidents(limit)}


@router.get("/incidents/{incident_id}")
@limiter.limit("60/minute")
async def get_incident(incident_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    incident = get_intelligence_core().store.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="incident_not_found")
    return incident


@router.post("/incidents")
@limiter.limit("60/minute")
async def upsert_incident(payload: dict[str, Any], request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    if not str(payload.get("title") or "").strip():
        raise HTTPException(status_code=400, detail="incident_title_required")
    return get_intelligence_core().store.upsert_incident(payload)


@router.get("/cases/{case_id}/stix")
@limiter.limit("30/minute")
async def export_case_stix(case_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    case = get_intelligence_core().store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case_not_found")
    return case_to_stix(case)


@router.post("/cases/{case_id}/opencti/push")
@limiter.limit("10/minute")
async def push_case_opencti(case_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    core = get_intelligence_core()
    case = core.store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case_not_found")
    result = await core.opencti.push_stix_bundle(case_to_stix(case))
    if result.get("ok"):
        core.store.audit("opencti.case_pushed", "case", case_id, {"status_code": result.get("status_code")})
    return result


@router.get("/evidence/{evidence_id}/verify")
@limiter.limit("60/minute")
async def verify_evidence(evidence_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    result = get_intelligence_core().store.verify_evidence(evidence_id)
    if not result:
        raise HTTPException(status_code=404, detail="evidence_not_found")
    return result


@router.get("/storage")
@limiter.limit("30/minute")
async def intelligence_storage(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().store.storage_stats()


@router.post("/storage/prune")
@limiter.limit("10/minute")
async def intelligence_storage_prune(
    request: Request,
    keep_days: int = Query(default=30, ge=1, le=3650),
    keep_per_namespace: int = Query(default=500, ge=2, le=100000),
    resolved_alert_days: int = Query(default=90, ge=1, le=3650),
    audit_days: int = Query(default=180, ge=7, le=3650),
    _: None = Depends(require_local_operator),
) -> dict[str, Any]:
    return get_intelligence_core().store.prune_history(keep_days, keep_per_namespace, resolved_alert_days, audit_days)


@router.get("/backup")
@limiter.limit("10/minute")
async def intelligence_backup(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return get_intelligence_core().store.export_state()


@router.post("/restore")
@limiter.limit("5/minute")
async def intelligence_restore(request: Request, payload: dict[str, Any] = Body(...), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    try:
        return {"ok": True, "restored": get_intelligence_core().store.import_state(payload)}
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/diagnostics/bundle")
@limiter.limit("5/minute")
async def intelligence_diagnostics_bundle(request: Request, level: str = Query(default="privacy-safe", pattern="^(privacy-safe|standard|full)$"), _: None = Depends(require_local_operator)) -> StreamingResponse:
    core = get_intelligence_core()
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", json.dumps(core.diagnostics(), ensure_ascii=False, indent=2, default=str))
        archive.writestr("storage.json", json.dumps(core.store.storage_stats(), ensure_ascii=False, indent=2, default=str))
        if level in {"standard", "full"}:
            # Standard keeps source operational health but removes provider metadata
            # that can contain operator-selected labels/URLs.
            health = core.sources.snapshot()
            if level == "standard":
                health = [{k: v for k, v in item.items() if k != "metadata"} for item in health]
            archive.writestr("source-health.json", json.dumps(health, ensure_ascii=False, indent=2, default=str))
        if level == "full":
            archive.writestr("audit-tail.json", json.dumps(core.store.list_audit(200), ensure_ascii=False, indent=2, default=str))
        archive.writestr("README.txt", f"Gokdogan Intelligence Desktop diagnostics bundle. Privacy level: {level}. API secrets, tokens, environment values, evidence content, and database files are intentionally excluded.\n")
    memory.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="shadowbroker-diagnostics-{level}.zip"'}
    return StreamingResponse(memory, media_type="application/zip", headers=headers)


@router.get("/snapshots/full")
@limiter.limit("30/minute")
async def intelligence_full_snapshots(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"snapshots": get_intelligence_core().store.list_full_snapshots()}


@router.post("/snapshots/full")
@limiter.limit("5/minute")
async def intelligence_create_full_snapshot(payload: SnapshotCreateRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await asyncio.to_thread(get_intelligence_core().store.create_full_snapshot, payload.label)


@router.post("/snapshots/full/{snapshot_id}/restore")
@limiter.limit("2/minute")
async def intelligence_restore_full_snapshot(snapshot_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(get_intelligence_core().store.restore_full_snapshot, snapshot_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/snapshots/full/{snapshot_id}/validate")
@limiter.limit("30/minute")
async def intelligence_validate_full_snapshot(snapshot_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    result = await asyncio.to_thread(get_intelligence_core().store.validate_full_snapshot, snapshot_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "snapshot_validation_failed")
    return result


@router.post("/search/semantic/reindex")
@limiter.limit("2/minute")
async def intelligence_semantic_reindex(payload: SemanticReindexRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().semantic_reindex(payload.model, payload.limit)


@router.post("/search/semantic")
@limiter.limit("30/minute")
async def intelligence_semantic_search(payload: SemanticSearchRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().semantic_search(payload.query, payload.model, payload.limit)


@router.get("/feeds/dashboard")
@limiter.limit("12/minute")
async def passive_dashboard(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.dashboard()


@router.get("/feeds/cisa-kev")
@limiter.limit("20/minute")
async def passive_cisa_kev(request: Request, limit: int = Query(default=30, ge=1, le=100), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.cisa_kev(limit)


@router.get("/feeds/who")
@limiter.limit("20/minute")
async def passive_who(request: Request, limit: int = Query(default=25, ge=1, le=100), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.who_outbreaks(limit)


@router.get("/feeds/humanitarian")
@limiter.limit("20/minute")
async def passive_humanitarian(request: Request, query: str = Query(default="", max_length=300), limit: int = Query(default=20, ge=1, le=50), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.reliefweb(query, limit)


@router.get("/feeds/radiation/safecast")
@limiter.limit("20/minute")
async def passive_safecast(request: Request, latitude: float | None = Query(default=None, ge=-90, le=90), longitude: float | None = Query(default=None, ge=-180, le=180), distance_km: float = Query(default=100, ge=1, le=1000), limit: int = Query(default=50, ge=1, le=200), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=400, detail="latitude_and_longitude_must_be_supplied_together")
    return await get_intelligence_core().passive.safecast(latitude, longitude, distance_km, limit)


@router.get("/feeds/radiation/epa")
@limiter.limit("20/minute")
async def passive_epa(request: Request, rows: int = Query(default=100, ge=1, le=250), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.epa_radnet(rows)


@router.get("/feeds/trade")
@limiter.limit("20/minute")
async def passive_trade(request: Request, reporter_code: int = Query(default=842, ge=1, le=9999), commodity: str = Query(default="2709", min_length=1, max_length=6), period: int | None = Query(default=None, ge=1900, le=2100), flow: str = Query(default="M", pattern="^[MXmx]$"), limit: int = Query(default=50, ge=1, le=100), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.comtrade(reporter_code, commodity, period, flow, limit)


@router.get("/feeds/fred/{series_id}")
@limiter.limit("20/minute")
async def passive_fred(series_id: str, request: Request, limit: int = Query(default=60, ge=1, le=500), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.fred(series_id, limit)

@router.get("/feeds/bls")
@limiter.limit("20/minute")
async def passive_bls(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.bls()


@router.get("/feeds/eia")
@limiter.limit("20/minute")
async def passive_eia(request: Request, length: int = Query(default=10, ge=1, le=100), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.eia(length)


@router.get("/feeds/treasury")
@limiter.limit("20/minute")
async def passive_treasury(request: Request, days: int = Query(default=14, ge=1, le=365), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.treasury(days)


@router.get("/feeds/usaspending")
@limiter.limit("20/minute")
async def passive_usaspending(request: Request, days: int = Query(default=30, ge=1, le=365), limit: int = Query(default=20, ge=1, le=100), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.usaspending(days, limit)


@router.get("/feeds/gscpi")
@limiter.limit("20/minute")
async def passive_gscpi(request: Request, months: int = Query(default=24, ge=1, le=240), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().passive.gscpi(months)


@router.get("/adapters")
@limiter.limit("60/minute")
async def intelligence_adapters(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"adapters": get_intelligence_core().adapters.list()}


@router.post("/adapters/{adapter_id}/fetch")
@limiter.limit("30/minute")
async def intelligence_adapter_fetch(adapter_id: str, payload: AdapterFetchRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    if len(payload.params) > 32:
        raise HTTPException(status_code=400, detail="too_many_adapter_parameters")
    adapter = get_intelligence_core().adapters.get(adapter_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="adapter_not_found")
    core = get_intelligence_core()
    source_id = f"adapter:{adapter_id}"
    provider = adapter.metadata.name
    try:
        raw = await core.sources.call(source_id, provider, lambda: adapter.fetch(**payload.params), record_success=False)
        normalized = adapter.normalize(raw)
        raw_nonempty = raw not in (None, [], {}, "")
        if raw_nonempty and not normalized:
            current = next((x for x in core.sources.snapshot() if x.get("source_id") == source_id), {})
            failures = int(current.get("consecutive_failures") or 0) + 1
            core.sources.record_failure(source_id, provider, "adapter_normalization_contract", metadata={"adapter_id": adapter_id, "failure_kind": "normalization"})
            if failures >= 3:
                core.sources.quarantine(source_id, provider, "adapter_normalization_contract", quarantine_kind="schema-drift", failure_count=failures, duration_seconds=3600, metadata={"adapter_id": adapter_id})
            raise HTTPException(status_code=502, detail="adapter_normalization_contract_failed")
        core.sources.record_success(source_id, provider, record_count=len(normalized), metadata={"adapter_id": adapter_id, "normalized": True})
        return {"adapter": adapter_id, "data": raw, "normalized_count": len(normalized), "quarantined": False}
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_adapter_parameters:{exc}") from exc
    except HTTPException:
        raise
    except RuntimeError as exc:
        detail = str(exc)
        if detail.startswith("source_quarantined:"):
            raise HTTPException(status_code=423, detail=detail) from exc
        raise HTTPException(status_code=502, detail=f"adapter_fetch_failed:{type(exc).__name__}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"adapter_fetch_failed:{type(exc).__name__}") from exc


@router.get("/tasks")
@limiter.limit("60/minute")
async def intelligence_tasks(request: Request, limit: int = Query(default=100, ge=1, le=200), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    core = get_intelligence_core()
    return {"status": core.tasks.status(), "jobs": core.tasks.list(limit)}


@router.get("/tasks/{job_id}")
@limiter.limit("120/minute")
async def intelligence_task(job_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    result = get_intelligence_core().tasks.get(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="task_not_found")
    return result


@router.post("/tasks/passive-dashboard")
@limiter.limit("12/minute")
async def intelligence_task_passive_dashboard(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    core = get_intelligence_core()
    return core.tasks.submit("passive-dashboard", core.passive.dashboard)


@router.post("/tasks/storage-prune")
@limiter.limit("10/minute")
async def intelligence_task_storage_prune(request: Request, keep_days: int = Query(default=30, ge=1, le=3650), keep_per_namespace: int = Query(default=500, ge=2, le=100000), _: None = Depends(require_local_operator)) -> dict[str, Any]:
    core = get_intelligence_core()
    async def run_prune() -> dict[str, Any]:
        return await asyncio.to_thread(core.store.prune_history, keep_days, keep_per_namespace)
    return core.tasks.submit("storage-prune", run_prune)


@router.delete("/tasks/{job_id}")
@limiter.limit("30/minute")
async def intelligence_task_cancel(job_id: str, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    if not get_intelligence_core().tasks.cancel(job_id):
        raise HTTPException(status_code=404, detail="task_not_running")
    return {"ok": True, "job_id": job_id}


@router.get("/local-ai/status")
@limiter.limit("30/minute")
async def intelligence_local_ai_status(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().local_ai.status()


@router.post("/local-ai/summarize")
@limiter.limit("30/minute")
async def intelligence_local_ai_summary(payload: LocalSummaryRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return await get_intelligence_core().local_ai.summarize(payload.text, payload.model, payload.max_sentences)


@router.post("/local-ai/models/pull")
@limiter.limit("4/hour")
async def intelligence_local_ai_model_pull(payload: LocalModelRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    core = get_intelligence_core()
    prefs = core.store.get_setting("runtime_preferences", {}) or {}
    if bool(prefs.get("offline_mode")):
        raise HTTPException(status_code=409, detail="offline_mode_blocks_model_download")
    if bool(prefs.get("metered_network")) and not payload.allow_metered:
        raise HTTPException(status_code=409, detail="metered_network_requires_explicit_model_download_override")
    try:
        result = await core.local_ai.pull_model(payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    core.store.audit("local_ai.model_pulled", "local_ai_model", payload.model, {"provider": "ollama-local"})
    return result


@router.delete("/local-ai/models")
@limiter.limit("20/minute")
async def intelligence_local_ai_model_delete(payload: LocalModelRequest, request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    core = get_intelligence_core()
    try:
        result = await core.local_ai.delete_model(payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    core.store.audit("local_ai.model_deleted", "local_ai_model", payload.model, {"provider": "ollama-local"})
    return result


@router.post("/search/reindex")
@limiter.limit("5/minute")
async def intelligence_search_reindex(request: Request, _: None = Depends(require_local_operator)) -> dict[str, Any]:
    return {"ok": True, "indexed": await asyncio.to_thread(get_intelligence_core().store.rebuild_search_index)}
