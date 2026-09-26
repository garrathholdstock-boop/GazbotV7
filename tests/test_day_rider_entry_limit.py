"""Entries go in on a MARKETABLE LIMIT, and the book records what actually FILLED.

★★★ WHY (2026-09-04, SESSIONS §387). The IBKR paper engine fills every lot beyond the first at
EXACTLY 0.1% of price, adverse, rounded to the tick — a price that never prints. Measured
0.09897-0.09998% on 21/21 multi-lot rider orders, both session halves, both sides, three weeks; the
same signature appears on the tournament's independent order path. $2,916.50 over 32 orders / 101
lots — more than the desk's entire booked loss. A limit cannot fill worse than its price, so the
fabricated fill becomes impossible.

⚠⚠ THE HAZARD THIS FIX INTRODUCES, AND MUST NOT LEAVE OPEN: a limit can PARTIAL-fill where a market
order could not. Both entry paths used to book `qty=LOTS` / `qty=_q` from the REQUEST. Booking 4
against a venue of 1 is exactly the unaccounted-lot condition the cross-desk reconciler stops both
desks for — the cure must not manufacture the false kill it was written beside.

★★ 2026-09-15 UPDATE — MULTI-LOT EXITS ARE LIMITS TOO NOW, by operator decision, after the same
fabrication booked 3 lots at 29262.00 (a price that never printed; the six-minute low was 29274.75)
and turned a -$115 claim into -$304.50. This file used to say "EXITS STAY ON MARKET ORDERS", on the
grounds that an unfilled exit is unbounded risk while a fabricated fill is bounded. THAT ARGUMENT
WAS NEVER WRONG — place_exit() removes its PREMISE instead, by escalating to a market order for
whatever the limit has not filled inside RIDER_EXIT_LIMIT_WAIT_S. The position always closes.
⚠ What did NOT change, and is asserted below: the 20:40Z HARD FLAT is a market order,
unconditionally, and single-lot exits are untouched because the fabrication cannot reach them.
"""
import asyncio
import sys
import types

sys.path.insert(0, "/home/alphabot/gazbot7/src")

import gazbot7.day_rider as dr

SRC = "/home/alphabot/gazbot7/src/gazbot7/day_rider.py"


class _Status:
    def __init__(self, filled, avg, status="Filled"):
        self.filled, self.avgFillPrice, self.status = filled, avg, status


class _Trade:
    def __init__(self, filled, avg, status="Filled"):
        self.orderStatus = _Status(filled, avg, status)
        self.order = object()


class _IB:
    """Records what was placed and fills it the way a LIMIT really behaves: never worse than lmt."""

    def __init__(self, fill_qty, fill_px, status="Filled"):
        self.placed, self.cancelled = [], []
        self._t = _Trade(fill_qty, fill_px, status)

    def placeOrder(self, contract, order):
        self.placed.append(order)
        return self._t

    def cancelOrder(self, order):
        self.cancelled.append(order)


class _Notes:
    def __init__(self):
        self.sent = []

    def __call__(self, msg, critical=False):
        self.sent.append((msg, critical))


def _run(ib, side="BUY", qty=4, ref=29625.50, notify=None):
    return asyncio.run(dr.place_entry(ib, object(), side, qty, ref, "MNQ",
                                      what=f"TEST {side}", notify=notify))


# ── ⚠⚠⚠ THESE THREE USED TO BORROW THE LIVE MARKET (fixed 2026-09-26) ────────────────────────────
# They called last_tape_price() against the PRODUCTION capture.db and asserted a real price came
# back. That works while the venue is open and FAILS EVERY WEEKEND: run on Saturday 05:07Z with the
# newest bar 8.1 HOURS old, all three failed and none of them had a bug — the tape was simply shut.
# ⚠ It is [[tests-must-not-read-the-wall-clock]] in a new costume: not the clock directly, but a
# dependency on what the clock implies about the market. 37 core tests once failed only between
# 00-07 UTC for the same reason.
# ★ THE INVARIANTS ARE GOOD AND ARE KEPT EXACTLY — the fallback exists, and the symbol filter holds.
# They are now checked against a FIXTURE with known prices and fresh timestamps, so they test the
# LOGIC rather than the opening hours of an exchange.
def _tape_fixture(tmp_path, ages=(5, 5)):
    """A capture.db with one fresh MNQ bar and one fresh MGC bar, at unmistakable prices."""
    import sqlite3, time
    p = tmp_path / "capture.db"
    c = sqlite3.connect(str(p))
    c.execute("create table bars (symbol text, timeframe text, bar_ts int, open real, "
              "high real, low real, close real, volume real)")
    now = int(time.time())
    for sym, px, age in (("MNQ", 29500.0, ages[0]), ("MGC", 2410.0, ages[1])):
        c.execute("insert into bars values (?,'5s',?,?,?,?,?,?)",
                  (sym, now - age, px, px, px, px, 100.0))
    c.commit(); c.close()
    return str(p)


