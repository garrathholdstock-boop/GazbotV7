"""Multi-slot ledger — per-gate positions over a NETTED venue, attributed by coid.
The load-bearing case: a long slot + a short slot net to 0 at the venue, yet each
must be tracked (and closed, and scored) independently."""

from __future__ import annotations

from gazbot7.slotbook import SlotBook
from gazbot7.store import Fill

VPP, FEE = 2.0, 1.5


def _book():
    return SlotBook(["grind_long", "grind_short"], value_per_point=VPP, fee_rt=FEE)


def _f(exec_id, coid, side, qty, price):
    return Fill(exec_id=exec_id, order_id=coid, symbol="MNQ", side=side, qty=qty,
                price=price, exec_time="2026-07-20T14:00:00+00:00")


def test_two_opposing_slots_net_zero_but_tracked_independently():
    b = _book()
    b.register("cL", "grind_long")
    b.register("cS", "grind_short")
    b.apply(_f("e1", "cL", "BUY", 1, 29000.0))    # long slot opens +1
    b.apply(_f("e2", "cS", "SELL", 1, 29050.0))   # short slot opens -1
    assert b.net_qty() == 0.0                      # venue sees FLAT...
    assert b.slot("grind_long").net == 1.0         # ...but the ledger holds both
    assert b.slot("grind_short").net == -1.0
    assert b.slot("grind_long").entry_price == 29000.0
    assert b.slot("grind_short").entry_price == 29050.0


def test_a_close_attributes_to_the_right_slot_only():
    b = _book()
    b.register("cL", "grind_long")
    b.register("cS", "grind_short")
    b.apply(_f("e1", "cL", "BUY", 1, 29000.0))
    b.apply(_f("e2", "cS", "SELL", 1, 29050.0))
    b.register("xL", "grind_long")                 # close the LONG slot only
    trade = b.apply(_f("x1", "xL", "SELL", 1, 29030.0), exit_reason="CHANDELIER")
    assert trade is not None and trade["gate"] == "grind_long" and trade["side"] == "LONG"
    assert trade["pnl_usd"] == (29030 - 29000) * 1 * VPP - FEE   # +58.5
    assert b.slot("grind_long").is_flat            # long slot flat again
    assert b.slot("grind_short").net == -1.0       # short slot UNTOUCHED
    assert b.net_qty() == -1.0                      # venue now net -1 (the short)


def test_reconcile_match_and_drift():
    b = _book()
    b.register("cS", "grind_short")
    b.apply(_f("e1", "cS", "SELL", 2, 29000.0))
    assert b.reconcile(-2.0) == "match"            # logical -2 == venue -2
    assert b.reconcile(-1.0) == "drift"            # a lot vanished/leaked at venue


def test_short_slot_pnl_sign():
    b = _book()
    b.register("cS", "grind_short")
    b.register("xS", "grind_short")
    b.apply(_f("e1", "cS", "SELL", 1, 29000.0))
    t = b.apply(_f("x1", "xS", "BUY", 1, 28950.0), exit_reason="TARGET")   # cover lower = win
    assert t["side"] == "SHORT" and t["pnl_usd"] == (29000 - 28950) * VPP - FEE  # +98.5


def test_partial_exit_is_atomic():
    b = _book()
    b.register("cL", "grind_long")
    b.register("xL", "grind_long")
    b.apply(_f("e", "cL", "BUY", 2, 100.0))
    assert b.apply(_f("x1", "xL", "SELL", 1, 105.0), exit_reason="STOP") is None  # 1 of 2 — not done
    assert b.slot("grind_long").net == 1.0
    t = b.apply(_f("x2", "xL", "SELL", 1, 107.0), exit_reason="STOP")             # 2nd → complete
    assert t is not None and t["exit_price"] == 106.0                            # fills-VWAP
    assert b.slot("grind_long").is_flat


def test_idempotent_on_exec_id():
    b = _book()
    b.register("cL", "grind_long")
    b.apply(_f("e1", "cL", "BUY", 1, 100.0))
    b.apply(_f("e1", "cL", "BUY", 1, 100.0))       # re-delivered same exec → no double
    assert b.slot("grind_long").net == 1.0


def test_unattributed_fill_is_ignored_not_guessed():
    b = _book()                                     # no register() for this coid
    assert b.apply(_f("e1", "unknown-coid", "BUY", 1, 100.0)) is None
    assert b.net_qty() == 0.0                        # nothing booked to a guessed slot
