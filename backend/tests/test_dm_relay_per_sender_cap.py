"""Per-(sender, recipient) anti-spam cap on the DM relay.

The user-stated rule: a single sender can have at most N UNACKED messages
parked in a single recipient's mailbox at any one time (N=2 by default).
Once the recipient pulls a message, the sender's quota for that pair
frees up.

Network rule, not local rule
-----------------------------
The cap is enforced TWICE:

1. ``DMRelay.deposit(...)`` -- local check on the sender's own node.
   Refuses to spool the (N+1)th message before it can be replicated.

2. ``DMRelay.accept_replica(...)`` -- replication-acceptance check on
   every receiving peer. Refuses to accept an inbound replica that
   would put the local mailbox over the cap, even if the originating
   peer claims it had cap room.

The double enforcement matters because cap (1) is client-side -- a
hostile relay could patch it out and continue to spool extras locally.
Cap (2) means those extras can't propagate: every honest peer rejects
them on the way in. A recipient who polls from honest peers therefore
never sees more than N pending from any one sender, regardless of how
many spam attempts the sender's own relay accepted.

These tests pin both halves of the rule.
"""

from __future__ import annotations

import time

import pytest


@pytest.fixture
def relay():
    """Fresh ``DMRelay`` per test."""
    from services.mesh.mesh_dm_relay import DMRelay
    r = DMRelay()
    r._mailboxes.clear()
    r._blocks.clear()
    r._stats = {"messages_in_memory": 0}
    return r


def _deposit(
    relay,
    *,
    sender: str = "alice",
    recipient_token: str = "bob_mailbox_token_abc",
    ciphertext: str = "ciphertext-blob",
    msg_id: str = "",
):
    """Convenience wrapper using ``shared`` delivery class."""
    return relay.deposit(
        sender_id=sender,
        raw_sender_id=sender,
        recipient_id="bob",
        ciphertext=ciphertext,
        msg_id=msg_id,
        delivery_class="shared",
        recipient_token=recipient_token,
    )


# ---------------------------------------------------------------------------
# Local cap on ``deposit``
# ---------------------------------------------------------------------------


class TestDepositCap:
    def test_two_deposits_from_same_sender_succeed(self, relay):
        r1 = _deposit(relay)
        r2 = _deposit(relay)
        assert r1["ok"] is True
        assert r2["ok"] is True
        assert r1["msg_id"] != r2["msg_id"]

    def test_third_deposit_from_same_sender_rejected(self, relay):
        _deposit(relay)
        _deposit(relay)
        r3 = _deposit(relay)
        assert r3["ok"] is False
        detail = r3["detail"].lower()
        assert "unread" in detail or "read your messages" in detail

    def test_different_senders_have_independent_quotas(self, relay):
        for _ in range(2):
            assert _deposit(relay, sender="alice")["ok"] is True
        for _ in range(2):
            assert _deposit(relay, sender="carol")["ok"] is True
        assert _deposit(relay, sender="carol")["ok"] is False

    def test_different_recipients_have_independent_quotas(self, relay):
        for _ in range(2):
            assert _deposit(relay, sender="alice", recipient_token="bob_token")["ok"] is True
        for _ in range(2):
            assert _deposit(relay, sender="alice", recipient_token="dave_token")["ok"] is True

    def test_ack_frees_quota(self, relay):
        r1 = _deposit(relay)
        _deposit(relay)
        assert _deposit(relay)["ok"] is False

        mailbox_key = relay._hashed_mailbox_token("bob_mailbox_token_abc")
        relay._mailboxes[mailbox_key] = [
            m for m in relay._mailboxes[mailbox_key]
            if m.msg_id != r1["msg_id"]
        ]
        relay._stats["messages_in_memory"] = sum(
            len(v) for v in relay._mailboxes.values()
        )

        r3 = _deposit(relay)
        assert r3["ok"] is True, f"expected quota free after ack, got: {r3}"

    def test_cap_is_env_tunable(self, relay, monkeypatch):
        import services.mesh.mesh_dm_relay as mdr
        monkeypatch.setattr(
            mdr.DMRelay,
            "_per_sender_pending_limit",
            lambda self: 1,
        )

        assert _deposit(relay)["ok"] is True
        assert _deposit(relay)["ok"] is False


# ---------------------------------------------------------------------------
# Replication-acceptance cap (the half that makes this a network rule)
# ---------------------------------------------------------------------------


