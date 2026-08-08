"""S7 — the single realized-P&L source: net, sign-aware, Paris-day."""

from __future__ import annotations

from datetime import UTC, datetime

from gazbot7 import pnl
from gazbot7.store import open_store, record_trade


def _trade(store, side, p, closed_at, exit_exec):
    record_trade(store, symbol="MNQ", side=side, qty=1, entry_price=100.0, exit_price=101.0,
                 opened_at="2026-07-15T13:00:00+00:00", closed_at=closed_at,
                 pnl_usd=p, fees_usd=1.5, exit_reason="X", exit_exec_id=exit_exec)


def test_realized_is_signed_sum():
    s = open_store(":memory:")
    _trade(s, "LONG", 18.5, "2026-07-15T14:00:00+00:00", "x1")
    _trade(s, "SHORT", -12.0, "2026-07-15T15:00:00+00:00", "x2")  # a short LOSS is negative
    pnl_usd, n, wins = pnl.realized(s, "MNQ")
    assert pnl_usd == 6.5 and n == 2 and wins == 1


def test_cleanup_trades_excluded_from_desk_pnl():
    s = open_store(":memory:")
    _trade(s, "SHORT", -449.81, "2026-07-15T19:45:00+00:00", "adopt")  # an ADOPT_FLATTEN cleanup
    s.execute("UPDATE trades SET exit_reason='ADOPT_FLATTEN' WHERE exit_exec_id='adopt'")
    _trade(s, "LONG", 12.0, "2026-07-15T19:50:00+00:00", "real")  # a real strategy trade
    s.commit()
    pnl_usd, n, _w = pnl.realized(s, "MNQ")
    assert pnl_usd == 12.0 and n == 1  # cleanup excluded — desk P&L is the real trade only


def test_day_filters_to_paris_day():
    s = open_store(":memory:")
    # Paris day of 2026-07-15 starts 2026-07-14T22:00Z (CEST). A trade closed
    # before that boundary is a prior day and excluded.
    _trade(s, "LONG", 100.0, "2026-07-14T20:00:00+00:00", "old")   # prior Paris day
    _trade(s, "LONG", 5.0, "2026-07-15T09:00:00+00:00", "today")   # today
    now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    pnl_usd, n, _w = pnl.day(s, "MNQ", now)
    assert pnl_usd == 5.0 and n == 1  # only today's trade counts


# ── 2026-08-07: TWO DESKS, TWO P&Ls ───────────────────────────────────────────────────────────
# The day-rider holds for hours with no stop; one trade swings more than 20 tournament scalps.
# On 08-07 the desk made +$227 across 23 trades while the day-rider ran ~-$975 on ONE — blended,
# the desk's result is invisible. Attribution is by gate prefix.

def _two_desk_store():
    from gazbot7.store import open_store
    st = open_store(":memory:")
    rows = [("grind_long_A", 100.0), ("grind_long_B", -40.0),
            ("day_rider_crossdesk", -500.0), ("day_rider", -475.0)]
    for i, (gate, p) in enumerate(rows):
        st.execute(
            "INSERT INTO trades (symbol,side,qty,entry_price,exit_price,opened_at,closed_at,"
            "pnl_usd,fees_usd,exit_reason,gate) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("MNQ", "LONG", 1, 100.0, 101.0, "2026-08-07T10:00:00+00:00",
             f"2026-08-07T10:0{i}:00+00:00", p, 1.5, "TARGET", gate))
    st.commit()
    return st


def test_desk_filter_splits_tournament_from_day_rider():
    from gazbot7 import pnl
    st = _two_desk_store()
    allp, alln, _ = pnl.realized(st, "MNQ")
    tour, tn, _ = pnl.realized(st, "MNQ", desk="tournament")
    dr, drn, _ = pnl.realized(st, "MNQ", desk="day_rider")
    assert (allp, alln) == (-915.0, 4)      # default unchanged — every existing caller is safe
    assert (tour, tn) == (60.0, 2), "day-rider rows leaked into the tournament book"
    assert (dr, drn) == (-975.0, 2), "day-rider rows not attributed"
    assert round(tour + dr, 2) == allp      # the split is exhaustive, nothing lost


def test_desk_filter_keeps_null_gate_rows_with_the_tournament():
    """A legacy row with no gate must not vanish from the desk's book."""
    from gazbot7 import pnl
    from gazbot7.store import open_store
    st = open_store(":memory:")
    st.execute("INSERT INTO trades (symbol,side,qty,entry_price,exit_price,opened_at,closed_at,"
               "pnl_usd,fees_usd,exit_reason,gate) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
               ("MNQ", "LONG", 1, 100.0, 101.0, "2026-08-07T10:00:00+00:00",
                "2026-08-07T10:01:00+00:00", 25.0, 1.5, "TARGET", None))
    st.commit()
    assert pnl.realized(st, "MNQ", desk="tournament")[0] == 25.0
    assert pnl.realized(st, "MNQ", desk="day_rider")[1] == 0
