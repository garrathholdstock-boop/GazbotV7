"""`BADFILL:` = SHOW IT, DO NOT COUNT IT. `EXCLUDE:` = gone. Two flags, two meanings.

2026-08-21: a real round trip was labelled `EXCLUDE:` (a system-bug loss) and vanished from all six
views — the operator watched a trade happen on his own account and could not find it. Then one of
its two fills turned out to be broken: 1 lot at 29388.25 while the book was 29418.25/29419.00, a
price that had not traded since 07:01Z. That lot must stay VISIBLE (it happened) and stay OUT of the
P&L (its price is fiction). This pins both halves, because "shown" leaking into "counted" is the
same class of bug as the flag that hid the trade in the first place.
"""
import sqlite3, pytest
from gazbot7.web import _dq


def _db():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE trades(symbol TEXT, side TEXT, gate TEXT, exit_reason TEXT, "
              "pnl_usd REAL, entry_price REAL, exit_price REAL, qty REAL, closed_at TEXT, "
              "data_quality TEXT)")
    rows = [("MNQ", "LONG", "day_rider", "CLOCK_FLAT_BUG", -69.0, 29428.25, 29417.5, 3.0,
             "2026-08-21T09:12:06", None),
            ("MNQ", "LONG", "day_rider", "CLOCK_FLAT_BUG", -81.5, 29428.25, 29388.25, 1.0,
             "2026-08-21T09:12:07", "BADFILL:stale_price_30pt_outside_book_20260821"),
            ("MNQ", "LONG", "day_rider", "TARGET", 999.0, 1.0, 2.0, 1.0,
             "2026-08-21T09:12:08", "EXCLUDE:phantom")]
    c.executemany("INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return c


def _sum(c, clause):
    return c.execute("SELECT COALESCE(SUM(pnl_usd),0) FROM trades WHERE 1=1" + clause).fetchone()[0]


def test_pnl_surfaces_exclude_both_flags():
    c = _db()
    assert _sum(c, _dq(c)) == -69.0, "a flagged row reached a P&L surface"


def test_the_blotter_shows_badfill_but_never_exclude():
    c = _db()
    got = c.execute("SELECT exit_price, data_quality FROM trades WHERE 1=1"
                    + _dq(c, show_badfill=True)).fetchall()
    prices = {r["exit_price"] for r in got}
    assert 29388.25 in prices, "the bad fill vanished — the operator cannot see his own trade"
    assert 2.0 not in prices, "an EXCLUDE row surfaced in the blotter"
    assert len(got) == 2


def test_badfill_is_still_absent_from_the_default_filter():
    """The default MUST stay strict: every caller that does not opt in is a P&L surface."""
    c = _db()
    assert "BADFILL" not in _dq(c)
    assert _sum(c, _dq(c)) == -69.0


def test_the_strict_row_source_never_opts_in():
    """★ _strategy_trades feeds the curve, gate table, leaderboard and loss buckets. If it ever
    passes show_badfill it re-enters five P&L surfaces at once."""
    src = open("/home/alphabot/gazbot7/src/gazbot7/web.py").read()
    body = src[src.index("def _strategy_trades("):src.index("def _blotter_rows(")]
    assert "show_badfill" not in body, "_strategy_trades opted into BADFILL — that is five P&L bugs"
    blot = src[src.index("def _blotter_rows("):src.index("def _gate_groups(")]
    assert "show_badfill=True" in blot, "the blotter stopped showing flagged trades"
