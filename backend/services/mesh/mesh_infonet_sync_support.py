from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from datetime import timezone

from services.mesh.mesh_peer_store import PeerRecord


class PeerSyncRateLimited(Exception):
    """Upstream peer returned HTTP 429 — Too Many Requests.

    Carries the ``Retry-After`` header value (parsed to seconds) so
    the caller can pass it to ``finish_sync(retry_after_s=...)`` and
    actually wait that long instead of hammering the upstream every
    60s and keeping its rate-limit bucket full.

    ``retry_after_s`` is 0 when the upstream didn't provide a header.
    Caller should still apply the exponential backoff in that case.
    """

    def __init__(self, message: str, retry_after_s: int = 0, status: int = 429):
        super().__init__(message)
        self.retry_after_s = max(0, int(retry_after_s or 0))
        self.status = int(status or 429)


def parse_retry_after_header(header_value: str, *, now: float | None = None) -> int:
    """Parse the ``Retry-After`` HTTP header.

    Two valid forms per RFC 7231 §7.1.3:

      * Delay-seconds: a non-negative integer (e.g. ``Retry-After: 120``)
      * HTTP-date: an absolute time (e.g. ``Retry-After: Wed, 21 Oct 2026 07:28:00 GMT``)

    Returns the wait in **seconds from now**. Unparseable / empty headers
    return 0 (caller falls back to exponential backoff). Clamped at a
    sane upper bound (1 hour) so a typo'd or hostile peer can't pin us
    silent for days.
    """
    value = str(header_value or "").strip()
    if not value:
        return 0
    upper_bound = 3600  # never trust a peer to silence us > 1h
    # Form 1: pure integer seconds.
    if value.isdigit():
        return min(max(0, int(value)), upper_bound)
    # Form 2: HTTP-date.
    try:
        target = parsedate_to_datetime(value)
        if target is None:
            return 0
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        current = float(now if now is not None else time.time())
        delta = int(target.timestamp() - current)
        return min(max(0, delta), upper_bound)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class SyncWorkerState:
    last_sync_started_at: int = 0
    last_sync_finished_at: int = 0
    last_sync_ok_at: int = 0
    next_sync_due_at: int = 0
    last_peer_url: str = ""
    last_error: str = ""
    last_outcome: str = "idle"
    current_head: str = ""
    fork_detected: bool = False
    consecutive_failures: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def eligible_sync_peers(records: list[PeerRecord], *, now: float | None = None) -> list[PeerRecord]:
    current_time = int(now if now is not None else time.time())
    candidates = [
        record
        for record in records
        if record.bucket == "sync" and record.enabled and int(record.cooldown_until or 0) <= current_time
    ]

    def _seed_priority(record: PeerRecord) -> int:
        role = str(record.role or "").strip().lower()
        source = str(record.source or "").strip().lower()
        if role == "seed" and source in {"bundle", "bootstrap_promoted"}:
            return 0
        return 1

    return sorted(
        candidates,
        key=lambda record: (
            -int(record.last_sync_ok_at or 0),
            _seed_priority(record),
            int(record.failure_count or 0),
            int(record.added_at or 0),
            record.peer_url,
        ),
    )


def begin_sync(
    state: SyncWorkerState,
    *,
    peer_url: str = "",
    current_head: str = "",
    now: float | None = None,
) -> SyncWorkerState:
    timestamp = int(now if now is not None else time.time())
    return SyncWorkerState(
        last_sync_started_at=timestamp,
        last_sync_finished_at=state.last_sync_finished_at,
        last_sync_ok_at=state.last_sync_ok_at,
        next_sync_due_at=state.next_sync_due_at,
        last_peer_url=peer_url or state.last_peer_url,
        last_error="",
        last_outcome="running",
        current_head=current_head or state.current_head,
        fork_detected=False,
        consecutive_failures=state.consecutive_failures,
    )


