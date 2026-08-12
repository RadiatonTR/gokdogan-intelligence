"""Infonet sync respects upstream HTTP 429 + applies exponential backoff.

Background
----------
Before this fix, ``finish_sync`` used a constant 60s ``failure_backoff_s``
regardless of how many consecutive failures preceded. When an upstream
peer (e.g. the seed onion) returned HTTP 429 "Too Many Requests", the
sync worker would:

  1. Receive 429
  2. Stringify the status into a generic ``ValueError``
  3. Call ``finish_sync(error=str(exc))`` -- losing the status code
  4. Schedule next attempt for ``now + 60s``
  5. Retry. Upstream's rate-limit bucket is still full. 429 again. Loop.

Net effect: a node with one transient 429 would hammer the upstream
every 60s forever, keeping the bucket full and never recovering. This
is what kept the user's Infonet node from reaching the seed peer.

What the fix does
-----------------
* New typed exception ``PeerSyncRateLimited`` carries the parsed
  ``Retry-After`` value out of the HTTP layer.
* ``_sync_from_peer`` returns ``(ok, error, forked, retry_after_s)``
  instead of the old 3-tuple.
* ``finish_sync`` honors ``retry_after_s`` AND applies exponential
  backoff: ``delay = max(retry_after_s, base * 2^failures, cap=1800)``.
* ``parse_retry_after_header`` handles both RFC 7231 forms (delay
  seconds, and HTTP-date).

These tests pin every part of the new contract.
"""

from __future__ import annotations

import time

import pytest


# ---------------------------------------------------------------------------
# parse_retry_after_header — both RFC 7231 forms + edge cases
# ---------------------------------------------------------------------------


class TestParseRetryAfter:
    def test_integer_seconds(self):
        from services.mesh.mesh_infonet_sync_support import parse_retry_after_header
        assert parse_retry_after_header("120") == 120
        assert parse_retry_after_header("  30  ") == 30
        assert parse_retry_after_header("0") == 0

    def test_http_date(self):
        """RFC 7231 §7.1.3 explicitly allows ``Retry-After: <HTTP-date>``.
        We compute seconds-from-now so callers can use the same field
        regardless of which form the upstream chose."""
        from services.mesh.mesh_infonet_sync_support import parse_retry_after_header
        # Pin "now" so the test is deterministic.
        now = 1_700_000_000.0  # 2023-11-14T22:13:20Z
        # 300 seconds in the future, formatted per RFC 7231.
        future = "Tue, 14 Nov 2023 22:18:20 GMT"
        result = parse_retry_after_header(future, now=now)
        assert 295 <= result <= 305, f"expected ~300s, got {result}"

    def test_http_date_in_past_returns_zero(self):
        from services.mesh.mesh_infonet_sync_support import parse_retry_after_header
        now = 1_700_000_000.0
        past = "Mon, 13 Nov 2023 00:00:00 GMT"
        assert parse_retry_after_header(past, now=now) == 0

    def test_empty_and_whitespace_return_zero(self):
        from services.mesh.mesh_infonet_sync_support import parse_retry_after_header
        assert parse_retry_after_header("") == 0
        assert parse_retry_after_header("   ") == 0

    def test_malformed_returns_zero(self):
        from services.mesh.mesh_infonet_sync_support import parse_retry_after_header
        assert parse_retry_after_header("not a header") == 0
        assert parse_retry_after_header("xyz") == 0

    def test_clamps_to_one_hour(self):
        """A hostile peer can't silence us for a week by claiming a
        24h Retry-After. We cap at 1 hour."""
        from services.mesh.mesh_infonet_sync_support import parse_retry_after_header
        assert parse_retry_after_header("86400") == 3600  # 24h -> 1h
        assert parse_retry_after_header("99999999") == 3600

    def test_negative_returns_zero(self):
        """RFC 7231 says ``Retry-After`` is a non-negative integer;
        leading-minus parses as a non-digit and yields 0 here."""
        from services.mesh.mesh_infonet_sync_support import parse_retry_after_header
        assert parse_retry_after_header("-10") == 0


# ---------------------------------------------------------------------------
# _failure_backoff_seconds — exponential growth, retry-after override, cap
# ---------------------------------------------------------------------------


