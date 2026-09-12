"""GF6 — the LIVE gold shadow book, 2026-08-18 .. 2026-09-04.

This is the only gold number on the desk that nobody had to model: `gazbot7-shadow-mgc.service` has
been up since 18 Aug and every trade is tick-repriced by `repricer.reprice()` against real bid/ask.

The comparison last week said would decide the thesis was: do the two BOOK-FILTERED hole arms beat
the unfiltered control? At n=7 a side it could not be answered. It can now.

⚠ THE CONTROL IS TWO-SIDED (side=""), the hole arms are one-sided. Comparing a LONG arm against a
bidirectional control mixes in the control's shorts, so the control is split by side before any
comparison is made.
"""
from __future__ import annotations
import sqlite3, datetime as dt
import numpy as np, pandas as pd

DB = "/home/alphabot/gazbot7/data/shadow_mgc.db"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

def load():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    df = pd.read_sql("""select t.id, t.strategy, t.side, t.entry_ts, t.exit_ts, t.entry_price,
                               t.exit_price, t.exit_reason, t.entry_atr, t.ceiling_pnl,
                               r.real_pnl, r.fill_status
                        from shadow_trades t join shadow_real r on r.trade_id=t.id
                        order by t.entry_ts""", c)
    df["day"] = pd.to_datetime(df.entry_ts, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    df["held_m"] = (df.exit_ts - df.entry_ts) / 60.0
    return df

def boot(df, n=2000, seed=3):
    rng = np.random.default_rng(seed)
    days = df.day.unique()
    grp = {d: g.real_pnl.values for d, g in df.groupby("day")}
    out = []
    for _ in range(n):
        pick = rng.choice(len(days), len(days), replace=True)
        v = np.concatenate([grp[days[i]] for i in pick])
        out.append(v.mean())
    return np.percentile(out, [5, 95])

def card(df, label):
    if df.empty: return None
    v = df.real_pnl
    o = df.groupby("day").real_pnl.sum().sort_values(ascending=False).index
    lo, hi = boot(df)
    return dict(arm=label, n=len(df), days=df.day.nunique(), net=v.sum(), per=v.mean(),
                med=float(v.median()), win=float((v > 0).mean()),
                best=float(v.max()), worst=float(v.min()), held=float(df.held_m.median()),
                strip_best3=float((v.sum() - v.nlargest(3).sum()) / (len(v) - 3)),
                strip_day3=float(df[~df.day.isin(o[:3])].real_pnl.mean()),
                lo=lo, hi=hi)

def main():
    df = load()
    pd.set_option("display.width", 250)
    print(f"live gold shadow: {df.day.min()} .. {df.day.max()}  "
          f"{df.day.nunique()} sessions, {len(df)} trades, all {df.fill_status.unique()}")
    rows = []
    for arm, g in df.groupby("strategy"):
        rows.append(card(g, arm))
    ctrl = df[df.strategy == "mgc_break_fade_nobook"]
    rows.append(card(ctrl[ctrl.side == "LONG"], "  control, LONG legs only"))
    rows.append(card(ctrl[ctrl.side == "SHORT"], "  control, SHORT legs only"))
    rows.append(card(df, "ALL THREE ARMS"))
    r = pd.DataFrame([x for x in rows if x])
    print("\n" + r.round(2).to_string(index=False))
    r.to_csv(f"{OUT}/live_shadow.csv", index=False)

    print("\n=== the decisive comparison, side for side ===")
    for side, arm in (("LONG", "mgc_holebreak_fade_long"), ("SHORT", "mgc_holebreak_fade_short")):
        a = df[df.strategy == arm]; b = ctrl[ctrl.side == side]
        print(f"  {side:5}  book-filtered ${a.real_pnl.mean():7.2f}/tr (n={len(a):3d})   vs   "
              f"unfiltered ${b.real_pnl.mean():7.2f}/tr (n={len(b):3d})   "
              f"->  the book gate adds ${a.real_pnl.mean()-b.real_pnl.mean():+7.2f}")

    print("\n=== week by week ($/trade) ===")
    df["wk"] = pd.to_datetime(df.day).dt.isocalendar().week
    p = df.pivot_table(index="wk", columns="strategy", values="real_pnl", aggfunc="mean")
    n = df.pivot_table(index="wk", columns="strategy", values="real_pnl", aggfunc="size")
    print(p.round(2).to_string()); print("\ntrade counts:"); print(n.to_string())

    print("\n=== exit reasons ===")
    print(df.pivot_table(index="strategy", columns="exit_reason", values="real_pnl",
                         aggfunc=["size", "sum"]).round(0).to_string())

    print("\n=== the sim's own mark vs the tick-repriced truth ===")
    d = df.assign(gap=df.ceiling_pnl - df.real_pnl)
    print(f"  mean |gap| ${d.gap.abs().mean():.2f}   median ${d.gap.abs().median():.2f}   "
          f"worst ${d.gap.abs().max():.2f}")
    print(f"  sim total ${df.ceiling_pnl.sum():,.0f}  vs repriced ${df.real_pnl.sum():,.0f}")

if __name__ == "__main__":
    main()
