from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from .models import SourceState, utc_now_iso
from .storage import IntelligenceStore

T = TypeVar("T")


@dataclass
class SourcePolicy:
    max_failures: int = 2
    cooldown_seconds: int = 300
    stale_after_seconds: int = 600
    reliability: float = 0.5


@dataclass
class SourceRuntime:
    source_id: str
    provider: str
    policy: SourcePolicy = field(default_factory=SourcePolicy)
    failures: int = 0
    cooldown_until: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def on_cooldown(self) -> bool:
        return time.time() < self.cooldown_until


class SourceHealthRegistry:
    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store
        self._sources: dict[str, SourceRuntime] = {}

    def register(self, source_id: str, provider: str, policy: SourcePolicy | None = None, metadata: dict[str, Any] | None = None) -> SourceRuntime:
        runtime = self._sources.get(source_id) or SourceRuntime(source_id, provider, policy or SourcePolicy())
        runtime.provider = provider
        if policy is not None:
            runtime.policy = policy
        if metadata:
            runtime.metadata.update(metadata)
        self._sources[source_id] = runtime
        self.store.upsert_source_health(source_id, provider, reliability=runtime.policy.reliability, metadata=runtime.metadata)
        return runtime

    def record_success(self, source_id: str, provider: str, latency_ms: float | None = None, record_count: int = 0, metadata: dict[str, Any] | None = None) -> None:
        rt = self.register(source_id, provider)
        rt.failures = 0
        rt.cooldown_until = 0
        self.store.upsert_source_health(source_id, provider, state=SourceState.LIVE.value, last_success_at=utc_now_iso(), last_error=None, latency_ms=latency_ms, record_count=record_count, consecutive_failures=0, cooldown_until=0.0, reliability=rt.policy.reliability, metadata={**rt.metadata, **(metadata or {})})

    def record_failure(self, source_id: str, provider: str, error: str, *, state: SourceState = SourceState.ERROR, metadata: dict[str, Any] | None = None) -> None:
        rt = self.register(source_id, provider)
        rt.failures += 1
        if rt.failures >= rt.policy.max_failures:
            rt.cooldown_until = time.time() + rt.policy.cooldown_seconds
        self.store.upsert_source_health(source_id, provider, state=state.value, last_failure_at=utc_now_iso(), last_error=str(error)[:1000], consecutive_failures=rt.failures, cooldown_until=rt.cooldown_until, reliability=rt.policy.reliability, metadata={**rt.metadata, **(metadata or {})})

    def can_call(self, source_id: str) -> bool:
        if self.store.get_source_quarantine(source_id):
            return False
        rt = self._sources.get(source_id)
        return not rt or not rt.on_cooldown

    def quarantine(self, source_id: str, provider: str, reason: str, *, quarantine_kind: str = "contract", failure_count: int = 1, duration_seconds: int = 3600, manual: bool = False, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.store.quarantine_source(source_id, provider, reason, quarantine_kind=quarantine_kind, failure_count=failure_count, duration_seconds=duration_seconds, manual=manual, metadata=metadata)

    def clear_quarantine(self, source_id: str) -> bool:
        return self.store.clear_source_quarantine(source_id)

    def snapshot(self) -> list[dict[str, Any]]:
        from datetime import datetime

        now = time.time()
        out = []
        quarantines = {q["source_id"]: q for q in self.store.list_source_quarantine()}
        for row in self.store.list_source_health():
            state = row.get("state") or SourceState.UNKNOWN.value
            last = row.get("last_success_at")
            if state == SourceState.LIVE.value and last:
                try:
                    age = now - datetime.fromisoformat(last).timestamp()
                    row["cache_age_seconds"] = max(0, age)
                    rt = self._sources.get(row["source_id"])
                    stale_after = rt.policy.stale_after_seconds if rt else 600
                    if age > stale_after:
                        row["state"] = SourceState.STALE.value
                except Exception:
                    pass
            quarantine = quarantines.get(row.get("source_id"))
            if quarantine:
                row["quarantined"] = True
                row["quarantine"] = quarantine
                row["state"] = SourceState.DISABLED.value
            else:
                row["quarantined"] = False
            out.append(row)
        return out

    async def call(self, source_id: str, provider: str, fn: Callable[[], Any], policy: SourcePolicy | None = None, *, record_success: bool = True) -> T:
        rt = self.register(source_id, provider, policy)
        prefs = self.store.get_setting("runtime_preferences", {}) or {}
        if bool(prefs.get("offline_mode")):
            self.store.upsert_source_health(
                source_id, provider, state=SourceState.DISABLED.value,
                last_error="runtime_offline_mode", reliability=rt.policy.reliability,
                metadata={**rt.metadata, "runtime_policy": "offline"},
            )
            raise RuntimeError(f"source_offline_mode:{source_id}")
        quarantine = self.store.get_source_quarantine(source_id)
        if quarantine:
            raise RuntimeError(f"source_quarantined:{source_id}:{quarantine.get('quarantine_kind','contract')}")
        if rt.on_cooldown:
            raise RuntimeError(f"source_circuit_open:{source_id}:{int(rt.cooldown_until - time.time())}")
        started = time.perf_counter()
        try:
            value = fn()
            if hasattr(value, "__await__"):
                value = await value
            count = len(value) if isinstance(value, (list, tuple, dict, set)) else 1
            if record_success:
                self.record_success(source_id, provider, latency_ms=(time.perf_counter() - started) * 1000, record_count=count)
            return value
        except Exception as exc:
            self.record_failure(source_id, provider, type(exc).__name__)
            raise
