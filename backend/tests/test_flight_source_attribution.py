"""Per-flight source attribution.

Background
----------
Pre-fix, adsb.lol records (the primary source for most flights) carried
no source marker. OpenSky records got ``is_opensky: True`` and
supplementals got ``supplemental_source``, so any UI that wanted to show
which provider a flight came from saw OpenSky/airplanes.live records as
explicitly tagged and adsb.lol records as "unlabeled" — making it look
like adsb.lol wasn't even being used.

This caused user confusion ("only military planes have adsb.lol
telemetry") that was diagnostic noise, not a real bug. The actual fix:
stamp ``source`` at every fetch site so the downstream consumer can
attribute the provider with no guesswork.

These tests pin:

  * adsb.lol regional records get ``source: "adsb.lol"`` at fetch time
    (synthesized via the published flight dict).
  * OpenSky records get ``source: "OpenSky"`` (alongside the existing
    ``is_opensky: True`` for backwards compat).
  * Supplementals (airplanes.live, adsb.fi) flow through with their
    ``supplemental_source`` honored.
  * The military fetcher tags ``source`` on military_flights and uavs.
  * The published flight dict carries ``source`` so downstream code
    can render attribution.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _classify_and_publish — source field flows into published flight dict
# ---------------------------------------------------------------------------


class TestClassifyAndPublishSource:
    def _reset_store(self):
        """Clear store before each test so we get deterministic state."""
        from services.fetchers._store import latest_data, _data_lock
        with _data_lock:
            for key in (
                "flights", "commercial_flights", "private_flights",
                "private_jets", "military_flights", "tracked_flights",
            ):
                latest_data[key] = []
        return latest_data

    def test_adsb_lol_record_tagged_in_published_flight(self, monkeypatch):
        """A raw adsb.lol record (carrying ``source: 'adsb.lol'`` from the
        fetch site) flows through ``_classify_and_publish`` and the
        published flight dict carries the same ``source`` field."""
        from services.fetchers import flights as flights_module
        from services.fetchers._store import latest_data, _data_lock

        self._reset_store()

        # Patch route + type lookups so they don't try to hit the network.
        monkeypatch.setattr(flights_module, "lookup_route", lambda _: None)
        monkeypatch.setattr(flights_module, "lookup_aircraft_type", lambda _: "")

        flights_module._classify_and_publish(
            [
                {
                    "hex": "ad7701",
                    "flight": "JBU711",
                    "r": "N967JT",
                    "t": "A321",
                    "lat": 40.0,
                    "lon": -100.0,
                    "alt_baro": 36000,
                    "gs": 401.6,
                    "nac_p": 9,
                    "source": "adsb.lol",  # stamped at fetch site
                }
            ]
        )

        with _data_lock:
            published = list(latest_data.get("flights", []))
        assert len(published) == 1
        assert published[0]["source"] == "adsb.lol"
        # nac_p still flows through too — sanity check that adding source
        # didn't break the existing GPS jamming signal.
        assert published[0]["nac_p"] == 9

    def test_opensky_record_tagged_in_published_flight(self, monkeypatch):
        """OpenSky-sourced records carry ``source: 'OpenSky'`` (plus the
        existing ``is_opensky: True`` for back-compat)."""
        from services.fetchers import flights as flights_module
        from services.fetchers._store import latest_data, _data_lock

        self._reset_store()
        monkeypatch.setattr(flights_module, "lookup_route", lambda _: None)
        monkeypatch.setattr(flights_module, "lookup_aircraft_type", lambda _: "")

        flights_module._classify_and_publish(
            [
                {
                    "hex": "a12345",
                    "flight": "UAL100",
                    "r": "N100UA",
                    "t": "Unknown",
                    "lat": 41.0,
                    "lon": -87.0,
                    "alt_baro": 35000,
                    "gs": 450,
                    # No nac_p — OpenSky doesn't carry it.
                    "is_opensky": True,
                    "source": "OpenSky",
                }
            ]
        )

        with _data_lock:
            published = list(latest_data.get("flights", []))
        assert len(published) == 1
        assert published[0]["source"] == "OpenSky"

    def test_supplemental_source_propagates(self, monkeypatch):
        """Supplemental records (airplanes.live, adsb.fi) have their
        legacy ``supplemental_source`` field promoted to the unified
        ``source`` field in the published dict — so consumers don't have
        to inspect two different keys."""
        from services.fetchers import flights as flights_module
        from services.fetchers._store import latest_data, _data_lock

        self._reset_store()
        monkeypatch.setattr(flights_module, "lookup_route", lambda _: None)
        monkeypatch.setattr(flights_module, "lookup_aircraft_type", lambda _: "")

        flights_module._classify_and_publish(
            [
                {
                    "hex": "b22222",
                    "flight": "DAL200",
                    "r": "N200DL",
                    "t": "B738",
                    "lat": 42.0,
                    "lon": -90.0,
                    "alt_baro": 32000,
                    "gs": 420,
                    "supplemental_source": "airplanes.live",
                    # No explicit "source" — should fall through to
                    # supplemental_source.
                }
            ]
        )

        with _data_lock:
            published = list(latest_data.get("flights", []))
        assert len(published) == 1
        assert published[0]["source"] == "airplanes.live"

    def test_explicit_source_wins_over_supplemental_source(self, monkeypatch):
        """If both fields are present, explicit ``source`` wins (it's the
        newer canonical tag)."""
        from services.fetchers import flights as flights_module
        from services.fetchers._store import latest_data, _data_lock

        self._reset_store()
        monkeypatch.setattr(flights_module, "lookup_route", lambda _: None)
        monkeypatch.setattr(flights_module, "lookup_aircraft_type", lambda _: "")

        flights_module._classify_and_publish(
            [
                {
                    "hex": "c33333",
                    "flight": "AAL300",
                    "r": "N300AA",
                    "t": "A321",
                    "lat": 33.0,
                    "lon": -97.0,
                    "alt_baro": 34000,
                    "gs": 430,
                    "source": "adsb.lol",
                    "supplemental_source": "adsb.fi",
                }
            ]
        )

        with _data_lock:
            published = list(latest_data.get("flights", []))
        assert published[0]["source"] == "adsb.lol"

    def test_untagged_record_defaults_to_adsb_lol(self, monkeypatch):
        """A record with neither ``source`` nor ``supplemental_source``
        (e.g. synthesized by a test, or a fetcher that hasn't been
        migrated yet) defaults to ``"adsb.lol"`` since that's been the
        primary source historically. Defensive default — better than
        empty string."""
        from services.fetchers import flights as flights_module
        from services.fetchers._store import latest_data, _data_lock

        self._reset_store()
        monkeypatch.setattr(flights_module, "lookup_route", lambda _: None)
        monkeypatch.setattr(flights_module, "lookup_aircraft_type", lambda _: "")

        flights_module._classify_and_publish(
            [
                {
                    "hex": "d44444",
                    "flight": "SWA400",
                    "r": "N400SW",
                    "t": "B737",
                    "lat": 32.0,
                    "lon": -110.0,
                    "alt_baro": 30000,
                    "gs": 410,
                }
            ]
        )

        with _data_lock:
            published = list(latest_data.get("flights", []))
        assert published[0]["source"] == "adsb.lol"


# ---------------------------------------------------------------------------
# adsb.lol regional fetcher tags at fetch time
# ---------------------------------------------------------------------------


class TestAdsbLolRegionalTagging:
    def test_fetch_region_stamps_source_on_each_aircraft(self, monkeypatch):
        """The wrapper around the adsb.lol regional endpoint stamps
        ``source: 'adsb.lol'`` on every record before returning, so the
        downstream merge step sees attribution survive even when the
        record gets reshuffled (e.g. dedupe-by-hex during OpenSky merge)."""
        from services.fetchers import flights as flights_module

        # Fake response — 3 aircraft, none have a source field originally.
        class FakeResp:
            status_code = 200

            def json(self):
                return {
                    "ac": [
                        {"hex": "a1", "lat": 40.0, "lon": -100.0, "nac_p": 8},
                        {"hex": "a2", "lat": 40.1, "lon": -100.1, "nac_p": 9},
                        {"hex": "a3", "lat": 40.2, "lon": -100.2, "nac_p": 10},
                    ]
                }

        monkeypatch.setattr(
            flights_module, "fetch_with_curl", lambda *a, **kw: FakeResp()
        )

        results = flights_module._fetch_adsb_lol_regions()

        assert len(results) >= 3
        # Every aircraft we got back must be tagged.
        sources = {a.get("source") for a in results}
        assert sources == {"adsb.lol"}, (
            f"adsb.lol regional fetcher must stamp source on every record; "
            f"got: {sources}"
        )

    def test_fetch_region_failure_returns_empty_without_crashing(self, monkeypatch):
        """If adsb.lol returns non-200, the fetcher returns [] gracefully —
        downstream code already handles this. Sanity check that the source
        tagging doesn't introduce a new failure mode."""
        from services.fetchers import flights as flights_module

        class FakeResp:
            status_code = 500
            def json(self): return {}

        monkeypatch.setattr(
            flights_module, "fetch_with_curl", lambda *a, **kw: FakeResp()
        )

        results = flights_module._fetch_adsb_lol_regions()

        assert results == []


