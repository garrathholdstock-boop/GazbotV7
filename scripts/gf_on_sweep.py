#!/usr/bin/env python3
"""OPEN-NEWS greenfield — parameter sweep + the whole robustness battery, for all five candidates.

Signals are generated ONCE per candidate and reused across the whole exit grid, so the grid is a
sweep of EXIT SHAPE against a fixed entry — which is the only way to read a plateau honestly.

Battery (every candidate gets all of it, survivors and corpses alike):
  * exit/stop grid, reported WHOLE (plateau vs single-cell spike)
  * per-regime and per-time-of-day scoring on the best plateau config
  * PLACEBO — the same rules on a signal series shifted +/-10..45 min, and on a day-shuffle
  * strip-the-3-best trades
  * leave-one-day-out
  * long/short symmetry
  * OOS split (first half of the days fitted, second half untouched)
  * cost stress (2x slippage)
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_cands as C  # noqa: E402
import gf_on_engine as E  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"

EXITS = [
    ("tgt1.5R", dict(target_r=1.5)),
    ("tgt2R",   dict(target_r=2.0)),
    ("tgt3R",   dict(target_r=3.0)),
    ("tgt4R",   dict(target_r=4.0)),
    ("trail1/1",   dict(trail_arm_r=1.0, trail_r=1.0)),
    ("trail1.5/1", dict(trail_arm_r=1.5, trail_r=1.0)),
    ("trail2/1",   dict(trail_arm_r=2.0, trail_r=1.0)),
    ("trail2/1.5", dict(trail_arm_r=2.0, trail_r=1.5)),
    ("be1+trail2/1", dict(be_arm_r=1.0, trail_arm_r=2.0, trail_r=1.0)),
    ("time-only", dict()),
]


def gen_signals(days, siggen, sigkw=None, tick_days_only=True):
    """[(day, sod, dir, meta)] — computed once, reused by every cell of the grid."""
    sigkw = sigkw or {}
    out = []
    for d in sorted(days):
        dd = days[d]
        if tick_days_only and dd["ticks"] is None:
            continue
        for sod, direction, meta in siggen(dd, **sigkw):
            out.append((d, int(sod), int(direction), meta))
    return out


def exec_signals(days, sigs, *, stop_mode, stop_k, slip_ticks=1.0, time_stop=E.WIN_HI + 3600,
                 shift=0, day_map=None, **exitkw):
    trades = []
    for d, sod, direction, meta in sigs:
        dd_src = days[d]
        d_exec = day_map.get(d, d) if day_map else d
        dd = days[d_exec]
        if dd["ticks"] is None:
            continue
        s = sod + shift
        if not (E.WIN_LO <= s < E.WIN_HI):
            continue
        mkey = s // 60 * 60 - 60
        atr = dd["amap"].get(mkey, np.nan)
        if np.isnan(atr) or atr <= 0:
            continue
        if stop_mode == "range":
            stop_pt = stop_k * meta.get("rng", atr)
        else:
            stop_pt = stop_k * atr
        stop_pt = max(stop_pt, 4 * E.TICK)
        ex = {k: (None if v is None else v * stop_pt) for k, v in
              dict(target_pt=exitkw.get("target_r"), trail_arm=exitkw.get("trail_arm_r"),
                   trail_pt=exitkw.get("trail_r"), be_arm=exitkw.get("be_arm_r")).items()}
        t = E.simulate_fast(dd["ticks"], s, direction, stop_pt=stop_pt, time_stop_sod=time_stop,
                            slip_ticks=slip_ticks, **ex)
        if t is None:
            continue
        t.update(day=d_exec, regime=dd["rmap"].get(mkey, "unknown"), atr=float(atr),
                 er=float(dd["emap"].get(mkey, np.nan)), stop_pt=float(stop_pt), sig_sod=s,
                 src_day=d)
        _ = dd_src
        trades.append(t)
    return trades


def sweep(days, sigs, stop_mode, stop_ks, time_stops=(E.WIN_HI, E.WIN_HI + 3600)):
    grid = {}
    for sk in stop_ks:
        for ename, ekw in EXITS:
            for ts in time_stops:
                tr = exec_signals(days, sigs, stop_mode=stop_mode, stop_k=sk, time_stop=ts, **ekw)
                lbl = f"stop{sk}|{ename}|to{ts // 3600}:00"
                grid[lbl] = {"score": E.score(tr), "n": len(tr)}
    return grid


def plateau(grid, stop_ks, time_stops):
    """A config's neighbours are the same exit at the adjacent stop_k. An edge that survives its
    NEIGHBOURHOOD is a plateau; one that doesn't is a single-cell spike, i.e. a fit."""
    out = []
    for sk in stop_ks:
        for ename, _ in EXITS:
            for ts in time_stops:
                lbl = f"stop{sk}|{ename}|to{ts // 3600}:00"
                if lbl not in grid:
                    continue
                nb = []
                for sk2 in stop_ks:
                    if abs(stop_ks.index(sk2) - stop_ks.index(sk)) <= 1:
                        l2 = f"stop{sk2}|{ename}|to{ts // 3600}:00"
                        if l2 in grid and grid[l2]["score"]["per"] is not None:
                            nb.append(grid[l2]["score"]["per"])
                s = grid[lbl]["score"]
                out.append({"cfg": lbl, "n": s["n"], "net": s["net"], "per": s["per"],
                            "win": s["win"], "nbhd_per": round(float(np.mean(nb)), 2) if nb else None,
                            "nbhd_min": round(float(np.min(nb)), 2) if nb else None})
    return sorted(out, key=lambda r: -(r["net"] or 0))


