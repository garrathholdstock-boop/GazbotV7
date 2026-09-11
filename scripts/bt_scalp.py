#!/usr/bin/env python3
"""SCALP sweep: small, fast targets on the WHEN -> 10-minute-wait entry.

The operator's reasoning: a coin-flip entry still pays if the targets are small enough to
be hit often, because $1.50 of cost is trivial against a $25-$50 target and we get 4-6
trades a day.

★ THE TRAP THIS MUST EXPOSE, not hide: a small target with a wide stop ALWAYS produces a
  high win rate. That is arithmetic, not edge. The question is whether the rare big loser
  eats the many small winners - which is the exact "capped wins, runaway losers" shape the
  desk's own V5 archive identified as its founding pathology. So every table here reports
  the hit rate AND the expectancy AND the per-period stability together.
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
    """(session, side, entry, forward highs, lows, closes). Computed once."""
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
            end = j + 1
            while end < n and not (FLAT <= mod[end] < 22*60):
                end += 1
            if end - j < 6:
                i += 30; continue
            out.append((s, side, o[j+1], h[j+1:end], l[j+1:end], c[j+1:end]))
            i = j + 30
    return out


def hit_rates(E, targets):
    """% of entries that EVER reach $X favourable, and that reach it BEFORE -$X adverse."""
    rows = []
    for X in targets:
        pt = X / VPP                       # per lot
        ever = race = 0
        for (s, side, e, h, l, c) in E:
            fav = (h - e) if side > 0 else (e - l)
            adv = (e - l) if side > 0 else (h - e)
            gi = np.argmax(fav >= pt) if (fav >= pt).any() else -1
            bi = np.argmax(adv >= pt) if (adv >= pt).any() else -1
            if gi >= 0:
                ever += 1
            if gi >= 0 and (bi < 0 or gi < bi):
                race += 1
        rows.append((X, pt, 100*ever/len(E), 100*race/len(E)))
    return rows


def sim(E, tp1, tp2, cut):
    pnl = []
    t1_pt, t2_pt = tp1/VPP, tp2/VPP
    c_pt = cut/(VPP*LOTS) if cut else None
    for (s, side, e, h, l, c) in E:
        lots, real, done = LOTS, 0.0, False
        for k in range(len(h)):
            adv = (e - l[k]) if side > 0 else (h[k] - e)
            if c_pt is not None and adv >= c_pt:      # cut checked FIRST; ties lose
                real += -adv*VPP*lots - FEE*lots
                done = True; break
            if lots == LOTS and (((h[k] >= e+t1_pt) if side > 0 else (l[k] <= e-t1_pt))):
                real += tp1 - FEE; lots -= 1
            if lots == 1 and (((h[k] >= e+t2_pt) if side > 0 else (l[k] <= e-t2_pt))):
                real += tp2 - FEE; lots = 0; done = True; break
        if not done:
            real += side*(c[-1]-e)*VPP*lots - FEE*lots
        pnl.append(real)
    P = np.array(pnl)
    t = P.mean()/(P.std(ddof=1)/np.sqrt(len(P))) if len(P) > 2 else np.nan
    return P.mean(), P.sum(), 100*(P > 0).mean(), t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vmin", type=float, default=3.0)
    a = ap.parse_args()
    df = tape()
    ss = sorted(df.sess.unique()); n = len(ss)
    P = {"TRAIN": set(ss[:int(n*.4)]), "VALIDATE": set(ss[int(n*.4):int(n*.7)]),
         "TEST": set(ss[int(n*.7):])}
    ALL = entries(df, a.vmin)
    print(f"trigger vol>={a.vmin}x · {len(ALL)} entries over {df.sess.nunique()} sessions "
          f"= {len(ALL)/df.sess.nunique():.1f} per session\n")

    print("── HOW OFTEN IS EACH TARGET REACHED? (per lot, $) ──")
    print(f"{'target':>8}{'points':>8}{'EVER hit':>11}{'hit BEFORE the same loss':>26}")
    for X, pt, ev, rc in hit_rates(ALL, [25, 50, 75, 100, 150, 200, 300]):
        print(f"{'$'+str(X):>8}{pt:>8.1f}{ev:>10.0f}%{rc:>25.0f}%")
    print("   'ever' has no stop, so it flatters: a trade 300pt underwater still counts")
    print("   if it eventually ticks back. The right-hand column is the honest one.\n")

    print("── EXPECTANCY GRID, per period ──")
    print(f"{'tp1':>5}{'tp2':>6}{'cut':>6}" +
          "".join(f"{p:>22}" for p in P) + f"{'ALL':>16}")
    print(f"{'':>17}" + "".join(f"{'$/tr':>8}{'win%':>7}{'t':>7}" for p in P)
          + f"{'$/tr':>8}{'win%':>7}")
    best = []
    for tp1 in (25, 50, 75, 100):
        for tp2 in (50, 100, 150, 200):
            if tp2 < tp1:
                continue
            for cut in (100, 200, 400, 0):
                line = f"{tp1:>5}{tp2:>6}{('none' if cut == 0 else cut):>6}"
                vals = []
                for p, keep in P.items():
                    E = entries(df[df.sess.isin(keep)], a.vmin)
                    m, tot, w, t = sim(E, tp1, tp2, cut if cut else None)
                    vals.append(m)
                    line += f"{m:>8.2f}{w:>6.0f}%{t:>7.2f}"
                m, tot, w, t = sim(ALL, tp1, tp2, cut if cut else None)
                line += f"{m:>8.2f}{w:>6.0f}%"
                allpos = all(x > 0 for x in vals)
                print(line + ("  ***" if allpos else ""))
                if allpos:
                    best.append((tp1, tp2, cut, min(vals), m))
    print("\n  *** = positive in ALL THREE periods")
    if best:
        print("\n  cells positive in every period:")
        for (t1, t2, c, worst, allm) in sorted(best, key=lambda x: -x[3]):
            print(f"     tp1 ${t1}  tp2 ${t2}  cut {'none' if not c else '$'+str(c)}"
                  f"   worst period ${worst:+.2f}/tr   all-sample ${allm:+.2f}/tr")
    else:
        print("\n  NONE. No combination is positive in all three periods.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