# ---------------------------------------------------------------------------
# Military fetcher tags source on output dicts
# ---------------------------------------------------------------------------


class TestMilitarySourceTagging:
    def test_military_output_carries_source_field(self, monkeypatch):
        """Each entry in ``military_flights`` should carry a ``source``
        field. Pre-fix the only military attribution was inferring from
        which endpoint we hit; now it's explicit."""
        from services.fetchers import military as mil_module
        from services.fetchers._store import latest_data, _data_lock

        # Reset relevant store state.
        with _data_lock:
            latest_data["military_flights"] = []
            latest_data["uavs"] = []
            latest_data["tracked_flights"] = []

        # Stub _store.is_any_active so the fetch doesn't early-return.
        # The military module imports the function inline at call time,
        # so we have to patch it on the _store module itself rather than
        # on the military module.
        from services.fetchers import _store as store_module
        monkeypatch.setattr(store_module, "is_any_active", lambda *_: True)

        # Stub fetch_with_curl to return one synthetic military aircraft
        # from adsb.lol, none from airplanes.live.
        class _RespMil:
            status_code = 200
            def json(self):
                return {
                    "ac": [
                        {
                            "hex": "ae6c1d",
                            "flight": "CRUSH52",
                            "r": "170281",
                            "t": "C30J",
                            "lat": 47.594,
                            "lon": -124.879,
                            "alt_baro": 9025,
                            "gs": 162.8,
                            "track": 334.5,
                            "nac_p": 10,
                        }
                    ]
                }

        class _RespEmpty:
            status_code = 200
            def json(self):
                return {"ac": []}

        def _fake_fetch(url, *a, **kw):
            if "adsb.lol" in url:
                return _RespMil()
            return _RespEmpty()

        monkeypatch.setattr(mil_module, "fetch_with_curl", _fake_fetch)
        # Stubs for downstream enrichments that try to hit external state.
        monkeypatch.setattr(mil_module, "enrich_with_plane_alert", lambda mf: None)
        monkeypatch.setattr(mil_module, "_enrich_country", lambda hex_, flag: ("US", "USAF"))
        monkeypatch.setattr(mil_module, "_classify_military_type", lambda t: "transport")
        monkeypatch.setattr(mil_module, "_classify_uav", lambda m, c: (False, "", ""))
        monkeypatch.setattr(mil_module, "get_emissions_info", lambda model: None)
        monkeypatch.setattr(mil_module, "_mark_fresh", lambda *keys: None)

        mil_module.fetch_military_flights()

        with _data_lock:
            mil_published = list(latest_data.get("military_flights", []))

        assert len(mil_published) == 1
        assert mil_published[0]["source"] == "adsb.lol"