def _failure_backoff_seconds(
    *,
    base_backoff_s: int,
    consecutive_failures: int,
    retry_after_s: int,
    cap_s: int = 1800,
) -> int:
    """Compute the next-attempt delay after a failed sync.

    Two inputs combine:

    * ``retry_after_s`` — when an upstream peer answered HTTP 429
      with a ``Retry-After`` header, we honor it exactly. Continuing
      to hammer the upstream every 60s is the bug this fix exists to
      close: it keeps the upstream's rate-limit bucket full
      indefinitely and no sync ever lands.

    * Exponential growth on ``consecutive_failures`` — even without an
      explicit Retry-After, repeated failures should slow us down. The
      first failure waits ``base`` (preserves pre-fix behavior for
      one-off blips). Each subsequent failure doubles the wait, capped
      to ``cap_s`` (default 30 minutes). With base=60 and cap=1800,
      the schedule is 60s → 120s → 240s → 480s → 960s → 1800s →
      1800s → … .

    The actual delay is the MAX of the two — whichever asks for more
    patience wins. ``retry_after_s == 0`` (no header) falls back to
    pure exponential. An aggressive ``Retry-After`` (say 600s while
    we're only at 1 failure) wins over the exponential ladder.
    """
    base = max(0, int(base_backoff_s or 0))
    failures = max(0, int(consecutive_failures or 0))
    cap = max(0, int(cap_s or 0))
    retry_after = max(0, int(retry_after_s or 0))
    # ``cap_s=0`` explicitly disables the exponential ladder entirely
    # — operators who want the pre-fix "honor Retry-After only" behavior
    # can set this. The default cap of 1800s is what saturates the
    # ladder at the 5th-6th failure for base=60.
    if cap == 0:
        return retry_after
    # 2^(failures-1) — so failure #1 = base (preserves the pre-fix
    # default for transient blips), failure #2 = 2*base, etc. Cap on
    # the exponent (16) is defense against integer overflow on a
    # hostile or very large failures counter.
    if base > 0 and failures > 0:
        exponent = min(max(0, failures - 1), 16)
        grown = base * (2 ** exponent)
    else:
        grown = 0
    exponential = min(max(0, grown), cap)
    return max(exponential, retry_after)


def finish_sync(
    state: SyncWorkerState,
    *,
    ok: bool,
    peer_url: str = "",
    current_head: str = "",
    error: str = "",
    fork_detected: bool = False,
    now: float | None = None,
    interval_s: int = 300,
    failure_backoff_s: int = 60,
    retry_after_s: int = 0,
    failure_backoff_cap_s: int = 1800,
) -> SyncWorkerState:
    """Finalise a sync attempt and compute when the next one should run.

    New args (added for the 429 retry storm fix):

    * ``retry_after_s`` — if the peer responded with HTTP 429 + a
      ``Retry-After`` header, pass that value here. ``finish_sync``
      will use ``max(exponential, retry_after_s)`` for the delay so
      we never hammer a peer that asked us to back off.
    * ``failure_backoff_cap_s`` — upper bound on the exponential
      ladder. Default 1800 (30 min) — keeps a sync queue from going
      silent for hours while still cutting the request rate to
      something the upstream can absorb.

    The pre-fix behavior (constant 60s on every failure) is recoverable
    by passing ``failure_backoff_cap_s=0`` and ``retry_after_s=0``, but
    there's no reason to.
    """
    timestamp = int(now if now is not None else time.time())
    if ok:
        return SyncWorkerState(
            last_sync_started_at=state.last_sync_started_at,
            last_sync_finished_at=timestamp,
            last_sync_ok_at=timestamp,
            next_sync_due_at=timestamp + max(0, int(interval_s or 0)),
            last_peer_url=peer_url or state.last_peer_url,
            last_error="",
            last_outcome="ok",
            current_head=current_head or state.current_head,
            fork_detected=bool(fork_detected),
            consecutive_failures=0,
        )

    next_failures = state.consecutive_failures + 1
    delay_s = _failure_backoff_seconds(
        base_backoff_s=failure_backoff_s,
        consecutive_failures=next_failures,
        retry_after_s=retry_after_s,
        cap_s=failure_backoff_cap_s,
    )

    return SyncWorkerState(
        last_sync_started_at=state.last_sync_started_at,
        last_sync_finished_at=timestamp,
        last_sync_ok_at=state.last_sync_ok_at,
        next_sync_due_at=timestamp + delay_s,
        last_peer_url=peer_url or state.last_peer_url,
        last_error=str(error or "").strip(),
        last_outcome="fork" if fork_detected else "error",
        current_head=current_head or state.current_head,
        fork_detected=bool(fork_detected),
        consecutive_failures=next_failures,
    )


def finish_solo_sync(
    state: SyncWorkerState,
    *,
    current_head: str = "",
    now: float | None = None,
    interval_s: int = 300,
) -> SyncWorkerState:
    timestamp = int(now if now is not None else time.time())
    return SyncWorkerState(
        last_sync_started_at=state.last_sync_started_at,
        last_sync_finished_at=timestamp,
        last_sync_ok_at=state.last_sync_ok_at,
        next_sync_due_at=timestamp + max(0, int(interval_s or 0)),
        last_peer_url="",
        last_error="",
        last_outcome="solo",
        current_head=current_head or state.current_head,
        fork_detected=False,
        consecutive_failures=0,
    )


def should_run_sync(
    state: SyncWorkerState,
    *,
    now: float | None = None,
) -> bool:
    current_time = int(now if now is not None else time.time())
    if state.last_outcome == "running":
        started_at = int(state.last_sync_started_at or 0)
        return started_at <= 0 or current_time - started_at >= 300
    return int(state.next_sync_due_at or 0) <= current_time
