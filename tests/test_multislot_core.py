"""Multi-slot execution core — intents → orders → fills → SlotBook → trades + per-slot
stops, over a netted venue. Two slots run concurrently; a leaked lot halts."""

from __future__ import annotations

import asyncio
from datetime import datetime

from gazbot7.config import RunConfig
from gazbot7.multislot_core import EXIT_REFIRE_MAX, EXIT_STUCK_CYCLES, MultiSlotCore
from gazbot7.safety import SafetyManager
from gazbot7.slotbook import SlotBook
from gazbot7.store import Fill, get_slot_positions, get_trades, open_store


class FakeEngine:
    def __init__(self):
        self.orders: list[dict] = []
        self.cancelled: list[str] = []
        self._n = 0

    def submit(self, *, symbol, side, qty, order_type, limit_price=None, coid=None, tif=None):
        self._n += 1
        c = coid or f"c{self._n}"
        self.orders.append(dict(coid=c, side=side, qty=qty, type=order_type, limit=limit_price, tif=tif))
        return c

    def cancel(self, coid):
        self.cancelled.append(coid)


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


def _restart(store):
    """A fresh core over the SAME durable store — new process, empty in-memory state."""
    eng = FakeEngine()
    sb = SlotBook(list(GATES), value_per_point=2.0, fee_rt=1.5)
    sbrokers = {g: FakeStopBroker(tag=g + "-") for g in GATES}
    safeties = {g: SafetyManager(sbrokers[g]) for g in GATES}
    core = MultiSlotCore(RunConfig(place_live=True), eng, sb, safeties, FakePub(), store)
    return core, eng, sb, sbrokers


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


def test_slot_position_persists_and_reconstructs_after_restart():
    core, eng, sb, sbrokers, store = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, coid, "BUY", 1, 29001.0)
    assert [r["gate"] for r in get_slot_positions(store)] == ["grind_long"]   # snapshotted

    core2, eng2, sb2, sbrokers2 = _restart(store)      # process restart, same store
    adopted = core2.reconstruct()
    assert adopted == ["grind_long"]
    s = sb2.slot("grind_long")
    assert s.side == "LONG" and s.net == 1.0 and s.entry_price == 29001.0
    assert s.entry_atr == 20.0                          # the stop distance the venue can't give back
    stop = core2._safeties["grind_long"].stop_for("MNQ")
    assert stop is not None and stop.stop_price == 29001.0 - 20.0   # 1-ATR below entry, re-attached


def test_reconstruct_reattaches_stop_without_placing_a_duplicate():
    core, eng, sb, sbrokers, store = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, coid, "BUY", 1, 29000.0)
    orig_stop_coid = core._safeties["grind_long"].stop_for("MNQ").coid

    core2, eng2, sb2, sbrokers2 = _restart(store)
    core2.reconstruct()
    assert sbrokers2["grind_long"].stops == []          # NO fresh place_stop → no double coverage
    stop = core2._safeties["grind_long"].stop_for("MNQ")
    assert stop.coid == orig_stop_coid                  # same venue order re-attached
    core2._boot_mono = 0.0
    assert core2.assess_slot("grind_long", {orig_stop_coid}, 1000.0) == "ok"   # auditor sees it live


def test_reconstruct_two_netted_slots_survive_restart():
    core, eng, sb, sbrokers, store = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    cS = _open(core, eng, "grind_short", "SHORT", 29050.0, atr=20.0)
    _fill(core, cS, "SELL", 1, 29050.0)
    assert sb.net_qty() == 0.0                          # netted venue would show 0

    core2, eng2, sb2, sbrokers2 = _restart(store)
    assert sorted(core2.reconstruct()) == ["grind_long", "grind_short"]
    assert sb2.slot("grind_long").net == 1.0
    assert sb2.slot("grind_short").net == -1.0
    assert sb2.net_qty() == 0.0
    assert core2.reconcile(0.0) == "match"              # ledger truth agrees with venue net


