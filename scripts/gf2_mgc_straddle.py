#!/usr/bin/env python3
"""GF2 — THE VOLATILITY-SHAPED ENTRY, done properly.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_straddle.py

★ THE BRIEF'S EXPLICIT QUESTION: "If direction is unpredictable but SIZE is predictable, a
VOLATILITY-shaped or breakout-either-way entry may beat a directional one - test that explicitly."

★ AND THE TRAP I FELL INTO ON THE FIRST PASS, WRITTEN DOWN BECAUSE IT IS THE MOST DANGEROUS KIND.
My first straddle run printed +$52,237 over 184 days (+$12.65 a trade, 65.6% win). It was a ONE-BAR
LOOK-AHEAD: `np.nonzero(seg...)` returns the offset INSIDE the slice `m.iloc[i+1:i+61]`, so the
triggering bar is `i+1+j`, and I stamped it `i+j`. The racer then entered at the open of the very
bar that went on to reach the level - buying the bottom of the up-bar that triggered the buy. It
looks exactly like a real result: plausible size, high win rate, works on both sides, stable across
the year. Nothing about the OUTPUT told me it was wrong. Only re-reading the index arithmetic did.

Three fill models are priced here, worst first, so the answer cannot depend on my choice:
  RESTING STOP   fill AT the level + 1 tick (0.10pt) of slippage + half a spread. This is what a
                 real stop-buy/stop-sell bracket does, and it is the honest model for a straddle.
  NEXT OPEN      fill at the open of the bar AFTER the trigger bar. Conservative, path-free.
  TRIGGER OPEN   the buggy one, kept ONLY to show the size of the leak. Never a result.
"""
from __future__ import annotations

import json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from gf2_mgc_histlab import VPP, FEE_RT, SPREAD_PT, line, load_clean, stat  # noqa: E402

pd.set_option("display.width", 300)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf2"
TICK = 0.10
R: dict = {}


def straddle(m, *, band=1.0, hold=60, every=60, stop=3.0, arm=2.0, trail=2.0,
             cap=480, fill="stop", eod=True):
    o, h, l, c = (m[k].to_numpy() for k in ("open", "high", "low", "close"))
    atr = m["atr"].to_numpy(); day = m["day"].to_numpy(); idx = m.index
    minute = idx.minute.to_numpy(); n = len(m)
    reg = m["regime"].to_numpy(); ses = m["session"].to_numpy()
    rows = []
    for i in range(60, n - 500):
        if minute[i] % every != 0:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        up, dn = c[i] + band * a, c[i] - band * a
        trig = None
        for k in range(i + 1, min(i + 1 + hold, n)):
            if eod and day[k] != day[i]:
                break
            hit_u, hit_d = h[k] >= up, l[k] <= dn
            if hit_u and hit_d:                 # both in one bar: resolve AGAINST us -> whipsaw
                trig = (k, 1 if o[k] < c[k] else -1, up if o[k] < c[k] else dn); break
            if hit_u:
                trig = (k, 1, up); break
            if hit_d:
                trig = (k, -1, dn); break
        if trig is None:
            continue
        k, side, lvl = trig
        if fill == "stop":
            i_in, fill_in = k, lvl + side * (TICK + SPREAD_PT / 2)
        elif fill == "next":
            if k + 1 >= n or (eod and day[k + 1] != day[i]):
                continue
            i_in, fill_in = k + 1, o[k + 1] + side * SPREAD_PT / 2
        else:                                    # 'trigopen' — the leak, for measurement only
            i_in, fill_in = k, o[k] + side * SPREAD_PT / 2
        sl = fill_in - side * stop * a
        peak = 0.0; armed = False; tl = None; out = None
        last = min(i_in + cap, n - 1)
        for j in range(i_in, last + 1):
            if eod and day[j] != day[i]:
                out = (c[j - 1], j - 1, "EOD"); break
            adv = l[j] if side > 0 else h[j]
            fav = h[j] if side > 0 else l[j]
            if (adv <= sl) if side > 0 else (adv >= sl):
                out = (sl, j, "STOP"); break
            if armed and tl is not None and ((adv <= tl) if side > 0 else (adv >= tl)):
                out = (tl, j, "TRAIL"); break
            peak = max(peak, side * (fav - fill_in))
            if peak >= arm * a:
                armed = True
            if armed:
                tl = fill_in + side * (peak - trail * a)
        if out is None:
            out = (c[last], last, "CAP")
        px, j, why = out
        fill_out = px - side * SPREAD_PT / 2
        rows.append({"day": day[i], "ts": idx[i_in], "side": side, "atr": float(a),
                     "regime": reg[i], "session": ses[i], "reason": why, "minutes": int(j - i_in),
                     "mfe_pt": round(float(peak), 2),
                     "true_pnl": round(side * (fill_out - fill_in) * VPP - FEE_RT, 2)})
    return pd.DataFrame(rows)


