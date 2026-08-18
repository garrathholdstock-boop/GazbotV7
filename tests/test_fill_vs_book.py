"""A fill that lands outside the whole visible order book must be a finding.

★★2026-08-18. The day rider's TRAIL exit filled two lots at 29579.50 and 29609.00 — 29.5pt apart —
while the L2 ladder showed best ask 29580.50 with 3 lots and the deepest of ten levels at 29582.75.
~$57 on one lot, and the OPERATOR found it by watching the screen.

`book_vs_fills` structurally cannot catch this: the book and the venue AGREE — we recorded exactly
the bad price we got. Agreement is not quality, and nothing measured quality.

⚠ THESE TESTS EXIST TO PIN THE CONSERVATISM. The check shares an alarm channel with naked-position
alarms, so a false positive is expensive. `test_slop_makes_it_stricter_never_looser` and
`test_an_mgc_book_cannot_judge_an_mnq_fill` are the ones that matter.
"""
import os
import sqlite3
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from sweep import OK, WARN, check_fill_vs_book  # noqa: E402

T0 = datetime(2026, 8, 18, 15, 27, 6, tzinfo=UTC)


def _dbs(tmp_path, fills, snaps):
    store = sqlite3.connect(f"{tmp_path}/g.db")
    store.execute("CREATE TABLE fills (exec_id TEXT, order_id TEXT, symbol TEXT, side TEXT,"
                  " qty REAL, price REAL, exec_time TEXT)")
    store.executemany("INSERT INTO fills VALUES (?,?,?,?,?,?,?)", fills)
    store.commit()
    d = sqlite3.connect(f"{tmp_path}/d.db")
    d.execute("CREATE TABLE depth_snap (symbol TEXT, ts_ms INTEGER, bid1p REAL, ask1p REAL,"
              " bid10p REAL, ask10p REAL)")
    d.executemany("INSERT INTO depth_snap VALUES (?,?,?,?,?,?)", snaps)
    d.commit()
    d.close()
    return store, f"{tmp_path}/d.db"


def _snap(off_ms, ask10=29582.75, bid10=29575.0, sym="MNQ"):
    return (sym, int(T0.timestamp() * 1000) + off_ms, 29580.0, 29580.5, bid10, ask10)


def _fill(price, side="BUY", sym="MNQ", oid="rider-100"):
    return ("e1", oid, sym, side, 1.0, price, T0.isoformat())


def test_the_real_2026_08_18_bad_fill_is_caught(tmp_path):
    store, dp = _dbs(tmp_path, [_fill(29609.00)], [_snap(o) for o in (-500, 0, 500)])
    r = check_fill_vs_book(store, T0, depth_path=dp)
    assert r["status"] == WARN, r
    f = r["findings"][0]
    assert f["price"] == 29609.00 and f["deepest_visible"] == 29582.75
    assert round(f["excess_pt"], 2) == 26.25
    assert f["est_cost_usd"] == 52.5, "MNQ is $2/pt — never $5"


def test_a_fill_inside_the_book_is_not_flagged(tmp_path):
    """The sibling lot at 29579.50 filled at the touch. It must be silent."""
    store, dp = _dbs(tmp_path, [_fill(29579.50)], [_snap(o) for o in (-500, 0, 500)])
    r = check_fill_vs_book(store, T0, depth_path=dp)
    assert r["status"] == OK, r
    assert r["findings"] == [] and r["checked"] == 1


def test_slop_makes_it_stricter_never_looser(tmp_path):
    """★ THE ONE THAT MATTERS. Rider fills carry SECOND-ROUNDED timestamps, so the match window is
    ±2s. If ANY snapshot in that window shows the price inside the ladder, it must NOT be flagged —
    otherwise a mis-stamped fill manufactures a finding on a shared alarm channel."""
    snaps = [_snap(-1500, ask10=29582.75), _snap(0, ask10=29582.75),
             _snap(1500, ask10=29650.0)]           # one snapshot where 29609 IS inside
    store, dp = _dbs(tmp_path, [_fill(29609.00)], snaps)
    assert check_fill_vs_book(store, T0, depth_path=dp)["status"] == OK


def test_an_mgc_book_cannot_judge_an_mnq_fill(tmp_path):
    """depth_snap is MULTI-SYMBOL. Folding MGC into MNQ once made ATR read 1848 against a true 15
    and opened live trades with $3,700 stops ([[md-stream-multi-symbol-filter]])."""
    store, dp = _dbs(tmp_path, [_fill(29609.00)],
                     [_snap(o, ask10=3400.0, sym="MGC") for o in (-500, 0, 500)])
    r = check_fill_vs_book(store, T0, depth_path=dp)
    assert r["status"] == WARN and r["unverifiable"] == 1
    assert r["findings"] == [], "an MGC ladder must never be used to judge an MNQ fill"
    assert "not the same as clean" in r["detail"]


def test_no_book_is_unverifiable_not_clean(tmp_path):
    """The book_vs_fills precedent: a day with no execution record is REFUSED, never scored clean."""
    store, dp = _dbs(tmp_path, [_fill(29609.00)], [])
    r = check_fill_vs_book(store, T0, depth_path=dp)
    assert r["unverifiable"] == 1 and r["findings"] == []
    assert "not the same as clean" in r["detail"]


def test_a_sell_is_judged_against_the_BID_side(tmp_path):
    """A SELL leaves by hitting the bid, so it is bad when it prints BELOW the deepest bid."""
    store, dp = _dbs(tmp_path, [_fill(29500.0, side="SELL")],
                     [_snap(o, bid10=29575.0) for o in (-500, 0, 500)])
    r = check_fill_vs_book(store, T0, depth_path=dp)
    assert r["status"] == WARN
    assert round(r["findings"][0]["excess_pt"], 2) == 75.0


def test_small_excess_inside_tolerance_stays_quiet(tmp_path):
    """250ms sampling means a fill can sit a shade past the last snapshot legitimately."""
    store, dp = _dbs(tmp_path, [_fill(29584.0)], [_snap(o, ask10=29582.75) for o in (-500, 0, 500)])
    assert check_fill_vs_book(store, T0, depth_path=dp)["status"] == OK
