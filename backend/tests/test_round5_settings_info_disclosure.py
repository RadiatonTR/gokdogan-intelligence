"""Issues #243, #252, #253 (tg12): settings endpoints must not leak
operational posture to unauthenticated callers.

- **#243**: ``GET /api/settings/wormhole``, ``/api/settings/privacy-profile``,
  and ``/api/settings/node`` were leaking transport choice, anonymous-mode
  state, the named privacy profile, and node-participant state to any
  unauthenticated caller. The fix tightens the redaction allowlists to
  expose ONLY a bare "is this feature on?" boolean and gates node mode
  behind authenticated reads.

- **#252**: ``GET /api/settings/news-feeds`` returned the operator's full
  curated feed inventory (names + URLs) to anyone. Now gated on
  local-operator.

- **#253**: ``GET /api/settings/timemachine`` returned whether archival
  capture is enabled to anyone. Now gated on local-operator.

Auth model: ``require_local_operator`` allows loopback (Tauri shell),
the Docker bridge frontend container (via the hostname-bound trust from
PR #278), and any caller that presents the configured admin key.
Anonymous LAN or internet callers do NOT pass and either receive 403
(news-feeds, timemachine) or a redacted minimum (wormhole / node).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


_ADMIN_KEY = "test-admin-key-for-round5-fixture-32+chars"


@pytest.fixture
def client():
    """TestClient with the private-lane transport middleware disabled.

    Same shape as the oracle resolve fixture — the mesh privacy
    middleware returns 202 for ``/api/settings/*`` under TestClient
    because Wormhole is not actually running. Patching out the tier
    requirement lets requests reach the route's auth gate.
    """
    import main
    with patch("main._minimum_transport_tier", return_value=None):
        yield TestClient(main.app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# #243: Wormhole posture redaction
# ---------------------------------------------------------------------------


class TestWormholeSettingsRedaction:
    """``GET /api/settings/wormhole`` must NOT leak transport choice or
    anonymous-mode state to unauthenticated callers."""

    def _read_settings_payload(self):
        return {
            "enabled": True,
            "transport": "tor_arti",
            "anonymous_mode": True,
            "privacy_profile": "high",
            "socks_proxy": "socks5h://127.0.0.1:9050",
        }

    def test_anonymous_caller_sees_only_enabled_bool(self, client):
        with (
            patch("main.read_wormhole_settings", return_value=self._read_settings_payload()),
            patch("routers.wormhole.read_wormhole_settings", return_value=self._read_settings_payload()),
            patch("services.wormhole_settings.read_wormhole_settings", return_value=self._read_settings_payload()),
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get("/api/settings/wormhole")
        assert r.status_code == 200
        body = r.json()
        # Only the bare "is Wormhole on?" boolean is exposed publicly.
        assert "enabled" in body
        assert body["enabled"] is True
        # Posture fields the audit flagged must be absent.
        assert "transport" not in body
        assert "anonymous_mode" not in body
        assert "privacy_profile" not in body
        assert "socks_proxy" not in body

    def test_authenticated_caller_sees_full_state(self, client):
        with (
            patch("main.read_wormhole_settings", return_value=self._read_settings_payload()),
            patch("routers.wormhole.read_wormhole_settings", return_value=self._read_settings_payload()),
            patch("services.wormhole_settings.read_wormhole_settings", return_value=self._read_settings_payload()),
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get(
                "/api/settings/wormhole",
                headers={"X-Admin-Key": _ADMIN_KEY},
            )
        assert r.status_code == 200
        body = r.json()
        # All fields visible when authenticated.
        assert body["enabled"] is True
        assert body["transport"] == "tor_arti"
        assert body["anonymous_mode"] is True
        assert body["privacy_profile"] == "high"


class TestPrivacyProfileRedaction:
    """``GET /api/settings/privacy-profile`` must NOT leak the named
    profile to unauthenticated callers (the profile name itself
    discloses operator intent)."""

    def _payload(self):
        return {
            "enabled": True,
            "transport": "tor_arti",
            "anonymous_mode": True,
            "privacy_profile": "high",
        }

    def test_anonymous_caller_sees_only_wormhole_enabled_bool(self, client):
        with (
            patch("main.read_wormhole_settings", return_value=self._payload()),
            patch("routers.wormhole.read_wormhole_settings", return_value=self._payload()),
            patch("services.wormhole_settings.read_wormhole_settings", return_value=self._payload()),
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get("/api/settings/privacy-profile")
        assert r.status_code == 200
        body = r.json()
        assert "wormhole_enabled" in body
        assert body["wormhole_enabled"] is True
        # The named profile, transport, and anonymous mode must NOT
        # leak to anonymous callers.
        assert "profile" not in body or body.get("profile") is None
        assert "transport" not in body
        assert "anonymous_mode" not in body

    def test_authenticated_caller_sees_named_profile_and_transport(self, client):
        with (
            patch("main.read_wormhole_settings", return_value=self._payload()),
            patch("routers.wormhole.read_wormhole_settings", return_value=self._payload()),
            patch("services.wormhole_settings.read_wormhole_settings", return_value=self._payload()),
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get(
                "/api/settings/privacy-profile",
                headers={"X-Admin-Key": _ADMIN_KEY},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["profile"] == "high"
        assert body["wormhole_enabled"] is True
        assert body["transport"] == "tor_arti"
        assert body["anonymous_mode"] is True


class TestNodeSettingsRedaction:
    """``GET /api/settings/node`` must NOT disclose node_mode or
    node_enabled to anonymous callers."""

    def _node_data(self):
        return {"some_node_field": "value"}

    def test_anonymous_caller_sees_empty_stub(self, client):
        with (
            patch("services.node_settings.read_node_settings", return_value=self._node_data()),
            patch("routers.admin._current_node_mode", return_value="participant"),
            patch("routers.admin._participant_node_enabled", return_value=True),
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get("/api/settings/node")
        assert r.status_code == 200
        body = r.json()
        # No posture fields.
        assert "node_mode" not in body
        assert "node_enabled" not in body
        assert "some_node_field" not in body

    def test_authenticated_caller_sees_full_node_state(self, client):
        with (
            patch("services.node_settings.read_node_settings", return_value=self._node_data()),
            patch("routers.admin._current_node_mode", return_value="participant"),
            patch("routers.admin._participant_node_enabled", return_value=True),
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get(
                "/api/settings/node",
                headers={"X-Admin-Key": _ADMIN_KEY},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["node_mode"] == "participant"
        assert body["node_enabled"] is True
        assert body["some_node_field"] == "value"


# ---------------------------------------------------------------------------
# #252: news-feeds auth gate
# ---------------------------------------------------------------------------


class TestNewsFeedsAuthGate:
    def _fake_feeds(self):
        return [
            {"name": "Custom Internal", "url": "https://internal.example/rss", "weight": 5},
            {"name": "Default News", "url": "https://news.example/rss", "weight": 3},
        ]

    def test_anonymous_caller_rejected(self, client):
        with (
            patch("services.news_feed_config.get_feeds", return_value=self._fake_feeds()) as get_feeds,
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get("/api/settings/news-feeds")
        assert r.status_code == 403
        # Critically: the underlying config read must NOT have been performed
        # (else the response body could leak the count via response timing).
        assert get_feeds.call_count == 0

    def test_authenticated_caller_sees_full_feed_inventory(self, client):
        with (
            patch("services.news_feed_config.get_feeds", return_value=self._fake_feeds()),
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get(
                "/api/settings/news-feeds",
                headers={"X-Admin-Key": _ADMIN_KEY},
            )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 2
        assert body[0]["name"] == "Custom Internal"
        assert body[0]["url"] == "https://internal.example/rss"


# ---------------------------------------------------------------------------
# #253: timemachine auth gate
# ---------------------------------------------------------------------------


class TestTimemachineAuthGate:
    def test_anonymous_caller_rejected(self, client):
        node_data = {"timemachine_enabled": True}
        with (
            patch("services.node_settings.read_node_settings", return_value=node_data),
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get("/api/settings/timemachine")
        assert r.status_code == 403

    def test_authenticated_caller_sees_enabled_state(self, client):
        node_data = {"timemachine_enabled": True}
        with (
            patch("services.node_settings.read_node_settings", return_value=node_data),
            patch("auth._current_admin_key", return_value=_ADMIN_KEY),
        ):
            r = client.get(
                "/api/settings/timemachine",
                headers={"X-Admin-Key": _ADMIN_KEY},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert "storage_warning" in body