def test_reconstructed_state_disagreeing_with_venue_halts():
    core, eng, sb, sbrokers, store = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, coid, "BUY", 1, 29000.0)               # ledger net +1

    core2, eng2, sb2, sbrokers2 = _restart(store)
    core2.reconstruct()
    assert core2.reconcile(0.0) == "drift"             # venue flat (stop filled while down) → HALT
    assert core2._halted


def test_flat_slot_clears_persistence_nothing_to_reconstruct():
    core, eng, sb, sbrokers, store = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, coid, "BUY", 1, 29000.0)
    asyncio.run(core.on_intents([{"action": "CLOSE", "slot": "grind_long",
                                  "gate": "grind_long", "reason": "GIVEBACK"}]))
    _fill(core, eng.orders[-1]["coid"], "SELL", 1, 29020.0)
    assert get_slot_positions(store) == []             # closed → snapshot dropped

    core2, eng2, sb2, sbrokers2 = _restart(store)
    assert core2.reconstruct() == []


def test_native_stop_fill_attributes_and_closes_the_slot():
    # The latent bug this work surfaced: a stop coid was never registered, so a native
    # stop FILL was 'unattributed' and the slot never closed. Now it routes + records.
    core, eng, sb, sbrokers, store = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, coid, "BUY", 1, 29000.0)
    stop_coid = core._safeties["grind_long"].stop_for("MNQ").coid
    _fill(core, stop_coid, "SELL", 1, 28980.0)         # the stop triggers at venue
    trades = get_trades(store)
    assert len(trades) == 1 and trades[0]["exit_reason"] == "STOP"
    assert sb.slot("grind_long").is_flat


def test_fill_idempotent_across_restart_redelivery():
    core, eng, sb, sbrokers, store = _core()
    coid = _open(core, eng, "grind_long", "LONG", 29000.0)
    f = Fill("dup-exec-1", coid, "MNQ", "BUY", 1, 29000.0, "2026-07-20T14:00:00+00:00")
    core.on_fill(f)
    core.on_fill(f)                                     # redelivered same exec_id
    assert sb.slot("grind_long").net == 1.0            # applied exactly once, not doubled


def _at(iso):
    return lambda: datetime.fromisoformat(iso)


def test_max_hold_flattens_each_stale_slot_independently():
    core, eng, sb, sbrokers, store = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)        # opened_at = 14:00 (from _fill)
    _fill(core, cL, "BUY", 1, 29000.0)
    cS = _open(core, eng, "grind_short", "SHORT", 29050.0)
    _fill(core, cS, "SELL", 1, 29050.0)
    core._now = _at("2026-07-20T17:00:00+00:00")                # +3h, past 120m; not session-end
    n = len(eng.orders)
    core.time_exit_check()
    # both opened at 14:00 → both past max-hold; each gets its OWN per-slot MKT close
    assert len(eng.orders) == n + 2
    assert {o["side"] for o in eng.orders[-2:]} == {"SELL", "BUY"}
    assert core._close_reason["grind_long"] == "MAX_HOLD"
    assert core._close_reason["grind_short"] == "MAX_HOLD"


def test_max_hold_leaves_a_fresh_slot_alone():
    core, eng, sb, sbrokers, store = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    core._now = _at("2026-07-20T15:00:00+00:00")                # +1h < 120m ceiling
    n = len(eng.orders)
    core.time_exit_check()
    assert len(eng.orders) == n                                 # nothing cut
    assert "grind_long" not in core._closing


def test_session_end_flattens_every_open_slot():
    core, eng, sb, sbrokers, store = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    cS = _open(core, eng, "grind_short", "SHORT", 29050.0)
    _fill(core, cS, "SELL", 1, 29050.0)
    core._now = _at("2026-07-20T20:57:00+00:00")                # inside the 5-min session-end window
    core.time_exit_check()
    assert core._close_reason["grind_long"] == "SESSION_END_FLAT"
    assert core._close_reason["grind_short"] == "SESSION_END_FLAT"


