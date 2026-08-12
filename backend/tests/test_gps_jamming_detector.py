"""GPS jamming detection — nac_p=0 counted, lowered thresholds.

Background
----------
Pre-fix, the detector had three stacked filters that together meant the
``gps_jamming`` layer almost never lit up:

  1. ``nac_p == 0`` aircraft were dropped on the theory that "0 = old
     transponder." But modern Mode-S Enhanced Surveillance transponders
     also fall back to ``nac_p == 0`` when they lose GPS lock entirely —
     which is *exactly* the jamming signature we want to catch.
  2. ``GPS_JAMMING_MIN_AIRCRAFT = 5`` per 1°x1° cell.
  3. ``GPS_JAMMING_MIN_RATIO = 0.30`` adjusted ratio.

Combined with the existing ``-1`` noise cushion (``adjusted = degraded - 1``)
the bar to clear required dense, busy airspace — but jamming hotspots
(eastern Med, eastern Ukraine, Iran/Iraq) tend to have sparser traffic
precisely because pilots avoid them.

These tests pin the new behavior:

  * ``nac_p == 0`` is now counted as degraded.
  * ``nac_p == None`` (no field — typical for OpenSky records) is still
    skipped — absence isn't evidence.
  * Thresholds lowered to 3 aircraft / 0.20 ratio.
  * Public function signature accepts overrides so callers / future
    operators can re-tune without code edits.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# nac_p == 0 inclusion (the headline fix)
# ---------------------------------------------------------------------------


class TestNacpZeroCounted:
    def test_cell_dominated_by_nacp_zero_now_fires(self):
        """Three aircraft all reporting nac_p=0 in one cell, plus two
        with valid GPS. Pre-fix the three nac_p=0 records were skipped
        entirely (cell would have total=2, degraded=0, no zone). Post-fix
        they count as degraded — this IS the jamming signature."""
        from services.fetchers.flights import detect_gps_jamming_zones

        # All in 1°x1° cell at int(lat)=40, int(lng)=-100
        feed = [
            {"hex": "a1", "lat": 40.1, "lng": -100.1, "nac_p": 0},
            {"hex": "a2", "lat": 40.5, "lng": -100.5, "nac_p": 0},
            {"hex": "a3", "lat": 40.9, "lng": -100.9, "nac_p": 0},
            {"hex": "b1", "lat": 40.2, "lng": -100.3, "nac_p": 9},
            {"hex": "b2", "lat": 40.7, "lng": -100.7, "nac_p": 11},
        ]

        zones = detect_gps_jamming_zones(feed)

        # total=5, degraded=3, adjusted=2, ratio=0.40 > 0.20 → zone fires.
        assert len(zones) == 1
        assert zones[0]["degraded"] == 3
        assert zones[0]["total"] == 5
        assert zones[0]["ratio"] == 0.40
        # Grid-cell center coords.
        assert zones[0]["lat"] == 40.5
        assert zones[0]["lng"] == -99.5

    def test_nacp_zero_alone_clears_min_aircraft(self):
        """A cell with exactly 3 aircraft all reporting nac_p=0 must
        fire under the new MIN_AIRCRAFT=3 + MIN_RATIO=0.20 regime."""
        from services.fetchers.flights import detect_gps_jamming_zones

        feed = [
            {"hex": "a1", "lat": 50.1, "lng": 30.1, "nac_p": 0},
            {"hex": "a2", "lat": 50.5, "lng": 30.5, "nac_p": 0},
            {"hex": "a3", "lat": 50.9, "lng": 30.9, "nac_p": 0},
        ]

        zones = detect_gps_jamming_zones(feed)

        # total=3, degraded=3, adjusted=2, ratio=0.667 > 0.20 → fires.
        # severity is "medium" because 0.5 ≤ ratio < 0.75.
        assert len(zones) == 1
        assert zones[0]["severity"] == "medium"


# ---------------------------------------------------------------------------
# nac_p == None is still skipped (preserve OpenSky behavior)
# ---------------------------------------------------------------------------


class TestNoneStillSkipped:
    def test_none_records_dont_add_to_grid(self):
        """OpenSky's /states/all doesn't include nac_p, so its records
        arrive with the field absent (``rf.get("nac_p") is None``). These
        records must NOT count toward total — absence-of-data isn't
        evidence of either jamming OR working GPS."""
        from services.fetchers.flights import detect_gps_jamming_zones

        # 3 jammed + 4 OpenSky-style (no nac_p). Pre-fix and post-fix
        # behavior should be identical here: None always skipped.
        feed = [
            {"hex": "a1", "lat": 40.1, "lng": -100.1, "nac_p": 0},
            {"hex": "a2", "lat": 40.2, "lng": -100.2, "nac_p": 0},
            {"hex": "a3", "lat": 40.3, "lng": -100.3, "nac_p": 0},
            # OpenSky-style: no nac_p at all
            {"hex": "o1", "lat": 40.4, "lng": -100.4},
            {"hex": "o2", "lat": 40.5, "lng": -100.5},
            {"hex": "o3", "lat": 40.6, "lng": -100.6},
            {"hex": "o4", "lat": 40.7, "lng": -100.7},
        ]

        zones = detect_gps_jamming_zones(feed)

        # Only the 3 nac_p=0 records hit the grid. total=3, not 7.
        assert len(zones) == 1
        assert zones[0]["total"] == 3
        assert zones[0]["degraded"] == 3

    def test_explicit_none_skipped(self):
        """Same behavior when ``nac_p`` is present but set to None
        (defensive — adsb.lol shouldn't do this, but downstream
        normalizers might)."""
        from services.fetchers.flights import detect_gps_jamming_zones

        feed = [
            {"hex": "a1", "lat": 0.1, "lng": 0.1, "nac_p": None},
            {"hex": "a2", "lat": 0.2, "lng": 0.2, "nac_p": None},
            {"hex": "a3", "lat": 0.3, "lng": 0.3, "nac_p": None},
        ]

        zones = detect_gps_jamming_zones(feed)

        # No records counted → no zones.
        assert zones == []


# ---------------------------------------------------------------------------
# Lowered MIN_AIRCRAFT (5 → 3)
# ---------------------------------------------------------------------------


class TestMinAircraftLowered:
    def test_three_aircraft_cell_now_qualifies(self):
        """Pre-fix MIN_AIRCRAFT=5 blocked sparse cells entirely. Post-fix
        the bar is 3 aircraft per cell, which is realistic for the actual
        jamming hotspots where traffic is thinner."""
        from services.fetchers.flights import detect_gps_jamming_zones

        feed = [
            {"hex": "a1", "lat": 33.1, "lng": 44.1, "nac_p": 3},
            {"hex": "a2", "lat": 33.2, "lng": 44.2, "nac_p": 5},
            {"hex": "a3", "lat": 33.3, "lng": 44.3, "nac_p": 7},
        ]

        zones = detect_gps_jamming_zones(feed)

        # total=3, degraded=3, adjusted=2, ratio=0.667 — fires under new
        # rules, would have been blocked by MIN_AIRCRAFT=5 pre-fix.
        assert len(zones) == 1

    def test_two_aircraft_cell_still_blocked(self):
        """We didn't lower the bar to 2 — that would create too much
        single-transponder noise. Two aircraft per cell still doesn't
        qualify."""
        from services.fetchers.flights import detect_gps_jamming_zones

        feed = [
            {"hex": "a1", "lat": 33.1, "lng": 44.1, "nac_p": 3},
            {"hex": "a2", "lat": 33.2, "lng": 44.2, "nac_p": 3},
        ]

        zones = detect_gps_jamming_zones(feed)

        assert zones == []


# ---------------------------------------------------------------------------
# Lowered MIN_RATIO (0.30 → 0.20)
# ---------------------------------------------------------------------------


class TestMinRatioLowered:
    def test_ratio_between_old_and_new_threshold_fires(self):
        """Construct a cell whose ratio sits in the (0.20, 0.30) window:
        fires under the new bar, would have been blocked pre-fix."""
        from services.fetchers.flights import detect_gps_jamming_zones

        # 10 aircraft, 4 degraded → adjusted=3, ratio=3/10=0.30.
        # Pre-fix threshold was > 0.30 strict — would NOT fire.
        # Post-fix threshold is > 0.20 — fires.
        feed = (
            [{"hex": f"d{i}", "lat": 40.1, "lng": -100.1, "nac_p": 3} for i in range(4)]
            + [{"hex": f"c{i}", "lat": 40.5, "lng": -100.5, "nac_p": 9} for i in range(6)]
        )

        zones = detect_gps_jamming_zones(feed)

        assert len(zones) == 1
        assert zones[0]["degraded"] == 4
        assert zones[0]["total"] == 10
        assert zones[0]["ratio"] == 0.30

    def test_ratio_at_or_below_new_threshold_does_not_fire(self):
        """Ratio of exactly 0.20 must NOT fire (strict ``>`` comparison)."""
        from services.fetchers.flights import detect_gps_jamming_zones

        # 15 aircraft, 4 degraded → adjusted=3, ratio=3/15=0.20. Strictly
        # not greater than 0.20, so doesn't qualify.
        feed = (
            [{"hex": f"d{i}", "lat": 40.1, "lng": -100.1, "nac_p": 3} for i in range(4)]
            + [{"hex": f"c{i}", "lat": 40.5, "lng": -100.5, "nac_p": 9} for i in range(11)]
        )

        zones = detect_gps_jamming_zones(feed)

        assert zones == []


# ---------------------------------------------------------------------------
# Pre-existing noise cushion (-1) preserved
# ---------------------------------------------------------------------------


class TestNoiseCushionPreserved:
    def test_single_quirky_transponder_doesnt_fire(self):
        """One degraded aircraft in a healthy cell shouldn't fire even
        under the relaxed thresholds. The ``-1`` adjustment in the
        detector exists for this reason."""
        from services.fetchers.flights import detect_gps_jamming_zones

        feed = (
            [{"hex": "d1", "lat": 40.1, "lng": -100.1, "nac_p": 3}]
            + [{"hex": f"c{i}", "lat": 40.5, "lng": -100.5, "nac_p": 9} for i in range(10)]
        )

        zones = detect_gps_jamming_zones(feed)

        # total=11, degraded=1, adjusted=0 → cell short-circuits.
        assert zones == []


# ---------------------------------------------------------------------------
# Constants pinned (catches accidental rollback)
# ---------------------------------------------------------------------------


class TestConstantsPinned:
    def test_min_aircraft_is_three(self):
        from services.constants import GPS_JAMMING_MIN_AIRCRAFT
        assert GPS_JAMMING_MIN_AIRCRAFT == 3, (
            "MIN_AIRCRAFT must be 3; raising it back to 5 brings back the "
            "'jamming never shows' bug."
        )

    def test_min_ratio_is_0_20(self):
        from services.constants import GPS_JAMMING_MIN_RATIO
        assert GPS_JAMMING_MIN_RATIO == 0.20, (
            "MIN_RATIO must be 0.20; raising it back to 0.30 brings back "
            "the 'jamming never shows' bug."
        )


# ---------------------------------------------------------------------------
# Overrides honored
# ---------------------------------------------------------------------------


class TestOverridesHonored:
    def test_overrides_supersede_constants(self):
        """The public signature accepts overrides so an operator can
        re-tune at the call site (e.g. for a more aggressive setup in
        an active conflict zone) without editing the module constants."""
        from services.fetchers.flights import detect_gps_jamming_zones

        feed = [
            {"hex": "a1", "lat": 40.1, "lng": -100.1, "nac_p": 3},
            {"hex": "a2", "lat": 40.2, "lng": -100.2, "nac_p": 3},
        ]

        # With defaults (min_aircraft=3) this is blocked. With override=2 it fires.
        assert detect_gps_jamming_zones(feed) == []
        zones = detect_gps_jamming_zones(feed, min_aircraft=2)
        assert len(zones) == 1


# ---------------------------------------------------------------------------
# lon vs lng compatibility
# ---------------------------------------------------------------------------


class TestLonLngCompat:
    def test_lon_key_accepted(self):
        """adsb.lol records arrive with ``lon`` (no g). The OpenSky merge
        normalizes to ``lng`` but raw records flowing into the detector
        may use either. Make sure both work."""
        from services.fetchers.flights import detect_gps_jamming_zones

        feed = [
            {"hex": "a1", "lat": 40.1, "lon": -100.1, "nac_p": 0},
            {"hex": "a2", "lat": 40.2, "lon": -100.2, "nac_p": 0},
            {"hex": "a3", "lat": 40.3, "lon": -100.3, "nac_p": 0},
        ]

        zones = detect_gps_jamming_zones(feed)

        assert len(zones) == 1


# ---------------------------------------------------------------------------
# Empty / malformed inputs don't crash
# ---------------------------------------------------------------------------


class TestRobustness:
    def test_empty_feed(self):
        from services.fetchers.flights import detect_gps_jamming_zones
        assert detect_gps_jamming_zones([]) == []

    def test_none_feed(self):
        """The wrapper at the call site passes ``raw_flights_snapshot``
        which could in principle be None on a startup race. Handle it."""
        from services.fetchers.flights import detect_gps_jamming_zones
        assert detect_gps_jamming_zones(None) == []

    def test_records_missing_position_skipped(self):
        from services.fetchers.flights import detect_gps_jamming_zones
        feed = [
            {"hex": "noloc", "nac_p": 0},
            {"hex": "nolat", "lng": -100.0, "nac_p": 0},
            {"hex": "nolng", "lat": 40.0, "nac_p": 0},
        ]
        assert detect_gps_jamming_zones(feed) == []
