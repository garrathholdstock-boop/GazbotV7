#!/usr/bin/env python3
"""Execute the pre-registered run-entry grid (data/prereg_run_entry_grid.json).

    PYTHONPATH=src .venv/bin/python scripts/run_entry_grid.py --stage train
    PYTHONPATH=src .venv/bin/python scripts/run_entry_grid.py --stage validate
    PYTHONPATH=src .venv/bin/python scripts/run_entry_grid.py --stage test

Stages are deliberately separate commands so VALIDATE and TEST cannot be glanced at
while reading TRAIN. Every threshold is READ FROM THE REGISTRATION, never hardcoded.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys

import duckdb
import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
PREREG = f"{GB}/data/prereg_run_entry_grid.json"
MAXRACE, COOLDOWN, LOOKBACK = 240, 30, 30
FEE_NOTE = "no exits, no P&L - classification only"


def load_tape():
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
    df["mod"] = df.dt.dt.hour * 60 + df.dt.dt.minute
    # the CME trading day starts 22:00Z = midnight Paris, so +2h rolls it onto the right date
    df["sess"] = (df.dt + pd.Timedelta(hours=2)).dt.date
    # ★ TIME-OF-DAY NORMALISATION IS MANDATORY. Raw volume at 04:00Z and 14:00Z are not
    #   comparable; without this the filter is a clock, not a signal.
    tod = df.groupby("mod").volume.median()
    df["vol_rel"] = df.volume / df["mod"].map(tod).replace(0, np.nan)
    return df


def split(df, cfg):
    s = sorted(df.sess.unique())
    n = len(s)
    a, b = int(n * 0.40), int(n * 0.70)
    return {"train": set(s[:a]), "validate": set(s[a:b]), "test": set(s[b:])}, s


def race(sessions, K, R, V):
    """Symmetric +R vs -R race after a K-point confirmation. Causal throughout."""
    w = l = 0
    per = {}
    for s, g in sessions.items():
        h, lo, c, o, v = (g.high.values, g.low.values, g.close.values,
                          g.open.values, g.vol_rel.values)
        n = len(g)
        i = LOOKBACK + 1
        pw = pl = 0
        while i < n - MAXRACE:
            up = h[i] - lo[i-LOOKBACK:i].min() >= K
            dn = h[i-LOOKBACK:i].max() - lo[i] >= K
            if up == dn:                       # neither, or both in one bar
                i += 1
                continue
            if V > 1.0 and not (v[i] == v[i] and v[i] >= V):
                i += 1
                continue
            side = 1 if up else -1
            e = o[i+1] if i + 1 < n else c[i]
            res = 0
            for k in range(i + 1, min(i + 1 + MAXRACE, n)):
                good = (h[k] >= e + R) if side > 0 else (lo[k] <= e - R)
                bad = (lo[k] <= e - R) if side > 0 else (h[k] >= e + R)
                if good and bad:               # tie resolves AGAINST us
                    res = -1; break
                if good:
                    res = 1; break
                if bad:
                    res = -1; break
            if res == 1: w += 1; pw += 1
            elif res == -1: l += 1; pl += 1
            i += COOLDOWN
        if pw + pl:
            per[s] = (pw, pl)
    return w, l, per


def ci(per):
    d = np.array([a / (a + b) for a, b in per.values() if a + b >= 3])
    if len(d) < 8:
        return (np.nan, np.nan)
    rng = np.random.default_rng(17)
    bs = [rng.choice(d, len(d)).mean() for _ in range(4000)]
    return tuple(np.percentile(bs, [2.5, 97.5]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["train", "validate", "test"])
    a = ap.parse_args()
    cfg = json.load(open(PREREG))
    df = load_tape()
    sp, allsess = split(df, cfg)
    keep = sp[a.stage]
    sessions = {s: g.sort_values("ts").reset_index(drop=True)
                for s, g in df[df.sess.isin(keep)].groupby("sess")}
    print(f"STAGE {a.stage.upper()}  ·  {len(sessions)} sessions  "
          f"({min(keep)} .. {max(keep)})  ·  {FEE_NOTE}\n")

    G = cfg["grid"]
    if a.stage == "train":
        cells = [(k, r, v) for k in G["K_confirmation_pt"]
                 for r in G["R_run_pt"] for v in G["V_volume_multiple"]]
    else:
        prev = cfg.get("results") or {}
        key = "nominated" if a.stage == "validate" else "survived_validate"
        cells = [tuple(c) for c in prev.get(key, [])]
        if not cells:
            print(f"nothing to run: no '{key}' recorded by the previous stage.")
            return 1

    out = []
    for (K, R, V) in cells:
        w, l, per = race(sessions, K, R, V)
        if w + l == 0:
            continue
        p = w / (w + l)
        out.append(dict(K=K, R=R, V=V, n=w+l, p=p, lo=ci(per)[0], hi=ci(per)[1]))
    O = pd.DataFrame(out).sort_values("p", ascending=False)

    nom = cfg["selection_rule"]
    if a.stage == "train":
        bar, minn = 0.520, 200
        sel = O[(O.p >= bar) & (O.n >= minn)]
        print(f"full grid: {len(O)} cells with data · "
              f"P(run|fire) median {O.p.median():.3f}, "
              f"range {O.p.min():.3f}-{O.p.max():.3f}")
        print(f"cells at or above the nomination bar ({bar} with n>={minn}): {len(sel)}")
        print(f"expected by chance at a nominal 5%: ~{0.05*len(O):.1f}\n")
    elif a.stage == "validate":
        sel = O[O.p >= 0.510]
        print(f"survived VALIDATE (>=0.510): {len(sel)} of {len(O)}\n")
    else:
        sel = O[(O.p > 0.500) & (O.lo > 0.500)]
        print(f"CONFIRMED on TEST (>0.500 with CI excluding 0.500): "
              f"{len(sel)} of {len(O)}\n")

    print(f"{'K':>4}{'R':>5}{'V':>6}{'n':>7}{'P(run|fire)':>13}{'95% CI':>20}")
    for _, r in O.head(25).iterrows():
        star = " *" if ((a.stage == "train" and r.p >= 0.520 and r.n >= 200)
                        or (a.stage == "validate" and r.p >= 0.510)
                        or (a.stage == "test" and r.p > 0.5 and r.lo > 0.5)) else ""
        cis = f"[{r.lo:.3f},{r.hi:.3f}]" if r.lo == r.lo else "—"
        print(f"{r.K:>4.0f}{r.R:>5.0f}{r.V:>6.1f}{r.n:>7.0f}{r.p:>13.3f}{cis:>20}{star}")
    if len(O) > 25:
        print(f"   … {len(O)-25} more cells (full grid written to the registration)")

    res = cfg.get("results") or {}
    res[f"{a.stage}_all"] = O.round(4).to_dict("records")
    key = {"train": "nominated", "validate": "survived_validate",
           "test": "confirmed"}[a.stage]
    res[key] = [[int(r.K), int(r.R), float(r.V)] for _, r in sel.iterrows()]
    res[f"{a.stage}_sessions"] = [str(min(keep)), str(max(keep)), len(sessions)]
    cfg["results"] = res
    cfg["status"] = f"{a.stage.upper()} complete — {len(sel)} cell(s) carried forward."
    json.dump(cfg, open(PREREG, "w"), indent=2)
    print(f"\nwritten to the registration: {key} = {len(sel)} cell(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