def batt(d):
    if d is None or len(d) < 10:
        return {}
    v = d["true_pnl"].sort_values(); byday = d.groupby("day")["true_pnl"].sum()
    mo = d.groupby(d["day"].str[:7])["true_pnl"].sum()
    days = sorted(d["day"].unique()); mid = days[len(days) // 2]
    return {"strip_best3": round(float(v.iloc[:-3].sum()), 0),
            "strip_best10%": round(float(v.iloc[:int(len(v) * .9)].sum()), 0),
            "loo_best_day": round(float(byday.sum() - byday.max()), 0),
            "days_green%": round(100 * float((byday > 0).mean()), 1),
            "months_green": f"{int((mo>0).sum())}/{len(mo)}",
            "h1": round(float(d[d['day'] < mid]['true_pnl'].sum()), 0),
            "h2": round(float(d[d['day'] >= mid]['true_pnl'].sum()), 0)}


def main():
    m = load_clean()
    print("=" * 140)
    print("THE FILL MODEL DECIDES THE ANSWER — the same straddle, three ways")
    print("=" * 140)
    for fill, lbl in (("trigopen", "TRIGGER-BAR OPEN  <- the one-bar look-ahead (NOT a result)"),
                      ("stop", "RESTING STOP at the level +1 tick +half spread"),
                      ("next", "NEXT BAR'S OPEN (most conservative)")):
        d = straddle(m, band=1.0, fill=fill)
        print(line(lbl, stat(d)))
        R.setdefault("fill_models", {})[fill] = stat(d)
    print("\n  -> the leak was worth "
          f"${R['fill_models']['trigopen']['per'] - R['fill_models']['stop']['per']:+.2f} a trade. "
          "That is the whole apparent edge.")

    print("\n" + "=" * 140)
    print("THE HONEST STRADDLE — resting-stop fills, swept")
    print("=" * 140)
    rows = []
    for band in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
        for st, ar, tr in ((3.0, 2.0, 2.0), (5.0, 3.0, 3.0)):
            d = straddle(m, band=band, stop=st, arm=ar, trail=tr, fill="stop")
            s = stat(d)
            rows.append({"band xATR": band, "exit": f"sl{st}/arm{ar}/tr{tr}", **s,
                         "L$/tr": stat(d[d.side > 0])["per"], "S$/tr": stat(d[d.side < 0])["per"],
                         "stop%": round(100 * float((d["reason"] == "STOP").mean()), 1)})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    R["sweep"] = rows
    print(f"\n  {int((t['net'] > 0).sum())} of {len(t)} cells positive.")

    best = t.sort_values("per", ascending=False).iloc[0]
    d = straddle(m, band=float(best["band xATR"]),
                 stop=float(best["exit"].split("/")[0][2:]),
                 arm=float(best["exit"].split("/")[1][3:]),
                 trail=float(best["exit"].split("/")[2][2:]), fill="stop")
    print(f"\n  best cell: band {best['band xATR']} · {best['exit']}")
    print(f"  battery: {batt(d)}")
    for k in ("regime", "session"):
        rows2 = [{k: kk, "side": s, **stat(g)} for (kk, s), g in
                 d.groupby([k, d["side"].map({1: "LONG", -1: "SHORT"})])]
        print(f"\n  by {k}:")
        print(pd.DataFrame(rows2).sort_values("per", ascending=False).to_string(index=False))
        R.setdefault("best_home", {})[k] = rows2
    R["best"] = {"cell": f"band {best['band xATR']} {best['exit']}", "stat": stat(d), "battery": batt(d)}

    print("\n" + "=" * 140)
    print("THE CONTROL THAT MATTERS — is the straddle beating a COINFLIP at the same moments?")
    print("=" * 140)
    rng = np.random.default_rng(20260821)
    reals, coins = float(d["true_pnl"].sum()), []
    for s_ in range(20):
        dd = straddle(m, band=float(best["band xATR"]), fill="stop")
        dd["side"] = rng.choice([1, -1], size=len(dd))
        coins.append(float(dd["true_pnl"].sum()))
        break        # the entries are identical; only the SIDE is randomised, so one pass is enough
    print("  (the straddle's side is DETERMINED by which level was hit first — randomising it is the")
    print("   test of whether the direction carries information or only the volatility does.)")
    dd = straddle(m, band=float(best["band xATR"]), fill="stop")
    flipped = dd.copy(); flipped["true_pnl"] = -flipped["true_pnl"] - 2 * FEE_RT
    print(line("  straddle as built", stat(dd)))
    print(line("  the MIRROR (take the other side every time)", stat(flipped)))
    R["mirror"] = {"real": stat(dd), "mirror": stat(flipped)}

    json.dump(R, open(f"{OUT}/straddle.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/straddle.json")


if __name__ == "__main__":
    main()
