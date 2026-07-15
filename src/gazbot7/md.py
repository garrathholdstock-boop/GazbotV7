"""GAZBOT V7 — the md service: the sole market-data authority.

Subscribes MNQ 5s bars / L1 quotes / aggressor ticks / L2 depth on a dedicated
IBKR client (**clientId 2, read-only** — md never trades), persists everything to
the capture DB (the moat), AND publishes a live stream on ``MD_STREAM``: closed
5s bars (event-driven, via CaptureManager) plus a trailing tape summary (net
aggressor flow + price delta + last, ~1 s). Strategy decides off this stream, not
a DB poll; core may subscribe for marks. One producer → the DB and the stream
carry the same bars by construction, so strategy can never diverge from capture.

Isolated from the trading store: md opens only the capture DB. A gateway bounce
re-subscribes the farm (wired in S3 — the liveness/reconnect hardening). Clean-room.
"""

from __future__ import annotations

import asyncio
import time

from .capture import CaptureManager, open_capture, recent_tape
from .config import RunConfig
from .ib_gateway import IBGateway
from .ipc import MD_STREAM, T_TAPE, Publisher

MD_CLIENT_ID = 2  # dedicated md client (core=0 master, strategy touches IBKR never)


def _us_rth(now_ms: int) -> bool:
    """US regular trading hours (13:30–20:00 UTC = 09:30–16:00 ET). A stream hint;
    the authoritative session gate lives in core (S4)."""
    h = time.gmtime(now_ms / 1000)
    mins = h.tm_hour * 60 + h.tm_min
    return 13 * 60 + 30 <= mins <= 20 * 60


async def run(cfg: RunConfig, *, tape_interval_s: float = 1.0,
              tape_window_s: int = 60, max_seconds: float | None = None) -> None:
    cap = open_capture(cfg.capture_path)
    pub = Publisher(MD_STREAM)
    gw = IBGateway(cfg.host, cfg.port, client_id=MD_CLIENT_ID, readonly=True)
    await gw.start()
    cm = CaptureManager(gw, cap, [cfg.symbol], exchange=cfg.exchange, publisher=pub)
    await cm.start()
    start = time.monotonic()
    try:
        while max_seconds is None or (time.monotonic() - start) < max_seconds:
            now = int(time.time() * 1000)
            net, dpx, last = recent_tape(cap, cfg.symbol, now, window_s=tape_window_s)
            if last is not None:
                await pub.send(T_TAPE, {
                    "symbol": cfg.symbol, "ts_ms": now, "net_flow": net,
                    "win_price_delta": dpx, "last": last, "in_rth": _us_rth(now),
                })
            await asyncio.sleep(tape_interval_s)
    finally:
        await gw.stop()
        pub.close()
        cap.close()


def main() -> None:  # `python -m gazbot7.md`
    asyncio.run(run(RunConfig()))


if __name__ == "__main__":
    main()
