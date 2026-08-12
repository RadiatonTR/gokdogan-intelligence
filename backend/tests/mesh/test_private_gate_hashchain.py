import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from services.mesh import mesh_crypto, mesh_hashchain, mesh_protocol


def _keypair():
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key = base64.b64encode(public_raw).decode("utf-8")
    node_id = mesh_crypto.derive_node_id(public_key)
    return private_key, public_key, node_id


def _sign(private_key, *, event_type: str, node_id: str, sequence: int, payload: dict) -> str:
    signature_payload = mesh_crypto.build_signature_payload(
        event_type=event_type,
        node_id=node_id,
        sequence=sequence,
        payload=payload,
    )
    return private_key.sign(signature_payload.encode("utf-8")).hex()


def _message_payload(text: str) -> dict:
    return mesh_protocol.normalize_payload(
        "message",
        {
            "message": text,
            "destination": "broadcast",
            "channel": "LongFast",
            "priority": "normal",
            "ephemeral": False,
        },
    )


def _gate_payload(gate_id: str = "ops-gate", *, epoch: int = 2, plaintext: bool = False) -> dict:
    payload = {
        "gate": gate_id,
        "ciphertext": base64.b64encode(b"encrypted-gate-ciphertext").decode("ascii"),
        "nonce": base64.b64encode(b"nonce-value-1234").decode("ascii"),
        "sender_ref": "sender-ref-1",
        "format": "mls1",
        "transport_lock": "private_strong",
    }
    if epoch > 0:
        payload["epoch"] = epoch
    if plaintext:
        payload["message"] = "this must never land on the chain"
    return mesh_protocol.normalize_payload("gate_message", payload) if not plaintext else payload


def _gate_event(
    private_key,
    public_key: str,
    node_id: str,
    *,
    sequence: int,
    prev_hash: str,
    payload: dict,
    signature_payload: dict | None = None,
) -> dict:
    signature = _sign(
        private_key,
        event_type="gate_message",
        node_id=node_id,
        sequence=sequence,
        payload=signature_payload or payload,
    )
    return mesh_hashchain.ChainEvent(
        prev_hash=prev_hash,
        event_type="gate_message",
        node_id=node_id,
        payload=payload,
        timestamp=1234.0 + sequence,
        sequence=sequence,
        signature=signature,
        public_key=public_key,
        public_key_algo="Ed25519",
        protocol_version=mesh_protocol.PROTOCOL_VERSION,
        network_id=mesh_protocol.NETWORK_ID,
    ).to_dict()


def _fresh_infonet(tmp_path, monkeypatch) -> mesh_hashchain.Infonet:
    monkeypatch.setattr(mesh_hashchain, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mesh_hashchain, "CHAIN_FILE", tmp_path / "infonet.json")
    monkeypatch.setattr(mesh_hashchain, "WAL_FILE", tmp_path / "infonet.wal")
    return mesh_hashchain.Infonet()


def test_private_gate_fork_uses_gate_sequence_domain_and_signature_variants(tmp_path, monkeypatch):
    inf = _fresh_infonet(tmp_path, monkeypatch)
    private_key, public_key, node_id = _keypair()

    public_payload = _message_payload("public prefix")
    public_event = inf.append(
        event_type="message",
        node_id=node_id,
        payload=public_payload,
        sequence=1,
        signature=_sign(
            private_key,
            event_type="message",
            node_id=node_id,
            sequence=1,
            payload=public_payload,
        ),
        public_key=public_key,
        public_key_algo="Ed25519",
        protocol_version=mesh_protocol.PROTOCOL_VERSION,
    )

    gate_payload = _gate_payload(epoch=3)
    signature_payload = dict(gate_payload)
    signature_payload.pop("epoch", None)
    gate_event = _gate_event(
        private_key,
        public_key,
        node_id,
        sequence=1,
        prev_hash=public_event["event_id"],
        payload=gate_payload,
        signature_payload=signature_payload,
    )

    ok, reason = inf.apply_fork([gate_event], gate_event["event_id"], proof_count=2, quorum=2)

    assert ok is True, reason
    assert inf.events[-1]["event_type"] == "gate_message"
    assert inf.node_sequences[node_id] == 1
    assert inf.sequence_domains[f"{node_id}|gate_message"] == 1
    assert inf.validate_chain(verify_signatures=True)[0] is True


