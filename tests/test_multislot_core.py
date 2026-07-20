"""Multi-slot execution core — intents → orders → fills → SlotBook → trades + per-slot
stops, over a netted venue. Two slots run concurrently; a leaked lot halts."""

from __future__ import annotations

import asyncio

from gazbot7.config import RunConfig
from gazbot7.multislot_core import MultiSlotCore
from gazbot7.safety import SafetyManager
from gazbot7.slotbook import SlotBook
from gazbot7.store import Fill, get_trades, open_store


class FakeEngine:
    def __init__(self):
        self.orders: list[dict] = []
        self._n = 0

    def submit(self, *, symbol, side, qty, order_type, limit_price=None, coid=None, tif=None):
        self._n += 1
        c = coid or f"c{self._n}"
        self.orders.append(dict(coid=c, side=side, qty=qty, type=order_type, limit=limit_price, tif=tif))
        return c


class FakeStopBroker:
    def __init__(self, tag=""):
        self.stops: list[dict] = []
        self.cancelled: list[str] = []
        self._n = 0
        self._tag = tag                          # unique coids across slots (like the real shared broker)

    def place_stop(self, *, symbol, side, qty, stop_price):
        self._n += 1
        self.stops.append(dict(side=side, qty=qty, stop_price=stop_price))
        return f"{self._tag}stp{self._n}"

    def cancel(self, coid):
        self.cancelled.append(coid)


class FakePub:
    async def send(self, topic, payload):
        pass


GATES = ("grind_long", "grind_short")


def _core():
    store = open_store(":memory:")
    eng = FakeEngine()
    sb = SlotBook(list(GATES), value_per_point=2.0, fee_rt=1.5)
    sbrokers = {g: FakeStopBroker(tag=g+"-") for g in GATES}
    safeties = {g: SafetyManager(sbrokers[g]) for g in GATES}
    core = MultiSlotCore(RunConfig(place_live=True), eng, sb, safeties, FakePub(), store)
    return core, eng, sb, sbrokers, store


def _open(core, eng, slot, side, price, qty=1, atr=20.0):
    asyncio.run(core.on_intents([{"action": "OPEN", "slot": slot, "gate": slot, "side": side,
                                  "qty": qty, "price": price, "meta": {"entry_atr": atr}}]))
    return eng.orders[-1]["coid"]


def _fill(core, coid, side, qty, price):
    core.on_fill(Fill(f"x-{coid}-{side}-{price}", coid, "MNQ", side, qty, price,
                      "2026-07-20T14:00:00+00:00"))


def test_open_submits_capped_marketable_limit_ioc():
    core, eng, sb, _sb, _s = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0)
    o = eng.orders[-1]
    assert o["type"] == "LMT" and o["tif"] == "IOC" and o["side"] == "BUY"
    assert o["limit"] == 29003.0            # ceil(ref 29000 + buffer 3)
    assert sb.owner(coid) == "grind_long"   # fills will route to this slot


def test_fill_opens_slot_and_arms_its_stop():
    core, eng, sb, sbrokers, _s = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, coid, "BUY", 1, 29001.0)
    assert sb.slot("grind_long").net == 1.0
    assert len(sbrokers["grind_long"].stops) == 1                 # this slot's native stop armed
    assert sbrokers["grind_long"].stops[-1]["side"] == "SELL"     # protects a long
    assert sbrokers["grind_short"].stops == []                    # other slot untouched


def test_close_records_the_trade_and_cancels_the_slot_stop():
    core, eng, sb, sbrokers, store = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, coid, "BUY", 1, 29000.0)
    xcoid = None
    asyncio.run(core.on_intents([{"action": "CLOSE", "slot": "grind_long", "gate": "grind_long",
                                  "reason": "CHANDELIER"}]))
    xcoid = eng.orders[-1]["coid"]
    _fill(core, xcoid, "SELL", 1, 29030.0)
    trades = get_trades(store)
    assert len(trades) == 1
    t = trades[0]
    assert t["gate"] == "grind_long" and t["side"] == "LONG" and t["exit_reason"] == "CHANDELIER"
    assert t["pnl_usd"] == (29030 - 29000) * 2.0 - 1.5           # +58.5
    assert sbrokers["grind_long"].cancelled                       # stop cancelled on close
    assert sb.slot("grind_long").is_flat


