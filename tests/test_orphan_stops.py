"""The inverse audit: does every working STOP have a position behind it?

★ WHY. The desk has always asked "does every slot have a stop?" and never the inverse. An order
belonging to no position is invisible to a per-slot auditor, and that is exactly what fires
unattended:
  · 2026-08-06 a leftover stop triggered with nothing behind it and OPENED A NAKED SHORT, booked
    six hours later as a gate trade nobody placed.
  · 2026-08-13 the day-rider's 600pt venue stop (orderId 49, SELL 2 STP @ 29424.25) outlived the
    position it protected by ~2h. eod_flatten's cancel returned `Error 10147: not found` — IBKR
    saying "not yours to cancel" (clientId 6 vs the order's clientId 4) — which reads as an
    all-clear and was reported as one.

The cross-desk POSITION reconcile cannot catch this: an orphan order is not a position until the
moment it becomes one.
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

from desk_reconcile import orphan_stops  # noqa: E402


def O(**kw):
    base = {"id": 49, "client": 4, "action": "SELL", "type": "STP", "qty": 2.0,
            "aux": 29424.25, "status": "PreSubmitted"}
    base.update(kw)
    return base


def test_the_0813_orphan_is_caught():
    # venue flat, a working SELL stop for 2 — the exact live case.
    bad = orphan_stops(0.0, [O()])
    assert len(bad) == 1
    assert bad[0]["id"] == 49 and "FLAT" in bad[0]["why"]


def test_a_real_protective_stop_is_not_flagged():
    assert orphan_stops(2.0, [O(action="SELL", qty=2.0)]) == []      # SELL guards a LONG
    assert orphan_stops(-2.0, [O(action="BUY", qty=2.0)]) == []      # BUY guards a SHORT
    assert orphan_stops(2.0, [O(action="SELL", qty=1.0)]) == []      # partial cover is fine


def test_a_stop_on_the_wrong_side_would_ADD_not_protect():
    bad = orphan_stops(2.0, [O(action="BUY")])
    assert len(bad) == 1 and "ADD" in bad[0]["why"]
    bad = orphan_stops(-2.0, [O(action="SELL")])
    assert len(bad) == 1 and "ADD" in bad[0]["why"]


def test_an_oversized_stop_would_flip_the_position():
    bad = orphan_stops(1.0, [O(action="SELL", qty=3.0)])
    assert len(bad) == 1 and "exceeds" in bad[0]["why"]


def test_non_stop_orders_are_ignored():
    # a resting LIMIT is an entry, not a protective order — not this check's business
    assert orphan_stops(0.0, [O(type="LMT")]) == []
    assert orphan_stops(0.0, [O(type="MKT")]) == []


def test_trailing_stops_count_as_protective_orders():
    # the day-rider's venue stop is a TRAIL in some configurations; it must not slip through
    assert len(orphan_stops(0.0, [O(type="TRAIL")])) == 1
    assert len(orphan_stops(0.0, [O(type="STP LMT")])) == 1


def test_no_orders_is_clean():
    assert orphan_stops(0.0, []) == []
    assert orphan_stops(-8.0, []) == []


def test_multiple_orphans_all_reported():
    bad = orphan_stops(0.0, [O(id=49), O(id=53, action="BUY"), O(id=57, type="TRAIL")])
    assert {b["id"] for b in bad} == {49, 53, 57}, "a silent cap here would hide the second one"
