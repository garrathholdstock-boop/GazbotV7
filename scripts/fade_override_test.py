#!/usr/bin/env python3
"""FADE-THESIS OVERRIDE TEST (operator 2026-07-28).

Question: exhaustion_short is a FADE gate — its native thesis is a SNAP-BACK: heavy buyers
absorbed into a wall → fade for a small reversal, bank quick (fixed 8pt stop / 12pt target).
But the LIVE adaptive selector OVERRIDES that: when it enters SHORT into a proven down-trend it
picks WIDE (lock-chandelier ride) and hands the loss side to the native ~1-ATR STP. So the
override changes the WHOLE risk geometry — not just ride-vs-bank, but an 8pt stop → ~1-ATR stop.

Is letting the selector override the fade thesis a net winner or loser over many trades?

Repriced TICK-HONEST on capture.db 250ms ticks, on the 46 realised exhaustion_short entries.
Books (all reuse the desk's OWN live deciders — zero drift):
  NATIVE   : exit_fixed(stop 8pt / target 12pt)              — the snap-back thesis (both sides)
  ADAPTIVE : regime@entry → wide lock-chand(3.5/6.0/0.5) / counter k2.0 / chop k1.5,
             loss = native 1-ATR STP                          — WHAT RUNS LIVE
  WIDE     : always lock-chand(3.5/6.0/0.5) + native 1-ATR STP (the pure ride)
  SCALP2R  : exit_scalp 2R / 1-ATR                            (reference)
The OVERRIDE subset = aligned-trend entries (TREND_DOWN for a short) — where ADAPTIVE=WIDE
overrides the fade. On THOSE, head-to-head NATIVE (bank 12pt) vs WIDE (ride). + per-day + LODO.

Fees $1.50/RT, $2/pt, MAX_HOLD 120min (⚠ live also has a 20min flat-clock — hold-time reported).
⚠ 46 entries, one week, one real trend day (07-28) — a LEAD not a verdict; ranking > absolute $.

  PYTHONPATH=src .venv/bin/python scripts/fade_override_test.py
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict

from collections import namedtuple

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import (  # noqa: E402
    Position, exit_chandelier, exit_chandelier_lock, exit_fixed, exit_scalp,
)
from gazbot7.slot_strategy import SlotStrategy  # noqa: E402  — LIVE _regime_mode (no drift)

Bar = namedtuple("Bar", "close")

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 120 * 60


def replay(book, side, ep, atr, mode, ticks):
    """Step a book over post-entry ticks → (exit_px, hold_s). Mirrors slot_strategy._manage."""
    peak = 0.0
    t0 = ticks[0][0]
    for ts, px in ticks:
        fav = (px - ep) if side == "LONG" else (ep - px)
        if fav > peak:
            peak = fav
        pos = Position(side, ep, atr, peak)
        r = None
        if book == "NATIVE":
            r = exit_fixed(pos, px, stop_pt=8.0, target_pt=12.0)
        elif book == "SCALP2R":
            r = exit_scalp(pos, px, target_r=2.0, stop_atr_mult=1.0)
        else:  # ADAPTIVE or WIDE — profit exit + native 1-ATR stop backstop
            use_wide = (book == "WIDE") or (book == "ADAPTIVE" and mode == "wide")
            if use_wide:
                r = exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
            else:  # ADAPTIVE non-wide: counter → k2.0, chop → k1.5
                k = 2.0 if mode == "mid" else 1.5
                if exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75):
                    r = "CHANDELIER"
            r = r or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0)  # native 1-ATR STP (loss)
        if r:
            return px, (ts - t0) / 1000.0
    return ticks[-1][1], (ticks[-1][0] - t0) / 1000.0


def pnl(side, ep, xp, q):
    return ((xp - ep) if side == "LONG" else (ep - xp)) * VPP * q - FEE * q


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    trades = con.execute("""
        SELECT side, entry_price, qty, epoch(opened_at::TIMESTAMPTZ) t0,
               strftime(opened_at::TIMESTAMPTZ,'%Y-%m-%d') d
        FROM g.trades WHERE gate='exhaustion_short' AND symbol='MNQ'
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY opened_at""").fetchall()

    daybars: dict = {}

    def load_day(t0):
        now = dt.datetime.fromtimestamp(t0, dt.UTC)
        s = dr.pnl.paris_day_start_utc(now)
        ds = (dt.datetime.fromisoformat(s).timestamp() if isinstance(s, str) else s.timestamp())
        ds = int(ds)
        if ds in daybars:
            return daybars[ds]
        rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo
            FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
              AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1""").fetchall()
        mins = [r[0] for r in rows]
        marks = dr.replay_marks(mins, [r[1] for r in rows], ds, ds+86400) if len(mins) > dr.WINDOW else []
        daybars[ds] = (rows, marks)
        return daybars[ds]

    def regime_at(marks, t):
        st = "CHOP"
        for mt, s, _e, _n in marks:
            if mt <= t:
                st = s
            else:
                break
        return st

    def atr_at(rows, t):
        ctx = [r for r in rows if t - 1800 <= r[0] <= t]
        return sum(r[2]-r[3] for r in ctx) / len(ctx) if len(ctx) >= 6 else 0.0

    BOOKS = ["NATIVE", "ADAPTIVE", "WIDE", "SCALP2R"]
    tot = defaultdict(float)
    by_regime = defaultdict(lambda: defaultdict(float))   # regime -> book -> $
    per_day = defaultdict(lambda: defaultdict(float))      # day -> book -> $
    override_rows = []   # the aligned-trend (wide-override) trades
    reg_n = defaultdict(int)
    n = 0

    for (side, ep, qty, t0, d) in trades:
        rows, marks = load_day(t0)
        atr = atr_at(rows, t0)
        if atr <= 0:
            continue
        ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>{int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        if len(ticks) < 2:
            continue
        # FAITHFUL to live: exit mode frozen at entry by _regime_mode on the trailing WINDOW
        # minute-closes (NOT the router's Paris-day replay — they diverge at the open).
        mclose = [Bar(r[1]) for r in rows if r[0] <= t0]
        mode = SlotStrategy._regime_mode(side, mclose) if len(mclose) >= 6 else "tight"
        regtag = {"wide": "ALIGNED(override)", "mid": "COUNTER", "tight": "CHOP"}[mode]
        q = qty or 1
        n += 1
        reg_n[regtag] += 1
        res = {}
        for book in BOOKS:
            xp, hold = replay(book, side, ep, atr, mode, ticks)
            p = pnl(side, ep, xp, q)
            res[book] = (p, hold)
            tot[book] += p
            by_regime[regtag][book] += p
            per_day[d][book] += p
        if mode == "wide":
            override_rows.append((d, ep, atr, res["NATIVE"][0], res["WIDE"][0],
                                  res["WIDE"][1], q))

    con.close()

    W = 12
    print(f"\nFADE-THESIS OVERRIDE TEST — {n} exhaustion_short entries repriced tick-honest")
    print(f"router: ER>={dr.ER_TREND} |net|>={dr.NET_MIN} · regimes: " +
          " ".join(f"{k}={v}" for k, v in reg_n.items()) + "\n")

    print(f"{'':>18}" + "".join(f"{b:>{W}}" for b in BOOKS) + "   winner")
    row = "".join(f"{tot[b]:>+{W}.0f}" for b in BOOKS)
    print(f"{'ALL entries':>18}{row}   {max(tot, key=tot.get)}")
    for regtag in ("ALIGNED(override)", "COUNTER", "CHOP"):
        b = by_regime[regtag]
        if not b:
            continue
        row = "".join(f"{b[bk]:>+{W}.0f}" for bk in BOOKS)
        print(f"{regtag:>18}{row}   {max(b, key=b.get)}")

    print(f"\n── THE OVERRIDE SUBSET (aligned down-trend shorts): NATIVE(bank 12pt) vs WIDE(ride) ──")
    print(f"{'day':>11}{'entry':>9}{'atr':>6}{'NATIVE$':>9}{'WIDE$':>8}{'hold_min':>9}")
    nat_o = wide_o = 0.0
    for (d, ep, atr, pn_, pw, hold, q) in override_rows:
        nat_o += pn_; wide_o += pw
        print(f"{d:>11}{ep:>9.0f}{atr:>6.0f}{pn_:>+9.0f}{pw:>+8.0f}{hold/60:>9.1f}")
    if override_rows:
        print(f"{'TOTAL':>11}{'':>9}{'':>6}{nat_o:>+9.0f}{wide_o:>+8.0f}")
        print(f"\n  → override verdict: WIDE {wide_o:+.0f} vs NATIVE {nat_o:+.0f} "
              f"= riding {'WINS' if wide_o > nat_o else 'LOSES'} by {abs(wide_o-nat_o):.0f} on {len(override_rows)} trades")

    # LODO robustness on the ALL book (does ADAPTIVE's edge over NATIVE survive dropping any day?)
    print(f"\n── LEAVE-ONE-DAY-OUT (ADAPTIVE − NATIVE, drop each day) ──")
    days = sorted(per_day)
    full = tot["ADAPTIVE"] - tot["NATIVE"]
    print(f"  full-sample ADAPTIVE−NATIVE = {full:+.0f}")
    worst = None
    for dd in days:
        adj = full - (per_day[dd]["ADAPTIVE"] - per_day[dd]["NATIVE"])
        tag = "  <<< that day carries it" if (full > 0 and adj <= 0) else ""
        if worst is None or adj < worst[1]:
            worst = (dd, adj)
        print(f"  drop {dd}: {adj:+.0f}{tag}")
    if worst:
        print(f"  worst-case (robustness floor) = drop {worst[0]} → {worst[1]:+.0f}")
    print(f"\n  per-day: " + "  ".join(f"{dd[5:]}:A{per_day[dd]['ADAPTIVE']:+.0f}/N{per_day[dd]['NATIVE']:+.0f}" for dd in days))


if __name__ == "__main__":
    main()