class TestAcceptReplicaCap:
    def _envelope(self, *, msg_id: str, sender_block_ref: str, mailbox_key: str):
        return {
            "msg_id": msg_id,
            "mailbox_key": mailbox_key,
            "sender_block_ref": sender_block_ref,
            "sender_id": "alice",
            "sender_seal": "",
            "ciphertext": f"ciphertext-{msg_id}",
            "timestamp": time.time(),
            "delivery_class": "shared",
            "relay_salt": "",
            "payload_format": "dm1",
            "session_welcome": "",
        }

    def test_replica_accepted_under_cap(self, relay):
        env = self._envelope(
            msg_id="dm_replica_1",
            sender_block_ref="alice_block_ref",
            mailbox_key="mailbox_xyz",
        )
        result = relay.accept_replica(envelope=env)
        assert result["ok"] is True

    def test_replica_idempotent_on_duplicate_msg_id(self, relay):
        mailbox_key = "mailbox_xyz"
        env = self._envelope(
            msg_id="dm_dup_1",
            sender_block_ref="alice_block_ref",
            mailbox_key=mailbox_key,
        )
        r1 = relay.accept_replica(envelope=env)
        r2 = relay.accept_replica(envelope=env)
        assert r1["ok"] is True
        assert r2["ok"] is True
        assert r2.get("duplicate") is True
        assert len(relay._mailboxes[mailbox_key]) == 1

    def test_replica_rejected_when_local_count_already_at_cap(self, relay):
        mailbox_key = "mailbox_xyz"
        for i in (1, 2):
            relay.accept_replica(envelope=self._envelope(
                msg_id=f"dm_seeded_{i}",
                sender_block_ref="alice_block_ref",
                mailbox_key=mailbox_key,
            ))

        result = relay.accept_replica(envelope=self._envelope(
            msg_id="dm_overcap_3",
            sender_block_ref="alice_block_ref",
            mailbox_key=mailbox_key,
        ))
        assert result["ok"] is False
        assert result.get("cap_violation") is True
        assert result.get("pending") == 2
        assert result.get("limit") == 2
        assert len(relay._mailboxes[mailbox_key]) == 2

    def test_replica_from_different_sender_passes_when_one_is_at_cap(self, relay):
        mailbox_key = "mailbox_xyz"
        for i in (1, 2):
            relay.accept_replica(envelope=self._envelope(
                msg_id=f"dm_alice_{i}",
                sender_block_ref="alice_block_ref",
                mailbox_key=mailbox_key,
            ))
        assert relay.accept_replica(envelope=self._envelope(
            msg_id="dm_alice_3",
            sender_block_ref="alice_block_ref",
            mailbox_key=mailbox_key,
        ))["ok"] is False
        assert relay.accept_replica(envelope=self._envelope(
            msg_id="dm_carol_1",
            sender_block_ref="carol_block_ref",
            mailbox_key=mailbox_key,
        ))["ok"] is True

    def test_replica_rejects_malformed_envelopes(self, relay):
        for bad in (
            {},
            {"msg_id": "x"},
            {"msg_id": "x", "mailbox_key": "y"},
            "not an object at all",
        ):
            result = relay.accept_replica(envelope=bad)
            assert result["ok"] is False


# ---------------------------------------------------------------------------
# ``envelope_for_replication`` -- helper for the outbound replication path
# ---------------------------------------------------------------------------


class TestEnvelopeForReplication:
    def test_returns_envelope_for_stored_message(self, relay):
        r = _deposit(relay, ciphertext="hello-ciphertext")
        msg_id = r["msg_id"]
        mailbox_key = relay._hashed_mailbox_token("bob_mailbox_token_abc")

        env = relay.envelope_for_replication(mailbox_key=mailbox_key, msg_id=msg_id)
        assert env is not None
        assert env["msg_id"] == msg_id
        assert env["mailbox_key"] == mailbox_key
        assert env["ciphertext"] == "hello-ciphertext"
        assert env["delivery_class"] == "shared"
        for k in ("msg_id", "mailbox_key", "sender_block_ref", "ciphertext"):
            assert env.get(k), f"envelope missing required field {k!r}"

    def test_returns_none_for_unknown_message(self, relay):
        env = relay.envelope_for_replication(
            mailbox_key="never_existed", msg_id="never_existed",
        )
        assert env is None

    def test_envelope_round_trips_through_accept_replica(self, relay):
        from services.mesh.mesh_dm_relay import DMRelay
        receiver_relay = DMRelay()
        receiver_relay._mailboxes.clear()
        receiver_relay._stats = {"messages_in_memory": 0}

        r = _deposit(relay)
        msg_id = r["msg_id"]
        mailbox_key = relay._hashed_mailbox_token("bob_mailbox_token_abc")
        env = relay.envelope_for_replication(
            mailbox_key=mailbox_key, msg_id=msg_id,
        )
        assert env is not None

        result = receiver_relay.accept_replica(envelope=env)
        assert result["ok"] is True
        stored = receiver_relay._mailboxes.get(mailbox_key, [])
        assert len(stored) == 1
        assert stored[0].msg_id == msg_id
        assert stored[0].ciphertext == "ciphertext-blob"
