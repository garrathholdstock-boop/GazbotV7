#!/usr/bin/env python3
"""ADVERSE CUT as a MONITORED level, not a resting stop.

The distinction the operator drew, and it is a real one:

  RESTING STOP     lives at the venue, fires on any WICK through the level - including a
                   spike that recovers in the same second.
  MONITORED CUT    a process samples price and fires a market order when what it SEES is
                   beyond the level. A wick between samples is never seen and never acts.

On 1-minute bars that is the difference between testing the bar's LOW (every wick fires)
and the bar's CLOSE (only a level that still holds at the sample fires). The desk already
runs this shape: gazbot7-rider-peak-watch samples the MD_STREAM tape at 1 Hz.

The trade-off is not free and both halves are reported: fewer false triggers, but the
realised loss can exceed the nominal level, because price is beyond it before we look.
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


def sim(E, tp1, tp2, cut, mode, slip):
    """mode 'stop'   -> the bar's extreme breaches the level (a resting stop)
       mode 'monitor'-> only the bar's CLOSE is seen; fill at that close + slip"""
    pnl, mae, ncut = [], [], 0
    a, b = tp1/VPP, tp2/VPP
    for (side, e, h, l, c) in E:
        lots, real, worst, done = LOTS, 0.0, 0.0, False
        for k in range(len(h)):
            adv_ext = (e - l[k]) if side > 0 else (h[k] - e)
            adv_cls = (e - c[k]) if side > 0 else (c[k] - e)
            worst = max(worst, adv_ext*VPP*lots)
            if cut:
                cpt = cut/(VPP*lots)
                if mode == "stop" and adv_ext >= cpt:
                    real += -(cpt + slip)*VPP*lots - FEE*lots
                    done = True; ncut += 1; break
                if mode == "monitor" and adv_cls >= cpt:
                    # we only know what the sample showed; we fill THERE, not at the level
                    real += -(adv_cls + slip)*VPP*lots - FEE*lots
                    done = True; ncut += 1; break
            if lots == LOTS and ((h[k] >= e+a) if side > 0 else (l[k] <= e-a)):
                real += tp1 - FEE; lots -= 1
            if lots == 1 and ((h[k] >= e+b) if side > 0 else (l[k] <= e-b)):
                real += tp2 - FEE; lots = 0; done = True; break
        if not done and lots:
            real += side*(c[-1]-e)*VPP*lots - FEE*lots
        pnl.append(real); mae.append(worst)
    P = np.array(pnl)
    t = P.mean()/(P.std(ddof=1)/np.sqrt(len(P))) if len(P) > 2 else np.nan
    return dict(mean=P.mean(), win=100*(P > 0).mean(), t=t, worst=P.min(),
                cutpct=100*ncut/len(P))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vmin", type=float, default=3.0)
    ap.add_argument("--slip", type=float, default=1.0)
    a = ap.parse_args()
    df = tape()
    ss = sorted(df.sess.unique()); n = len(ss)
    PER = {"TRAIN": set(ss[:int(n*.4)]), "VALIDATE": set(ss[int(n*.4):int(n*.7)]),
           "TEST": set(ss[int(n*.7):])}
    E = {p: entries(df[df.sess.isin(k)], a.vmin) for p, k in PER.items()}
    ALL = entries(df, a.vmin)
    print(f"trigger vol>={a.vmin}x · {len(ALL)} entries · slip {a.slip:g}pt\n")
    print("RESTING STOP = any wick fires it.  MONITORED CUT = only the 1-min sample fires it.\n")

    green = []
    for (t1, t2) in ((100,100),(100,150),(100,200),(150,150),(150,250),(200,200),(200,400),(300,300)):
        print(f"── tp1 ${t1} / tp2 ${t2} ──")
        print(f"{'cut':>6}{'mode':>9}" + "".join(f"{p:>16}" for p in PER)
              + f"{'ALL':>25}")
        print(f"{'':>15}" + "".join(f"{'$/tr':>9}{'win%':>7}" for p in PER)
              + f"{'$/tr':>9}{'win%':>7}{'%cut':>9}")
        for cut in (200, 300, 400, 600, 800, None):
            for mode in (("stop", "monitor") if cut else ("monitor",)):
                vals, line = [], f"{('none' if cut is None else cut):>6}{mode:>9}"
                for p in PER:
                    r = sim(E[p], t1, t2, cut, mode, a.slip)
                    vals.append(r["mean"]); line += f"{r['mean']:>9.2f}{r['win']:>6.0f}%"
                r = sim(ALL, t1, t2, cut, mode, a.slip)
                line += f"{r['mean']:>9.2f}{r['win']:>6.0f}%{r['cutpct']:>8.0f}%"
                ok = all(x > 0 for x in vals)
                print(line + ("  ***" if ok else ""))
                if ok:
                    green.append((t1, t2, cut, mode, min(vals), r))
        print()
    print("  *** = positive in ALL THREE periods")
    if green:
        print("\n  ── GREEN IN EVERY PERIOD ──")
        for (t1, t2, cut, mode, w, r) in sorted(green, key=lambda x: -x[4]):
            print(f"     tp1 ${t1}/tp2 ${t2} · {mode} cut "
                  f"{'none' if cut is None else '$'+str(cut)} → worst period ${w:+.2f}/tr"
                  f" · all ${r['mean']:+.2f}/tr · win {r['win']:.0f}%"
                  f" · worst trade ${r['worst']:.0f}")
    else:
        print("\n  NONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
