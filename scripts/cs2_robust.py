"""CHOP-SCALP step 7 — the robustness battery on the finalists.

placebo (random direction) / label shuffle / strip-the-best-3 / leave-one-day-out /
IS-OOS split / trend-day bleed / the +$200-300-a-chop-day arithmetic.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import (OUT, VPP, FEE, SLIP_STOP_PT, load_events, IS_DAYS, OOS_DAYS, WEEK)
from cs2_sweep import sequential

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
rng = np.random.default_rng(20260825)

FINAL = {
    "CT13  L30 k4        (6/10)": (CHOP & (d.f_ext30 > 0) & (d.f_mv20 >= 4.0), 6.0, 10.0),
    "CT16  L30 k5        (8/10)": (CHOP & (d.f_ext30 > 0) & (d.f_mv20 >= 5.0), 8.0, 10.0),
    "CT15  L30 k4 REFILL (8/10)": (CHOP & (d.f_ext30 > 0) & (d.f_mv20 >= 4.0)
                                   & (d.f_refill >= d.f_refill[CHOP].median()), 8.0, 10.0),
}

def take(mask, tp, sp, days=None):
    sub = d[mask] if days is None else d[mask & d.date.isin(days)]
    if not len(sub):
        return None
    parts = [sequential(g.sort_values("dts"), tp, sp) for _, g in sub.groupby("date")]
    o = pd.concat(parts, ignore_index=True)
    return o if len(o) else None

def S(o, lab=""):
    if o is None or not len(o):
        return dict(label=lab, n=0, net=0.0, ptr=0.0, win=0.0, days=0)
    return dict(label=lab, n=len(o), net=round(float(o.usd.sum()), 2), ptr=round(float(o.usd.mean()), 3),
                win=round(float((o.usd > 0).mean()), 3), days=int(o.date.nunique()),
                open=int((o.kind == "OPEN").sum()))

out = {}
for name, (m, tp, sp) in FINAL.items():
    o = take(m, tp, sp)
    r = {"headline": S(o, name)}
    print(f"\n{'='*78}\n{name}   events={int(m.sum())}   exit tp={tp} sp={sp}")
    print("  headline:", r["headline"])

    # ---- IS / OOS
    r["IS"] = S(take(m, tp, sp, IS_DAYS), "IS 07-31..08-14")
    r["OOS"] = S(take(m, tp, sp, OOS_DAYS), "OOS 08-17..08-24")
    r["WEEK"] = S(take(m, tp, sp, WEEK), "report week")
    print("  IS  :", r["IS"]); print("  OOS :", r["OOS"]); print("  WEEK:", r["WEEK"])

    # ---- per day
    pd_ = o.groupby("date").usd.agg(["size", "sum"]).round(2)
    r["per_day"] = {k: [int(v["size"]), float(v["sum"])] for k, v in pd_.iterrows()}
    print("  per-day:", {k: v[1] for k, v in r["per_day"].items()})

    # ---- strip the best N
    s = o.usd.sort_values(ascending=False).values
    r["strip"] = {f"strip{k}": [round(float(s[k:].sum()), 2), round(float(s[k:].mean()), 3)]
                  for k in (0, 1, 2, 3, 5)}
    print("  strip-the-best:", r["strip"])

    # ---- leave one day out
    loo = {}
    for day in sorted(o.date.unique()):
        rest = o[o.date != day]
        loo[day] = [len(rest), round(float(rest.usd.sum()), 2), round(float(rest.usd.mean()), 3)]
    r["loo"] = loo
    ptrs = [v[2] for v in loo.values()]
    r["loo_range"] = [round(min(ptrs), 3), round(max(ptrs), 3), int(sum(p > 0 for p in ptrs)), len(ptrs)]
    print(f"  leave-one-day-out $/tr: min={min(ptrs):.3f} max={max(ptrs):.3f} positive {sum(p>0 for p in ptrs)}/{len(ptrs)}")

    # ---- PLACEBO: same events, same exits, RANDOM direction. 400 draws.
    sub = d[m].copy()
    pl = []
    for it in range(400):
        flip = rng.random(len(sub)) < 0.5
        s2 = sub.copy()
        s2["side"] = np.where(flip, np.where(s2.side == "SHORT", "LONG", "SHORT"), s2.side)
        # recompute the race for flipped rows: a flipped row's target/stop swap roles, which the
        # event table cannot answer — so the placebo uses the SYMMETRIC-cell identity only where
        # tp==sp. For tp!=sp we mark the flipped rows unresolvable and drop the draw.
        pl.append(np.nan)
    # placebo done properly below with the symmetric cell
    tpc = sp if tp != sp else tp
    o_sym = take(m, sp, sp)
    if o_sym is not None:
        base_sym = float(o_sym.usd.mean())
        draws = []
        for it in range(2000):
            flip = rng.random(len(o_sym)) < 0.5
            # under a flip a TARGET becomes a STOP and vice versa (symmetric cell, first-touch)
            k = o_sym.kind.values.copy()
            k2 = np.where(flip, np.where(k == "TARGET", "STOP", np.where(k == "STOP", "TARGET", k)), k)
            pts = np.where(k2 == "STOP", -(sp + SLIP_STOP_PT), np.where(k2 == "TARGET", sp,
                           np.where(flip, -o_sym[f"r_{sp}_{sp}"], o_sym[f"r_{sp}_{sp}"])))
            draws.append(float((pts * VPP - FEE).mean()))
        draws = np.array(draws)
        r["placebo"] = {"cell": f"{sp}/{sp}", "real_ptr": round(base_sym, 3),
                        "placebo_mean": round(float(draws.mean()), 3),
                        "placebo_sd": round(float(draws.std()), 3),
                        "pct_placebo_beating_real": round(float((draws >= base_sym).mean()), 4)}
        print("  placebo:", r["placebo"])
    out[name] = r

# ---------------- trend-day bleed
print(f"\n{'='*78}\nTREND-DAY BLEED — the same rule armed on NON-chop tape")
days = pd.read_csv(f"{OUT}/regime_days.csv")
trend_days = set(days[days.daytype == "TREND"].date)
bleed = {}
for name, (m, tp, sp) in FINAL.items():
    m2 = (d.f_ext30 > 0) & (d.f_mv20 >= (5.0 if "k5" in name else 4.0))
    if "REFILL" in name:
        m2 = m2 & (d.f_refill >= d.f_refill[CHOP].median())
    non = take(m2 & ~CHOP, tp, sp)
    onday = take(m2, tp, sp, sorted(trend_days))
    bleed[name] = {"non_chop_tape": S(non, "non-chop blocks"), "on_trend_days": S(onday, "trend days")}
    print(f"  {name}: non-chop {S(non)} | trend-days {S(onday)}")
out["_bleed"] = bleed

# ---------------- the +$200-300 arithmetic
blocks = pd.read_csv(f"{OUT}/regime_blocks.csv")
chop_blocks = blocks[blocks.regime.isin(("CHOP", "DEAD_CHOP"))]
out["_arith"] = {
    "chop_block_median_range_pt": round(float(chop_blocks.rng.median()), 2),
    "chop_blocks_per_day": round(float(len(chop_blocks) / blocks.date.nunique()), 1),
    "chop_day_total_range_pt": round(float(chop_blocks.rng.median() * len(chop_blocks) / blocks.date.nunique()), 1),
}
print("\nCHOP-BLOCK ARITHMETIC:", out["_arith"])
json.dump(out, open(f"{OUT}/robust.json", "w"), indent=1, default=str)
