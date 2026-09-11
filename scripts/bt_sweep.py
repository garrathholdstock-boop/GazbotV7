#!/usr/bin/env python3
"""Parameter sweep for the WHEN->wait->join spec: adverse cut x take-profits x hold time.

Entries are computed ONCE per trigger level and reused for every exit combination, so the
sweep varies only what it claims to vary - and it is fast enough to cover a real grid.

★ RUN ON TRAIN ONLY by default. With ~300 cells something always looks good; the landscape
  is the diagnostic (a broad plateau is a signal, an isolated spike is noise), and the
  survivors must then face held-out data. --stage validate/test replays named cells only.
"""
from __future__ import annotations

import argparse, glob, json
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
VPP, FEE, LOTS, WAIT, FLAT_MOD = 2.0, 1.50, 2, 10, 20*60+40


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


def entries(df, vmin, maxbars=480):
    """Every (entry price, side, forward path) once. Exits are applied later."""
    out = []
    for s, g in df.groupby("sess"):
        g = g.sort_values("ts").reset_index(drop=True)
        v, c, o = g.vol_rel.values, g.close.values, g.open.values
        h, l, mod = g.high.values, g.low.values, g["mod"].values
        n = len(g)
        i = 60
        while i < n - WAIT - 30:
            if FLAT_MOD <= mod[i] < 22*60:
                break
            if not (v[i] == v[i] and v[i] >= vmin):
                i += 1
                continue
            j = i + WAIT
            if j + 1 >= n:
                break
            side = 1 if c[j] > c[i] else (-1 if c[j] < c[i] else 0)
            if side == 0:
                i += 30
                continue
            e = o[j+1]
            end = j + 1
            while end < n and not (FLAT_MOD <= mod[end] < 22*60) and end - j <= maxbars:
                end += 1
            if end - j < 5:
                i += 30
                continue
            out.append((s, side, e, h[j+1:end].copy(), l[j+1:end].copy(), c[j+1:end].copy()))
            i = j + 30
    return out


def score(E, cut, tp1, tp2, maxhold):
    """cut/tp in DOLLARS for the whole position; maxhold in minutes (0 = to the flat)."""
    pnl, why = [], []
    c_pt, t1_pt, t2_pt = cut/(VPP*LOTS), tp1/VPP, tp2/VPP
    for (s, side, e, h, l, c) in E:
        lots, real, done = LOTS, 0.0, None
        lim = len(h) if maxhold == 0 else min(len(h), maxhold)
        for k in range(lim):
            adverse = (e - l[k]) if side > 0 else (h[k] - e)
            # the CUT is checked first; a bar touching both takes the loss
            if adverse >= c_pt:
                real += -cut/LOTS*lots - FEE*lots if lots == LOTS else -(c_pt*VPP*lots) - FEE*lots
                done = "CUT"; break
            if lots == LOTS:
                if (h[k] >= e+t1_pt) if side > 0 else (l[k] <= e-t1_pt):
                    real += tp1 - FEE; lots -= 1
            if lots and lots < LOTS:
                if (h[k] >= e+t2_pt) if side > 0 else (l[k] <= e-t2_pt):
                    real += tp2 - FEE; lots = 0; done = "TP2"; break
        if done is None:
            last = c[min(lim, len(c))-1]
            real += side*(last-e)*VPP*lots - FEE*lots
            done = "TIME" if maxhold and lim < len(h) else "FLAT"
        pnl.append(real); why.append(done)
    P = np.array(pnl)
    t = P.mean()/(P.std(ddof=1)/np.sqrt(len(P))) if len(P) > 2 else np.nan
    return dict(n=len(P), mean=P.mean(), total=P.sum(), win=100*(P > 0).mean(), t=t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="train", choices=["train", "validate", "test"])
    ap.add_argument("--vmin", type=float, default=3.0)
    ap.add_argument("--cells", help="JSON list of [cut,tp1,tp2,hold] to replay")
    a = ap.parse_args()
    df = tape()
    ss = sorted(df.sess.unique()); n = len(ss)
    lo, hi = int(n*0.40), int(n*0.70)
    keep = {"train": set(ss[:lo]), "validate": set(ss[lo:hi]), "test": set(ss[hi:])}[a.stage]
    D = df[df.sess.isin(keep)]
    E = entries(D, a.vmin)
    print(f"STAGE {a.stage.upper()} · {len(keep)} sessions · trigger vol>={a.vmin}x · "
          f"{len(E)} entries · 2 lots · $1.50/contract/RT\n")

    if a.cells:
        cells = json.loads(a.cells)
    else:
        cells = [[c, t1, t2, hh]
                 for c in (100, 150, 200, 300, 400, 600)
                 for t1 in (50, 100, 150)
                 for t2 in (100, 200, 300, 400)
                 for hh in (60, 120, 240, 0) if t2 >= t1]
    res = []
    for (c, t1, t2, hh) in cells:
        r = score(E, c, t1, t2, hh)
        r.update(cut=c, tp1=t1, tp2=t2, hold=hh)
        res.append(r)
    R = pd.DataFrame(res).sort_values("mean", ascending=False)
    pos = (R["mean"] > 0).sum()
    print(f"{len(R)} cells · {pos} positive ({100*pos/len(R):.0f}%) · "
          f"mean/trade median ${R['mean'].median():+.2f}, "
          f"range ${R['mean'].min():+.2f} .. ${R['mean'].max():+.2f}\n")
    print(f"{'cut':>6}{'tp1':>6}{'tp2':>6}{'hold':>6}{'n':>6}{'$/trade':>10}"
          f"{'total':>10}{'win%':>7}{'t':>7}")
    for _, r in R.head(20).iterrows():
        print(f"{r.cut:>6.0f}{r.tp1:>6.0f}{r.tp2:>6.0f}"
              f"{('flat' if r.hold == 0 else f'{r.hold:.0f}m'):>6}{r.n:>6.0f}"
              f"{r['mean']:>10.2f}{r.total:>10.0f}{r.win:>7.1f}{r.t:>7.2f}")

    if not a.cells:
        print(f"\n── LANDSCAPE: is the top a plateau or a spike? ──")
        print("   mean $/trade by CUT (rows) x TP2 (cols), best hold/tp1 per cell")
        piv = R.pivot_table(index="cut", columns="tp2", values="mean", aggfunc="max")
        print("        " + "".join(f"{c:>9.0f}" for c in piv.columns))
        for idx, row in piv.iterrows():
            print(f"  {idx:>5.0f} " + "".join(f"{x:>9.2f}" for x in row.values))
        print("\n   (a broad region of positives is a signal; one hot cell surrounded by "
              "negatives is noise)")
        top = R.head(8)[["cut", "tp1", "tp2", "hold"]].values.tolist()
        print(f"\n   top-8 cells for held-out replay:\n   --cells '{json.dumps(top)}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
