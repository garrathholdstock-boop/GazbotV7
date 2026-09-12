"""GF6 — the battery, at TRADE level, on a named config. This is what decides a cell.

Five things, and a candidate has to survive all of them:
  CONSTANT   the same exit machinery entered at a FIXED time every session, same side. Gold fell
             this year; if the constant makes the same money the trigger is decorative.
  PLACEBO    the same NUMBER of entries on the SAME sessions at RANDOM minutes of the same session
             window, 200 draws. This controls for both the day mix and the firing rate, which a
             random-across-the-tape placebo does not.
  SPLIT-HALF the sign in the first half of the sessions and in the second, independently.
  BY-MONTH   how many months are the right sign.
  STRIP      the best 1 and 3 trades, and the best 1 and 3 sessions.
"""
from __future__ import annotations
import numpy as np, pandas as pd
import gf6_mgc_gate as G
from gf6_mgc_exitgrid import ENTRIES

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

def _walk(g, idx, side, stop_k, cap, target_r=None, arm_k=None, trail_k=None):
    o, h, l, c = g.open.values, g.high.values, g.low.values, g.close.values
    atr = g.atr60.values; n = len(g); out = []
    for i in idx:
        if i + 1 >= n or not np.isfinite(atr[i]) or atr[i] <= 0: continue
        e = i + 1; entry = o[e]
        xp, held, why = G._exit(o, h, l, c, e, n, side, entry, atr[i], stop_k,
                                target_r, arm_k, trail_k, cap)
        gross = side * (xp - entry) * G.VPP
        out.append(gross - G.FEE - 2 * G.SLIP * G.VPP)
    return out

def battery(d, key, *, stop_k, cap, target_r=None, arm_k=None, trail_k=None,
            cool=30, seed=5, draws=200, label=""):
    sess, trig, side = ENTRIES[key]
    t = G.backtest(d, sess, trig, side, stop_k=stop_k, target_r=target_r, arm_k=arm_k,
                   trail_k=trail_k, cap=cap, cool=cool)
    res = G.summarise(t, label or key)
    days = sorted(t.sday.unique()); mid = len(days) // 2
    res["h1"] = t[t.sday.isin(days[:mid])].pnl.mean()
    res["h2"] = t[t.sday.isin(days[mid:])].pnl.mean()
    mo = t.assign(mo=t.sday.str[:7]).groupby("mo").pnl.mean()
    res["mo_pos"], res["mo_n"] = int((mo > 0).sum()), len(mo)
    res["mo_worst"], res["mo_best"] = float(mo.min()), float(mo.max())

    # --- CONSTANT: one entry per session at a fixed minute of the home window -----------
    conts = {}
    for hhmm in ({"US": (13*60+35, 15*60, 17*60), "LONDON": (7*60+5, 9*60, 11*60),
                  "ASIA": (0*60+5, 2*60, 4*60)}[sess]):
        v = []
        for sday, g in d.groupby("sday"):
            g = g.reset_index(drop=True)
            k = g.index[g.hhmm == hhmm]
            if len(k): v += _walk(g, [int(k[0])], side, stop_k, cap, target_r, arm_k, trail_k)
        conts[f"{hhmm//60:02d}:{hhmm%60:02d}"] = (len(v), float(np.mean(v)))
    res["const"] = max(x[1] for x in conts.values())
    res["const_detail"] = conts

    # --- PLACEBO: same sessions, same count, random minutes in the same window ----------
    rng = np.random.default_rng(seed)
    cnt = t.groupby("sday").size().to_dict()
    pool = {sd: np.where((g.sess.values == sess) & np.isfinite(g.atr60.values))[0]
            for sd, g in ((sd, gg.reset_index(drop=True)) for sd, gg in d.groupby("sday"))}
    frames = {sd: gg.reset_index(drop=True) for sd, gg in d.groupby("sday")}
    means = []
    for _ in range(draws):
        v = []
        for sd, k in cnt.items():
            p = pool[sd]
            if len(p) == 0: continue
            v += _walk(frames[sd], rng.choice(p, min(k, len(p)), replace=False),
                       side, stop_k, cap, target_r, arm_k, trail_k)
        means.append(np.mean(v))
    means = np.array(means)
    res["placebo_mean"] = float(means.mean())
    res["placebo_pct"] = float((means < res["per"]).mean() * 100)
    return res, t, means

def show(res):
    r = res
    print(f"  n={r['n']}  sessions={r['days']}  net=${r['net']:,.0f}  ${r['per']:.2f}/trade  "
          f"median ${r['med']:.2f}  win {100*r['win']:.0f}%  median hold {r['held']:.0f}m")
    print(f"  CONSTANT (best fixed-time entry, same exit): ${r['const']:.2f}/trade   "
          f"-> the trigger adds ${r['per']-r['const']:.2f}")
    print(f"  PLACEBO  (same sessions, same count, random minutes, 200 draws): "
          f"mean ${r['placebo_mean']:.2f}, candidate sits at the {r['placebo_pct']:.1f}th percentile")
    print(f"  SPLIT-HALF  first ${r['h1']:.2f}  second ${r['h2']:.2f}      "
          f"MONTHS positive {r['mo_pos']}/{r['mo_n']} (worst ${r['mo_worst']:.0f}, best ${r['mo_best']:.0f})")
    print(f"  STRIP best 1 trade ${r['strip_best1']:.2f} · best 3 trades ${r['strip_best3']:.2f} · "
          f"best session ${r['strip_day1']:.2f} · best 3 sessions ${r['strip_day3']:.2f}")
    print(f"  worst single trade ${r['worst']:.0f}")

if __name__ == "__main__":
    d = G.frame()
    for cfg in [dict(key="revS_US_fadeup", stop_k=7.0, cap=480, label="revS_US_fadeup 7xATR/480m"),
                dict(key="revS_US_fadeup", stop_k=5.0, cap=240, label="revS_US_fadeup 5xATR/240m")]:
        lab = cfg.pop("label"); key = cfg.pop("key")
        res, t, _ = battery(d, key, label=lab, **cfg)
        print(f"\n===== {lab} =====")
        show(res)
        print("  constant by entry time:", res["const_detail"])
