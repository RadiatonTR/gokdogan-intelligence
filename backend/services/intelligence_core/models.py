from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class ObservationKind(StrEnum):
    OBSERVED = "observed"
    REPORTED = "reported"
    DERIVED = "derived"
    AI_ASSESSMENT = "ai_assessment"
    FORECAST = "forecast"
    UNVERIFIED = "unverified"


class SourceState(StrEnum):
    LIVE = "live"
    STALE = "stale"
    DEGRADED = "degraded"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    AUTH_REQUIRED = "auth_required"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class AlertSeverity(StrEnum):
    INFO = "info"
    WATCH = "watch"
    PRIORITY = "priority"
    FLASH = "flash"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class Location(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    uncertainty_km: float | None = Field(default=None, ge=0)
    country_code: str | None = Field(default=None, max_length=8)
    label: str | None = Field(default=None, max_length=300)


class ProvenanceStep(BaseModel):
    stage: str = Field(min_length=1, max_length=64)
    actor: str = Field(min_length=1, max_length=128)
    timestamp: str = Field(default_factory=utc_now_iso)
    detail: str | None = Field(default=None, max_length=1000)


class SourceRef(BaseModel):
    source_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=160)
    uri: str | None = Field(default=None, max_length=2000)
    license: str | None = Field(default=None, max_length=160)
    attribution: str | None = Field(default=None, max_length=500)
    observed_at: str | None = None
    received_at: str = Field(default_factory=utc_now_iso)
    reliability: float = Field(default=0.5, ge=0, le=1)


class EntityRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ent"))
    entity_type: str = Field(min_length=1, max_length=64)
    canonical_name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list)
    identifiers: dict[str, str] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    location: Location | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ObservationRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("obs"))
    kind: ObservationKind = ObservationKind.OBSERVED
    entity_id: str | None = None
    event_type: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=2000)
    location: Location | None = None
    source: SourceRef
    observed_at: str | None = None
    received_at: str = Field(default_factory=utc_now_iso)
    confidence: float = Field(default=0.5, ge=0, le=1)
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceStep] = Field(default_factory=list)


class IncidentRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("inc"))
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=5000)
    severity: AlertSeverity = AlertSeverity.WATCH
    confidence: float = Field(default=0.5, ge=0, le=1)
    location: Location | None = None
    observation_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    first_seen: str = Field(default_factory=utc_now_iso)
    last_seen: str = Field(default_factory=utc_now_iso)
    status: str = Field(default="open", max_length=32)
    tags: list[str] = Field(default_factory=list)
    assessment: dict[str, Any] = Field(default_factory=dict)


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=10000)
    case_type: str = Field(default="investigation", max_length=64)
    priority: str = Field(default="normal", max_length=32)
    tags: list[str] = Field(default_factory=list)


class EvidenceCreate(BaseModel):
    case_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    source_uri: str | None = Field(default=None, max_length=3000)
    content_text: str | None = Field(default=None, max_length=200000)
    content_mime: str = Field(default="text/plain", max_length=160)
    capture_method: str = Field(default="manual", max_length=80)
    captured_by: str = Field(default="local-operator", max_length=160)
    source_headers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WatchlistCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=500)
    label: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeofenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    polygon: list[Location] = Field(min_length=3, max_length=5000)
    severity: AlertSeverity = AlertSeverity.WATCH
    enabled: bool = True
    entity_types: list[str] = Field(default_factory=list, max_length=100)
    cooldown_seconds: int = Field(default=300, ge=0, le=604800)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=3000)
    severity: AlertSeverity = AlertSeverity.WATCH
    enabled: bool = True
    conditions: dict[str, Any] = Field(default_factory=dict)
    cooldown_seconds: int = Field(default=300, ge=0, le=604800)


class AlertCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    detail: str = Field(default="", max_length=10000)
    severity: AlertSeverity = AlertSeverity.WATCH
    rule_id: str | None = None
    incident_id: str | None = None
    entity_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
