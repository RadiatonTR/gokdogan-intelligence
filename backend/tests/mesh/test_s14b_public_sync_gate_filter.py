"""S14B private sync gate event policy.

Private Infonet sync carries encrypted gate_message ledger events. If a node
is configured to allow clearnet-compatible sync, those gate events are filtered
out of the sync response.
"""

import asyncio
import base64
import json

from starlette.requests import Request

import main
from services.mesh import mesh_hashchain


def _message_event() -> dict:
    return {
        "event_id": "msg-1",
        "event_type": "message",
        "node_id": "!node-1",
        "payload": {"text": "hello world"},
        "timestamp": 100.0,
        "sequence": 1,
        "signature": "sig",
        "public_key": "pub",
        "public_key_algo": "Ed25519",
        "protocol_version": "infonet/2",
    }


def _vote_event() -> dict:
    return {
        "event_id": "vote-1",
        "event_type": "vote",
        "node_id": "!node-2",
        "payload": {"gate": "finance", "vote": 1},
        "timestamp": 101.0,
        "sequence": 2,
        "signature": "sig",
        "public_key": "pub",
        "public_key_algo": "Ed25519",
        "protocol_version": "infonet/2",
    }


def _key_rotate_event() -> dict:
    return {
        "event_id": "rotate-1",
        "event_type": "key_rotate",
        "node_id": "!node-3",
        "payload": {
            "old_node_id": "!old-node",
            "old_public_key": "old-pub",
            "old_public_key_algo": "Ed25519",
            "old_signature": "old-sig",
            "timestamp": 123,
        },
        "timestamp": 102.0,
        "sequence": 3,
        "signature": "sig",
        "public_key": "pub",
        "public_key_algo": "Ed25519",
        "protocol_version": "infonet/2",
    }


def _gate_message_event() -> dict:
    return {
        "event_id": "gate-1",
        "event_type": "gate_message",
        "node_id": "!node-4",
        "payload": {
            "gate": "finance",
            "ciphertext": "opaque-blob",
            "epoch": 2,
            "nonce": "nonce-1",
            "sender_ref": "sender-ref-1",
            "format": "mls1",
            "transport_lock": "private_strong",
        },
        "timestamp": 103.0,
        "sequence": 4,
        "signature": "sig",
        "public_key": "pub",
        "public_key_algo": "Ed25519",
        "protocol_version": "infonet/2",
    }


def _dm_message_event() -> dict:
    return {
        "event_id": "dm-1",
        "event_type": "dm_message",
        "node_id": "!node-5",
        "payload": {
            "recipient_id": "recipient-a",
            "delivery_class": "request",
            "recipient_token": "",
            "ciphertext": base64.b64encode(b"sealed-dm-ciphertext").decode("ascii"),
            "msg_id": "dm-1",
            "timestamp": 104,
            "format": "mls1",
            "transport_lock": "private_strong",
        },
        "timestamp": 104.0,
        "sequence": 5,
        "signature": "sig",
        "public_key": "pub",
        "public_key_algo": "Ed25519",
        "protocol_version": "infonet/2",
    }


class _FakeInfonet:
    def __init__(self):
        self.head_hash = "head-1"
        self.events = [
            _message_event(),
            _vote_event(),
            _key_rotate_event(),
            _gate_message_event(),
        ]

    @staticmethod
    def _limit_value(limit) -> int:
        try:
            return int(limit)
        except Exception:
            return int(getattr(limit, "default", 100) or 100)

    def get_events_after(self, after_hash: str, limit=100):
        return [dict(e) for e in self.events[: self._limit_value(limit)]]

    def get_events_after_locator(self, locator: list[str], limit=100):
        return self.head_hash, 0, [dict(e) for e in self.events[: self._limit_value(limit)]]

    def get_merkle_proofs(self, start_index: int, count: int):
        return {"root": "merkle-root", "total": len(self.events), "start": start_index, "proofs": []}

    def get_merkle_root(self):
        return "merkle-root"


def _json_request(path: str, body: dict, *, client_host: str = "127.0.0.1", headers: dict[str, str] | None = None) -> Request:
    payload = json.dumps(body).encode("utf-8")
    sent = {"value": False}

    async def receive():
        if sent["value"]:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent["value"] = True
        return {"type": "http.request", "body": payload, "more_body": False}

    raw_headers = [(b"content-type", b"application/json")]
    for key, value in dict(headers or {}).items():
        raw_headers.append((key.lower().encode("ascii"), str(value).encode("ascii")))
    return Request(
        {
            "type": "http",
            "headers": raw_headers,
            "client": (client_host, 12345),
            "method": "POST",
            "path": path,
        },
        receive,
    )


def _get_request(path: str, *, client_host: str = "127.0.0.1", headers: dict[str, str] | None = None) -> Request:
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(
        {
            "type": "http",
            "headers": [(key.lower().encode("ascii"), str(value).encode("ascii")) for key, value in dict(headers or {}).items()],
            "client": (client_host, 12345),
            "method": "GET",
            "path": path,
        },
        receive,
    )


def _force_private_sync(monkeypatch):
    monkeypatch.setattr(main, "_infonet_private_transport_required", lambda: True)
    monkeypatch.setattr(main, "_request_appears_private_infonet_transport", lambda request: True)


def _force_private_policy_only(monkeypatch):
    monkeypatch.setattr(main, "_infonet_private_transport_required", lambda: True)


def _force_clearnet_sync(monkeypatch):
    monkeypatch.setattr(main, "_infonet_private_transport_required", lambda: False)


def _event_types(events: list[dict]) -> list[str]:
    return [str(e.get("event_type", "")) for e in events]


