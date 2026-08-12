"""Cumulative fuel/CO2 tracking via per-aircraft observation timestamps.

Background
----------
Users want the running total of fuel burned per aircraft — not just the
rate. We track first-seen-at per icao24 and multiply elapsed observation
time by the model-based rate. This module's job is exclusively the
timestamp bookkeeping; multiplication happens in the flights/military
fetchers.

These tests pin:

  * First sighting returns 0 (no airtime yet).
  * Repeated sightings within ``REOPEN_GAP_S`` accumulate elapsed time.
  * Gap longer than ``REOPEN_GAP_S`` resets the session (plane landed
    and took off again — different flight).
  * ``MAX_SESSION_SECONDS`` clamp protects against clock skew bugs.
  * ``prune()`` drops stale entries.
  * ``get_session_seconds`` reads without bumping last_seen.
  * Empty / None icao input is a defensive no-op.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_observations():
    from services.fetchers import flight_observations as obs
    obs._reset_for_tests()
    yield
    obs._reset_for_tests()


class TestRecordObservation:
    def test_first_sighting_returns_zero(self):
        from services.fetchers.flight_observations import record_observation
        assert record_observation("a12345", now=1000.0) == 0

    def test_repeated_sightings_accumulate(self):
        """ADS-B refreshes every ~minute in practice, so each observation
        is within ``REOPEN_GAP_S`` (15 min) of the last and we keep
        accumulating. Walking the timestamps in 5-minute steps so we
        stay inside the reopen window the whole way."""
        from services.fetchers.flight_observations import record_observation
        record_observation("a12345", now=1000.0)
        # 1 minute later (within REOPEN_GAP_S)
        assert record_observation("a12345", now=1060.0) == 60
        # Step through 5-minute spaced refreshes — first_seen_at stays
        # at 1000.0 the whole time, and we approach a 1-hour airtime.
        assert record_observation("a12345", now=1360.0) == 360
        assert record_observation("a12345", now=1660.0) == 660
        assert record_observation("a12345", now=1960.0) == 960
        assert record_observation("a12345", now=2260.0) == 1260
        assert record_observation("a12345", now=2560.0) == 1560
        assert record_observation("a12345", now=2860.0) == 1860
        assert record_observation("a12345", now=3160.0) == 2160
        assert record_observation("a12345", now=3460.0) == 2460
        assert record_observation("a12345", now=3760.0) == 2760
        assert record_observation("a12345", now=4060.0) == 3060
        assert record_observation("a12345", now=4360.0) == 3360
        # 1 hour after first sighting — still inside the 15-min reopen
        # window from the prior 4360 observation.
        assert record_observation("a12345", now=4600.0) == 3600

    def test_gap_longer_than_reopen_resets_session(self):
        """If a hex hasn't been seen in ``REOPEN_GAP_S`` (15 min default),
        the next sighting is treated as a new flight — first_seen_at resets."""
        from services.fetchers.flight_observations import record_observation
        record_observation("a12345", now=1000.0)
        record_observation("a12345", now=1500.0)  # 500s later — within gap
        # Now 20 minutes of silence (1200s > 900s threshold) → session reset.
        assert record_observation("a12345", now=2700.0) == 0
        # And the next quick sighting starts accumulating from 2700 again.
        assert record_observation("a12345", now=2760.0) == 60

    def test_session_clamp(self):
        """Clock skew protection: when a hex has been continuously
        observed for longer than ``MAX_SESSION_SECONDS``, clamp.

        Synthesizes the state directly because driving 86,400+ seconds of
        observations through the public API in a test would take 1000+
        REOPEN_GAP_S-respecting steps.
        """
        from services.fetchers import flight_observations as obs
        from services.fetchers.flight_observations import _observations, _lock

        # last_seen_at very recent so REOPEN_GAP_S branch does NOT fire,
        # but first_seen_at way in the past so the elapsed math overflows
        # MAX_SESSION_SECONDS. Clamp must kick in.
        big_now = float(obs.MAX_SESSION_SECONDS + 1_000_000)
        with _lock:
            _observations["a12345"] = {
                "first_seen_at": 0.0,
                "last_seen_at": big_now - 60,  # 60s ago — well inside gap window
            }
        elapsed = obs.record_observation("a12345", now=big_now)
        assert elapsed == obs.MAX_SESSION_SECONDS, (
            f"elapsed must be clamped to MAX_SESSION_SECONDS; got {elapsed}"
        )

    def test_empty_input_returns_zero(self):
        from services.fetchers.flight_observations import record_observation
        assert record_observation("") == 0
        assert record_observation(None) == 0  # type: ignore[arg-type]
        assert record_observation("   ") == 0

    def test_case_insensitive_key(self):
        """ICAO24 hex codes are case-insensitive — adsb.lol lowercases
        them, OpenSky may not. Normalize so both refer to the same airframe."""
        from services.fetchers.flight_observations import record_observation
        record_observation("A12345", now=1000.0)
        # Different case must hit the same entry.
        assert record_observation("a12345", now=1060.0) == 60


class TestGetSessionSeconds:
    def test_read_only_does_not_bump(self):
        from services.fetchers.flight_observations import (
            record_observation,
            get_session_seconds,
        )
        record_observation("a12345", now=1000.0)
        record_observation("a12345", now=1060.0)  # bumps last_seen

        # Now read at t=2000. Without bumping, gap=2000-1060=940 > 900,
        # so a recording call would reset. But the read should NOT reset.
        seconds_at_2000 = get_session_seconds("a12345", now=2000.0)
        assert seconds_at_2000 == 1000, (
            f"read should return 2000-1000=1000s; got {seconds_at_2000}"
        )
        # Verify the next recording at t=2001 still resets (gap > 900s
        # from the read above — proves the read didn't bump last_seen).
        from services.fetchers.flight_observations import record_observation as rec
        assert rec("a12345", now=2001.0) == 0  # session reset

    def test_unknown_hex_returns_zero(self):
        from services.fetchers.flight_observations import get_session_seconds
        assert get_session_seconds("nonexistent") == 0


class TestPrune:
    def test_drops_stale_entries(self):
        from services.fetchers import flight_observations as obs

        obs.record_observation("active", now=10_000.0)
        obs.record_observation("stale", now=1.0)

        dropped = obs.prune(now=10_000.0)

        assert dropped == 1
        # Active entry survives:
        assert obs.get_session_seconds("active", now=10_001.0) == 1
        # Stale entry was dropped — next obs starts fresh:
        assert obs.record_observation("stale", now=10_002.0) == 0

    def test_no_op_when_nothing_stale(self):
        from services.fetchers import flight_observations as obs
        obs.record_observation("hex1", now=1000.0)
        obs.record_observation("hex2", now=1000.0)

        dropped = obs.prune(now=1500.0)

        assert dropped == 0


# ---------------------------------------------------------------------------
# Integration: emissions enrichment in _classify_and_publish honors the
# cumulative tracker.
# ---------------------------------------------------------------------------


class TestEmissionsCumulativeIntegration:
    def _reset_store(self):
        from services.fetchers._store import latest_data, _data_lock
        with _data_lock:
            for key in (
                "flights", "commercial_flights", "private_flights",
                "private_jets", "military_flights", "tracked_flights",
            ):
                latest_data[key] = []

    def test_first_publish_zero_cumulative(self, monkeypatch):
        """On the first observation, cumulative values are 0 — but the
        rate fields and observed_seconds are still present in the dict."""
        from services.fetchers import flights as flights_module
        from services.fetchers._store import latest_data, _data_lock

        self._reset_store()
        monkeypatch.setattr(flights_module, "lookup_route", lambda _: None)
        monkeypatch.setattr(flights_module, "lookup_aircraft_type", lambda _: "")

        flights_module._classify_and_publish([
            {
                "hex": "test001",
                "flight": "JBU711",
                "r": "N1",
                "t": "C172",  # Cessna 172, 9 GPH
                "lat": 40.0,
                "lon": -100.0,
                "alt_baro": 3000,
                "gs": 100,
            }
        ])

        with _data_lock:
            published = list(latest_data.get("flights", []))
        assert len(published) == 1
        emi = published[0].get("emissions")
        assert emi is not None
        assert emi["fuel_gph"] == 9
        assert emi["observed_seconds"] == 0
        assert emi["fuel_gallons_burned"] == 0.0
        assert emi["co2_kg_emitted"] == 0.0

    def test_second_publish_accumulates(self, monkeypatch):
        """Publishing the same hex a second time picks up real elapsed time
        and produces non-zero cumulative values."""
        import time as _time_real
        from services.fetchers import flights as flights_module
        from services.fetchers import flight_observations as obs
        from services.fetchers._store import latest_data, _data_lock

        self._reset_store()
        monkeypatch.setattr(flights_module, "lookup_route", lambda _: None)
        monkeypatch.setattr(flights_module, "lookup_aircraft_type", lambda _: "")

        # Manually seed an observation 1 hour in the past so the next
        # publish picks up ~3600s elapsed.
        with obs._lock:
            obs._observations["test002"] = {
                "first_seen_at": _time_real.time() - 3600,
                "last_seen_at": _time_real.time() - 60,
            }

        flights_module._classify_and_publish([
            {
                "hex": "test002",
                "flight": "JBU711",
                "r": "N1",
                "t": "C172",  # 9 GPH
                "lat": 40.0,
                "lon": -100.0,
                "alt_baro": 3000,
                "gs": 100,
            }
        ])

        with _data_lock:
            published = list(latest_data.get("flights", []))
        assert len(published) == 1
        emi = published[0].get("emissions")
        # Roughly 1 hour observed → 9 gal burned.
        assert 3500 <= emi["observed_seconds"] <= 3700
        assert 8.7 <= emi["fuel_gallons_burned"] <= 9.3
        # CO2 = 9 gph * 9.57 kg/gal = 86.1 kg/hr.
        assert 84 <= emi["co2_kg_emitted"] <= 88
