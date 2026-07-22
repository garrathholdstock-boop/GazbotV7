#!/usr/bin/env python3
"""ER>=0.20 gate + ATR-floor sweep on BOTH momentum gates (grind_long, thrust_short), tick-honest.

Entry on the 1-min signal, exit repriced on the real ticks (reuses gate_backtest_tickhonest's
engine). For each momentum gate: apply the live ER floor (>=0.20), then a per-ATR-band breakdown
+ an ATR-floor sweep. Answers "does an ATR floor help each momentum gate, and where."

  PYTHONPATH=src:scripts python scripts/momentum_atr_sweep.py
"""
from __future__ import annotations

import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import compute_features  # noqa: E402

import gate_backtest as gb  # noqa: E402
import gate_backtest_tickhonest as th  # noqa: E402

ER_FLOOR = 0.20
ATR_GRID = [6, 8, 10, 12, 14, 16, 18, 20, 24, 28]
MOMO = [("grind_long", "grind", "LONG"), ("thrust_short", "thrust", "SHORT")]


def run():
    days = gb.load_days("/home/alphabot/alphabot2/data/alphabot.db", "1m")
    con = duckdb.connect()
    con.execute(f"ATTACH '{th.TICKS}' AS tk (TYPE sqlite, READ_ONLY)")
    con.execute("CREATE TABLE tick AS SELECT ts_ms, price FROM tk.trade_tick WHERE symbol='MNQ'")
    con.execute("CREATE INDEX ix ON tick(ts_ms)")
    span = con.execute("SELECT min(ts_ms), max(ts_ms) FROM tick").fetchone()
    d0 = dt.datetime.fromtimestamp(span[0] / 1000, dt.UTC).date()
    d1 = dt.datetime.fromtimestamp(span[1] / 1000, dt.UTC).date()

    trades = {t: [] for t, _, _ in MOMO}       # tag -> (pnl, er, atr)
    for _day, bars in days.items():
        nxt = {t: 0 for t, _, _ in MOMO}
        for i in range(len(bars)):
            w = bars[max(0, i - 59):i + 1]
            if len(w) < 6:
                continue
            f = compute_features(w)
            dms = (bars[i].ts + 60) * 1000
            er = gb.er_of(bars[max(0, i - 30):i + 1])
            for tag, kind, side in MOMO:
                if dms <= nxt[tag] or not gb._fires(kind, side, f):
                    continue
                ticks = con.execute("SELECT ts_ms, price FROM tick WHERE ts_ms>? AND ts_ms<=? ORDER BY ts_ms",
                                    [dms, dms + th.CAP_MIN * 60000]).fetchall()
                if len(ticks) < 2:
                    continue
                epx = ticks[0][1]
                xpx, xms = th.replay_exit("chandelier", side, epx, f.atr, ticks[1:])
                g = ((xpx - epx) if side == "LONG" else (epx - xpx)) * th.VPP - th.FEE
                trades[tag].append((g, er, f.atr))
                nxt[tag] = xms

    print(f"MOMENTUM gates — ER>={ER_FLOOR} + ATR-floor sweep, TICK-HONEST ({d0} → {d1})\n")
    for tag, _kind, _side in MOMO:
        kept = [(p, er, a) for p, er, a in trades[tag] if er >= ER_FLOOR]
        if not kept:
            print(f"{tag}: no trades at ER>={ER_FLOOR}\n")
            continue
        natv = sum(p for p, _, _ in kept)
        med = sorted(a for _, _, a in kept)[len(kept) // 2]
        print(f"══ {tag} ══  ER>={ER_FLOOR}: {len(kept)} trades, nat ${round(natv):+} (median ATR {med:.1f}pt)")
        b = {}
        for p, _er, a in kept:
            k = min(int(a // 2) * 2, 30)
            d = b.setdefault(k, [0.0, 0, 0])
            d[0] += p
            d[1] += 1
            d[2] += p > 0
        print("  per-ATR-band:  " + "  ".join(
            f"[{k}-{k+2}]{b[k][1]}tr${round(b[k][0]):+}" for k in sorted(b)))
        best = None
        cells = []
        for c in ATR_GRID:
            sub = [p for p, _er, a in kept if a >= c]
            net, n = round(sum(sub)), len(sub)
            cells.append(f"≥{c}:{n}tr${net:+}")
            if n >= 15 and (best is None or net > best[1]):
                best = (c, net, n)
        print("  ATR-floor:     " + "  ".join(cells))
        if best:
            print(f"  ★ best ATR floor ≥{best[0]}pt → ${best[1]:+} ({best[2]}tr, +${round(best[1]-natv)} vs no floor)\n")
        else:
            print("  ★ no ATR cut keeps >=15 trades\n")
    print("⚠ tick coverage ~9 days (one summer regime) + 60-min hold cap — a LEAD, not a verdict.")


if __name__ == "__main__":
    run()
