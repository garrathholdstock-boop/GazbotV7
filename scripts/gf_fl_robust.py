#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 4: the robustness battery. This is what kills things here, not win%.

Run as:  gf_fl_robust.py NAME z stop_k targ_k hold [segment_key=value ...]

The battery, and what each test is for:
  PLACEBO / SHUFFLE   the same machinery fired at FAKE moments (the signal series slid 20-240 min,
                      200 draws) and with SHUFFLED directions. If the fake books most of the money,
                      the flow signal is not the edge — the exit and the tape are.
  STRIP-3-BEST        does the whole result live in three trades?
  LEAVE-ONE-DAY-OUT   does it live in one session?
  OOS LEG             chronological halves, plus the natural V5-era (07-05..07-17) vs V7-era
                      (07-24..08-14) split — two different volatility eras, a real held-out leg.
  LONG/SHORT SYMMETRY a mechanism that only works one way on a two-sided signal is a regime bet.
  COST STRESS         $1.50 -> $2.50 round trip, 1 -> 2 ticks of slippage.
  BIG-MOVES-CAUGHT    X/N against the runs the census proved we sat out.

Writes reports/friday_v7/sections/fl/robust_<NAME>.json
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("GF_FL_TICK_CACHE", "40")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from gf_fl_cands import BUILDERS, load_feat, run  # noqa: E402
from gf_fl_engine import FEE, VPP, score, simulate  # noqa: E402
from gf_fl_label import detect_runs  # noqa: E402
import gf_fl_sweep  # noqa: E402,F401  (registers FBIG in BUILDERS)

DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"
V7_ERA_FROM = "2026-07-24"


def seg_filter(trades, filters):
    out = trades
    for k, v in filters.items():
        out = [t for t in out if str(t.get(k)) == v]
    return out


def per_day(trades):
    d = {}
    for t in trades:
        d.setdefault(t["day"], []).append(t["net"])
    return {k: (len(v), round(sum(v), 2)) for k, v in sorted(d.items())}


