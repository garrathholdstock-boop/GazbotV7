#!/usr/bin/env python3
"""GF2 — THE 60-MINUTE LEVEL BREAK, put in front of a YEAR of gold.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_trigger.py

The 08-15 section built its whole gold 2x2 on one price trigger (close beyond the 60-minute extreme)
and then let the BOOK decide whether to fade it or follow it. The book part cannot be tested before
2026-07-16 - there is no depth. The PRICE part can, and this is the first time it has been.

Four questions, in order, and each one can kill the trigger:
  Q1  Over 184 days, is a gold level break a TRAP (fade wins) or a SIGNAL (follow wins)?
  Q2  Is that answer stable, or is it a 2026 artefact? Split by quarter and by half.
  Q3  Which REGIME is its home (Rule 4 - the router will bench it everywhere else)?
  Q4  Is the threshold a PLATEAU or a spike (look-back x margin, the curve-fit tell)?

Then the honest controls: the same trades at random minutes, and the best CONSTANT on the same rows.

Costs modelled at 0.30pt/leg + $1.50/RT = $7.50 all-in, stressed at 0.15 and 0.50.
"""
from __future__ import annotations

import json
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from gf2_mgc_histlab import (BarRacer, VPP, breaks, line, load_clean, run, stat)  # noqa: E402

pd.set_option("display.width", 300)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf2"
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
R: dict = {}


def sides(d):
    return {"LONG": stat(d[d["side"] > 0]), "SHORT": stat(d[d["side"] < 0])}