def test_the_limit_is_marketable_and_on_the_right_side():
    ib = _IB(4, 29626.0)
    _run(ib)
    o = ib.placed[0]
    assert type(o).__name__ == "LimitOrder", f"an entry must not be a market order: {type(o).__name__}"
    assert o.lmtPrice > 29625.50, "a BUY limit below the reference would never cross"
    assert o.lmtPrice == 29625.50 + dr.ENTRY_LIMIT_BAND_PT, o.lmtPrice
    ib2 = _IB(4, 29625.0)
    _run(ib2, side="SELL")
    assert ib2.placed[0].lmtPrice == 29625.50 - dr.ENTRY_LIMIT_BAND_PT


def test_the_band_blocks_the_fabricated_fill():
    """★ THE WHOLE POINT. The synthetic fill is 0.1% of price; the limit must sit well inside it."""
    ref = 29625.50
    fabricated = ref * 1.001                       # 29655.13 — what the paper engine did on 09-04
    ib = _IB(4, 29626.0)
    _run(ib, ref=ref)
    assert ib.placed[0].lmtPrice < fabricated, (
        f"limit {ib.placed[0].lmtPrice} would still permit the fabricated {fabricated:.2f} fill")
    # and it must still clear a real spread comfortably
    assert ib.placed[0].lmtPrice - ref >= 2.0, "too tight to cross a normal MNQ spread"


def test_a_partial_fill_returns_what_filled_and_cancels_the_rest():
    ib = _IB(1, 29626.0, status="Submitted")
    notes = _Notes()
    px, got = _run(ib, notify=notes)
    assert (px, got) == (29626.0, 1), "the caller must be told ONE lot, never the requested four"
    assert ib.cancelled, "the unfilled remainder was left working — that is the 08-06 orphan shape"
    assert any("PARTIAL" in m and c for m, c in notes.sent), "a partial fill must page critically"


def test_no_fill_takes_no_position():
    ib = _IB(0, 0.0, status="Submitted")
    notes = _Notes()
    px, got = _run(ib, notify=notes)
    assert got == 0 and px == 0.0
    assert ib.cancelled
    assert any("NOT FILLED" in m for m, _ in notes.sent)


def test_an_unpriceable_entry_is_refused_and_nothing_is_placed():
    """The reference price really does come back 0 — the 09-04 entry recorded entry_atr 0.0."""
    ib = _IB(4, 29626.0)
    notes = _Notes()
    px, got = _run(ib, ref=0.0, notify=notes)
    assert (px, got) == (0.0, 0)
    assert ib.placed == [], "an entry with no reference price must not reach the broker"
    assert any("REFUSED" in m and c for m, c in notes.sent)


def test_every_market_order_is_an_exit():
    """★ No ENTRY may ever be a market order — that is what the fabricated fill taught, and it is
    the half of the old safety property that is untouched by the 09-15 exit change."""
    src = open(SRC).read()
    exits = ("CLOCK_FLAT", "TARGET", "OPERATOR_SELL", "MANUAL_CLAIM", "TRAIL", "flat",
             "place_exit", "remainder", "ESCALATE")
    n = 0
    for i, line in enumerate(src.splitlines()):
        if "MarketOrder(" in line and "import" not in line:
            n += 1
            ctx = "\n".join(src.splitlines()[max(0, i - 20):i + 2])
            assert any(e in ctx for e in exits), f"a MarketOrder at line {i+1} is not an exit:\n{ctx}"
    assert n >= 3, f"expected market orders to survive on the exit paths, found {n}"