def test_time_exit_is_idempotent_across_cycles():
    core, eng, sb, sbrokers, store = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    core._now = _at("2026-07-20T17:00:00+00:00")
    core.time_exit_check()
    n = len(eng.orders)
    core.time_exit_check()                                      # already closing → no second close
    assert len(eng.orders) == n


def test_exit_wedge_refires_a_stuck_slot_close():
    core, eng, sb, sbrokers, store = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    core._now = _at("2026-07-20T17:00:00+00:00")
    core.time_exit_check()                                      # fires MAX_HOLD close, now in-flight
    stuck_coid = core._closing["grind_long"]
    for _ in range(EXIT_STUCK_CYCLES):                          # close never fills → wedge
        core.exit_watchdog_slot("grind_long")
    assert stuck_coid in eng.cancelled                         # dangling close cancelled before re-fire
    assert core._closing["grind_long"] != stuck_coid           # a fresh close was submitted
    assert core._exit_refires["grind_long"] == 1
    assert core._close_reason["grind_long"] == "MAX_HOLD"      # original reason preserved through re-fire


def test_exit_wedge_forces_reconnect_after_max_refires():
    core, eng, sb, sbrokers, store = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    core._flatten_slot("grind_long", "MAX_HOLD")               # a close in flight
    gw = FakeGw()
    for _ in range(EXIT_STUCK_CYCLES + EXIT_REFIRE_MAX + 1):
        core.exit_watchdog_slot("grind_long", gw)
    assert gw.reconnects >= 1                                   # exhausted re-fires → heal the session


def test_exit_wedge_clears_when_the_close_completes():
    core, eng, sb, sbrokers, store = _core()
    cL = _open(core, eng, "grind_long", "LONG", 29000.0)
    _fill(core, cL, "BUY", 1, 29000.0)
    core._flatten_slot("grind_long", "MAX_HOLD")
    for _ in range(EXIT_STUCK_CYCLES):
        core.exit_watchdog_slot("grind_long")
    assert core._exit_stuck["grind_long"] >= EXIT_STUCK_CYCLES
    _fill(core, core._closing["grind_long"], "SELL", 1, 29010.0)   # the close finally fills
    assert sb.slot("grind_long").is_flat
    assert core._exit_stuck["grind_long"] == 0                 # wedge state reset on completion


def test_write_heartbeat_reflects_flatness_and_held_slots(tmp_path):
    import json
    from dataclasses import replace
    dbp = str(tmp_path / "gb.db")
    store = open_store(dbp)
    eng = FakeEngine()
    sb = SlotBook(list(GATES), value_per_point=2.0, fee_rt=1.5)
    safeties = {g: SafetyManager(FakeStopBroker(tag=g + "-")) for g in GATES}
    cfg = replace(RunConfig(place_live=True), store_path=dbp)
    core = MultiSlotCore(cfg, eng, sb, safeties, FakePub(), store)

    core.write_heartbeat(conn="HEALTHY", healthy=True)
    h = json.loads((tmp_path / "core_health.json").read_text())
    assert h["flat"] is True and h["place_live"] is True and h["protection"]["held"] is False

    coid = _open(core, eng, "grind_long", "LONG", 29000.0, atr=20.0)
    _fill(core, coid, "BUY", 1, 29000.0)
    core.write_heartbeat(conn="HEALTHY", healthy=True)
    h = json.loads((tmp_path / "core_health.json").read_text())
    assert h["flat"] is False
    slot = h["protection"]["slots"][0]
    assert slot["gate"] == "grind_long"
    assert slot["stop_coid"]                                  # the slot's live stop is reported
    assert slot["stop_price"] == 29000.0 - 20.0              # + the price + opened_at the dashboard needs
    assert slot["entry_price"] == 29000.0 and slot["opened_at"]


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