def battery(days, sigs, stop_mode, stop_k, exitkw, time_stop, label):
    base = exec_signals(days, sigs, stop_mode=stop_mode, stop_k=stop_k, time_stop=time_stop, **exitkw)
    res = {"cfg": label, "headline": E.score(base),
           "by_regime": E.by(base, lambda t: t["regime"]),
           "by_tod": E.by(base, C.tod),
           "by_dir": E.by(base, lambda t: "LONG" if t["dir"] > 0 else "SHORT"),
           "by_day": E.by(base, lambda t: t["day"]),
           "by_reason": E.by(base, lambda t: t["reason"])}

    # ── placebo: same rules, signal series SHIFTED in time ────────────────────────────────
    pl = {}
    for sh in (-45, -30, -20, -10, 10, 20, 30, 45):
        tr = exec_signals(days, sigs, stop_mode=stop_mode, stop_k=stop_k, time_stop=time_stop,
                          shift=sh * 60, **exitkw)
        pl[f"{sh:+d}min"] = E.score(tr)
    res["placebo_shift"] = pl

    # ── placebo: day-SHUFFLE — day X's signal clock applied to a different day's tape ──────
    tdays = sorted({d for d, *_ in sigs})
    rng = np.random.default_rng(11)
    sh_scores = []
    for k in range(12):
        perm = list(tdays)
        rng.shuffle(perm)
        dm = {a: b for a, b in zip(tdays, perm) if a != b}
        tr = exec_signals(days, sigs, stop_mode=stop_mode, stop_k=stop_k, time_stop=time_stop,
                          day_map=dm, **exitkw)
        sh_scores.append(E.score(tr))
    nets = [s["net"] for s in sh_scores]
    res["placebo_dayshuffle"] = {
        "runs": len(nets), "median_net": round(float(np.median(nets)), 2),
        "mean_net": round(float(np.mean(nets)), 2),
        "p10": round(float(np.percentile(nets, 10)), 2),
        "p90": round(float(np.percentile(nets, 90)), 2),
        "real_net": res["headline"]["net"],
        "pct_shuffles_beating_real": round(100 * float(np.mean([n >= res["headline"]["net"] for n in nets])), 1)}

    # ── strip the 3 best ──────────────────────────────────────────────────────────────────
    srt = sorted(base, key=lambda t: -t["net"])
    for k in (1, 3, 5):
        res[f"strip_best_{k}"] = E.score(srt[k:])

    # ── leave-one-day-out ─────────────────────────────────────────────────────────────────
    loo = {}
    for d in sorted({t["day"] for t in base}):
        loo[d] = E.score([t for t in base if t["day"] != d])
    nets = [v["net"] for v in loo.values()]
    res["loo"] = {"days": len(loo), "min_net": min(nets) if nets else None,
                  "max_net": max(nets) if nets else None,
                  "n_negative": sum(1 for n in nets if n < 0), "detail": loo}

    # ── OOS split: first half of days / second half ───────────────────────────────────────
    ds = sorted({t["day"] for t in base})
    cut = len(ds) // 2
    res["oos"] = {"in_sample_days": ds[:cut], "oos_days": ds[cut:],
                  "in_sample": E.score([t for t in base if t["day"] in set(ds[:cut])]),
                  "oos": E.score([t for t in base if t["day"] in set(ds[cut:])])}

    # ── cost stress: double the slippage ──────────────────────────────────────────────────
    tr2 = exec_signals(days, sigs, stop_mode=stop_mode, stop_k=stop_k, time_stop=time_stop,
                       slip_ticks=2.0, **exitkw)
    res["cost_stress_2x_slip"] = E.score(tr2)
    tr0 = exec_signals(days, sigs, stop_mode=stop_mode, stop_k=stop_k, time_stop=time_stop,
                       slip_ticks=0.0, **exitkw)
    res["no_slip"] = E.score(tr0)
    res["trades"] = base
    return res


