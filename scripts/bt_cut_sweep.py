#!/usr/bin/env python3
"""ADVERSE-CUT SWEEP with a REALISTIC stop fill.

The earlier sweeps filled the stop at the BAR'S EXTREME, which on 1-minute bars can be 30+
points beyond the trigger and made every stopped variant look far worse than reality. Here
a stop is what it actually is: a market order fired when price trades through the level,
filling at the level plus slippage. Measured MNQ book (median spread 0.50pt, ~4 lots at the
touch, a real 4-lot market order costing ~$0.43) says 1 point is a fair-to-pessimistic
assumption for 2 lots; --slip sweeps it.

Reports BOTH what the cut does to expectancy AND what it does to the tail, because on a
$30k account capping a $6,183 single-trade excursion is worth something even if the mean
does not move.
"""
from __future__ import annotations

import argparse, glob
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
VPP, FEE, LOTS, WAIT, FLAT = 2.0, 1.50, 2, 10, 20*60+40


def tape():
    con = duckdb.connect()
    files = sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
    rows = [f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume "
            f"from read_parquet('{f}')" for f in files]
    df = con.execute(f"""
     with a as ({' union all '.join(rows)}),
     t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d from a),
     v as (select d,exp,sum(volume) vv from t group by 1,2),
     fr as (select d,exp from (select *,row_number() over
            (partition by d order by vv desc) rn from v) where rn=1)
     select t.ts,t.open,t.high,t.low,t.close,t.volume
     from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts""").df()
    df["dt"] = pd.to_datetime(df.ts, unit="s", utc=True)
    df["mod"] = df.dt.dt.hour*60 + df.dt.dt.minute
    df["sess"] = (df.dt + pd.Timedelta(hours=2)).dt.date
    tod = df.groupby("mod").volume.median()
    df["vol_rel"] = df.volume / df["mod"].map(tod).replace(0, np.nan)
    return df


def entries(D, vmin):
    out = []
    for s, g in D.groupby("sess"):
        g = g.sort_values("ts").reset_index(drop=True)
        v, c, o, h, l, mod = (g.vol_rel.values, g.close.values, g.open.values,
                              g.high.values, g.low.values, g["mod"].values)
        n = len(g); i = 60
        while i < n - WAIT - 30:
            if FLAT <= mod[i] < 22*60:
                break
            if not (v[i] == v[i] and v[i] >= vmin):
                i += 1; continue
            j = i + WAIT
            if j + 1 >= n:
                break
            side = 1 if c[j] > c[i] else (-1 if c[j] < c[i] else 0)
            if side == 0:
                i += 30; continue
            e = j + 1
            while e < n and not (FLAT <= mod[e] < 22*60):
                e += 1
            if e - j < 6:
                i += 30; continue
            out.append((side, o[j+1], h[j+1:e], l[j+1:e], c[j+1:e]))
            i = j + 30
    return out


def sim(E, tp1, tp2, cut, slip):
    """cut in $ for the WHOLE position; filled at the level + slip points. None = no stop."""
    pnl, mae = [], []
    a, b = tp1/VPP, tp2/VPP
    for (side, e, h, l, c) in E:
        lots, real, worst, done = LOTS, 0.0, 0.0, False
        cpt = (cut/(VPP*lots)) if cut else None      # recomputed as lots change
        for k in range(len(h)):
            adv_pt = (e - l[k]) if side > 0 else (h[k] - e)
            worst = max(worst, adv_pt*VPP*lots)
            if cut:
                cpt = cut/(VPP*lots)
                if adv_pt >= cpt:
                    # ★ FILLED AT THE LEVEL + SLIPPAGE, not at the bar's extreme.
                    real += -(cpt + slip)*VPP*lots - FEE*lots
                    done = True; break
            if lots == LOTS and ((h[k] >= e+a) if side > 0 else (l[k] <= e-a)):
                real += tp1 - FEE; lots -= 1
            if lots == 1 and ((h[k] >= e+b) if side > 0 else (l[k] <= e-b)):
                real += tp2 - FEE; lots = 0; done = True; break
        if not done and lots:
            real += side*(c[-1]-e)*VPP*lots - FEE*lots
        pnl.append(real); mae.append(worst)
    P, M = np.array(pnl), np.array(mae)
    t = P.mean()/(P.std(ddof=1)/np.sqrt(len(P))) if len(P) > 2 else np.nan
    return dict(mean=P.mean(), win=100*(P > 0).mean(), t=t, worst=P.min(),
                p99loss=np.percentile(P, 1), maemax=M.max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vmin", type=float, default=3.0)
    ap.add_argument("--slip", type=float, default=1.0, help="points of stop slippage")
    a = ap.parse_args()
    df = tape()
    ss = sorted(df.sess.unique()); n = len(ss)
    PER = {"TRAIN": set(ss[:int(n*.4)]), "VALIDATE": set(ss[int(n*.4):int(n*.7)]),
           "TEST": set(ss[int(n*.7):])}
    E = {p: entries(df[df.sess.isin(k)], a.vmin) for p, k in PER.items()}
    ALL = entries(df, a.vmin)
    print(f"trigger vol>={a.vmin}x · {len(ALL)} entries · stop fills at level + "
          f"{a.slip:g}pt slippage · 2 lots\n")

    CUTS = [50, 75, 100, 150, 200, 250, 300, 400, 500, 600, 800, None]
    TPS = [(50, 50), (50, 75), (75, 75), (50, 100), (75, 100), (100, 150)]
    print(f"{'tp1':>4}{'tp2':>5}{'cut':>6}" + "".join(f"{p:>16}" for p in PER)
          + f"{'ALL':>26}")
    print(f"{'':>15}" + "".join(f"{'$/tr':>9}{'win%':>7}" for p in PER)
          + f"{'$/tr':>9}{'win%':>7}{'worst tr':>10}")
    green = []
    for (t1, t2) in TPS:
        for cut in CUTS:
            vals, line = [], f"{t1:>4}{t2:>5}{('none' if cut is None else cut):>6}"
            for p in PER:
                r = sim(E[p], t1, t2, cut, a.slip)
                vals.append(r["mean"])
                line += f"{r['mean']:>9.2f}{r['win']:>6.0f}%"
            r = sim(ALL, t1, t2, cut, a.slip)
            line += f"{r['mean']:>9.2f}{r['win']:>6.0f}%{r['worst']:>10.0f}"
            ok = all(x > 0 for x in vals)
            print(line + ("  ***" if ok else ""))
            if ok:
                green.append((t1, t2, cut, min(vals), r))
        print()
    print("  *** = positive in ALL THREE periods")
    if green:
        print("\n  ── GREEN IN EVERY PERIOD ──")
        for (t1, t2, cut, worstper, r) in sorted(green, key=lambda x: -x[3]):
            print(f"     tp1 ${t1} / tp2 ${t2} / cut {'none' if cut is None else '$'+str(cut)}"
                  f" → worst period ${worstper:+.2f}/tr · all-sample ${r['mean']:+.2f}/tr"
                  f" · win {r['win']:.0f}% · worst single trade ${r['worst']:.0f}")
    else:
        print("\n  NONE — no cut level makes it positive in all three periods.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