def battery(d, col="true_pnl") -> dict:
    if d is None or len(d) < 10:
        return {}
    v = d[col].sort_values()
    byday = d.groupby("day")[col].sum()
    days = sorted(d["day"].unique()); mid = days[len(days) // 2]
    mo = d.groupby(d["day"].str[:7])[col].sum()
    return {"strip_best3": round(float(v.iloc[:-3].sum()), 0),
            "strip_best10pct": round(float(v.iloc[:int(len(v) * 0.9)].sum()), 0),
            "loo_best_day": round(float(byday.sum() - byday.max()), 0),
            "days_green%": round(100.0 * float((byday > 0).mean()), 1),
            "months_green": f"{int((mo > 0).sum())}/{len(mo)}",
            "h1": [int((d['day'] < mid).sum()), round(float(d[d['day'] < mid][col].sum()), 0)],
            "h2": [int((d['day'] >= mid).sum()), round(float(d[d['day'] >= mid][col].sum()), 0)]}


def main():
    m = load_clean()
    racer = BarRacer(m)
    print("=" * 140)
    print("Q1 — IS A GOLD LEVEL BREAK A TRAP OR A SIGNAL?   184 days, 2025-07-28 .. 2026-07-29")
    print("=" * 140)
    ef = breaks(m, fade=True)
    ec = ef.copy(); ec["side"] = -ec["side"]
    print(f"breaks: {len(ef)}  ({len(ef)/m['day'].nunique():.1f}/day, 45-min cooldown per side)")
    rf = run(racer, ef, **CHAND)
    rc = run(racer, ec, **CHAND)
    print("\n  chandelier stop3/arm2/trail2, 480m cap, flat at the day boundary:")
    print(line("FADE the break  (reversion)", stat(rf)))
    print(line("  LONG  (fade a DOWN break)", sides(rf)["LONG"]))
    print(line("  SHORT (fade an UP break)", sides(rf)["SHORT"]))
    print(line("FOLLOW the break (momentum)", stat(rc)))
    print(line("  LONG  (follow an UP break)", sides(rc)["LONG"]))
    print(line("  SHORT (follow a DOWN break)", sides(rc)["SHORT"]))
    R["q1"] = {"fade": stat(rf), "fade_sides": sides(rf), "follow": stat(rc), "follow_sides": sides(rc),
               "n_breaks": len(ef), "days": int(m["day"].nunique())}

    print("\n  cost stress (spread per leg):")
    for sp in (0.15, 0.30, 0.50):
        r2 = run(BarRacer(m, spread_pt=sp), ef, **CHAND)
        r3 = run(BarRacer(m, spread_pt=sp), ec, **CHAND)
        print(f"    {sp:.2f}pt/leg  (${2*sp*VPP+1.5:.2f}/RT)   fade {stat(r2)['per']:+7.2f}/tr "
              f"net ${stat(r2)['net']:>8,.0f}    follow {stat(r3)['per']:+7.2f}/tr net ${stat(r3)['net']:>8,.0f}")
        R.setdefault("cost_stress", {})[str(sp)] = {"fade": stat(r2), "follow": stat(r3)}

    print("\n" + "=" * 140)
    print("Q2 — IS IT STABLE, OR A 2026 ARTEFACT?")
    print("=" * 140)
    for nm, r in (("FADE", rf), ("FOLLOW", rc)):
        r = r.copy(); r["q"] = r["day"].str[:4] + "Q" + ((r["day"].str[5:7].astype(int) - 1) // 3 + 1).astype(str)
        g = r.groupby("q")["true_pnl"].agg(n="size", net="sum", per="mean",
                                           win=lambda x: 100 * (x > 0).mean()).round(2)
        print(f"\n  {nm} by quarter:"); print(g.to_string())
        mo = r.groupby(r["day"].str[:7])["true_pnl"].agg(n="size", net="sum", per="mean").round(2)
        print(f"  {nm} by month: " + " ".join(f"{k[2:]}:{v:+.0f}" for k, v in mo["net"].items()))
        R.setdefault("q2", {})[nm] = {"quarter": g.to_dict(), "month": mo["net"].round(0).to_dict(),
                                      "battery": battery(r)}
        print(f"  {nm} battery: {battery(r)}")

    print("\n" + "=" * 140)
    print("Q3 — THE HOME REGIME (Rule 4: score on home, report blanket as context)")
    print("=" * 140)
    for nm, r in (("FADE", rf), ("FOLLOW", rc)):
        print(f"\n  {nm} by regime x side:")
        rows = [{"regime": k, "side": s, **stat(g)}
                for (k, s), g in r.groupby(["regime", r["side"].map({1: "LONG", -1: "SHORT"})])]
        t = pd.DataFrame(rows).sort_values(["side", "per"], ascending=[True, False])
        print(t.to_string(index=False))
        print(f"\n  {nm} by session x side:")
        rows2 = [{"session": k, "side": s, **stat(g)}
                 for (k, s), g in r.groupby(["session", r["side"].map({1: "LONG", -1: "SHORT"})])]
        print(pd.DataFrame(rows2).sort_values(["side", "per"], ascending=[True, False]).to_string(index=False))
        R.setdefault("q3", {})[nm] = {"regime": rows, "session": rows2}

    print("\n" + "=" * 140)
    print("Q4 — PLATEAU OR SPIKE?  look-back x margin, FADE side, $/trade  (n in brackets)")
    print("=" * 140)
    grid = {}
    for look in (20, 30, 45, 60, 90, 120, 180):
        row = {}
        for marg in (0.0, 0.10, 0.25, 0.50, 1.0):
            e = breaks(m, look=look, margin_atr=marg, fade=True)
            r = run(racer, e, **CHAND)
            s = stat(r)
            row[marg] = f"{s['per']:+6.2f} ({s['n']})"
            grid.setdefault(str(look), {})[str(marg)] = s
        print(f"  look {look:>3}m : " + "   ".join(f"m{k}={v}" for k, v in row.items()))
    R["q4_plateau"] = grid

    print("\n" + "=" * 140)
    print("THE CONTROLS")
    print("=" * 140)
    rng = np.random.default_rng(20260821)
    idx_ok = np.nonzero(m["atr"].notna().to_numpy() & (m["atr"].to_numpy() > 0))[0]
    idx_ok = idx_ok[idx_ok < len(m) - 500]
    real = float(rf["true_pnl"].sum()); k = len(rf)
    nets = []
    for _ in range(30):
        pick = rng.choice(idx_ok, size=k, replace=False)
        e = pd.DataFrame({"i": pick, "side": rng.choice([1, -1], size=k),
                          "atr": m["atr"].to_numpy()[pick], "day": m["day"].to_numpy()[pick],
                          "regime": m["regime"].to_numpy()[pick], "session": m["session"].to_numpy()[pick],
                          "ts": m.index[pick]})
        nets.append(float(run(racer, e, **CHAND)["true_pnl"].sum()))
    beaten = sum(1 for x in nets if x >= real)
    print(f"  PLACEBO  same n={k}, random minutes, random side, identical exit, 30 draws:")
    print(f"    real ${real:,.0f}   placebo mean ${np.mean(nets):,.0f}  p90 ${np.percentile(nets,90):,.0f}  "
          f"beaten {beaten}/30")
    R["placebo"] = {"real": round(real, 0), "mean": round(float(np.mean(nets)), 0),
                    "p90": round(float(np.percentile(nets, 90)), 0), "beaten": beaten, "runs": 30}

    print("\n  THE BEST CONSTANT on the same rows (nothing may be shipped that loses to this):")
    for lbl, sd in (("always LONG at every break", 1), ("always SHORT at every break", -1)):
        e = ef.copy(); e["side"] = sd
        s = stat(run(racer, e, **CHAND))
        print(line(lbl, s))
        R.setdefault("constants", {})[lbl] = s

    json.dump(R, open(f"{OUT}/trigger.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/trigger.json")


if __name__ == "__main__":
    main()
