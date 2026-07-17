"""core — the broker service: intents in, orders out, position truth published.

Exercises the execution half lifted out of Desk: the one-position guard, the
open→arm-stop path, the close→record→clear-stop path, native-STP-fill recording,
two-sided entries, and place_live gating. Fakes for the broker + publisher; the
real engine/tracker/safety do the work (the same primitives Desk used)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from gazbot7.config import RunConfig
from gazbot7.core import EXIT_STUCK_CYCLES, Core
from gazbot7.engine import OrderEngine
from gazbot7.ipc import T_FILL, T_INTENT_RESULT, T_POSITION, T_TRADE
from gazbot7.safety import SafetyManager
from gazbot7.store import (
    Fill,
    get_open_position,
    get_trades,
    open_store,
    record_trade,
    upsert_open_position,
)
from gazbot7.tracker import TradeTracker

VPP, FEE = 2.0, 1.5
# a fixed in-session clock (Wed 2026-07-15 16:00 UTC = 12:00 ET) so entry-gate
# tests never depend on when the suite runs.
IN_SESSION = datetime(2026, 7, 15, 16, 0, tzinfo=UTC)


class FakeBroker:
    def __init__(self):
        self.orders: list[dict] = []

    def place(self, order):
        self.orders.append(dict(side=order.side, qty=order.qty))

    def cancel(self, coid):
        pass


class FakeStopBroker:
    def __init__(self):
        self.stops: list[dict] = []
        self.cancelled: list[str] = []
        self._n = 0

    def place_stop(self, *, symbol, side, qty, stop_price):
        self._n += 1
        self.stops.append(dict(side=side, qty=qty, stop_price=stop_price))
        return f"stp-{self._n}"

    def cancel(self, coid):
        self.cancelled.append(coid)


class FakePub:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    async def send(self, topic, payload):
        self.sent.append((topic, payload))


class FakeGateway:
    """Just the surface the unverified-protection watchdog touches."""
    def __init__(self):
        self.reconnects = 0

    def force_reconnect(self):
        self.reconnects += 1


def _build(*, place_live=True, is_healthy=None, now_fn=None, **cfgkw):
    store = open_store(":memory:")
    broker, sb = FakeBroker(), FakeStopBroker()
    oe = OrderEngine(broker, store)
    tt = TradeTracker(store, value_per_point=VPP, fee_rt=FEE)
    sm = SafetyManager(sb)
    pub = FakePub()
    cfg = RunConfig(place_live=place_live, **cfgkw)
    core = Core(cfg, oe, tt, sm, pub, store, is_healthy=is_healthy,
                now_fn=now_fn or (lambda: IN_SESSION))
    return core, broker, sb, pub, store


def _loss(store, i, p=-5.0):
    record_trade(store, symbol="MNQ", side="LONG", qty=1, entry_price=100.0, exit_price=99.0,
                 opened_at="2026-07-15T13:00:00+00:00", closed_at=f"2026-07-15T1{i}:00:00+00:00",
                 pnl_usd=p, fees_usd=1.5, exit_reason="STOP", exit_exec_id=f"x{i}")


def _fill(exec_id, side, qty, price):
    return Fill(exec_id=exec_id, order_id="o", symbol="MNQ", side=side, qty=qty, price=price,
                exec_time="2026-07-15T13:00:00+00:00")


def _topics(pub, topic):
    return [p for t, p in pub.sent if t == topic]


def test_open_intent_submits_and_arms_stop():
    async def scenario():
        core, broker, sb, pub, _s = _build()
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG",
                              "qty": 1, "meta": {"entry_atr": 4.0}})
        assert broker.orders == [dict(side="BUY", qty=1)]
        res = _topics(pub, T_INTENT_RESULT)[-1]
        assert res["iid"] == "i1" and res["accepted"] is True
        core.on_fill(_fill("e1", "BUY", 1, 100.0))
        await asyncio.sleep(0)  # flush the fire-and-forget emits
        assert core.position is not None and core.position.side == "LONG"
        assert sb.stops == [dict(side="SELL", qty=1.0, stop_price=96.0)]  # 100 − 1·ATR(4)
        assert _topics(pub, T_FILL) and _topics(pub, T_POSITION)[-1]["flat"] is False
    asyncio.run(scenario())


def test_one_position_guard_rejects_second_open():
    async def scenario():
        core, broker, _sb, pub, _s = _build()
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG", "meta": {"entry_atr": 4.0}})
        core.on_fill(_fill("e1", "BUY", 1, 100.0))
        await asyncio.sleep(0)
        await core.on_intent({"iid": "i2", "action": "OPEN", "side": "LONG", "meta": {"entry_atr": 4.0}})
        assert len(broker.orders) == 1  # the second OPEN never reached the broker
        assert _topics(pub, T_INTENT_RESULT)[-1] == {
            "iid": "i2", "accepted": False, "reason": "already in position", "coid": None}
    asyncio.run(scenario())


def test_close_intent_records_trade_and_clears_stop():
    async def scenario():
        core, broker, sb, pub, store = _build()
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG", "meta": {"entry_atr": 4.0}})
        core.on_fill(_fill("e1", "BUY", 1, 100.0))
        await asyncio.sleep(0)
        await core.on_intent({"iid": "i2", "action": "CLOSE", "reason": "SIGNAL_CLOSE"})
        assert broker.orders[-1] == dict(side="SELL", qty=1.0)
        core.on_fill(_fill("x1", "SELL", 1, 110.0))
        await asyncio.sleep(0)
        (tr,) = get_trades(store)
        assert tr["exit_reason"] == "SIGNAL_CLOSE"
        assert tr["pnl_usd"] == (110 - 100) * 1 * VPP - FEE  # +18.5
        assert core.position is None
        assert sb.cancelled == ["stp-1"]
        assert _topics(pub, T_TRADE)[-1]["pnl"] == 18.5
    asyncio.run(scenario())


def test_native_stop_fill_records_as_STOP():
    async def scenario():
        core, _b, _sb, _pub, store = _build()
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG", "meta": {"entry_atr": 4.0}})
        core.on_fill(_fill("e1", "BUY", 1, 100.0))
        await asyncio.sleep(0)
        core.on_fill(_fill("x1", "SELL", 1, 96.0))  # STP filled at the venue, no CLOSE intent
        await asyncio.sleep(0)
        (tr,) = get_trades(store)
        assert tr["exit_reason"] == "STOP"
    asyncio.run(scenario())


def test_short_entry_two_sided():
    async def scenario():
        core, broker, sb, _pub, _s = _build()
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "SHORT", "meta": {"entry_atr": 4.0}})
        assert broker.orders == [dict(side="SELL", qty=1)]
        core.on_fill(_fill("e1", "SELL", 1, 100.0))
        await asyncio.sleep(0)
        assert core.position.side == "SHORT"
        assert sb.stops == [dict(side="BUY", qty=1.0, stop_price=104.0)]  # 100 + 1·ATR above
    asyncio.run(scenario())


async def _open_long(core):
    await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG", "meta": {"entry_atr": 4.0}})
    core.on_fill(_fill("e1", "BUY", 1, 100.0))
    await asyncio.sleep(0)
    core._boot_mono = 0.0  # neutralise boot-settle for the assess tests
    core._armed_mono = 0.0  # neutralise arm-settle too (set fresh in the arm-settle test)


def test_naked_auditor_covered_is_ok():
    async def scenario():
        core, *_ = _build()
        await _open_long(core)
        live_stop = [("STP", "SELL", "PreSubmitted", 1.0)]
        assert core.assess_protection(1.0, live_stop, now_mono=200.0) == "ok"
    asyncio.run(scenario())


def test_naked_auditor_reprotects_then_flattens():
    async def scenario():
        core, *_ = _build()
        await _open_long(core)
        naked = [("STP", "SELL", "Inactive", 1.0)]  # placed but didn't stick
        assert core.assess_protection(1.0, naked, now_mono=200.0) == "reprotect"
        assert core.assess_protection(1.0, naked, now_mono=205.0) == "flatten"  # 2nd strike
    asyncio.run(scenario())


def test_naked_auditor_boot_settle_grace():
    async def scenario():
        core, *_ = _build()
        await _open_long(core)
        naked = [("STP", "SELL", "Cancelled", 1.0)]
        assert core.assess_protection(1.0, naked, now_mono=50.0) == "settle"  # within 120s
    asyncio.run(scenario())


def test_naked_auditor_flat_resets_streak():
    async def scenario():
        core, *_ = _build()
        await _open_long(core)
        core.assess_protection(1.0, [("STP", "SELL", "Inactive", 1.0)], now_mono=200.0)  # streak→1
        assert core.assess_protection(0.0, [], now_mono=205.0) == "flat"  # venue flat
        assert core._naked_streak == 0
    asyncio.run(scenario())


# ── arm-time stop confirmation: a just-armed stop gets a propagation settle ───
def test_arm_settle_defers_naked_then_reprotects():
    from gazbot7.core import ARM_SETTLE_S

    async def scenario():
        core, *_ = _build()
        await _open_long(core)
        core._boot_mono = 0.0
        naked = [("STP", "SELL", "Inactive", 1.0)]  # no live coverage at venue
        core._armed_mono = 200.0  # armed at t=200 (past the 120s boot-settle window)
        # within the settle window → give the just-placed stop time to appear (no double-arm)
        assert core.assess_protection(1.0, naked, now_mono=200.0 + ARM_SETTLE_S - 1) == "settle"
        # past it → a placement that never landed is caught + re-armed
        assert core.assess_protection(1.0, naked, now_mono=200.0 + ARM_SETTLE_S + 1) == "reprotect"
    asyncio.run(scenario())


def test_open_confirms_the_stop_by_poking_the_auditor():
    async def scenario():
        core, *_ = _build()
        core._protect_poke.clear()
        # open WITHOUT the neutralising helper so we can see _on_opened's arm confirmation
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG", "meta": {"entry_atr": 4.0}})
        core.on_fill(_fill("e1", "BUY", 1, 100.0))
        await asyncio.sleep(0)
        assert core._protect_poke.is_set()  # arm-time confirmation was requested
        assert core._armed_mono != 0.0       # arm anchor stamped
    asyncio.run(scenario())


# ── vanished close → reconstruct + record from venue executions (recording gap) ─
class _Exec:
    def __init__(self, execId, side, shares, price):
        self.execId, self.side, self.shares, self.price = execId, side, shares, price


class _ExecRow:
    def __init__(self, ex, symbol="MNQ"):
        self.execution = ex
        self.contract = type("C", (), {"symbol": symbol})()
        self.time = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)


class _ExecIB:
    def __init__(self, rows):
        self._rows = rows

    async def reqExecutionsAsync(self, _filter):
        return self._rows


class _ExecGW:
    def __init__(self, rows):
        self._ib = _ExecIB(rows)


def test_vanished_reconstructs_and_records_the_close():
    async def scenario():
        core, _b, _sb, _pub, store = _build()
        await _open_long(core)  # LONG 1 @ 100; tracker holds it, entry exec 'e1' applied
        rows = [_ExecRow(_Exec("e1", "BOT", 1, 100.0)),  # entry — already applied, skipped
                _ExecRow(_Exec("x9", "SLD", 1, 108.0))]  # UNSEEN close @ 108
        await core._reconcile_vanished(_ExecGW(rows))
        trades = get_trades(store)
        assert len(trades) == 1
        assert trades[0]["exit_reason"] == "RECONCILED_CLOSE"
        assert trades[0]["pnl_usd"] == (108.0 - 100.0) * VPP - FEE  # real exit price, real P&L
        assert core._pos is None and core._tt.net_qty("MNQ") == 0.0  # cleared
    asyncio.run(scenario())


def test_vanished_pages_and_forgets_when_unreconstructable():
    async def scenario():
        core, _b, _sb, _pub, store = _build()
        await _open_long(core)
        msgs: list[str] = []
        core._notify = msgs.append
        await core._reconcile_vanished(_ExecGW([]))  # no executions available
        assert any("couldn't be reconstructed" in m for m in msgs)  # paged, not silent
        assert get_trades(store) == []          # nothing fabricated
        assert core._pos is None and core._tt.net_qty("MNQ") == 0.0  # dangling open forgotten
    asyncio.run(scenario())


# ── protection-unverifiable watchdog (2026-07-17 naked-bleed fix) ─────────────
def test_unverified_protection_silent_when_flat():
    # a FLAT desk has nothing at risk — 'can't verify' is silent, no page/reconnect
    core, *_ = _build()
    gw = FakeGateway()
    msgs: list[str] = []
    core._notify = msgs.append
    for _ in range(20):
        core._on_unverified_protection(gw)
    assert msgs == [] and gw.reconnects == 0 and core._unverified == 0


def test_unverified_protection_held_pages_then_heals():
    # a HELD position that can't be verified must NEVER silently skip: page fast,
    # then force a fresh session to heal the data path (the 3h no-op bug)
    from gazbot7.core import UNVERIFIED_PAGE_CYCLES, UNVERIFIED_RECONNECT_CYCLES

    async def scenario():
        core, *_ = _build()
        await _open_long(core)
        gw = FakeGateway()
        msgs: list[str] = []
        core._notify = msgs.append
        for _ in range(UNVERIFIED_PAGE_CYCLES):
            core._on_unverified_protection(gw)
        assert len(msgs) == 1 and "CANNOT VERIFY" in msgs[0]  # paged the operator fast
        assert gw.reconnects == 0
        for _ in range(UNVERIFIED_RECONNECT_CYCLES - UNVERIFIED_PAGE_CYCLES):
            core._on_unverified_protection(gw)
        assert gw.reconnects == 1  # forced a session heal once we passed the reconnect threshold
    asyncio.run(scenario())


def test_verify_ok_clears_the_watchdog():
    async def scenario():
        core, *_ = _build()
        await _open_long(core)
        gw = FakeGateway()
        core._notify = lambda _m: None
        for _ in range(5):
            core._on_unverified_protection(gw)
        assert core._unverified == 5
        core._verify_ok()  # a good snapshot resets the escalation
        assert core._unverified == 0 and core._unverified_alarmed is False
    asyncio.run(scenario())


def test_protection_status_flags_held_and_verified():
    async def scenario():
        core, *_ = _build()
        assert core._protection_status() == {"held": False}  # flat → nothing to protect
        await _open_long(core)
        core._protection_ok = True
        st = core._protection_status()
        assert st["held"] is True and st["verified"] is True
        core._protection_ok = False
        assert core._protection_status()["verified"] is False  # naked/unverified surfaces
    asyncio.run(scenario())


def test_reprotect_and_emergency_flatten_actions():
    async def scenario():
        core, broker, sb, _pub, _s = _build()
        await _open_long(core)
        assert len(sb.stops) == 1  # the initial arm
        core._reprotect()
        assert len(sb.stops) == 2  # re-armed a fresh protective stop
        core._emergency_flatten()
        assert broker.orders[-1] == dict(side="SELL", qty=1.0)  # MKT close of the long
    asyncio.run(scenario())


def test_place_live_off_rejects_open():
    async def scenario():
        core, broker, _sb, pub, _s = _build(place_live=False)
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG", "meta": {"entry_atr": 4.0}})
        assert broker.orders == []
        assert _topics(pub, T_INTENT_RESULT)[-1]["reason"] == "place_live off"
    asyncio.run(scenario())


# ── S2: reconcile / adopt ────────────────────────────────────────────────────
def test_open_persists_and_close_clears_open_position():
    async def scenario():
        core, _b, _sb, _pub, store = _build()
        await _open_long(core)
        rec = get_open_position(store, "MNQ")
        assert rec is not None and rec["side"] == "LONG"
        assert rec["entry_atr"] == 4.0 and rec["stop_price"] == 96.0  # persisted for adopt
        await core.on_intent({"iid": "c", "action": "CLOSE", "reason": "SIGNAL_CLOSE"})
        core.on_fill(_fill("x1", "SELL", 1, 110.0))
        await asyncio.sleep(0)
        assert get_open_position(store, "MNQ") is None  # cleared on flat
    asyncio.run(scenario())


def test_adopt_from_venue_recovers_atr_and_rearms():
    async def scenario():
        core, _b, sb, _pub, store = _build()
        # a prior position persisted, as if before a restart
        upsert_open_position(store, symbol="MNQ", side="LONG", qty=1, entry_price=100.0,
                             entry_atr=4.0, opened_at="t0", stop_price=96.0)
        assert core.adopt_from_venue(1.0) == "adopted"
        assert core.position.side == "LONG" and core._qty == 1.0
        assert sb.stops[-1] == dict(side="SELL", qty=1.0, stop_price=96.0)  # re-armed at recovered ATR
    asyncio.run(scenario())


def test_adopt_flattens_unrecoverable_and_records_clean():
    async def scenario():
        core, broker, _sb, _pub, store = _build()  # no persisted open_position → un-adoptable
        core._handle_adopt(-2.0, avg_price=29000.0)  # IBKR shows a SHORT 2 we can't protect
        assert broker.orders[-1] == dict(side="BUY", qty=2.0)  # flatten (buy to cover)
        core.on_fill(_fill("x1", "BUY", 2, 29100.0))  # the cover fills
        await asyncio.sleep(0)
        (tr,) = get_trades(store)  # closed cleanly as an honest trade, no phantom
        assert tr["exit_reason"] == "ADOPT_FLATTEN" and tr["side"] == "SHORT"
        assert tr["pnl_usd"] == (29000 - 29100) * 2 * VPP - FEE  # short covered higher = a loss
        assert core.position is None and core._qty == 0.0  # flat, no mis-booked long
    asyncio.run(scenario())


def test_unhealthy_gateway_rejects_open():
    async def scenario():
        core, broker, _sb, pub, _s = _build(is_healthy=lambda: False)
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG", "meta": {"entry_atr": 4.0}})
        assert broker.orders == []  # not TRADING-eligible → no entry
        assert _topics(pub, T_INTENT_RESULT)[-1]["reason"] == "gateway not healthy"
    asyncio.run(scenario())


def test_halt_gate_rejects_open():
    async def scenario():
        core, broker, _sb, pub, _s = _build()
        core._halted = True
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG", "meta": {"entry_atr": 4.0}})
        assert broker.orders == []
        assert _topics(pub, T_INTENT_RESULT)[-1]["reason"] == "halted (reconcile drift)"
    asyncio.run(scenario())


def test_clear_phantom_drops_state_and_cancels_stop():
    async def scenario():
        core, _b, sb, _pub, store = _build()
        await _open_long(core)
        core._clear_phantom()
        assert core.position is None and core._qty == 0.0
        assert sb.cancelled == ["stp-1"]  # tracked stop cancelled
        assert get_open_position(store, "MNQ") is None
    asyncio.run(scenario())


# ── S4: session discipline ───────────────────────────────────────────────────
def test_session_block_gates_entry():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    core, *_ = _build()
    assert core._session_block(datetime(2026, 7, 15, 12, 0, tzinfo=et)) is None            # open midday
    assert core._session_block(datetime(2026, 7, 18, 12, 0, tzinfo=et)) == "market closed"  # Saturday
    assert core._session_block(datetime(2026, 7, 15, 16, 50, tzinfo=et)) == "no-open window (session end)"


def test_over_max_hold():
    from datetime import UTC, datetime

    async def scenario():
        core, *_ = _build(max_hold_minutes=120)
        await _open_long(core)  # opened_at = 2026-07-15T13:00:00+00:00
        assert core.over_max_hold(datetime(2026, 7, 15, 14, 0, tzinfo=UTC)) is False   # 60 min
        assert core.over_max_hold(datetime(2026, 7, 15, 15, 30, tzinfo=UTC)) is True   # 150 min
    asyncio.run(scenario())


# ── S5: safe-flatten + exit-not-completing watchdog ──────────────────────────
def test_emergency_flatten_fires_only_venue_qty():
    async def scenario():
        core, broker, _sb, _pub, _s = _build()
        await _open_long(core)  # tracked qty 1
        core._emergency_flatten("MAX_HOLD", venue_net=2.0)  # IBKR truth says 2 → SELL 2
        assert broker.orders[-1] == dict(side="SELL", qty=2.0)
    asyncio.run(scenario())


def test_emergency_flatten_skips_when_venue_flat():
    async def scenario():
        core, broker, _sb, _pub, _s = _build()
        await _open_long(core)
        n0 = len(broker.orders)
        core._emergency_flatten("MAX_HOLD", venue_net=0.0)  # venue flat → a close would OPEN → SKIP
        assert len(broker.orders) == n0 and core._closing is False
    asyncio.run(scenario())


# ── S8: kill-switches ────────────────────────────────────────────────────────
def test_kill_switch_daily_loss():
    core, *_rest = _build(max_daily_loss_usd=100, loss_streak_halt=0)
    store = _rest[3]
    _loss(store, 4, -60.0)
    _loss(store, 5, -60.0)  # today's realized −120 ≤ −100
    reason = core._open_reject_reason({"side": "LONG"}, IN_SESSION)
    assert reason is not None and "daily loss limit" in reason


def test_kill_switch_loss_streak():
    core, *_rest = _build(max_daily_loss_usd=0, loss_streak_halt=4)
    store = _rest[3]
    for i in range(4):
        _loss(store, i, -5.0)  # 4 losers in a row
    reason = core._open_reject_reason({"side": "LONG"}, IN_SESSION)
    assert reason is not None and "loss streak" in reason


def test_kill_switch_lets_a_clean_book_trade():
    core, *_ = _build(max_daily_loss_usd=100, loss_streak_halt=4)
    assert core._open_reject_reason({"side": "LONG"}, IN_SESSION) is None


# ── S6: the intent funnel ────────────────────────────────────────────────────
def test_funnel_records_submitted_then_blocked():
    async def scenario():
        core, _b, _sb, _pub, store = _build()
        await core.on_intent({"iid": "i1", "action": "OPEN", "side": "LONG",
                              "gate": "thrust", "meta": {"entry_atr": 4.0}})
        core.on_fill(_fill("e1", "BUY", 1, 100.0))
        await asyncio.sleep(0)
        await core.on_intent({"iid": "i2", "action": "OPEN", "side": "LONG",
                              "gate": "thrust", "meta": {"entry_atr": 4.0}})
        rows = store.execute("SELECT gate, outcome, block_reason FROM signals ORDER BY id").fetchall()
        assert (rows[0]["gate"], rows[0]["outcome"]) == ("thrust", "submitted")
        assert rows[1]["outcome"] == "blocked" and rows[1]["block_reason"] == "already in position"
    asyncio.run(scenario())


def test_exit_not_completing_alarms():
    async def scenario():
        core, _b, _sb, _pub, _s = _build()
        notes: list[str] = []
        core._notify = notes.append
        await _open_long(core)
        core._emergency_flatten("MAX_HOLD", venue_net=1.0)  # fires, _closing latched
        for _ in range(EXIT_STUCK_CYCLES):  # cycles where the position never reduces
            core._exit_watchdog(1.0)
        assert any("EXIT_NOT_COMPLETING" in n for n in notes)
    asyncio.run(scenario())
