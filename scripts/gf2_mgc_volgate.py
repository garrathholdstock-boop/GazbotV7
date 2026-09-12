#!/usr/bin/env python3
"""GF2 — THE VOLATILITY GATE, interrogated. One position at a time, and every control I can build.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_volgate.py

★ WHAT SURVIVED THE LOOK-AHEAD FIX. With honest resting-stop fills, a breakout-EITHER-WAY entry at
a 0.25xATR band, exited on a wide 5xATR stop / 3xATR trail, made +$4.45 a trade over 4,135 firings
and 184 days. That is the only structure in this whole section that is positive at scale, so it gets
the hardest interrogation, not the softest.

★ THE FIRST OBJECTION, AND IT IS MINE, NOT A SKEPTIC'S: 4,135 trades over 184 days is 22 a day with
an 8-hour cap. Those positions OVERLAP - up to eight at once - so 4,135 is not 4,135 independent
bets and the n is a lie. Everything below runs ONE POSITION AT A TIME: a new straddle is armed only
when the book is flat. That is the number a desk could actually trade.

Controls, all of them:
  MIRROR        the same entries, side flipped, RE-RACED (not negated - a negated P&L keeps the
                winner's own trail and is not a mirror at all)
  RANDOM SIDE   the same entry moments, side chosen by coin, 30 draws
  PLACEBO       the same number of entries at random minutes, identical exit, 30 draws
  DRIFT-NEUTRAL the long and short halves averaged, so gold's 3,300 -> 4,400 year cannot be it
  CONSTANT      buy-and-hold gold over the same window, per lot
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


def _exit(o, h, l, c, day, i_in, side, fill_in, a, stop, arm, trail, cap, n):
    sl = fill_in - side * stop * a
    peak = 0.0; armed = False; tl = None
    last = min(i_in + cap, n - 1)
    for j in range(i_in, last + 1):
        if day[j] != day[i_in]:
            return c[j - 1], j - 1, "EOD", peak
        adv = l[j] if side > 0 else h[j]
        fav = h[j] if side > 0 else l[j]
        if (adv <= sl) if side > 0 else (adv >= sl):
            return sl, j, "STOP", peak
        if armed and tl is not None and ((adv <= tl) if side > 0 else (adv >= tl)):
            return tl, j, "TRAIL", peak
        peak = max(peak, side * (fav - fill_in))
        if peak >= arm * a:
            armed = True
        if armed:
            tl = fill_in + side * (peak - trail * a)
    return c[last], last, "CAP", peak


def volgate(m, *, band=0.25, hold=60, every=60, stop=5.0, arm=3.0, trail=3.0, cap=480,
            flip=False, force_side=None, one_at_a_time=True, rng=None, slip=TICK,
            spread=SPREAD_PT):
    """One straddle armed at the top of each hour; if `one_at_a_time`, only while the book is flat."""
    o, h, l, c = (m[k].to_numpy() for k in ("open", "high", "low", "close"))
    atr = m["atr"].to_numpy(); day = m["day"].to_numpy(); idx = m.index
    minute = idx.minute.to_numpy(); n = len(m)
    reg = m["regime"].to_numpy(); ses = m["session"].to_numpy()
    rows = []; busy_until = -1
    for i in range(60, n - 500):
        if minute[i] % every != 0 or (one_at_a_time and i < busy_until):
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        up, dn = c[i] + band * a, c[i] - band * a
        trig = None
        for k in range(i + 1, min(i + 1 + hold, n)):
            if day[k] != day[i]:
                break
            if h[k] >= up and l[k] <= dn:
                # BOTH legs filled inside one bar. A minute bar cannot say which came first, so
                # take the side that ENDS UP WORSE: if the bar closed up we were filled SHORT on
                # the way down and then run over. Resolving this by the bar's colour the OTHER way
                # is a look-ahead - it hands the straddle the winning leg for free.
                trig = (k, -1 if c[k] >= o[k] else 1); break
            if h[k] >= up:
                trig = (k, 1); break
            if l[k] <= dn:
                trig = (k, -1); break
        if trig is None:
            continue
        k, side = trig
        lvl = up if side > 0 else dn
        if flip:
            side = -side
        if force_side is not None:
            side = int(force_side[len(rows) % len(force_side)]) if hasattr(force_side, "__len__") else int(force_side)
        # GAP-HONEST FILL. A resting stop does not fill at its own level when the bar OPENS through
        # it - it fills at the open. Assuming the level would be a free gift on exactly the bars
        # that gapped, which are the ones that matter.
        gap = max(lvl, o[k]) if side > 0 else min(lvl, o[k])
        fill_in = gap + side * (slip + spread / 2)
        px, j, why, peak = _exit(o, h, l, c, day, k, side, fill_in, a, stop, arm, trail, cap, n)
        fill_out = px - side * (spread / 2 + slip)
        busy_until = j + 1
        rows.append({"day": day[i], "ts": idx[k], "i": k, "side": side, "atr": float(a),
                     "regime": reg[i], "session": ses[i], "reason": why, "minutes": int(j - k),
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
            "h1$": round(float(d[d['day'] < mid]['true_pnl'].sum()), 0),
            "h2$": round(float(d[d['day'] >= mid]['true_pnl'].sum()), 0)}


def main():
    m = load_clean(); n = len(m)
    print("=" * 140)
    print("STEP 1 — THE OVERLAP CORRECTION.  what happens when the book may hold only ONE position")
    print("=" * 140)
    d_many = volgate(m, one_at_a_time=False)
    d_one = volgate(m, one_at_a_time=True)
    print(line("all overlapping straddles (the inflated n)", stat(d_many)))
    print(line("ONE POSITION AT A TIME (the tradeable book)", stat(d_one)))
    print(f"  median hold {d_many['minutes'].median():.0f} min · "
          f"{len(d_many)/m['day'].nunique():.1f} trades/day overlapping vs "
          f"{len(d_one)/m['day'].nunique():.1f} sequential")
    R["overlap"] = {"overlapping": stat(d_many), "sequential": stat(d_one)}
    d = d_one
    print(f"\n  battery (sequential): {batt(d)}")
    R["battery"] = batt(d)

    print("\n" + "=" * 140)
    print("STEP 2 — THE CONTROLS")
    print("=" * 140)
    dm = volgate(m, one_at_a_time=True, flip=True)
    print(line("THE MIRROR — same moments, side flipped, RE-RACED", stat(dm)))
    R["mirror"] = stat(dm)

    rng = np.random.default_rng(20260821)
    coin = []
    for s_ in range(30):
        cs = rng.choice([1, -1], size=len(d) + 10)
        dc = volgate(m, one_at_a_time=True, force_side=cs)
        coin.append(float(dc["true_pnl"].sum()))
    real = float(d["true_pnl"].sum())
    print(f"  RANDOM SIDE at the same moments, 30 draws: real ${real:,.0f}  "
          f"coin mean ${np.mean(coin):,.0f}  p90 ${np.percentile(coin,90):,.0f}  "
          f"beaten {sum(1 for x in coin if x>=real)}/30")
    R["random_side"] = {"real": round(real, 0), "mean": round(float(np.mean(coin)), 0),
                        "p90": round(float(np.percentile(coin, 90)), 0),
                        "beaten": int(sum(1 for x in coin if x >= real))}

    # placebo: same count, random minutes, same exit
    o, h, l, c = (m[k].to_numpy() for k in ("open", "high", "low", "close"))
    atr = m["atr"].to_numpy(); day = m["day"].to_numpy()
    ok = np.nonzero(np.isfinite(atr) & (atr > 0))[0]; ok = ok[(ok > 60) & (ok < n - 500)]
    nets = []
    for _ in range(30):
        pick = rng.choice(ok, size=len(d), replace=False)
        sd = rng.choice([1, -1], size=len(d))
        tot = 0.0
        for ii, ss in zip(pick, sd):
            a = atr[ii]; fi = o[ii] + ss * SPREAD_PT / 2
            px, j, why, pk = _exit(o, h, l, c, day, ii, int(ss), fi, a, 5.0, 3.0, 3.0, 480, n)
            tot += ss * (px - ss * SPREAD_PT / 2 - fi) * VPP - FEE_RT
        nets.append(tot)
    print(f"  PLACEBO same n at random minutes, 30 draws: real ${real:,.0f}  "
          f"mean ${np.mean(nets):,.0f}  p90 ${np.percentile(nets,90):,.0f}  "
          f"beaten {sum(1 for x in nets if x>=real)}/30")
    R["placebo"] = {"real": round(real, 0), "mean": round(float(np.mean(nets)), 0),
                    "p90": round(float(np.percentile(nets, 90)), 0),
                    "beaten": int(sum(1 for x in nets if x >= real))}

    L, S = stat(d[d.side > 0]), stat(d[d.side < 0])
    print(f"  DRIFT-NEUTRAL: LONG {L['per']:+.2f}/tr (n={L['n']})  SHORT {S['per']:+.2f}/tr "
          f"(n={S['n']})  ->  mean of the two sides {(L['per']+S['per'])/2:+.2f}/tr")
    R["sides"] = {"LONG": L, "SHORT": S, "drift_neutral": round((L["per"] + S["per"]) / 2, 2)}
    bh = (m["close"].iloc[-1] - m["close"].iloc[0]) * VPP
    print(f"  BUY-AND-HOLD one MGC lot over the same 184 days: ${bh:,.0f} "
          f"(and it is exposed 24/5, not {100*d['minutes'].sum()/len(m):.0f}% of the time)")
    R["buy_hold"] = round(float(bh), 0)

    print("\n" + "=" * 140)
    print("STEP 3 — THE PARAMETER SURFACE (plateau or spike?)  sequential book, $/trade (n)")
    print("=" * 140)
    surf = {}
    for band in (0.10, 0.25, 0.50, 0.75):
        row = []
        for st, ar, tr in ((3.0, 2.0, 2.0), (5.0, 3.0, 3.0), (5.0, 2.0, 2.0), (8.0, 3.0, 3.0),
                           (8.0, 5.0, 5.0)):
            dd = volgate(m, band=band, stop=st, arm=ar, trail=tr, one_at_a_time=True)
            s = stat(dd)
            row.append(f"sl{st:g}/a{ar:g}/t{tr:g}={s['per']:+6.2f}({s['n']})")
            surf.setdefault(str(band), {})[f"{st}/{ar}/{tr}"] = s
        print(f"  band {band:.2f}xATR : " + "  ".join(row))
    R["surface"] = surf

    print("\n" + "=" * 140)
    print("STEP 4 — WHERE IT LIVES (Rule 4)")
    print("=" * 140)
    for k in ("regime", "session"):
        rows = [{k: kk, "side": s, **stat(g)} for (kk, s), g in
                d.groupby([k, d["side"].map({1: "LONG", -1: "SHORT"})])]
        print(f"\n  by {k} x side:")
        print(pd.DataFrame(rows).sort_values("per", ascending=False).to_string(index=False))
        R.setdefault("home", {})[k] = rows
    print("\n  by month:")
    mo = d.groupby(d["day"].str[:7])["true_pnl"].agg(n="size", net="sum", per="mean").round(1)
    print(mo.to_string())
    R["by_month"] = mo.to_dict()
    print("\n  by quarter:")
    d2 = d.copy(); d2["q"] = d2["day"].str[:4] + "Q" + ((d2["day"].str[5:7].astype(int) - 1) // 3 + 1).astype(str)
    print(d2.groupby("q")["true_pnl"].agg(n="size", net="sum", per="mean",
                                          win=lambda x: 100 * (x > 0).mean()).round(2).to_string())
    R["by_quarter"] = d2.groupby("q")["true_pnl"].agg(n="size", net="sum", per="mean").round(2).to_dict()
    print("\n  exit reasons:")
    print(d.groupby("reason")["true_pnl"].agg(n="size", net="sum", per="mean").round(2).to_string())
    R["reasons"] = d.groupby("reason")["true_pnl"].agg(n="size", net="sum", per="mean").round(2).to_dict()
    print("\n" + "=" * 140)
    print("STEP 5 — THE COST STRESS, and it is the test this gate lives or dies on")
    print("=" * 140)
    print("  gross edge before costs is thin relative to the churn, so the cost model is not a")
    print("  footnote here - it is the result. Swept over spread AND stop-entry slippage.")
    rows = []
    for sp in (0.20, 0.30, 0.40, 0.50):
        for sl_ in (0.10, 0.20, 0.30):
            dd = volgate(m, one_at_a_time=True, spread=sp, slip=sl_)
            s_ = stat(dd)
            rows.append({"spread/leg": sp, "entry slip": sl_,
                         "$/RT": round(2 * (sp / 2 + sl_) * VPP + FEE_RT, 2), **s_})
    tt = pd.DataFrame(rows)
    print(tt.to_string(index=False))
    R["cost_stress"] = rows
    print(f"\n  {int((tt['net'] > 0).sum())} of {len(tt)} cost cells stay positive.")
    print(f"  break-even all-in cost: the gate books ${stat(d)['net']:,.0f} on {stat(d)['n']} trades at "
          f"${2*(SPREAD_PT/2+TICK)*VPP+FEE_RT:.2f}/RT, so it dies at "
          f"${2*(SPREAD_PT/2+TICK)*VPP+FEE_RT + stat(d)['per']:.2f}/RT.")
    R["breakeven_cost_rt"] = round(2 * (SPREAD_PT / 2 + TICK) * VPP + FEE_RT + stat(d)["per"], 2)

    d.assign(ts=d["ts"].astype(str)).to_json(f"{OUT}/volgate_trades.json", orient="records")
    json.dump(R, open(f"{OUT}/volgate.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/volgate.json")


if __name__ == "__main__":
    main()