def test_the_hard_flat_is_never_a_limit():
    """★★★ THE SAFETY PROPERTY THAT SURVIVES THE 2026-09-15 CHANGE, and the reason place_exit() is
    NOT wired everywhere. "NEVER HOLD OVERNIGHT. EVER." is absolute: the 20:40Z flatten must not
    acquire a fill condition of any kind, not even one that escalates. A limit there would be a
    strictly worse trade than the fabricated fill it prevents."""
    src = open(SRC).read().splitlines()
    hard = [i for i, ln in enumerate(src) if "CLOCK_FLAT" in ln]
    assert hard, "could not locate the 20:40Z hard flat — this test has gone blind"
    lo, hi = min(hard) - 60, max(hard) + 20
    block = "\n".join(src[max(0, lo):hi])
    assert "MarketOrder(" in block, "the hard flat no longer places a MARKET order"
    assert "place_exit(" not in block, (
        "the 20:40Z HARD FLAT was routed through place_exit(). It must not be: an exit that can "
        "wait, even briefly, is not an unconditional flatten.")


def test_single_lot_exits_were_left_alone():
    """★ The fabrication hits only lots BEYOND THE FIRST, so a 1-lot exit has nothing to prevent.
    Changing them would be risk taken for no measured benefit on the desk's most-used exit."""
    src = open(SRC).read()
    for needle in ('MarketOrder("SELL" if d > 0 else "BUY", 1)', "MarketOrder(v[0], 1)"):
        assert needle in src, (
            f"a single-lot exit ({needle}) is no longer a plain market order — the 09-15 change "
            f"was scoped to MULTI-LOT exits and this one has drifted out of that scope")


def test_both_entry_paths_go_through_place_entry():
    """Manual AND automatic. The automatic entry is 4 lots and took the fabricated fill too."""
    src = open(SRC).read()
    assert src.count("await place_entry(") == 2, "both entry sites must use the limit helper"
    auto = src.index('_side = "BUY" if d > 0 else "SELL"')
    tail = src[auto:auto + 2600]
    assert "qty=_lots" in tail and "lots_open=_lots" in tail, (
        "the automatic path must book the FILLED lots, not LOTS — booking the request against a "
        "partial fill is the unaccounted-lot condition the reconciler kills both desks for")


# ── the reference price a limit is built from ────────────────────────────────
# ★★2026-09-04 CAUGHT LIVE WHILE SHIPPING THIS FIX. Every price in day_rider comes from
# drift_read().price, which is anchored to the 13:30 UTC cash open and returns 0.0 outside it —
# confirmed at 06:00Z with a position open. Harmless for a market order, fatal for a LIMIT: pricing
# entries off drift_read alone would have REFUSED EVERY MANUAL PRESS outside US hours, and the
# operator's BUY/SELL is deliberately live across the whole CME session. The fix would have broken
# the button it was written to protect.

def test_the_reference_falls_back_to_the_live_tape_when_drift_is_blind(tmp_path):
    import types
    cfg = types.SimpleNamespace(capture_path=_tape_fixture(tmp_path), symbol="MNQ")
    blind = types.SimpleNamespace(price=0.0)            # what drift_read really returns in Asia
    ref = dr.entry_reference(blind, cfg)
    assert ref > 0, "an entry outside US hours would be refused for want of a price"
    live = types.SimpleNamespace(price=29500.0)
    assert dr.entry_reference(live, cfg) == 29500.0, "drift_read wins when it has a real read"


def test_the_tape_reference_filters_the_symbol(tmp_path):
    """capture.db carries MGC too; folding them once made ATR read 1848 against a true 15."""
    cap = _tape_fixture(tmp_path)
    mnq = dr.last_tape_price(cap, "MNQ")
    mgc = dr.last_tape_price(cap, "MGC")
    assert mnq > 20000 and 0 < mgc < 20000, f"symbol filter is not holding: MNQ={mnq} MGC={mgc}"


def test_a_stale_tape_prices_nothing():
    """A halted or dead feed must REFUSE, never guess — an absence of tape is not a measurement."""
    assert dr.last_tape_price("/home/alphabot/gazbot7/data/capture.db", "MNQ", max_age_s=1) == 0.0
    assert dr.last_tape_price("/nonexistent/capture.db", "MNQ") == 0.0
