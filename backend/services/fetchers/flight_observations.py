"""Per-aircraft observation tracking for cumulative fuel/CO2 estimates.

Background
----------
The pre-existing emissions enrichment attached a *rate* to each flight
(GPH and kg/hr) based on aircraft model. Users — reasonably — wanted the
running total: how much fuel HAS this plane burned since we started
seeing it? Multiplying the rate by elapsed observation time gets us
there, but it requires somewhere to remember "when did this icao24
first appear on our radar?"

Why this lives outside ``flight_trails``
----------------------------------------
``flight_trails`` is sized and pruned aggressively for map rendering
(5-minute TTL for untracked aircraft, 200 trail points max). That's
wrong for cumulative burn: if a plane has been airborne 2 hours but
its trail was pruned 30 min in, the "first trail point" timestamp is
30 min ago, not 2h ago. Worse, when the trail expires and re-creates,
the cumulative counter would reset mid-flight.

This module tracks observation lifecycle separately:

* When a hex is first observed: start a new flight session.
* While observed regularly (gap < ``REOPEN_GAP_S``): keep accumulating.
* When unseen for longer than ``REOPEN_GAP_S``: treat next sighting as
  a new session (the plane landed and took off again, or it's a
  different leg). Reset ``first_seen_at``.
* Stale sessions are pruned every ``PRUNE_INTERVAL_S`` so memory stays
  bounded.

The user explicitly asked for this counting semantic: "as soon as a
plane appears there should be a counter that keeps a running count of
the fuel being burned... If there is no estimate take off time then it
can just be from the time the server starts to keep a log of whats in
the air."
"""

from __future__ import annotations

import threading
import time


# Gap between sightings that resets the session. ADS-B refreshes the
# whole aircraft list every minute or two, so anything over a few
# minutes means the plane left our coverage window (landed, transit
# through dead zone, etc). 15 minutes is conservative.
REOPEN_GAP_S = 15 * 60

# Don't accumulate runaway memory: drop entries unseen for an hour.
PRUNE_AFTER_S = 60 * 60

# Cap on accumulated airtime per session so a single bug elsewhere
# (e.g. ts clock skew) can't produce comically large numbers.
MAX_SESSION_SECONDS = 24 * 3600  # 24h — longest realistic civilian leg


_observations: dict[str, dict[str, float]] = {}
_lock = threading.Lock()
_last_prune_at = 0.0


def record_observation(icao_hex: str, *, now: float | None = None) -> int:
    """Record a sighting of ``icao_hex`` and return airtime so far (seconds).

    Returns 0 for the first-ever sighting (no elapsed time yet) or when
    ``icao_hex`` is falsy. The caller can multiply the returned seconds
    by ``rate_per_hour / 3600`` to get cumulative consumption.
    """
    if not icao_hex:
        return 0
    key = str(icao_hex).strip().lower()
    if not key:
        return 0
    current = float(now if now is not None else time.time())

    with _lock:
        entry = _observations.get(key)
        if entry is None:
            _observations[key] = {"first_seen_at": current, "last_seen_at": current}
            return 0
        # Use explicit ``is None`` checks instead of ``or`` short-circuit:
        # ``0.0`` is a legitimate timestamp value (e.g. test fixtures
        # seeding a far-past first_seen_at to exercise the clamp) but
        # ``0.0 or fallback`` collapses to ``fallback`` because 0.0 is
        # falsy. Bit me on my own test — leaving the safer form here.
        last_raw = entry.get("last_seen_at")
        last_seen = float(last_raw) if last_raw is not None else current
        gap = current - last_seen
        if gap > REOPEN_GAP_S:
            # Treat as a new flight session — the plane landed/disappeared
            # long enough that the prior cumulative count is no longer
            # the same flight.
            _observations[key] = {"first_seen_at": current, "last_seen_at": current}
            return 0
        first_raw = entry.get("first_seen_at")
        first = float(first_raw) if first_raw is not None else current
        # Clamp absurd values from clock skew or bad input.
        elapsed = max(0, min(int(current - first), MAX_SESSION_SECONDS))
        entry["last_seen_at"] = current
        return elapsed


def prune(*, now: float | None = None) -> int:
    """Drop entries we haven't seen in ``PRUNE_AFTER_S`` seconds.

    Returns number of entries dropped. Safe to call from a scheduler tick;
    cheap (single dict scan) so cadence doesn't matter much.
    """
    current = float(now if now is not None else time.time())
    dropped = 0
    with _lock:
        stale_keys = []
        for k, v in _observations.items():
            last_raw = v.get("last_seen_at")
            last = float(last_raw) if last_raw is not None else 0.0
            if current - last > PRUNE_AFTER_S:
                stale_keys.append(k)
        for k in stale_keys:
            del _observations[k]
            dropped += 1
    return dropped


def get_session_seconds(icao_hex: str, *, now: float | None = None) -> int:
    """Read-only accessor: airtime for a known icao without bumping last-seen.

    Used by tests and external consumers (e.g. when rendering a snapshot
    of all in-flight aircraft, you want the current value, not to update
    last_seen_at as a side effect).
    """
    if not icao_hex:
        return 0
    key = str(icao_hex).strip().lower()
    with _lock:
        entry = _observations.get(key)
        if entry is None:
            return 0
        current = float(now if now is not None else time.time())
        first_raw = entry.get("first_seen_at")
        first = float(first_raw) if first_raw is not None else current
        return max(0, min(int(current - first), MAX_SESSION_SECONDS))


def _reset_for_tests() -> None:
    """Drop all observations. Test helper only."""
    with _lock:
        _observations.clear()
