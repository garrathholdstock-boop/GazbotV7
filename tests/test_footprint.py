"""Exhaustion-reversal footprint — the pure fade gate + the observe-only tick/book evaluator.
Fade heavy aggression absorbed into a wall; exit 8pt/12pt/120s, tick-repriced. Never trades."""
from __future__ import annotations

import sqlite3

from gazbot7.footprint import FootprintCfg, FootprintShadow, exhaustion_signal
from gazbot7.store import open_store


def test_signal_buy_absorbed_into_ask_wall_fades_short():
    # +500 buy tape, price barely moved, ask wall 3× the bid → SHORT the exhaustion
    s = exhaustion_signal(500, 1.0, bid1_size=10, ask1_size=30, bid1_price=100.0, ask1_price=100.5)
    assert s == ("SHORT", 100.25)


def test_signal_sell_absorbed_into_bid_wall_fades_long():
    s = exhaustion_signal(-500, -1.0, bid1_size=30, ask1_size=10, bid1_price=100.0, ask1_price=100.5)
    assert s == ("LONG", 100.25)


def test_signal_needs_the_net_floor():
    assert exhaustion_signal(300, 1.0, 10, 30, 100.0, 100.5) is None   # 300 < 400


def test_signal_rejects_when_price_actually_moved():
    # big tape but price moved 3pt → the aggression WORKED, not absorbed
    assert exhaustion_signal(500, 3.0, 10, 30, 100.0, 100.5) is None


def test_signal_needs_the_wall_on_the_hit_side():
    # buy-heavy but the ASK (hit side) is NOT ≥1.5× the bid → no wall → no fade
    assert exhaustion_signal(500, 1.0, bid1_size=30, ask1_size=20, bid1_price=100.0, ask1_price=100.5) is None


def _cap_with(ticks, book):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE ticks(symbol TEXT, ts_ms INT, price REAL, size REAL, aggressor TEXT)")
    con.execute("CREATE TABLE book(symbol TEXT, ts_ms INT, side TEXT, level INT, price REAL, size REAL)")
    con.executemany("INSERT INTO ticks VALUES('MNQ',?,?,?,?)", ticks)
    con.executemany("INSERT INTO book VALUES('MNQ',?,?,1,?,?)", book)
    return con


def test_evaluator_fires_and_records_a_target_win():
    store = open_store(":memory:")
    fp = FootprintShadow(store, "MNQ", value_per_point=2.0, fee_rt=1.5)
    # 20s of heavy BUY tape (net +500) that barely moves price (100.0→100.5)
    ticks = [(t, 100.0 + 0.02 * i, 50, "buy") for i, t in enumerate(range(1_000_000, 1_020_001, 1000))]
    book = [(1_020_000, "bid", 100.0, 10), (1_020_000, "ask", 100.5, 40)]     # ask wall 4× bid
    cap = _cap_with(ticks, book)
    fp.on_cycle(cap, 1_020_000)
    assert fp._open is not None and fp._open["side"] == "SHORT"
    # now price falls 12pt to the target within the hold window
    cap.executemany("INSERT INTO ticks VALUES('MNQ',?,?,?,?)",
                    [(1_030_000, 100.25 - 12.0, 5, "sell")])
    fp.on_cycle(cap, 1_030_000)
    assert fp._open is None
    rows = store.execute("SELECT strategy, side, exit_reason FROM shadow_trades").fetchall()
    assert rows and rows[0][0] == "exhaustion_rev" and rows[0][1] == "SHORT" and rows[0][2] == "TARGET"


def test_evaluator_stays_flat_when_no_wall():
    store = open_store(":memory:")
    fp = FootprintShadow(store, "MNQ", value_per_point=2.0, fee_rt=1.5)
    ticks = [(t, 100.0, 50, "buy") for t in range(1_000_000, 1_020_001, 1000)]
    book = [(1_020_000, "bid", 100.0, 40), (1_020_000, "ask", 100.5, 10)]    # no ask wall (bid is bigger)
    cap = _cap_with(ticks, book)
    fp.on_cycle(cap, 1_020_000)
    assert fp._open is None