def test_private_sync_redacts_private_events_from_exposed_clearnet_request(monkeypatch):
    _force_private_policy_only(monkeypatch)
    request = _get_request("/api/mesh/infonet/sync", client_host="203.0.113.10")

    events = main._infonet_sync_response_events(
        [_message_event(), _gate_message_event(), _dm_message_event()],
        request=request,
    )

    assert _event_types(events) == ["message"]


def test_private_sync_includes_private_events_for_loopback_request(monkeypatch):
    _force_private_policy_only(monkeypatch)
    request = _get_request("/api/mesh/infonet/sync", client_host="127.0.0.1")

    events = main._infonet_sync_response_events(
        [_message_event(), _gate_message_event(), _dm_message_event()],
        request=request,
    )

    assert _event_types(events) == ["message", "gate_message", "dm_message"]


def test_private_sync_redacts_private_events_when_forwarded_for_is_clearnet(monkeypatch):
    _force_private_policy_only(monkeypatch)
    request = _get_request(
        "/api/mesh/infonet/sync",
        client_host="127.0.0.1",
        headers={"x-forwarded-for": "198.51.100.44"},
    )

    events = main._infonet_sync_response_events(
        [_message_event(), _gate_message_event(), _dm_message_event()],
        request=request,
    )

    assert _event_types(events) == ["message"]


def test_get_sync_includes_gate_message_on_private_transport(client, monkeypatch):
    _force_private_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _FakeInfonet(), raising=False)

    data = client.get("/api/mesh/infonet/sync").json()

    assert "gate_message" in _event_types(data["events"])
    assert data["count"] == 4


def test_post_sync_includes_gate_message_on_private_transport(monkeypatch):
    _force_private_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _FakeInfonet(), raising=False)

    result = asyncio.run(
        main.infonet_sync_post(
            _json_request("/api/mesh/infonet/sync", {"locator": ["head-1"]})
        )
    )

    assert "gate_message" in _event_types(result["events"])
    assert result["count"] == 4


def test_router_get_sync_includes_gate_message_on_private_transport(monkeypatch):
    from routers.mesh_public import infonet_sync

    _force_private_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _FakeInfonet(), raising=False)

    result = asyncio.run(infonet_sync(_get_request("/api/mesh/infonet/sync")))

    assert "gate_message" in _event_types(result["events"])
    assert result["count"] == len(result["events"])


def test_router_post_sync_includes_gate_message_on_private_transport(monkeypatch):
    from routers.mesh_public import infonet_sync_post

    _force_private_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _FakeInfonet(), raising=False)

    result = asyncio.run(
        infonet_sync_post(
            _json_request("/api/mesh/infonet/sync", {"locator": ["head-1"]})
        )
    )

    assert "gate_message" in _event_types(result["events"])
    assert result["count"] == len(result["events"])


def test_get_sync_excludes_gate_message_when_clearnet_sync_allowed(client, monkeypatch):
    _force_clearnet_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _FakeInfonet(), raising=False)

    data = client.get("/api/mesh/infonet/sync").json()

    assert "gate_message" not in _event_types(data["events"])
    assert data["count"] == 3


def test_post_sync_excludes_gate_message_when_clearnet_sync_allowed(monkeypatch):
    _force_clearnet_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _FakeInfonet(), raising=False)

    result = asyncio.run(
        main.infonet_sync_post(
            _json_request("/api/mesh/infonet/sync", {"locator": ["head-1"]})
        )
    )

    assert "gate_message" not in _event_types(result["events"])
    assert result["count"] == 3


def test_get_sync_still_redacts_vote_gate_label(client, monkeypatch):
    _force_private_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _FakeInfonet(), raising=False)

    events = client.get("/api/mesh/infonet/sync").json()["events"]
    vote = next(e for e in events if e["event_type"] == "vote")

    assert "gate" not in vote.get("payload", {})


def test_get_sync_still_redacts_key_rotate_identity(client, monkeypatch):
    _force_private_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _FakeInfonet(), raising=False)

    events = client.get("/api/mesh/infonet/sync").json()["events"]
    rotate = next(e for e in events if e["event_type"] == "key_rotate")
    payload = rotate.get("payload", {})

    assert "old_node_id" not in payload
    assert "old_public_key" not in payload
    assert "old_signature" not in payload


def test_post_sync_still_redacts_vote_and_rotate(monkeypatch):
    _force_private_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _FakeInfonet(), raising=False)

    result = asyncio.run(
        main.infonet_sync_post(
            _json_request("/api/mesh/infonet/sync", {"locator": ["head-1"]})
        )
    )
    vote = next(e for e in result["events"] if e["event_type"] == "vote")
    rotate = next(e for e in result["events"] if e["event_type"] == "key_rotate")

    assert "gate" not in vote.get("payload", {})
    assert "old_node_id" not in rotate.get("payload", {})


def test_gate_message_still_in_fake_infonet_storage():
    fake = _FakeInfonet()
    assert "gate_message" in _event_types(fake.events)


def test_private_sync_with_only_gate_messages_returns_gate_events(client, monkeypatch):
    class _GateOnlyInfonet:
        head_hash = "head-1"
        events = [_gate_message_event()]

        def get_events_after(self, after_hash, limit=100):
            return [dict(e) for e in self.events]

        def get_events_after_locator(self, locator, limit=100):
            return self.head_hash, 0, [dict(e) for e in self.events]

        def get_merkle_proofs(self, start_index, count):
            return {"root": "r", "total": 1, "start": 0, "proofs": []}

        def get_merkle_root(self):
            return "r"

    _force_private_sync(monkeypatch)
    monkeypatch.setattr(mesh_hashchain, "infonet", _GateOnlyInfonet(), raising=False)

    data = client.get("/api/mesh/infonet/sync").json()

    assert _event_types(data["events"]) == ["gate_message"]
    assert data["count"] == 1
