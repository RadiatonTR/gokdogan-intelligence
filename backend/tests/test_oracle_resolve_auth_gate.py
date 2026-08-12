"""Issues #240 & #241 (tg12): oracle market/stake resolution endpoints
must require admin authentication.

Before the fix, ``POST /api/mesh/oracle/resolve`` and
``POST /api/mesh/oracle/resolve-stakes`` were decorated with
``@mesh_write_exempt(MeshWriteExemption.ADMIN_CONTROL)``. That decorator
only tags the route as not requiring a mesh signed-write envelope; it
does NOT enforce authorization. The rate limiter (5/minute) was the
only real gate, which is wrong for control-plane state mutations.

The fix adds ``dependencies=[Depends(require_admin)]`` to both routes.
These tests prove:

- Anonymous callers receive 403.
- A request bearing the configured admin key passes the auth gate.
- The underlying ledger mutator is not invoked on a 403.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


_ADMIN_KEY = "test-admin-key-for-oracle-resolve-fixture-32+"


@pytest.fixture
def client():
    """TestClient with the private-lane transport middleware short-circuited.

    The ``enforce_high_privacy_mesh`` middleware in ``main.py`` returns
    HTTP 202 ("preparing private lane") for ``/api/mesh/*`` requests
    when the Wormhole supervisor is not yet at the required transport
    tier. In tests that's always — Wormhole is not running. Patching
    ``_minimum_transport_tier`` to return None disables the tier check
    for the duration of the test, letting the request reach the route
    (and therefore reach the ``Depends(require_admin)`` we are testing).
    """
    import main
    with patch("main._minimum_transport_tier", return_value=None):
        yield TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def mock_ledger():
    """Replace oracle_ledger methods so tests don't mutate persistent state.

    The handler does ``from services.mesh.mesh_oracle import oracle_ledger``
    at call time, so we patch the module attribute.
    """
    fake = MagicMock()
    fake.resolve_market.return_value = (0, 0)
    fake.resolve_market_stakes.return_value = {"winners": 0, "losers": 0}
    fake.resolve_expired_stakes.return_value = []
    with patch("services.mesh.mesh_oracle.oracle_ledger", fake):
        yield fake


# ---------------------------------------------------------------------------
# /api/mesh/oracle/resolve — issue #240
# ---------------------------------------------------------------------------


class TestOracleResolveAuthGate:
    def test_anonymous_caller_is_rejected(self, client, mock_ledger):
        with patch("auth._current_admin_key", return_value=_ADMIN_KEY):
            r = client.post(
                "/api/mesh/oracle/resolve",
                json={"market_title": "test-market", "outcome": "Yes"},
            )
        assert r.status_code == 403
        # Critically: the ledger mutator must NOT have been called on a 403.
        assert mock_ledger.resolve_market.call_count == 0
        assert mock_ledger.resolve_market_stakes.call_count == 0

    def test_wrong_admin_key_rejected(self, client, mock_ledger):
        with patch("auth._current_admin_key", return_value=_ADMIN_KEY):
            r = client.post(
                "/api/mesh/oracle/resolve",
                headers={"X-Admin-Key": "this-key-is-wrong"},
                json={"market_title": "test-market", "outcome": "Yes"},
            )
        assert r.status_code == 403
        assert mock_ledger.resolve_market.call_count == 0

    def test_valid_admin_key_passes_auth_gate(self, client, mock_ledger):
        with patch("auth._current_admin_key", return_value=_ADMIN_KEY):
            r = client.post(
                "/api/mesh/oracle/resolve",
                headers={"X-Admin-Key": _ADMIN_KEY},
                json={"market_title": "test-market", "outcome": "Yes"},
            )
        # The auth gate let us through. The handler ran and called the
        # (mocked) ledger.
        assert r.status_code == 200
        assert mock_ledger.resolve_market.call_count == 1
        assert mock_ledger.resolve_market.call_args[0] == ("test-market", "Yes")

    def test_admin_key_unset_blocks_in_production_posture(self, client, mock_ledger):
        """When ADMIN_KEY env is not configured at all and we're not in
        debug, the endpoint must still refuse — never silently accept."""
        with (
            patch("auth._current_admin_key", return_value=""),
            patch("auth._allow_insecure_admin", return_value=False),
            patch("auth._debug_mode_enabled", return_value=False),
            patch("auth._scoped_admin_tokens", return_value={}),
        ):
            r = client.post(
                "/api/mesh/oracle/resolve",
                json={"market_title": "test-market", "outcome": "Yes"},
            )
        assert r.status_code == 403
        assert mock_ledger.resolve_market.call_count == 0


# ---------------------------------------------------------------------------
# /api/mesh/oracle/resolve-stakes — issue #241
# ---------------------------------------------------------------------------


class TestOracleResolveStakesAuthGate:
    def test_anonymous_caller_is_rejected(self, client, mock_ledger):
        with patch("auth._current_admin_key", return_value=_ADMIN_KEY):
            r = client.post("/api/mesh/oracle/resolve-stakes")
        assert r.status_code == 403
        assert mock_ledger.resolve_expired_stakes.call_count == 0

    def test_wrong_admin_key_rejected(self, client, mock_ledger):
        with patch("auth._current_admin_key", return_value=_ADMIN_KEY):
            r = client.post(
                "/api/mesh/oracle/resolve-stakes",
                headers={"X-Admin-Key": "nope"},
            )
        assert r.status_code == 403
        assert mock_ledger.resolve_expired_stakes.call_count == 0

    def test_valid_admin_key_passes_auth_gate(self, client, mock_ledger):
        with patch("auth._current_admin_key", return_value=_ADMIN_KEY):
            r = client.post(
                "/api/mesh/oracle/resolve-stakes",
                headers={"X-Admin-Key": _ADMIN_KEY},
            )
        assert r.status_code == 200
        assert mock_ledger.resolve_expired_stakes.call_count == 1
        body = r.json()
        assert body["ok"] is True
        assert body["count"] == 0

    def test_admin_key_unset_blocks_in_production_posture(self, client, mock_ledger):
        with (
            patch("auth._current_admin_key", return_value=""),
            patch("auth._allow_insecure_admin", return_value=False),
            patch("auth._debug_mode_enabled", return_value=False),
            patch("auth._scoped_admin_tokens", return_value={}),
        ):
            r = client.post("/api/mesh/oracle/resolve-stakes")
        assert r.status_code == 403
        assert mock_ledger.resolve_expired_stakes.call_count == 0