def test_two_slots_concurrent_close_one_leaves_the_other():
    core, eng, sb, _sb, store = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    cS = _open(core, eng, "grind_short", "SHORT", 29050.0)
    _fill(core, cS, "SELL", 1, 29050.0)
    assert sb.net_qty() == 0.0                                    # venue net 0, both held
    asyncio.run(core.on_intents([{"action": "CLOSE", "slot": "grind_long", "gate": "grind_long",
                                  "reason": "GIVEBACK"}]))
    _fill(core, eng.orders[-1]["coid"], "SELL", 1, 29020.0)
    assert len(get_trades(store)) == 1                            # only the long recorded
    assert sb.slot("grind_short").net == -1.0                     # short slot still open
    assert sb.net_qty() == -1.0


def test_reconcile_drift_halts_new_opens():
    core, eng, sb, _sb, _s = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    assert core.reconcile(1.0) == "match"
    assert core.reconcile(2.0) == "drift"                         # a phantom lot at venue
    n = len(eng.orders)
    _open(core, eng, "grind_short", "SHORT", 29050.0)             # halted → no order
    assert len(eng.orders) == n


def test_a_slot_wont_double_open_while_pending():
    core, eng, _sb, _s2, _s = _core()
    _open(core, eng, "grind_long", "LONG", 29000.0)              # first open, now pending (no fill yet)
    n = len(eng.orders)
    _open(core, eng, "grind_long", "LONG", 29000.0)             # second while pending → ignored
    assert len(eng.orders) == n


class FakeGw:
    def __init__(self):
        self.reconnects = 0

    def force_reconnect(self):
        self.reconnects += 1


def test_slot_ok_when_its_stop_is_live():
    core, eng, sb, sbrokers, _s = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, coid, "BUY", 1, 29000.0)
    stop_coid = core._safeties["grind_long"].stop_for("MNQ").coid
    core._boot_mono = 0.0
    assert core.assess_slot("grind_long", {stop_coid}, 1000.0) == "ok"


def test_naked_slot_reprotects_then_flattens():
    core, eng, sb, sbrokers, _s = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, coid, "BUY", 1, 29000.0)
    core._boot_mono = 0.0
    assert core.assess_slot("grind_long", set(), 1000.0) == "reprotect"   # stop not live
    assert core.assess_slot("grind_long", set(), 1000.0) == "flatten"     # still naked → cut


def test_naked_within_boot_settle_is_settle():
    core, eng, sb, sbrokers, _s = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, coid, "BUY", 1, 29000.0)
    assert core.assess_slot("grind_long", set(), core._boot_mono + 1.0) == "settle"


def test_flat_slot_assesses_flat():
    core, *_rest = _core()
    assert core.assess_slot("grind_long", set(), 1000.0) == "flat"


def test_netted_one_slot_naked_other_protected():
    # THE case aggregate is_naked can't handle: long+short net to 0, one protected, one not.
    core, eng, sb, sbrokers, _s = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    cS = _open(core, eng, "grind_short", "SHORT", 29050.0, atr=20.0)
    _fill(core, cS, "SELL", 1, 29050.0)
    assert sb.net_qty() == 0.0
    core._boot_mono = 0.0
    long_stop = core._safeties["grind_long"].stop_for("MNQ").coid
    assert core.assess_slot("grind_long", {long_stop}, 1000.0) == "ok"        # its stop live
    assert core.assess_slot("grind_short", {long_stop}, 1000.0) == "reprotect"  # its stop absent


def test_flatten_slot_submits_market_close():
    core, eng, sb, sbrokers, _s = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    n = len(eng.orders)
    core._flatten_slot("grind_long")
    assert len(eng.orders) == n + 1
    assert eng.orders[-1]["side"] == "SELL" and eng.orders[-1]["type"] == "MKT"


def test_unverified_escalates_only_when_a_slot_is_held():
    from gazbot7.multislot_core import UNVERIFIED_PAGE_CYCLES
    core, eng, sb, sbrokers, _s = _core()
    notes: list[str] = []
    core._notify = notes.append
    core._on_unverified(FakeGw())                         # flat → silent
    assert notes == []
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    for _ in range(UNVERIFIED_PAGE_CYCLES):
        core._on_unverified(FakeGw())
    assert any("CANNOT VERIFY" in n for n in notes)       # held + can't verify → page