class TestFailureBackoffSeconds:
    def test_exponential_growth(self):
        """First failure uses the base (preserves pre-fix behavior
        for one-off blips). Each subsequent failure doubles the wait,
        capped at 1800s. With base=60: 60, 120, 240, 480, 960, 1800,
        1800, 1800."""
        from services.mesh.mesh_infonet_sync_support import _failure_backoff_seconds
        delays = [
            _failure_backoff_seconds(
                base_backoff_s=60,
                consecutive_failures=n,
                retry_after_s=0,
                cap_s=1800,
            )
            for n in range(1, 9)
        ]
        assert delays == [60, 120, 240, 480, 960, 1800, 1800, 1800], delays

    def test_retry_after_wins_when_larger(self):
        """If the upstream says ``Retry-After: 600`` but exponential
        would only ask for 60s (one failure), we honor the upstream."""
        from services.mesh.mesh_infonet_sync_support import _failure_backoff_seconds
        assert _failure_backoff_seconds(
            base_backoff_s=60,
            consecutive_failures=1,
            retry_after_s=600,
            cap_s=1800,
        ) == 600

    def test_exponential_wins_when_larger(self):
        """If exponential is asking for 1800s (6+ failures) but
        upstream only sent ``Retry-After: 30``, we honor exponential.
        The 30s was the upstream's view at one moment; our exponential
        reflects sustained failure."""
        from services.mesh.mesh_infonet_sync_support import _failure_backoff_seconds
        result = _failure_backoff_seconds(
            base_backoff_s=60,
            consecutive_failures=7,
            retry_after_s=30,
            cap_s=1800,
        )
        assert result == 1800

    def test_cap_zero_disables_exponential(self):
        """Operators who want pre-fix behavior can set cap=0; only the
        upstream's Retry-After is respected. (Pre-fix had no
        exponential growth at all.)"""
        from services.mesh.mesh_infonet_sync_support import _failure_backoff_seconds
        assert _failure_backoff_seconds(
            base_backoff_s=60,
            consecutive_failures=10,
            retry_after_s=120,
            cap_s=0,
        ) == 120

    def test_zero_inputs_return_zero(self):
        from services.mesh.mesh_infonet_sync_support import _failure_backoff_seconds
        assert _failure_backoff_seconds(
            base_backoff_s=0,
            consecutive_failures=0,
            retry_after_s=0,
        ) == 0


# ---------------------------------------------------------------------------
# finish_sync end-to-end — failure path with retry-after + growing counter
# ---------------------------------------------------------------------------


class TestFinishSyncBackoff:
    def _state(self, **overrides):
        from services.mesh.mesh_infonet_sync_support import SyncWorkerState
        base = {
            "last_sync_started_at": 0,
            "last_sync_finished_at": 0,
            "last_sync_ok_at": 0,
            "next_sync_due_at": 0,
            "last_peer_url": "",
            "last_error": "",
            "last_outcome": "idle",
            "current_head": "",
            "fork_detected": False,
            "consecutive_failures": 0,
        }
        base.update(overrides)
        return SyncWorkerState(**base)

    def test_first_failure_uses_base_unchanged(self):
        """One failure means consecutive_failures becomes 1, which uses
        ``base * 2^0 = base``. Preserves the pre-fix behavior so a
        single transient upstream blip doesn't suddenly take 2 minutes
        to retry — that change has to be earned by sustained failure."""
        from services.mesh.mesh_infonet_sync_support import finish_sync
        result = finish_sync(
            self._state(),
            ok=False,
            error="some upstream blip",
            now=1000.0,
            failure_backoff_s=60,
        )
        assert result.consecutive_failures == 1
        assert result.next_sync_due_at == 1000 + 60
        assert result.last_error == "some upstream blip"
        assert result.last_outcome == "error"

    def test_consecutive_failures_grow_the_delay(self):
        """After 5 prior failures already in state, the next failure
        sets consecutive=6 and uses the cap (1800s = 60 * 2^5)."""
        from services.mesh.mesh_infonet_sync_support import finish_sync
        result = finish_sync(
            self._state(consecutive_failures=5),
            ok=False,
            error="HTTP 429",
            now=2000.0,
            failure_backoff_s=60,
        )
        assert result.consecutive_failures == 6
        assert result.next_sync_due_at == 2000 + 1800

    def test_retry_after_honored_at_low_failure_count(self):
        """When the upstream says ``Retry-After: 900`` but we'd
        otherwise only wait 240s (4 failures = 60*2^3), wait 900s."""
        from services.mesh.mesh_infonet_sync_support import finish_sync
        result = finish_sync(
            self._state(consecutive_failures=3),
            ok=False,
            error="HTTP 429",
            now=5000.0,
            failure_backoff_s=60,
            retry_after_s=900,
        )
        assert result.consecutive_failures == 4
        assert result.next_sync_due_at == 5000 + 900

    def test_success_resets_consecutive_failures(self):
        from services.mesh.mesh_infonet_sync_support import finish_sync
        result = finish_sync(
            self._state(consecutive_failures=4),
            ok=True,
            now=7000.0,
            interval_s=300,
        )
        assert result.consecutive_failures == 0
        assert result.next_sync_due_at == 7000 + 300
        assert result.last_outcome == "ok"

    def test_last_error_carries_status_string(self):
        """The pre-fix path stringified exceptions into ``last_error``
        but the string was often empty (HTTP layer raised ValueError
        with no message). We now require callers to pass something
        meaningful — see the typed exception path in main.py."""
        from services.mesh.mesh_infonet_sync_support import finish_sync
        result = finish_sync(
            self._state(),
            ok=False,
            error="HTTP 429 from peer (retry_after=120s): rate-limited",
            now=1000.0,
            failure_backoff_s=60,
            retry_after_s=120,
        )
        assert "HTTP 429" in result.last_error
        assert "retry_after=120s" in result.last_error