# ────────────────────────────────────────────────────────────────────────────────────────────
# the census runs we are hunting — big-moves-caught
# ────────────────────────────────────────────────────────────────────────────────────────────
CENSUS_SAT_OPEN_NEWS = [
    ("2026-08-10", "13:20", -74), ("2026-08-10", "13:56", +109), ("2026-08-10", "14:25", +46),
    ("2026-08-10", "14:45", -90), ("2026-08-11", "13:24", -137), ("2026-08-11", "13:51", +124),
    ("2026-08-11", "14:16", -49), ("2026-08-11", "14:40", +55), ("2026-08-11", "14:55", -89),
    ("2026-08-12", "13:08", +52), ("2026-08-13", "13:32", +236), ("2026-08-13", "14:20", +75),
    ("2026-08-13", "14:41", -45), ("2026-08-14", "13:22", -80), ("2026-08-14", "14:13", -98),
    ("2026-08-14", "14:48", -48),
]


def big_moves_caught(trades, runs=CENSUS_SAT_OPEN_NEWS, pre=300, post=900):
    hit = []
    for d, hm, mv in runs:
        h, m = hm.split(":")
        t0 = int(h) * 3600 + int(m) * 60
        want = 1 if mv > 0 else -1
        got = [t for t in trades if t["day"] == d and t["dir"] == want
               and t0 - pre <= t["entry_sod"] <= t0 + post]
        hit.append({"day": d, "time": hm, "move": mv, "caught": len(got) > 0,
                    "net": round(sum(x["net"] for x in got), 2) if got else 0.0})
    return {"caught": sum(1 for h in hit if h["caught"]), "of": len(hit),
            "net_on_them": round(sum(h["net"] for h in hit), 2), "detail": hit}


if __name__ == "__main__":
    days = E.load_days()
    E.attach_regimes(days)
    prs = sorted(x for x in (C.preopen_range(days[d]) for d in days if days[d]["ticks"] is not None)
                 if x is not None)
    sqz_cut = prs[len(prs) // 3]

    SPEC = {
        "ORX":    (C.sig_orx,    {},                     "range", [0.35, 0.5, 0.75, 1.0]),
        "VPOP":   (C.sig_vpop,   {},                     "atr",   [0.75, 1.0, 1.5, 2.0]),
        "SQZGO":  (C.sig_sqzgo,  dict(pct_cut=sqz_cut),  "range", [0.35, 0.5, 0.75, 1.0]),
        "FBURST": (C.sig_fburst, {},                     "atr",   [0.75, 1.0, 1.5, 2.0]),
        "VWRC":   (C.sig_vwrc,   {},                     "atr",   [0.75, 1.0, 1.5, 2.0]),
    }
    TS = (E.WIN_HI, E.WIN_HI + 3600)
    out = {}
    for name, (sg, skw, smode, sks) in SPEC.items():
        sigs = gen_signals(days, sg, skw)
        g = sweep(days, sigs, smode, sks, TS)
        pl = plateau(g, sks, TS)
        best = pl[0]
        # pick the best config by NEIGHBOURHOOD $/trade, not by the single best cell
        rob = sorted([r for r in pl if r["n"] >= 15 and r["nbhd_min"] is not None],
                     key=lambda r: -r["nbhd_min"])
        chosen = rob[0] if rob else best
        sk = float(chosen["cfg"].split("|")[0][4:])
        ename = chosen["cfg"].split("|")[1]
        ts = int(chosen["cfg"].split("|")[2][2:4].rstrip(":")) * 3600
        ekw = dict(next(v for n, v in EXITS if n == ename))
        b = battery(days, sigs, smode, sk, ekw, ts, chosen["cfg"])
        b["bmc"] = big_moves_caught(b["trades"])
        b["grid"] = pl
        b["n_signals"] = len(sigs)
        out[name] = b
        h = b["headline"]
        print(f"\n═══ {name}  signals={len(sigs)}  chosen={chosen['cfg']}")
        print(f"    blanket n={h['n']} net=${h['net']:+.0f} win={h['win']}% $/tr={h['per']}  "
              f"| best-cell {best['cfg']} ${best['net']:+.0f}")
        print(f"    placebo dayshuffle median ${b['placebo_dayshuffle']['median_net']:+.0f}  "
              f"({b['placebo_dayshuffle']['pct_shuffles_beating_real']}% of shuffles beat it)")
        print(f"    strip3 ${b['strip_best_3']['net']:+.0f}  LOO worst ${b['loo']['min_net']:+.0f}  "
              f"OOS ${b['oos']['oos']['net']:+.0f}  bmc {b['bmc']['caught']}/{b['bmc']['of']}")

    for v in out.values():
        v.pop("trades", None)
    json.dump(out, open(f"{SEC}/gf_on_sweep.json", "w"), indent=1, default=float)
    print(f"\n→ {SEC}/gf_on_sweep.json")
