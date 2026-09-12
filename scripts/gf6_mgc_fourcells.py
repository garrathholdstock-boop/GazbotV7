"""GF6 — the four cells, each scored against the CONSTANT that lives in its own home window.

Rule 4 says score a gate on its home regime, not blanket. Rule: 'anything new must clear the best
CONSTANT'. So for every cell: sweep the exit families, take the best config by strip-best-3-sessions
(NOT by raw $ - the raw peak is always the least robust cell), then put that config through the
constant, the placebo, the split-half and an out-of-sample leg.
"""
from __future__ import annotations
import itertools
import numpy as np, pandas as pd
import gf6_mgc_gate as G
from gf6_mgc_exitgrid import ENTRIES
from gf6_mgc_verdict import _walk

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"
WINDOW = {"US": (13*60+35, 20*60), "LONDON": (7*60+5, 13*60+30), "ASIA": (5, 7*60)}
OOS_FROM = "2026-07-01"

def best_exit(d, key):
    sess, trig, side = ENTRIES[key]
    rows = []
    for stop_k, cap in itertools.product((2.0, 3.0, 5.0, 7.0, 10.0), (60, 120, 240, 480)):
        t = G.backtest(d, sess, trig, side, stop_k=stop_k, cap=cap)
        if len(t) < 80: continue
        s = G.summarise(t); s.update(family="naked+clock", stop=stop_k, cap=cap, targ=None,
                                     arm=None, trail=None)
        rows.append(s)
    for stop_k, tr in itertools.product((2.0, 3.0, 5.0), (0.5, 1.0, 1.5, 2.0)):
        t = G.backtest(d, sess, trig, side, stop_k=stop_k, target_r=tr, cap=240)
        if len(t) < 80: continue
        s = G.summarise(t); s.update(family="scalp", stop=stop_k, cap=240, targ=tr,
                                     arm=None, trail=None)
        rows.append(s)
    for arm, trail in itertools.product((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)):
        t = G.backtest(d, sess, trig, side, stop_k=5.0, arm_k=arm, trail_k=trail, cap=480)
        if len(t) < 80: continue
        s = G.summarise(t); s.update(family="chandelier", stop=5.0, cap=480, targ=None,
                                     arm=arm, trail=trail)
        rows.append(s)
    return pd.DataFrame(rows)

def constants(d, sess, side, stop_k, cap, targ=None, arm=None, trail=None):
    lo, hi = WINDOW[sess]
    out = {}
    for hhmm in range(lo, hi, 30):
        v, dd = [], []
        for sd, g in d.groupby("sday"):
            g = g.reset_index(drop=True)
            k = g.index[g.hhmm == hhmm]
            if not len(k): continue
            r = _walk(g, [int(k[0])], side, stop_k, cap, targ, arm, trail)
            if r: v.append(r[0]); dd.append(sd)
        if len(v) > 100:
            s = pd.Series(v, index=dd)
            o = s.sort_values(ascending=False).index
            out[f"{hhmm//60:02d}:{hhmm%60:02d}"] = (float(s.mean()),
                                                    float(s[~s.index.isin(o[:3])].mean()))
    return out

def main():
    d = G.frame()
    ins = d[d.sday < OOS_FROM]; oos = d[d.sday >= OOS_FROM]
    pd.set_option("display.width", 250)
    summary = []
    for key in ENTRIES:
        sess, trig, side = ENTRIES[key]
        grid = best_exit(ins, key)
        grid.to_csv(f"{OUT}/grid_{key}.csv", index=False)
        pick = grid.sort_values("strip_day3", ascending=False).iloc[0]
        cfg = dict(stop_k=float(pick["stop"]), cap=int(pick["cap"]),
                   target_r=None if pd.isna(pick["targ"]) else float(pick["targ"]),
                   arm_k=None if pd.isna(pick["arm"]) else float(pick["arm"]),
                   trail_k=None if pd.isna(pick["trail"]) else float(pick["trail"]))
        t_is = G.backtest(ins, sess, trig, side, **cfg)
        t_oos = G.backtest(oos, sess, trig, side, **cfg)
        c = constants(ins, sess, side, cfg["stop_k"], cfg["cap"], cfg["target_r"],
                      cfg["arm_k"], cfg["trail_k"])
        best_c = max(c.items(), key=lambda kv: kv[1][1])
        days = sorted(t_is.sday.unique()); mid = len(days)//2
        print(f"\n########## {key}  ({sess}, {trig}-trigger, {'LONG' if side>0 else 'SHORT'}) ##########")
        print(f"  best exit by strip-best-3-sessions: {pick['family']} stop{pick['stop']}xATR "
              f"cap{pick['cap']}m targ={pick['targ']} arm={pick['arm']} trail={pick['trail']}")
        print(f"  IN-SAMPLE  n={len(t_is)} over {t_is.sday.nunique()} sessions  "
              f"${t_is.pnl.mean():.2f}/tr  median ${t_is.pnl.median():.2f}  "
              f"win {100*(t_is.pnl>0).mean():.0f}%  net ${t_is.pnl.sum():,.0f}")
        print(f"     split-half  ${t_is[t_is.sday.isin(days[:mid])].pnl.mean():.2f} / "
              f"${t_is[t_is.sday.isin(days[mid:])].pnl.mean():.2f}"
              f"   strip-best-3-sessions ${pick['strip_day3']:.2f}"
              f"   strip-best-3-trades ${pick['strip_best3']:.2f}")
        print(f"  OUT OF SAMPLE ({OOS_FROM}+)  n={len(t_oos)} over {t_oos.sday.nunique()} sessions  "
              f"${t_oos.pnl.mean() if len(t_oos) else float('nan'):.2f}/tr  "
              f"net ${t_oos.pnl.sum() if len(t_oos) else 0:,.0f}")
        print(f"  BEST CONSTANT in the same window, same exit: {best_c[0]} "
              f"${best_c[1][0]:.2f}/tr (strip-3 ${best_c[1][1]:.2f})"
              f"   ->  the trigger adds ${t_is.pnl.mean()-best_c[1][0]:.2f}")
        summary.append(dict(cell=key, n=len(t_is), per=t_is.pnl.mean(),
                            strip_day3=pick["strip_day3"], h1=t_is[t_is.sday.isin(days[:mid])].pnl.mean(),
                            h2=t_is[t_is.sday.isin(days[mid:])].pnl.mean(),
                            oos_n=len(t_oos), oos=t_oos.pnl.mean() if len(t_oos) else np.nan,
                            const=best_c[1][0], const_t=best_c[0],
                            adds=t_is.pnl.mean()-best_c[1][0],
                            cfg=f"{pick['family']} stop{pick['stop']}x cap{pick['cap']}m "
                                f"targ{pick['targ']} arm{pick['arm']}/{pick['trail']}"))
    s = pd.DataFrame(summary)
    s.to_csv(f"{OUT}/fourcells.csv", index=False)
    print("\n\n===== FOUR CELLS, one line each =====")
    print(s.round(2).to_string(index=False))

if __name__ == "__main__":
    main()
