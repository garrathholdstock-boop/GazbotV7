"""GAZBOT V7 — the multi-slot paper-tournament runner.

Composes the three tournament modules into a runnable desk:
    md bars/tape → SlotStrategy.decide (per-slot intents) → MultiSlotCore (execution)
    venue fills  → MultiSlotCore.on_fill  ·  reconcile loop → drift halt

Per-gate P&L falls out for free: every slot's round-trip is recorded with its own
``gate`` tag, so summing ``trades`` by gate gives each gate's standalone P&L — the
ranking the tournament runs on.

TWO MODES:
- **dry-run** (``place_live=False``, the default): subscribes to the REAL md feed,
  runs the slot decisions, and LOGS what each slot would do — NO gateway, NO orders,
  zero account risk. This proves the wiring + shows grind-long vs grind-short live
  before any cutover.
- **live** (``place_live=True``): connects the gateway and trades the paper account.
  ⚠ GATED — the per-slot venue-audit hardening (naked-auditor / adopt / wedge over the
  netted book, PAPER_TOURNAMENT_SCOPE §4) is DEFERRED; do NOT run live until it lands
  AND the single-position desk is stopped (one account — they must not co-trade).

Clean-room. The ``step`` helper is pure/testable; ``run`` is the I/O shell.
"""

from __future__ import annotations

import asyncio
import logging
import time

from .agg import MinuteBars
from .capture import open_capture
from .config import RunConfig
from .deciders import compute_features
from .ipc import MD_STREAM, T_BAR, T_TAPE, Subscriber
from .slot_strategy import SlotStrategy, grind_long_short_slots

log = logging.getLogger("tournament")

_STALE_TAPE_MS = 10_000
_STALE_BAR_MS = 30_000


def step(strat: SlotStrategy, mb: MinuteBars, tape: dict, slotbook, now_ms: int) -> list[dict]:
    """One decision cycle → per-slot intents (or []). Pure: freshness-gated, reads the
    rolling 1-min bars + the latest tape, defers to SlotStrategy. No side effects."""
    tape_ts = tape.get("ts_ms", 0)
    if not tape_ts or now_ms - tape_ts > _STALE_TAPE_MS:
        return []
    if not mb.fresh(now_ms, _STALE_BAR_MS):
        return []
    bars = mb.bars()
    if len(bars) < 6:
        return []
    f = compute_features(bars)
    price = tape.get("last") or f.price
    return strat.decide(f, price, bars, slotbook, tape.get("net_flow", 0.0))


async def run(specs=None, cfg: RunConfig | None = None, *, place_live: bool = False,
              max_seconds: float | None = None) -> None:
    cfg = cfg or RunConfig()
    specs = specs or grind_long_short_slots()
    gates = [s.tag for s in specs]

    cap = open_capture(cfg.capture_path)
    mb = MinuteBars(cfg.bar_lookback)
    mb.warm(cap, cfg.symbol, cfg.bar_lookback)
    cap.close()

    strat = SlotStrategy(specs, value_per_point=cfg.value_per_point)
    core = None
    gw = None
    if place_live:
        core, gw = await _build_live(cfg, gates)   # gateway + engine + per-slot safety + MultiSlotCore
    else:
        from .slotbook import SlotBook
        slotbook = SlotBook(gates, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)

    md = Subscriber(MD_STREAM, topics=[T_BAR, T_TAPE])
    tape: dict = {}
    log.info("tournament %s — slots=%s", "LIVE" if place_live else "DRY-RUN", gates)
    start = time.monotonic()
    try:
        while max_seconds is None or (time.monotonic() - start) < max_seconds:
            msg = await md.poll(500)
            if msg is None:
                continue
            topic, body = msg
            if topic == T_BAR:
                mb.fold(body["ts"], body["o"], body["h"], body["l"], body["c"], body["v"])
            elif topic == T_TAPE:
                tape = body
                now_ms = int(time.time() * 1000)
                book = core._sb if core is not None else slotbook
                intents = step(strat, mb, tape, book, now_ms)
                if not intents:
                    continue
                if place_live:
                    await core.on_intents(intents)
                else:
                    for i in intents:
                        log.info("[DRY] %s %s side=%s qty=%s @%s", i["action"], i["slot"],
                                 i.get("side", ""), i.get("qty", ""), i.get("price", ""))
    finally:
        md.close()
        if gw is not None:
            await gw.stop()


async def _build_live(cfg: RunConfig, gates):
    """Live execution wiring (paper account). ⚠ the deferred per-slot venue-audit loop
    (naked/adopt/wedge) is NOT here yet — see the module docstring before running."""
    from ib_async import ContFuture

    from .broker_adapter import IBBrokerAdapter
    from .engine import OrderEngine
    from .ib_gateway import IBGateway
    from .multislot_core import MultiSlotCore
    from .safety import SafetyManager
    from .slotbook import SlotBook
    from .store import open_store

    store = open_store(cfg.store_path)
    gw = IBGateway(cfg.host, cfg.port, client_id=cfg.client_id, readonly=not cfg.place_live)
    ref: dict = {}
    await gw.start()
    (contract,) = await gw._ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))
    broker = IBBrokerAdapter(gw._ib, contract, cfg.symbol,
                             on_fill=lambda f: ref["core"].on_fill(f),
                             on_stop_event=lambda coid, status: None)
    engine = OrderEngine(broker, store)
    slotbook = SlotBook(gates, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
    safeties = {g: SafetyManager(broker) for g in gates}
    core = MultiSlotCore(cfg, engine, slotbook, safeties, publisher=None, store=store)
    ref["core"] = core
    return core, gw


def main() -> None:  # `python -m gazbot7.tournament`
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    live = os.environ.get("GAZBOT7_TOURNAMENT_LIVE") == "1"
    asyncio.run(run(place_live=live))


if __name__ == "__main__":
    raise SystemExit(main())
