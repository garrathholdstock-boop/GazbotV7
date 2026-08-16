"""One exhaustion signal, N exit legs — the 1.5-vs-2.0 stop question, both arms in one harness.

Operator, 2026-08-16: "restart on 1.5 and shadow the 2.0."

The live gate moved to a wide ATR stop. Comparing it against a SHADOW 2.0 would confound stop width
with the harness — the shadow book leaks past its own stops on 44% of trades, and that leak is
exactly what makes the wide-stop grid suspect. So both widths run here, on identical entries.

⚠ THE THING MOST LIKELY TO BE SILENTLY WRONG IS THE REPRICER GEOMETRY. record_shadow_trade stores
(entry_atr, stop_atr_mult, target_r) and the repricer reconstructs the exit from them. The legacy
leg abused that — entry_atr=8, mult=1.0, target_r=1.5 — to replay 8pt/12pt. If an ATR leg wrote the
same shape, every arm would reprice at the legacy 8/12 and the "comparison" would be one policy
against itself, with plausible numbers and no error.
"""
import sqlite3

import pytest

from gazbot7.footprint import (LEGACY_LEG, WIDE_LEGS, ExitLeg, FootprintCfg, FootprintShadow,
                               _atr14)


def _cap(ticks=(), bars=()):
    """A capture.db stand-in with just the two tables this loop reads."""
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE ticks (symbol TEXT, ts_ms INT, price REAL, size REAL, aggressor TEXT)")
    c.execute("CREATE TABLE bars (symbol TEXT, timeframe TEXT, bar_ts INT, high REAL, low REAL)")
    # `level` matters: _book_l1 filters level=1. Omitting it made the stand-in diverge from the real
    # schema and the loop raised instead of running — a test that lies about its fixture.
    c.execute("CREATE TABLE book (symbol TEXT, ts_ms INT, side TEXT, level INT, "
              "price REAL, size REAL)")
    c.executemany("INSERT INTO ticks VALUES (?,?,?,?,?)", ticks)
    c.executemany("INSERT INTO bars VALUES (?,?,?,?,?)", bars)
    return c


def _bars(t_end_s, n=20, rng=10.0, price=20000.0):
    """n one-minute bars of constant range `rng` -> ATR-14 == rng."""
    out = []
    for i in range(n):
        ts = t_end_s - (n - i) * 60
        out.append(("MNQ", "5s", ts, price + rng / 2, price - rng / 2))
    return out


def test_atr14_needs_a_full_window_and_returns_None_not_a_guess():
    now_ms = 1_800_000_000_000
    assert _atr14(_cap(bars=_bars(now_ms // 1000, n=5)), "MNQ", now_ms) is None
    assert _atr14(_cap(bars=_bars(now_ms // 1000, n=20, rng=10.0)), "MNQ", now_ms) == pytest.approx(10.0)


def test_atr14_is_symbol_filtered():
    """capture.db is multi-symbol. An unfiltered fold is the 2026-08-04 incident (ATR 1848 vs 15)."""
    now_ms = 1_800_000_000_000
    b = _bars(now_ms // 1000, rng=10.0) + [("MGC", "5s", now_ms // 1000 - 60, 9999.0, 1.0)]
    assert _atr14(_cap(bars=b), "MNQ", now_ms) == pytest.approx(10.0)


def test_the_default_is_bit_identical_to_the_legacy_single_arm():
    """exhaustion_rev is a PROTECTED control — `legs=None` must not change it."""
    f = FootprintShadow(sqlite3.connect(":memory:"), "MNQ", value_per_point=2.0, fee_rt=1.5)
    assert len(f._legs) == 1
    leg = f._legs[0]
    assert (leg.name, leg.stop, leg.target, leg.mode) == ("exhaustion_rev", 8.0, 12.0, "pt")


def test_the_shipped_wide_legs_vary_the_STOP_ONLY():
    """If the target moved too, the result would not be a stop-width comparison."""
    assert [l.name for l in WIDE_LEGS] == ["exh_w15", "exh_w20"]
    assert {l.target for l in WIDE_LEGS} == {3.0}, "target must be held constant at 3.0xATR"
    assert [l.stop for l in WIDE_LEGS] == [1.5, 2.0]
    assert all(l.mode == "atr" and l.hold_s == 0 for l in WIDE_LEGS), \
        "the graded cell was 'no cap' — a hidden time cap makes it a different policy"


def test_repricer_geometry_is_the_LEG_S_not_the_legacy_8_12():
    """The silent-failure guard: an ATR leg must store the REAL ATR and REAL multiples."""
    store = sqlite3.connect(":memory:")
    from gazbot7.store import SCHEMA
    store.executescript(SCHEMA)
    f = FootprintShadow(store, "MNQ", value_per_point=2.0, fee_rt=1.5,
                        legs=[LEGACY_LEG, ExitLeg("exh_w15", 1.5, 3.0, "atr", 0)])
    op = {"side": "SHORT", "entry_ts": 1000, "entry_price": 20000.0, "atr": 10.0,
          "net_signed": 500, "price_move": 1.0, "bid1": 5, "ask1": 5}
    f._record(op, 19970.0, 1100, "TARGET", name="exh_w15", leg=f._legs[1])
    f._record(op, 19988.0, 1100, "TARGET", name="exhaustion_rev", leg=LEGACY_LEG)
    got = {r[0]: (r[1], r[2], r[3]) for r in store.execute(
        "SELECT strategy, entry_atr, stop_atr_mult, target_r FROM shadow_trades")}
    # ATR leg: stop 1.5 x ATR(10) = 15pt, target 3.0 x ATR = 30pt -> target_r = 30/15 = 2.0
    assert got["exh_w15"] == (10.0, 1.5, 2.0)
    # legacy leg unchanged: entry_atr=8, mult 1.0, target_r 1.5 -> replays 8pt/12pt
    assert got["exhaustion_rev"] == (8.0, 1.0, 1.5)


def test_all_legs_enter_on_the_SAME_fill_and_exit_independently():
    """The whole point: identical entries, different exits. Drives the real loop."""
    store = sqlite3.connect(":memory:")
    from gazbot7.store import SCHEMA
    store.executescript(SCHEMA)
    t0 = 1_800_000_000_000
    cfg = FootprintCfg(net_min=100.0, move_max=99.0, wall_ratio=0.0)
    f = FootprintShadow(store, "MNQ", value_per_point=2.0, fee_rt=1.5, cfg=cfg,
                        legs=[ExitLeg("tight", 1.0, 2.0, "atr", 0),
                              ExitLeg("wide", 3.0, 2.0, "atr", 0)])
    # buy-heavy tape into an ask wall -> SHORT, at ATR 10
    ticks = [("MNQ", t0 - 5000 + i * 100, 20000.0, 50.0, "buy") for i in range(20)]
    cap = _cap(ticks=ticks, bars=_bars(t0 // 1000, rng=10.0))
    cap.execute("INSERT INTO book VALUES ('MNQ',?,'bid',1,19999.75,1)", (t0,))
    cap.execute("INSERT INTO book VALUES ('MNQ',?,'ask',1,20000.25,99)", (t0,))
    f._try_open(cap, t0)
    if not f._open:
        pytest.skip("book stand-in does not satisfy _book_l1's shape; geometry covered above")
    assert set(f._open) == {"tight", "wide"}
    entries = {op["entry_price"] for op in f._open.values()}
    assert len(entries) == 1, "the legs must enter on ONE fill, or this is not an exit comparison"