def test_private_gate_fork_rejects_plaintext_payload(tmp_path, monkeypatch):
    inf = _fresh_infonet(tmp_path, monkeypatch)
    private_key, public_key, node_id = _keypair()

    public_payload = _message_payload("public prefix")
    public_event = inf.append(
        event_type="message",
        node_id=node_id,
        payload=public_payload,
        sequence=1,
        signature=_sign(
            private_key,
            event_type="message",
            node_id=node_id,
            sequence=1,
            payload=public_payload,
        ),
        public_key=public_key,
        public_key_algo="Ed25519",
        protocol_version=mesh_protocol.PROTOCOL_VERSION,
    )

    plaintext_payload = _gate_payload(plaintext=True)
    gate_event = _gate_event(
        private_key,
        public_key,
        node_id,
        sequence=1,
        prev_hash=public_event["event_id"],
        payload=plaintext_payload,
    )

    ok, reason = inf.apply_fork([gate_event], gate_event["event_id"], proof_count=2, quorum=2)

    assert ok is False
    assert "normalized" in reason or "plaintext" in reason
    assert len(inf.events) == 1
    assert "gate_message" not in inf.get_info()["event_types"]


def test_append_private_gate_message_rejects_plaintext_before_normalizing(tmp_path, monkeypatch):
    inf = _fresh_infonet(tmp_path, monkeypatch)
    private_key, public_key, node_id = _keypair()
    payload = _gate_payload()
    payload["message"] = "plaintext should not be silently dropped"

    try:
        inf.append_private_gate_message(
            node_id=node_id,
            payload=payload,
            sequence=1,
            signature=_sign(
                private_key,
                event_type="gate_message",
                node_id=node_id,
                sequence=1,
                payload=_gate_payload(),
            ),
            public_key=public_key,
            public_key_algo="Ed25519",
            protocol_version=mesh_protocol.PROTOCOL_VERSION,
        )
    except ValueError as exc:
        assert "plaintext" in str(exc)
    else:
        raise AssertionError("private gate append accepted plaintext")

    assert inf.events == []


def test_append_private_gate_message_requires_private_strong_transport_lock(tmp_path, monkeypatch):
    inf = _fresh_infonet(tmp_path, monkeypatch)
    private_key, public_key, node_id = _keypair()
    payload = _gate_payload()
    payload.pop("transport_lock", None)

    try:
        inf.append_private_gate_message(
            node_id=node_id,
            payload=payload,
            sequence=1,
            signature=_sign(
                private_key,
                event_type="gate_message",
                node_id=node_id,
                sequence=1,
                payload=_gate_payload(),
            ),
            public_key=public_key,
            public_key_algo="Ed25519",
            protocol_version=mesh_protocol.PROTOCOL_VERSION,
        )
    except ValueError as exc:
        assert "private_strong" in str(exc)
    else:
        raise AssertionError("private gate append accepted missing transport_lock")

    assert inf.events == []


def test_append_private_gate_message_rejects_non_sealed_ciphertext_shape(tmp_path, monkeypatch):
    inf = _fresh_infonet(tmp_path, monkeypatch)
    private_key, public_key, node_id = _keypair()
    payload = _gate_payload()
    payload["ciphertext"] = "not sealed plaintext"

    try:
        inf.append_private_gate_message(
            node_id=node_id,
            payload=payload,
            sequence=1,
            signature=_sign(
                private_key,
                event_type="gate_message",
                node_id=node_id,
                sequence=1,
                payload=payload,
            ),
            public_key=public_key,
            public_key_algo="Ed25519",
            protocol_version=mesh_protocol.PROTOCOL_VERSION,
        )
    except ValueError as exc:
        assert "sealed bytes" in str(exc)
    else:
        raise AssertionError("private gate append accepted non-base64 ciphertext")

    assert inf.events == []
