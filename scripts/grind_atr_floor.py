#!/usr/bin/env python3
"""Does an ATR floor help grind_long? Tick-honest scan over the V5 archive.

grind_long already has the live ER floor (>=0.20). Today's read: even in-regime (ER 0.20-0.30)
entries got stopped on a WEAK trend (ATR ~10pt) that never ran far enough to survive the give-back.
Hypothesis: add an ATR floor so grind won't ride a trend too small to run. This scans it honestly —
entry on the 1-min signal, exit repriced on the real ticks (reusing gate_backtest_tickhonest's engine),
ER>=0.20 applied first (matching live), then the ATR-at-entry floor scanned.

  PYTHONPATH=src:scripts python scripts/grind_atr_floor.py
"""
from __future__ import annotations

import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import compute_features  # noqa: E402

import gate_backtest as gb  # noqa: E402
import gate_backtest_tickhonest as th  # noqa: E402

ER_FLOOR = 0.20
ATR_GRID = [6, 8, 10, 12, 14, 16, 18, 20, 24]


def run():
    days = gb.load_days("/home/alphabot/alphabot2/data/alphabot.db", "1m")
    con = duckdb.connect()
    con.execute(f"ATTACH '{th.TICKS}' AS tk (TYPE sqlite, READ_ONLY)")
    con.execute("CREATE TABLE tick AS SELECT ts_ms, price FROM tk.trade_tick WHERE symbol='MNQ'")
    con.execute("CREATE INDEX ix ON tick(ts_ms)")

    trades = []                                    # (pnl, er, atr) for grind_long
    for _day, bars in days.items():
        nxt = 0
        for i in range(len(bars)):
            w = bars[max(0, i - 59):i + 1]
            if len(w) < 6:
                continue
            f = compute_features(w)
            if not gb._fires("grind", "LONG", f):
                continue
            dms = (bars[i].ts + 60) * 1000
            if dms <= nxt:
                continue
            ticks = con.execute("SELECT ts_ms, price FROM tick WHERE ts_ms>? AND ts_ms<=? ORDER BY ts_ms",
                                [dms, dms + th.CAP_MIN * 60000]).fetchall()
            if len(ticks) < 2:
                continue
            epx = ticks[0][1]
            xpx, xms = th.replay_exit("chandelier", "LONG", epx, f.atr, ticks[1:])
            g = (xpx - epx) * th.VPP - th.FEE
            er = gb.er_of(bars[max(0, i - 30):i + 1])
            trades.append((g, er, f.atr))
            nxt = xms

    kept = [(p, er, a) for p, er, a in trades if er >= ER_FLOOR]
    natv = sum(p for p, _, _ in kept)
    print(f"grind_long TICK-HONEST, ER>={ER_FLOOR} applied (live gate): {len(kept)} trades, "
          f"nat ${round(natv):+} (median ATR {sorted(a for _, _, a in kept)[len(kept)//2]:.1f}pt)\n")

    print("per-ATR-band (entry ATR, pts) — where does grind bleed by trend SIZE:")
    b = {}
    for p, _er, a in kept:
        k = min(int(a // 2) * 2, 30)
        d = b.setdefault(k, [0.0, 0, 0])
        d[0] += p
        d[1] += 1
        d[2] += p > 0
    for k in sorted(b):
        net, n, wn = b[k]
        flag = "  <<< bleeds" if net < 0 else ""
        print(f"  ATR {k:>2}-{k+2:<2}pt {n:>3}tr {round(100*wn/n):>3}% ${round(net):>+6}{flag}")

    print("\nATR-floor scan (keep atr>=cut; ER>=0.20 already applied):")
    best = None
    for c in ATR_GRID:
        sub = [p for p, _er, a in kept if a >= c]
        net, n = round(sum(sub)), len(sub)
        if n >= 15 and (best is None or net > best[1]):
            best = (c, net, n)
        print(f"  atr>={c:>2}pt: {n:>3}tr ${net:>+6}")
    if best:
        print(f"\n★ best ATR floor >= {best[0]}pt → ${best[1]:+} ({best[2]}tr, "
              f"+${round(best[1] - natv)} vs no ATR floor)")
    print("\n⚠ tick coverage ~9 days (Jul 5-17, one summer regime) + 60-min hold cap — a LEAD.")


if __name__ == "__main__":
    run()
