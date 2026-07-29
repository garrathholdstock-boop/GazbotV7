#!/usr/bin/env python3
"""WHERE DID TRADES PEAK this week (operator 2026-07-29: "$260 is high, show me where they peaked,
Lot A should be lower"). Tick-reprices every REAL trade to its max-favorable-excursion (MFE) and
shows the peak in $ (per-lot) and R, the distribution, and — the key table — what % of winners a
first-lot take-profit at each $ level would CATCH. Faithful ATR (ATR-14 TR, 1-min bars).

  PYTHONPATH=src .venv/bin/python scripts/peak_distribution.py [gate]   (default: exhaustion_short)
"""
from __future__ import annotations
import datetime as dt
import statistics
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import Bar, _atr  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"; DB = "/home/alphabot/gazbot7/data/gazbot7.db"
SH = "/home/alphabot/gazbot7/data/shadow.db"
VPP, MAX_HOLD_S = 2.0, 90 * 60
GATE = sys.argv[1] if len(sys.argv) > 1 else "exhaustion_short"


def main():
    con = duckdb.connect()
    for a, p in [("c", CAP), ("g", DB), ("s", SH)]:
        con.execute(f"ATTACH '{p}' AS {a} (TYPE sqlite, READ_ONLY)")
    daycache: dict = {}

    def bars_for(t0):
        ss = dr.pnl.paris_day_start_utc(dt.datetime.fromtimestamp(t0, dt.UTC))
        ds = dt.datetime.fromisoformat(ss).timestamp() if isinstance(ss, str) else ss.timestamp()
        if ds not in daycache:
            rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-3600} AND bar_ts<{ds+86400}
                GROUP BY 1 ORDER BY 1""").fetchall()
            daycache[ds] = [Bar(ts=r[0], open=r[1], high=r[2], low=r[3], close=r[1], volume=0.0) for r in rows]
        return daycache[ds]

    def peak_of(side, ep, t0, qty):
        mb = [b for b in bars_for(t0) if b.ts <= t0]
        if len(mb) < 15: return None
        atr = _atr(mb, n=14)
        if atr <= 0: return None
        ticks = con.execute(f"""SELECT price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>={int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        peak = 0.0
        for (px,) in ticks:
            fav = (ep - px) if side == "SHORT" else (px - ep)
            if fav > peak: peak = fav
        return peak, atr, qty

    # REAL trades this week (Mon 00:00 Paris → now), the gate
    real = con.execute(f"""SELECT side, entry_price, qty, epoch(opened_at::TIMESTAMPTZ) t0,
           strftime(opened_at::TIMESTAMPTZ,'%m-%d %H:%M') d, pnl_usd, exit_reason FROM g.trades
        WHERE symbol='MNQ' AND gate='{GATE}' AND opened_at::TIMESTAMPTZ >= TIMESTAMP '2026-07-27'
        ORDER BY opened_at""").fetchall()
    shad = con.execute(f"""SELECT 'SHORT', entry_price, 1, CAST(entry_ts AS BIGINT), '', 0, ''
        FROM s.shadow_trades WHERE strategy='exhaustion_rev' AND side='SHORT' AND exit_price IS NOT NULL
        AND CAST(entry_ts AS BIGINT) >= {int(dt.datetime(2026,7,27,tzinfo=dt.UTC).timestamp())} ORDER BY entry_ts""").fetchall()

    def collect(rows, label):
        pk = []   # (peak_usd_per_lot, peak_r, when, realized)
        for (side, ep, qty, t0, d, realized, _xr) in rows:
            r = peak_of(side, ep, t0, qty or 1)
            if r is None: continue
            peak_pt, atr, q = r
            pk.append((peak_pt*VPP, peak_pt/atr, d, realized))   # per-LOT $ (Lot A is 1 lot)
        return pk

    real_pk = collect(real, "real")
    shad_pk = collect(shad, "shadow")
    print(f"=== {GATE} — REAL trades since Mon 07-27 ({len(real_pk)} trades) ===")
    print(f"{'when':>12} | {'PEAK $/lot':>10} | {'peak R':>7} | {'realized$':>9}")
    for (pu, pr, d, rz) in sorted(real_pk, key=lambda x: -x[0]):
        print(f"{d:>12} | {pu:>+10.0f} | {pr:>6.1f}R | {rz:>+9.0f}")

    for label, pk in [("REAL", real_pk), ("SHADOW exhaustion_rev (bigger sample)", shad_pk)]:
        peaks = [p[0] for p in pk]
        if not peaks: continue
        print(f"\n=== {label}: peak $/lot distribution ({len(peaks)} trades) ===")
        print(f"  median peak ${statistics.median(peaks):.0f}/lot · mean ${statistics.mean(peaks):.0f}")
        buckets = [(0,50),(50,100),(100,150),(150,200),(200,300),(300,10000)]
        for lo, hi in buckets:
            n = sum(1 for x in peaks if lo <= x < hi)
            bar = "#"*n
            print(f"  ${lo:>4}-{hi if hi<10000 else '+':>4} : {n:>3}  {bar}")
        print(f"\n  first-lot TP CATCH-RATE (what % of trades peak >= the TP, so Lot A actually banks):")
        for tp in (50, 75, 100, 125, 150, 200, 260):
            n = sum(1 for x in peaks if x >= tp)
            print(f"    TP ${tp:>3}/lot : catches {n:>3}/{len(peaks)} = {100*n/len(peaks):>3.0f}% of trades  (~{tp/74:.1f}R at ATR37)")
    con.close()


if __name__ == "__main__":
    main()