def main():
    name, z, sk, tk, hold = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
    filters = dict(a.split("=", 1) for a in sys.argv[6:])
    df = load_feat()
    sigs = BUILDERS[name](df, z=z)
    if filters:
        sigs = [s for s in sigs if all(str(s.get(k)) == v for k, v in filters.items())]
    trades, sc = run(name, sigs, stop_k=sk, targ_k=tk, hold=hold)
    suffix = "".join(f"_{k}{v}" for k, v in filters.items()).replace('-', 'm')
    res = {"config": {"name": name, "z": z, "stop_k": sk, "targ_k": tk, "hold": hold,
                      "filters": filters},
           "headline": sc, "per_day": per_day(trades)}
    print("headline:", sc)

    net = np.array([t["net"] for t in trades])
    days = sorted({t["day"] for t in trades})

    # ── strip-the-best ───────────────────────────────────────────────────────────────────────
    s = np.sort(net)
    res["strip"] = {"strip1": round(float(s[:-1].sum()), 2), "strip3": round(float(s[:-3].sum()), 2),
                    "strip5": round(float(s[:-5].sum()), 2),
                    "strip3_per_trade": round(float(s[:-3].mean()), 2) if len(s) > 3 else None,
                    "top3_share_of_net": round(100 * float(s[-3:].sum() / net.sum()), 1)
                    if net.sum() else None}

    # ── leave-one-day-out ────────────────────────────────────────────────────────────────────
    loo = {}
    for d in days:
        keep = net[[i for i, t in enumerate(trades) if t["day"] != d]]
        loo[d] = {"n": int(len(keep)), "net": round(float(keep.sum()), 2),
                  "per_trade": round(float(keep.mean()), 2) if len(keep) else None}
    res["leave_one_day_out"] = loo
    pts = [v["per_trade"] for v in loo.values() if v["per_trade"] is not None]
    res["loo_summary"] = {"worst_per_trade": round(min(pts), 2), "best_per_trade": round(max(pts), 2),
                          "days_where_still_positive": sum(1 for p in pts if p > 0), "days": len(pts)}

    # ── OOS legs ─────────────────────────────────────────────────────────────────────────────
    half = days[len(days) // 2]
    res["oos"] = {
        "first_half": score([t for t in trades if t["day"] < half], "first_half"),
        "second_half": score([t for t in trades if t["day"] >= half], "second_half"),
        "v5_era_0705_0717": score([t for t in trades if t["day"] < V7_ERA_FROM], "v5_era"),
        "v7_era_0724_0814": score([t for t in trades if t["day"] >= V7_ERA_FROM], "v7_era"),
        "split_day": half,
    }

    # ── long / short symmetry ────────────────────────────────────────────────────────────────
    res["symmetry"] = {"long": score([t for t in trades if t["dir"] > 0], "long"),
                       "short": score([t for t in trades if t["dir"] < 0], "short")}

    # ── cost stress ──────────────────────────────────────────────────────────────────────────
    res["cost_stress"] = {
        "as_traded_fee_1.50_slip_1tick": round(float(net.sum()), 2),
        "fee_2.50": round(float(net.sum() - 1.00 * len(net)), 2),
        "slip_2_ticks": round(float(net.sum() - 1.00 * len(net)), 2),
        "both": round(float(net.sum() - 2.00 * len(net)), 2),
        "note": "one extra tick of slippage on entry+exit is $1.00 a trade at $2.00/pt; the fee "
                "stress adds another $1.00. A gate whose whole edge is under $2/trade dies here.",
    }

    # ── PLACEBO: the same machinery at fake moments ──────────────────────────────────────────
    rng = np.random.default_rng(20260815)
    by_ts = {int(r): i for i, r in enumerate(df["ts"].to_numpy("int64"))}
    ts_arr = df["ts"].to_numpy("int64")
    fake_nets, fake_pt = [], []
    for _ in range(200):
        shift = int(rng.choice([-1, 1]) * rng.integers(20, 240)) * 60
        fs = []
        for s0 in sigs:
            j = by_ts.get(s0["ts"] + shift)
            if j is None:
                continue
            r = df.iloc[j]
            if not np.isfinite(r["atr15"]):
                continue
            fs.append({"ts": int(r["ts"]), "day": r["day"], "dir": s0["dir"],
                       "atr": float(r["atr15"]), "regime": r["regime"], "session": r["session"],
                       "er": float(r["er15"]), "fz": float(s0["fz"]), "ext": 0.0})
        if len(fs) < 10:
            continue
        _, fsc = run(name + "_placebo", fs, stop_k=sk, targ_k=tk, hold=hold)
        fake_nets.append(fsc["net"])
        fake_pt.append(fsc["per_trade"])
    fake_nets = np.array(fake_nets, float)
    fake_pt = np.array([x for x in fake_pt if x is not None], float)
    res["placebo_time_shift"] = {
        "draws": int(len(fake_nets)),
        "real_net": round(float(net.sum()), 2), "real_per_trade": round(float(net.mean()), 2),
        "fake_net_mean": round(float(fake_nets.mean()), 2),
        "fake_net_median": round(float(np.median(fake_nets)), 2),
        "fake_per_trade_mean": round(float(fake_pt.mean()), 2),
        "fake_pct_positive": round(100 * float((fake_nets > 0).mean()), 1),
        "pctile_of_real": round(100 * float((fake_nets < net.sum()).mean()), 1),
        "p_value_one_sided": round(float((fake_nets >= net.sum()).mean()), 4),
    }

    # ── PLACEBO 2: shuffled directions, real moments ─────────────────────────────────────────
    sh_nets = []
    for _ in range(100):
        perm = rng.permutation(len(sigs))
        fs = [dict(s0, dir=int(sigs[perm[i]]["dir"])) for i, s0 in enumerate(sigs)]
        _, ssc = run(name + "_shuffle", fs, stop_k=sk, targ_k=tk, hold=hold)
        sh_nets.append(ssc["net"])
    sh = np.array(sh_nets, float)
    res["placebo_direction_shuffle"] = {
        "draws": int(len(sh)), "fake_net_mean": round(float(sh.mean()), 2),
        "fake_net_median": round(float(np.median(sh)), 2),
        "pctile_of_real": round(100 * float((sh < net.sum()).mean()), 1),
        "p_value_one_sided": round(float((sh >= net.sum()).mean()), 4)}

    # ── BIG-MOVES-CAUGHT ─────────────────────────────────────────────────────────────────────
    runs, _, thr, _ = detect_runs(df)
    tsr = df["ts"].to_numpy("int64")
    caught_all = caught25 = caught15 = 0
    big = sorted(runs, key=lambda r: -abs(r[1]))
    for rank, (i, mv) in enumerate(big):
        t0 = int(tsr[i])
        d = 1 if mv > 0 else -1
        hit = any(t["dir"] == d and t0 - 300 <= t["ts"] <= t0 + 900 for t in trades)
        caught_all += hit
        caught25 += hit and rank < 25
        caught15 += hit and rank < 15
    res["big_moves_caught"] = {"all_runs": f"{caught_all}/{len(runs)}",
                               "top25": f"{caught25}/25", "top15": f"{caught15}/15",
                               "run_threshold_pt": round(thr, 1)}

    json.dump(res, open(f"{DIR}/robust_{name}{suffix}.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items()
                      if k in ("headline", "strip", "loo_summary", "oos", "symmetry",
                               "cost_stress", "placebo_time_shift", "placebo_direction_shuffle",
                               "big_moves_caught")}, indent=1))
    print(f"→ {DIR}/robust_{name}{suffix}.json")


if __name__ == "__main__":
    main()
