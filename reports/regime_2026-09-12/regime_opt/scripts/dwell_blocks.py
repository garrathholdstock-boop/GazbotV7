#!/usr/bin/env python3
"""THE DWELL CURVE BY SESSION BLOCK (sibling instruction 2026-09-12).

A regime cell's result is not one number. The desk permanently benches ASIA; a sibling measured
the US cash session at -429.8pt over the same 240 sessions while carrying 43.7% of all movement.
So the dwell curve is reported per block, with the same three bars applied to each block cell.

BLOCKS (UTC, CME day 22:00 -> 21:00):
  ASIA   22:00-08:00   the desk's permanent bench
  LDN    08:00-13:30
  USCASH 13:30-20:00   the block the desk actually trades
  LATE   20:00-21:00
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd
from dwell import runs, dwell_trades

BLOCKS = {"ASIA": [(1320, 1440), (0, 480)], "LDN": [(480, 810)],
          "USCASH": [(810, 1200)], "LATE": [(1200, 1260)]}
FRIC = 1.25
g = R.load_bars(15)
M = R.Model(15, 3, "base", g=g)
mod = g["mod"].values


def in_block(i, bn):
    m = np.zeros(len(i), bool)
    for lo, hi in BLOCKS[bn]:
        m |= (mod[i] >= lo) & (mod[i] < hi)
    return m


rows = []
for arm, (q, s) in {"STATE": (M.sign != 0, M.sign),
                    "BOTH_er8_45": ((M.sign != 0) &
                                    (np.nan_to_num(M.feat["er8"], nan=-1) >= 0.45), M.sign),
                    "NEITHER": (np.isfinite(M.feat["d8"]),
                                np.sign(np.nan_to_num(M.feat["d8"])).astype(int))}.items():
    st, ln, sd = runs(q, s, g.sess.values)
    for K in range(1, 7):
        for hm in (30, 60, 90, 120):
            T = dwell_trades(M, st, ln, sd, K, hm // 15, friction=FRIC)
            if len(T) < 40:
                continue
            for bn in BLOCKS:
                sub = T[in_block(T.i.values, bn)]
                if len(sub) < 60:
                    continue
                sc = R.sign_control(sub, draws=2000, block="day", friction=FRIC)
                lo, mid, hi = R.day_block_boot(sub, friction=FRIC, draws=2000)
                ps = R.period_stats(sub, M)
                al = R.trades(M, sub.i.values, hold=hm // 15, friction=FRIC,
                              side_override=np.ones(len(sub), int))
                rows.append(dict(arm=arm, block=bn, K=K, hold_min=hm, n=len(sub), net=mid,
                                 forfeit_atr=sub.forfeit.mean(), lo=lo, hi=hi,
                                 edge_sd=(mid - sc["mean"]) / sc["sd"], p=sc["p"],
                                 always_long=al.pt.mean(), long_pct=100*(sub.side > 0).mean(),
                                 TR=ps["TRAIN"]["mean"], VA=ps["VALIDATE"]["mean"],
                                 TE=ps["TEST"]["mean"],
                                 a=mid > 0, b=(mid - sc["mean"]) > sc["sd"], c=lo > 0))
D = pd.DataFrame(rows)
D["ALL_BARS"] = D.a & D.b & D.c
D.to_csv(f"{R.ART}/tables/dwell_by_block.csv", index=False)
pd.set_option("display.width", 250)
for arm in D.arm.unique():
    print(f"\n{'='*104}\nDWELL CURVE BY BLOCK · arm = {arm} · net pt/trade at 1.25pt")
    s = D[D.arm == arm]
    print(s.pivot_table(index="K", columns=["block", "hold_min"], values="net").round(2)
          .to_string())
    print("  n:")
    print(s.pivot_table(index="K", columns=["block", "hold_min"], values="n").round(0)
          .to_string())
print(f"\n{'='*104}\nBLOCK CELLS CLEARING ALL THREE BARS: {int(D.ALL_BARS.sum())} of {len(D)}")
if D.ALL_BARS.any():
    print(D[D.ALL_BARS][["arm", "block", "K", "hold_min", "n", "net", "lo", "hi", "edge_sd",
                         "always_long", "TR", "VA", "TE"]].round(2).to_string(index=False))
print("\nBLOCK MARGINALS (mean net over all dwell cells in the block)")
print(D.groupby("block").agg(cells=("net", "size"), mean_net=("net", "mean"),
                             mean_always_long=("always_long", "mean"),
                             pass_all=("ALL_BARS", "sum")).round(2).to_string())
