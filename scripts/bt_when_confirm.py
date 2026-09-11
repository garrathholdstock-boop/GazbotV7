#!/usr/bin/env python3
"""Backtest of the operator's 2026-09-11 spec, exactly as given.

  WHEN trigger fires  ->  wait 10 minutes  ->  direction is whatever price DID
  ->  buy 2 lots  ->  lot 1 takes +$100, lot 2 takes +$200
  ->  cut the whole thing at -$200 total P&L  ->  flat at 20:40Z

Assumptions not in the spec, both from standing desk rules, both stated in the output:
  - flat at 20:40Z (never hold overnight)
  - $1.50 per contract per round turn

★ CAUSAL. Entry is the OPEN of the bar after the 10-minute confirmation, never a level
  that already passed. Same-bar ambiguity resolves AGAINST us: if a bar touches both the
  stop and a target, the STOP is taken first. A hopeful tie is how a backtest beats the
  desk in real life.
"""
from __future__ import annotations

import argparse, glob
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
VPP, FEE = 2.0, 1.50            # $/point/lot, $/contract/round-turn
LOTS = 2
TP1_USD, TP2_USD, CUT_USD = 100.0, 200.0, -200.0
WAIT = 10
FLAT_MOD = 20*60 + 40


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
    tr = np.maximum(df.high-df.low, np.maximum((df.high-df.close.shift()).abs(),
                                               (df.low-df.close.shift()).abs()))
    df["atr"] = tr.rolling(14).mean()
    return df


def simulate(g, i, side, cut_mode="total"):
    """One position from bar i+1's open. Returns (pnl_usd, reason, bars_held, mae_usd)."""
    h, l, c, o, mod = (g.high.values, g.low.values, g.close.values,
                       g.open.values, g["mod"].values)
    n = len(g)
    if i + 1 >= n:
        return None
    e = o[i+1]
    tp1 = e + side * (TP1_USD / VPP)            # +50 pt
    tp2 = e + side * (TP2_USD / VPP)            # +100 pt
    lots, realised, mae = LOTS, 0.0, 0.0
    for k in range(i+1, n):
        if mod[k] >= FLAT_MOD and mod[k] < 22*60:
            break
        adverse = (e - l[k]) if side > 0 else (h[k] - e)
        mae = max(mae, adverse * VPP * lots)
        # ── THE CUT, CHECKED FIRST. A bar that touches both takes the loss. ──
        # "total"    = -$200 on realised + unrealised (the literal reading). Once lot 1 banks
        #              +$100 the runner may fall $300 before this bites - that is the leak.
        # "position"  = -$200 of OPEN loss regardless of what has been banked, so the runner
        #              keeps a real stop after the first target.
        open_loss = side * ((l[k] - e) if side > 0 else (e - h[k])) * VPP * lots
        worst = (realised + open_loss) if cut_mode == "total" else open_loss
        if worst <= CUT_USD:
            realised = (realised + open_loss if cut_mode == "position" else CUT_USD) - FEE*lots
            return realised, "CUT", k - i, mae
        if lots == 2:
            hit1 = (h[k] >= tp1) if side > 0 else (l[k] <= tp1)
            if hit1:
                realised += TP1_USD - FEE
                lots = 1
        if lots >= 1:
            hit2 = (h[k] >= tp2) if side > 0 else (l[k] <= tp2)
            if hit2 and lots == 1:
                realised += TP2_USD - FEE
                lots = 0
                return realised, "TP2", k - i, mae
        if lots == 0:
            return realised, "TP2", k - i, mae
    # ran to the flat
    last = c[min(k, n-1)]
    realised += side * (last - e) * VPP * lots - FEE * lots
    return realised, "FLAT", k - i, mae


def run(df, vmin, atrmin, label, cut_mode="total"):
    recs = []
    for s, g in df.groupby("sess"):
        g = g.sort_values("ts").reset_index(drop=True)
        v, a, c, mod = g.vol_rel.values, g.atr.values, g.close.values, g["mod"].values
        n = len(g)
        i = 60
        while i < n - WAIT - 30:
            if mod[i] >= FLAT_MOD and mod[i] < 22*60:
                break
            if not (v[i] == v[i] and v[i] >= vmin and a[i] == a[i] and a[i] >= atrmin):
                i += 1
                continue
            j = i + WAIT
            if j + 1 >= n:
                break
            side = 1 if c[j] > c[i] else (-1 if c[j] < c[i] else 0)
            if side == 0:
                i += 30
                continue
            r = simulate(g, j, side, cut_mode)
            if r is None:
                break
            pnl, why, held, mae = r
            recs.append(dict(sess=s, side=side, pnl=pnl, why=why, held=held, mae=mae))
            i = j + held + 30
    R = pd.DataFrame(recs)
    if len(R) < 20:
        print(f"  {label:<28} too few trades"); return R
    t = R.pnl.mean()/(R.pnl.std(ddof=1)/np.sqrt(len(R)))
    eq = R.pnl.cumsum(); dd = (eq - eq.cummax()).min()
    print(f"  {label:<28} n={len(R):>5} ${R.pnl.mean():>7.2f}/tr  total ${R.pnl.sum():>9.0f}  "
          f"win {100*(R.pnl>0).mean():>3.0f}%  t={t:>5.2f}  maxDD ${dd:>8.0f}")
    return R


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()
    df = tape()
    print(f"MNQ 1-min · {df.sess.nunique()} CME sessions · {LOTS} lots · "
          f"TP ${TP1_USD:.0f}/${TP2_USD:.0f} · cut ${-CUT_USD:.0f} · wait {WAIT}m")
    print(f"assumptions: flat 20:40Z · ${FEE:.2f}/contract/RT · entry = next bar open · "
          f"ties resolve AGAINST\n")
    atrq = df.atr.quantile([.5, .67]).values
    best = None
    for cm in ("total", "position"):
        print(f"\n=== CUT MODE: {cm} "
              f"({'-$200 on realised+unrealised' if cm=='total' else '-$200 of OPEN loss, banked profit ignored'}) ===")
        for vmin in (2.0, 2.5, 3.0):
            R = run(df, vmin, 0, f"vol>={vmin}x, any ATR", cm)
            if len(R) >= 20 and (best is None or R.pnl.mean() > best[1].pnl.mean()):
                best = (f"vol>={vmin}x any ATR, cut={cm}", R)
    if best is None:
        return 1
    lbl, R = best
    print(f"\n── BEST CELL: {lbl} ──")
    print("  exit reason breakdown:")
    for why, gg in R.groupby("why"):
        print(f"     {why:<6} n={len(gg):>5} ({100*len(gg)/len(R):>3.0f}%)  "
              f"${gg.pnl.mean():>8.2f}/tr  total ${gg.pnl.sum():>9.0f}")
    k = len(R)//3
    print(f"\n  stability (chronological thirds): "
          f"${R.iloc[:k].pnl.mean():+.2f} / ${R.iloc[k:2*k].pnl.mean():+.2f} / "
          f"${R.iloc[2*k:].pnl.mean():+.2f} per trade")
    print(f"  median hold {R.held.median():.0f} min · median MAE ${R.mae.median():.0f} · "
          f"p90 MAE ${R.mae.quantile(.9):.0f}")
    print(f"  trades/session {len(R)/df.sess.nunique():.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
