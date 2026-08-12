"""POST /api/mesh/dm/replicate-envelope — receiving side of cross-node DM
mailbox replication.

This is the endpoint that peer relays call when they want to hand off an
encrypted DM envelope to us (so the recipient can log into our node and
find their messages). It re-enforces the per-(sender, recipient) anti-spam
cap so hostile sender relays can't widen the cap by skipping the local
check on their own deposit path.

The endpoint:

  * authenticates the caller via the existing per-peer HMAC pattern
    (same one /api/mesh/infonet/peer-push and /api/mesh/gate/peer-push
    use, introduced in #256 — ``X-Peer-Url`` + ``X-Peer-HMAC`` headers
    keyed off ``resolve_peer_key_for_url``)
  * rejects bodies > 64 KB (DM envelope size is bounded by
    ``MESH_DM_MAX_MSG_BYTES`` — 64KB ceiling has generous headroom)
  * rejects requests without a valid peer HMAC with 403
  * passes the envelope to ``DMRelay.accept_replica`` which enforces
    the cap

This file pins the endpoint contract. The cap enforcement itself is
tested in ``test_dm_relay_per_sender_cap.py`` against the relay's
``accept_replica`` method directly.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def remote_client():
    """ASGI client with peer IP 1.2.3.4 — never on the local-operator
    allowlist. Used to prove the endpoint isn't accidentally reachable
    by random remote callers without peer HMAC."""
    from main import app

    class _RemoteClient:
        def __init__(self):
            self._loop = asyncio.new_event_loop()
            self._transport = ASGITransport(app=app, client=("1.2.3.4", 12345))
            self._base = "http://1.2.3.4:8000"

        def post(self, url, **kw):
            async def go():
                async with AsyncClient(transport=self._transport, base_url=self._base) as ac:
                    return await ac.post(url, **kw)
            return self._loop.run_until_complete(go())

        def close(self):
            self._loop.close()

    c = _RemoteClient()
    yield c
    c.close()


class TestReplicateEndpointAuth:
    def test_rejects_request_without_peer_hmac(self, remote_client):
        """A peer push that does NOT carry X-Peer-Url + X-Peer-HMAC
        must be rejected with 403 before the envelope is ever passed
        to the relay. Same gate the existing infonet/gate peer-push
        endpoints enforce."""
        payload = {
            "envelope": {
                "msg_id": "dm_unauth_1",
                "mailbox_key": "mb",
                "sender_block_ref": "sender",
                "ciphertext": "x",
            },
        }
        r = remote_client.post(
            "/api/mesh/dm/replicate-envelope",
            json=payload,
        )
        assert r.status_code == 403
        assert "peer HMAC" in r.text or "peer hmac" in r.text.lower()

    def test_rejects_wrong_peer_hmac(self, remote_client, monkeypatch):
        """A request with a peer HMAC header keyed off the WRONG secret
        is rejected. Confirms the HMAC is actually verified — a tampered
        body or a key-substitution attack doesn't sneak through."""
        # Plant a known peer secret. The request will sign with a
        # DIFFERENT key, so verification must fail.
        from services.config import get_settings
        monkeypatch.setenv("MESH_PEER_PUSH_SECRET", "real-secret-32-chars-min-padding-padding")
        get_settings.cache_clear()

        body = json.dumps({
            "envelope": {
                "msg_id": "dm_wronghmac",
                "mailbox_key": "mb",
                "sender_block_ref": "sender",
                "ciphertext": "x",
            },
        }).encode("utf-8")
        wrong_hmac = hmac.new(b"wrong-key", body, hashlib.sha256).hexdigest()
        r = remote_client.post(
            "/api/mesh/dm/replicate-envelope",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Peer-Url": "http://example-peer.onion:8000",
                "X-Peer-HMAC": wrong_hmac,
            },
        )
        assert r.status_code == 403

    def test_rejects_oversize_body(self, remote_client):
        """64 KB ceiling — anything bigger doesn't even get parsed.
        Defends against memory amplification via giant ciphertexts."""
        # 100 KB body is well over the 64 KB cap.
        big = b"{" + b"x" * 100_000 + b"}"
        r = remote_client.post(
            "/api/mesh/dm/replicate-envelope",
            content=big,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(big)),
            },
        )
        assert r.status_code in (400, 413), (
            f"oversize body should be rejected with 400/413, got {r.status_code}"
        )


class TestReplicateEndpointRegistered:
    def test_route_present_in_app(self):
        """Static check that the route is actually wired into the app.
        Catches a future refactor that drops the router include or
        deletes the endpoint by accident."""
        from main import app

        paths_methods = set()
        for route in app.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", set()) or set()
            for m in methods:
                paths_methods.add((m, path))

        assert ("POST", "/api/mesh/dm/replicate-envelope") in paths_methods, (
            "POST /api/mesh/dm/replicate-envelope is not registered on the app"
        )
