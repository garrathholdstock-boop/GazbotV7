"""The three-service transport: pure framing + a live pub/sub + push/pull loop.

The pure encode/decode is the contract every service serialises against; the
socket roundtrips prove the zmq wrappers wire the way the split assumes (PUB→SUB
fan-out, PUSH→PULL intents). Ephemeral ports so it never clashes with a running
service. Uses asyncio.run — no pytest-asyncio dependency."""

from __future__ import annotations

import asyncio

import pytest

from gazbot7 import ipc


# ── pure framing ─────────────────────────────────────────────────────────────
def test_encode_decode_roundtrip():
    topic, body = ipc.decode(ipc.encode("bar", {"symbol": "MNQ", "c": 29491.5}))
    assert topic == "bar"
    assert body == {"symbol": "MNQ", "c": 29491.5}


def test_decode_rejects_bad_frames():
    with pytest.raises(ValueError):
        ipc.decode([b"only-one-frame"])


# ── live sockets ─────────────────────────────────────────────────────────────
async def _pub_sub_once() -> tuple[str, dict]:
    ep = "tcp://127.0.0.1:5591"
    pub = ipc.Publisher(ep)
    sub = ipc.Subscriber(ep, topics=["bar"])
    try:
        # slow-joiner: a PUB drops messages to a SUB that hasn't finished
        # connecting, so send until one lands (bounded).
        for _ in range(50):
            await pub.send("bar", {"symbol": "MNQ", "c": 1.0})
            await pub.send("tape", {"symbol": "MNQ", "net_flow": 9.0})  # filtered out
            msg = await sub.poll(50)
            if msg is not None:
                return msg
        raise AssertionError("no message received")
    finally:
        pub.close()
        sub.close()


def test_pub_sub_fanout_and_filter():
    topic, body = asyncio.run(_pub_sub_once())
    assert topic == "bar"  # the "tape" sends were filtered out by the subscription
    assert body["symbol"] == "MNQ"


async def _push_pull_once() -> dict:
    ep = "tcp://127.0.0.1:5592"
    server = ipc.PullServer(ep)
    client = ipc.PushClient(ep)
    try:
        await asyncio.sleep(0.1)  # let the PUSH connect before sending
        await client.send({"iid": "i1", "action": "OPEN", "side": "LONG", "qty": 1})
        return await asyncio.wait_for(server.recv(), timeout=2.0)
    finally:
        client.close()
        server.close()


def test_push_pull_intent():
    intent = asyncio.run(_push_pull_once())
    assert intent["action"] == "OPEN"
    assert intent["iid"] == "i1"
