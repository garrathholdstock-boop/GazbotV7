#!/usr/bin/env python3
"""ALL trades this week + the profit-MAXIMISING Lot-A take-profit R (operator 2026-07-29).

(1) Every REAL trade this week (all gates): peak $/lot, peak R, realized.
(2) For the give-back gate (exhaustion_short), sweep Lot-A's fixed-R take-profit FINELY and find the R
    that captures the MOST profit on Lot A. Faithful: walk each trade's ticks — Lot A banks +R*ATR if
    favorable hits it FIRST, stops -1*ATR if adverse hits first, else rides to the hold cap. ATR = the
    real _atr(ATR-14 TR, 1-min). $2/pt, $1.50/RT. Lot B rides the wide chandelier separately (unchanged by R).
  PYTHONPATH=src .venv/bin/python scripts/lotA_optimal_r.py
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
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 90 * 60


def main():
    con = duckdb.connect()
    for a, p in [("c", CAP), ("g", DB)]:
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

    def trade_ctx(side, ep, t0):
        mb = [b for b in bars_for(t0) if b.ts <= t0]
        if len(mb) < 15: return None
        atr = _atr(mb, n=14)
        if atr <= 0: return None
        ticks = con.execute(f"""SELECT price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>={int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        if len(ticks) < 2: return None
        return atr, [p[0] for p in ticks[1:]]

    def lotA(side, ep, atr, prices, target_r):
        """Lot A: first to hit +target_r*ATR (bank) or -1*ATR (stop); else ride to end."""
        tgt = target_r * atr; stp = atr
        for px in prices:
            fav = (ep - px) if side == "SHORT" else (px - ep)
            if fav >= tgt: return tgt * VPP - FEE
            if -fav >= stp: return -stp * VPP - FEE
        last = prices[-1]
        pts = (ep - last) if side == "SHORT" else (last - ep)
        return pts * VPP - FEE

    # (1) ALL trades this week, all gates
    allt = con.execute("""SELECT gate, side, entry_price, epoch(opened_at::TIMESTAMPTZ) t0,
           strftime(opened_at::TIMESTAMPTZ,'%m-%d %H:%M') d, pnl_usd FROM g.trades
        WHERE symbol='MNQ' AND opened_at::TIMESTAMPTZ >= TIMESTAMP '2026-07-27'
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY opened_at""").fetchall()
    recs = []   # (gate, side, ep, atr, prices, d, realized, peak_usd, peak_r)
    for (gate, side, ep, t0, d, rz) in allt:
        cx = trade_ctx(side, ep, t0)
        if cx is None: continue
        atr, prices = cx
        peak = max(((ep-px) if side == "SHORT" else (px-ep)) for px in prices)
        recs.append((gate, side, ep, atr, prices, d, rz, peak*VPP, peak/atr))

    print(f"=== ALL {len(recs)} real trades this week (07-27→now) — peak $/lot & R ===")
    print(f"{'gate':>17} {'when':>12} | {'peak$/lot':>9} | {'peakR':>6} | {'realized$':>9}")
    bygate = {}
    for (g, sd, ep, atr, pr, d, rz, pu, prr) in sorted(recs, key=lambda x: -x[7]):
        bygate.setdefault(g, []).append((sd, ep, atr, pr, pu, prr, rz))
        print(f"{g:>17} {d:>12} | {pu:>+9.0f} | {prr:>5.1f}R | {rz:>+9.0f}")

    print(f"\n=== per-gate: count · median peak$/lot · median peakR · total realized ===")
    for g, rows in sorted(bygate.items()):
        pus = [r[4] for r in rows]; prs = [r[5] for r in rows]; rz = sum(r[6] for r in rows)
        print(f"  {g:>17}: {len(rows):>2} trades · med peak ${statistics.median(pus):>4.0f} · med {statistics.median(prs):>4.1f}R · realized ${rz:>+5.0f}")

    # (2) Lot-A profit-max sweep on exhaustion_short (the give-back gate)
    exh = bygate.get("exhaustion_short", [])
    if exh:
        atr_med = statistics.median([r[2] for r in exh])
        print(f"\n=== exhaustion_short: LOT-A captured profit vs take-profit R ({len(exh)} trades, med ATR {atr_med:.0f}) ===")
        print(f"  {'R':>4} | {'$TP/lot':>7} | {'Lot-A captured$':>15} | {'trades that banked TP':>21}")
        best = None
        curve = []
        R = 0.5
        while R <= 6.01:
            tot = 0.0; banked = 0
            for (sd, ep, atr, pr, pu, prr, rz) in exh:
                p = lotA(sd, ep, atr, pr, R); tot += p
                if prr >= R: banked += 1
            curve.append((R, tot, banked))
            if best is None or tot > best[1]: best = (R, tot, banked)
            R = round(R + 0.5, 2)
        for (R, tot, banked) in curve:
            star = "  ★ MAX" if (R, tot, banked) == best else ""
            print(f"  {R:>4.1f} | {R*atr_med*VPP:>+7.0f} | {tot:>+15.0f} | {banked:>3}/{len(exh)} = {100*banked/len(exh):>3.0f}%{star}")
        R, tot, banked = best
        print(f"\n  ★ PROFIT-MAX Lot-A take-profit: {R}R ≈ ${R*atr_med*VPP:.0f}/lot → captures ${tot:+.0f} on Lot A "
              f"({banked}/{len(exh)} = {100*banked/len(exh):.0f}% of trades bank the TP)")
    con.close()


if __name__ == "__main__":
    main()
