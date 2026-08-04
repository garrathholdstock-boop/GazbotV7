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
import logging
import time

from .capture import CaptureManager, open_capture, recent_tape
from .config import RunConfig
from .ib_gateway import IBGateway
from .ipc import MD_STREAM, T_TAPE, Publisher

# ★2026-08-04 md.py had no module logger — adding a log call without this is the exact
# NameError that took gazbot7-shadow down 11 times this morning.
log = logging.getLogger("md")

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
    # ★2026-08-04 (operator: "add mgc to v7 md capture") — multi-symbol capture, env-driven so the
    # default is byte-identical to before. "MNQ:CME,MGC:COMEX"; gold is COMEX and will not resolve as CME.
    # ⚠ DEPTH stays MNQ-ONLY here: IBKR caps depth at THREE subscriptions account-wide and
    # gazbot7-depth-capture already holds two (MNQ + MGC, 10 levels, deduped). md's own 5-level book is
    # the weaker copy — a fourth request would take Error 309, exactly how M2K died unnoticed on 07-29.
    import os as _os
    syms = [x.strip() for x in _os.environ.get(
        "GAZBOT7_CAPTURE_SYMBOLS", f"{cfg.symbol}:{cfg.exchange}").split(",") if x.strip()]
    depth_for = {x.strip() for x in _os.environ.get(
        "GAZBOT7_MD_DEPTH_SYMBOLS", cfg.symbol).split(",") if x.strip()}
    log.info("md capture symbols=%s depth=%s", syms, sorted(depth_for))
    cm = CaptureManager(gw, cap, syms, exchange=cfg.exchange, publisher=pub,
                        depth_symbols=depth_for)
    # re-subscribe the reqRealTimeBars farm on the initial connect AND every
    # reconnect (S3) — a gateway bounce must not leave md silently unsubscribed.
    gw.on_reconnect(lambda _ib: cm.start())
    await gw.start()
    liveness_task = asyncio.ensure_future(gw.liveness_loop())  # S3 zombie guard
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
        liveness_task.cancel()
        await gw.stop()
        pub.close()
        cap.close()


def main() -> None:  # `python -m gazbot7.md`
    asyncio.run(run(RunConfig()))


if __name__ == "__main__":
    main()
