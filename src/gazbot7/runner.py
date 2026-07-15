"""GAZBOT V7 — the runner: assembles every module into one live process.

connect → capture → (each cadence) build features → run the desk + the shadow
sims → manage. Fills route from the ib_async adapter straight into the desk. One
process, one asyncio loop — no broker/strategy split, so a fill updates position,
records the trade, and arms the 1-ATR stop in the same tick.

``place_live`` gates real order placement: the default (False) is a dry-run that
captures, decides, and runs the shadow desk WITHOUT placing orders — safe to run
alongside V5. Cutover flips it to True (V7 solo, same paper account/ID).
"""

from __future__ import annotations

import asyncio
import time

from .broker_adapter import IBBrokerAdapter
from .capture import CaptureManager, open_capture
from .config import RunConfig
from .deciders import Bar, REVERSAL_SHORT_VARIANTS  # noqa: F401 (slate available to configure shadow)
from .desk import Desk, DeskConfig
from .engine import OrderEngine
from .ib_gateway import IBGateway
from .safety import SafetyManager
from .shadow import ShadowSim, ShadowVariant
from .store import open_store
from .tracker import TradeTracker


class _NoOpBroker:
    """Dry-run stand-in — the desk decides, but nothing reaches the venue."""

    def place(self, order):
        pass

    def cancel(self, coid):
        pass

    def place_stop(self, *, symbol, side, qty, stop_price):
        return "dry-run"


def _us_rth(now_ms: int) -> bool:
    # ~US regular hours 13:30–20:00 UTC (where the reversal short edge lived)
    h = time.gmtime(now_ms / 1000)
    mins = h.tm_hour * 60 + h.tm_min
    return 13 * 60 + 30 <= mins <= 20 * 60


def _recent_bars(cap, symbol: str, n: int) -> list[Bar]:
    rows = cap.execute(
        "SELECT bar_ts, open, high, low, close, volume FROM bars "
        "WHERE symbol=? AND timeframe='5s' ORDER BY bar_ts DESC LIMIT ?", (symbol, n),
    ).fetchall()
    return [Bar(r["bar_ts"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in reversed(rows)]


def _recent_tape(cap, symbol: str, window_s: int) -> tuple[float, float]:
    now = int(time.time() * 1000)
    rows = cap.execute(
        "SELECT price, size, aggressor FROM ticks WHERE symbol=? AND ts_ms>=? ORDER BY ts_ms",
        (symbol, now - window_s * 1000),
    ).fetchall()
    if not rows:
        return 0.0, 0.0
    buy = sum(r["size"] for r in rows if r["aggressor"] == "buy")
    sell = sum(r["size"] for r in rows if r["aggressor"] == "sell")
    return buy - sell, rows[-1]["price"] - rows[0]["price"]


async def run(cfg: RunConfig, *, shadow_variants: list[ShadowVariant] | None = None, max_seconds: float | None = None):
    store = open_store(cfg.store_path)
    cap = open_capture(cfg.capture_path)
    gw = IBGateway(cfg.host, cfg.port, cfg.client_id, readonly=not cfg.place_live)
    await gw.start()

    from ib_async import ContFuture

    (contract,) = await gw._ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))

    desk_ref: dict = {}
    if cfg.place_live:
        broker = IBBrokerAdapter(gw._ib, contract, cfg.symbol, on_fill=lambda f: desk_ref["desk"].on_fill(f))
        safety_broker = broker
    else:
        broker = _NoOpBroker()
        safety_broker = broker

    oe = OrderEngine(broker, store)
    tt = TradeTracker(store, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
    sm = SafetyManager(safety_broker)
    desk = Desk(DeskConfig(symbol=cfg.symbol, size=cfg.size, gate=cfg.gate,
                           gate_params=cfg.gate_params, target_r=cfg.target_r), oe, tt, sm)
    desk_ref["desk"] = desk

    shadow = ShadowSim(store, shadow_variants or [], value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)

    cm = CaptureManager(gw, cap, [cfg.symbol], exchange=cfg.exchange)
    await cm.start()
    gw.on_reconnect(lambda _ib: asyncio.ensure_future(cm.start()))  # re-subscribe feeds on reconnect

    start = time.monotonic()
    while max_seconds is None or (time.monotonic() - start) < max_seconds:
        bars = _recent_bars(cap, cfg.symbol, cfg.bar_lookback)
        if len(bars) >= 6:
            tape_net, wpd = _recent_tape(cap, cfg.symbol, cfg.tape_window_s)
            in_rth = _us_rth(int(time.time() * 1000))
            desk.on_bars(bars, tape_net=tape_net, window_price_delta=wpd, in_rth=in_rth)
            shadow.on_bars(bars, tape_net=tape_net, window_price_delta=wpd, in_rth=in_rth)
        await asyncio.sleep(cfg.cadence_s)

    await gw.stop()


def main() -> None:  # `python -m gazbot7.runner`
    asyncio.run(run(RunConfig()))


if __name__ == "__main__":
    main()
