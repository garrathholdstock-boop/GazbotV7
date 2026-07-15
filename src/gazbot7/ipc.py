"""GAZBOT V7 — the inter-service transport (the three-service split).

V7 runs as three processes — **md** (market data), **core** (the broker: orders,
fills, position truth, recording, safety), and **strategy** (decides, never
touches IBKR) — plus IB Gateway as its own infra. The split is only safe because
the boundaries carry *messages*, never competing copies of state:

    md  ──PUB  MD_STREAM   ──►  strategy, core     (closed 5s bars + tape summary)
    core ─PUB  CORE_STATE  ──►  strategy, monitors  (position, fill, trade, status,
                                                     intent_result)
    strategy ─PUSH INTENTS ──►  core                (order intents, fire-and-forget)

PUSH/PULL (not REQ/REP) for intents so a slow/dead core can never wedge the
strategy in a lockstep recv; the *outcome* of an intent comes back asynchronously
as an ``intent_result`` on CORE_STATE, which the strategy correlates by the
``iid`` it stamped. The stable server binds, the transient peer connects: md binds
MD_STREAM, core binds CORE_STATE + INTENTS.

Serialisation is JSON framed as ``[topic, payload]`` — debuggable, and small at
this cadence (bars/5s, tape/1s, fills rare). ``encode``/``decode`` are pure and
tested; the async socket wrappers are the thin live glue. Clean-room.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

# ── endpoints ───────────────────────────────────────────────────────────────
# Localhost TCP: fixed, inspectable, survives a peer restart (zmq reconnects).
MD_STREAM = "tcp://127.0.0.1:5561"   # md PUB binds; strategy/core SUB connect
CORE_STATE = "tcp://127.0.0.1:5562"  # core PUB binds; strategy/monitors SUB connect
INTENTS = "tcp://127.0.0.1:5563"     # core PULL binds; strategy PUSH connects


@dataclass(frozen=True, slots=True)
class Endpoints:
    md_stream: str = MD_STREAM
    core_state: str = CORE_STATE
    intents: str = INTENTS


# ── message topics (the SUB filter prefix) ───────────────────────────────────
# MD_STREAM
T_BAR = "bar"        # {symbol, tf, ts, o, h, l, c, v, closed}
T_TAPE = "tape"      # {symbol, ts_ms, net_flow, win_price_delta, last, in_rth}
# CORE_STATE
T_POSITION = "position"  # snapshot {symbol, side, qty, entry, atr, stop, opened_at, ...}
T_FILL = "fill"          # {symbol, side, qty, price, exec_id, exec_time}
T_TRADE = "trade"        # closed round-trip {symbol, side, pnl, exit_reason, ...}
T_STATUS = "status"      # {conn, healthy, halted, place_live, ...}
T_INTENT_RESULT = "intent_result"  # {iid, accepted, reason, coid}
# INTENTS
T_INTENT = "intent"  # {iid, action: OPEN|CLOSE|FLATTEN, side: LONG|SHORT|null, qty, gate, reason, meta}


# ── pure serialisation (tested without a socket) ─────────────────────────────
def encode(topic: str, payload: dict) -> list[bytes]:
    """A message is two frames: the topic (SUB filter) and the JSON body."""
    return [topic.encode(), json.dumps(payload, separators=(",", ":")).encode()]


def decode(frames: list[bytes]) -> tuple[str, dict]:
    """Inverse of :func:`encode`. Raises on a malformed frame pair."""
    if len(frames) != 2:
        raise ValueError(f"expected [topic, body], got {len(frames)} frames")
    return frames[0].decode(), json.loads(frames[1].decode())


# ── async socket wrappers ────────────────────────────────────────────────────
def _ctx():
    import zmq.asyncio

    return zmq.asyncio.Context.instance()


class Publisher:
    """A PUB that binds an endpoint. One producer per endpoint (md → MD_STREAM,
    core → CORE_STATE). Non-blocking sends; a slow/absent subscriber is dropped,
    never back-pressures the producer."""

    def __init__(self, endpoint: str) -> None:
        import zmq

        self._sock = _ctx().socket(zmq.PUB)
        self._sock.setsockopt(zmq.SNDHWM, 10_000)
        self._sock.bind(endpoint)

    async def send(self, topic: str, payload: dict) -> None:
        await self._sock.send_multipart(encode(topic, payload))

    def close(self) -> None:
        self._sock.close(0)


class Subscriber:
    """A SUB that connects an endpoint and filters to ``topics`` (empty = all).
    ``recv`` yields ``(topic, payload)``; ``poll`` is non-blocking with a timeout
    so a consumer loop can interleave other work (staleness checks, etc.)."""

    def __init__(self, endpoint: str, topics: Iterable[str] = ()) -> None:
        import zmq

        self._sock = _ctx().socket(zmq.SUB)
        self._sock.setsockopt(zmq.RCVHWM, 10_000)
        self._sock.connect(endpoint)
        subs = list(topics)
        if not subs:
            self._sock.setsockopt(zmq.SUBSCRIBE, b"")
        for t in subs:
            self._sock.setsockopt(zmq.SUBSCRIBE, t.encode())

    async def recv(self) -> tuple[str, dict]:
        return decode(await self._sock.recv_multipart())

    async def poll(self, timeout_ms: int = 100) -> tuple[str, dict] | None:
        """Return the next message, or None if none arrived within the timeout."""
        import zmq

        if await self._sock.poll(timeout_ms, zmq.POLLIN):
            return decode(await self._sock.recv_multipart())
        return None

    def close(self) -> None:
        self._sock.close(0)


class PushClient:
    """A PUSH that connects an endpoint. Fire-and-forget intents from strategy →
    core; the outcome returns asynchronously as an ``intent_result`` on
    CORE_STATE. Bounded send-queue so a dead core can't grow memory unbounded —
    a full queue drops the intent (and the strategy sees no result → stands by)."""

    def __init__(self, endpoint: str) -> None:
        import zmq

        self._sock = _ctx().socket(zmq.PUSH)
        self._sock.setsockopt(zmq.SNDHWM, 1_000)
        self._sock.setsockopt(zmq.LINGER, 0)
        self._sock.connect(endpoint)

    async def send(self, payload: dict) -> None:
        await self._sock.send_multipart(encode(T_INTENT, payload))

    def close(self) -> None:
        self._sock.close(0)


class PullServer:
    """A PULL that binds an endpoint. Core drains intents here; ``recv`` blocks
    until one arrives."""

    def __init__(self, endpoint: str) -> None:
        import zmq

        self._sock = _ctx().socket(zmq.PULL)
        self._sock.setsockopt(zmq.RCVHWM, 1_000)
        self._sock.bind(endpoint)

    async def recv(self) -> dict:
        _topic, payload = decode(await self._sock.recv_multipart())
        return payload

    def close(self) -> None:
        self._sock.close(0)
