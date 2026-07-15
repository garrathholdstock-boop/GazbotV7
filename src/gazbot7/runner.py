"""GAZBOT V7 — the runner: assembles every module into one live process.

connect → capture → (each cadence) build features → run the desk + the shadow
sims → manage. Fills route from the ib_async adapter straight into the desk. One
process, one asyncio loop — a fill updates position, records the trade, and arms
the 1-ATR stop in the same tick.

``place_live`` gates real order placement (default False = dry-run, safe alongside
V5). Each cycle it writes ``status.json`` for the watch page (web.py). Naked-guard
alerts route to Telegram via the injected notifier.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from datetime import UTC, datetime

from .broker_adapter import IBBrokerAdapter
from .capture import CaptureManager, open_capture
from .config import RunConfig
from .deciders import REVERSAL_SHORT_VARIANTS, Bar
from .desk import Desk, DeskConfig
from .engine import OrderEngine
from .ib_gateway import IBGateway
from .safety import SafetyManager
from .shadow import ShadowSim, ShadowVariant
from .store import open_store
from .tracker import TradeTracker


class _NoOpBroker:
    def place(self, order):
        pass

    def cancel(self, coid):
        pass

    def place_stop(self, *, symbol, side, qty, stop_price):
        return "dry-run"


def _us_rth(now_ms: int) -> bool:
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


def _write_status(cfg: RunConfig, gw: IBGateway, desk: Desk, store) -> None:
    pos = desk.position
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    r = store.execute(
        "SELECT COUNT(*), COALESCE(ROUND(SUM(pnl_usd),2),0) FROM trades "
        "WHERE symbol=? AND substr(closed_at,1,10)=?", (cfg.symbol, today),
    ).fetchone()
    status = {
        "ts": datetime.now(UTC).isoformat(),
        "conn": gw.state.value,
        "healthy": gw.healthy,
        "place_live": cfg.place_live,
        "symbol": cfg.symbol,
        "position": None if pos is None else {"side": pos.side, "entry": pos.entry_price},
        "today_trades": r[0],
        "today_pnl": r[1],
    }
    path = os.path.join(os.path.dirname(cfg.store_path) or ".", "status.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(status, f)
    os.replace(tmp, path)


def _telegram_notifier(msg: str) -> None:
    subprocess.run(
        ["/home/alphabot/alphabot2/.venv/bin/python",
         "/home/alphabot/alphabot2/scripts/notify_operator.py", f"[V7] {msg}"],
        check=False, timeout=15,
    )


async def run(cfg: RunConfig, *, shadow_variants=None, notifier=None, max_seconds=None):
    store = open_store(cfg.store_path)
    cap = open_capture(cfg.capture_path)
    gw = IBGateway(cfg.host, cfg.port, cfg.client_id, readonly=not cfg.place_live)
    await gw.start()

    from ib_async import ContFuture

    (contract,) = await gw._ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))

    desk_ref: dict = {}
    broker = (
        IBBrokerAdapter(gw._ib, contract, cfg.symbol, on_fill=lambda f: desk_ref["desk"].on_fill(f))
        if cfg.place_live else _NoOpBroker()
    )
    oe = OrderEngine(broker, store)
    tt = TradeTracker(store, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
    sm = SafetyManager(broker, notifier=notifier)
    desk = Desk(DeskConfig(symbol=cfg.symbol, size=cfg.size, gate=cfg.gate,
                           gate_params=cfg.gate_params, target_r=cfg.target_r), oe, tt, sm)
    desk_ref["desk"] = desk
    shadow = ShadowSim(store, shadow_variants or [], value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)

    cm = CaptureManager(gw, cap, [cfg.symbol], exchange=cfg.exchange)
    await cm.start()
    gw.on_reconnect(lambda _ib: asyncio.ensure_future(cm.start()))

    start = time.monotonic()
    while max_seconds is None or (time.monotonic() - start) < max_seconds:
        bars = _recent_bars(cap, cfg.symbol, cfg.bar_lookback)
        if len(bars) >= 6:
            tape_net, wpd = _recent_tape(cap, cfg.symbol, cfg.tape_window_s)
            in_rth = _us_rth(int(time.time() * 1000))
            desk.on_bars(bars, tape_net=tape_net, window_price_delta=wpd, in_rth=in_rth)
            shadow.on_bars(bars, tape_net=tape_net, window_price_delta=wpd, in_rth=in_rth)
        _write_status(cfg, gw, desk, store)
        await asyncio.sleep(cfg.cadence_s)

    await gw.stop()


def main() -> None:  # `python -m gazbot7.runner`  (GAZBOT7_PLACE_LIVE=1 to trade)
    live = os.environ.get("GAZBOT7_PLACE_LIVE") == "1"
    cfg = RunConfig(place_live=live)
    variants = [ShadowVariant("thrust_shadow", "thrust", {"thr": 1.5})] + [
        ShadowVariant(name, "reversal_grab", c) for name, c in REVERSAL_SHORT_VARIANTS.items()
    ]
    asyncio.run(run(cfg, shadow_variants=variants, notifier=_telegram_notifier))


if __name__ == "__main__":
    main()
