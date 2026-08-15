#!/usr/bin/env python3
"""OPEN-NEWS greenfield — THE ESCALATION, and the size-threshold question.

Three things, all on the FULL parquet lake, all inside 13:00-15:00Z:

  1. THE FOOTPRINT-vs-SIZE TEST. For every in-window run, and for a matched population of in-window
     NON-run windows, measure what the 10 minutes BEFORE looked like. Then ask whether the
     separation sharpens as we raise the size bar (all runs -> top 25 -> top 15 -> top 8). This is
     the escalation the scope demands, done as a MEASUREMENT rather than as five more backtests.

  2. WHY BIG-MOVES-CAUGHT IS LOW. Walk the census's 16 sat-out OPEN/NEWS runs one at a time and say,
     for each, whether the candidate fired, and if not, which clause refused it.

  3. THE OOS LEG for POPSAR — the 15 days that have bars but no ticks, bar-executed with the stop
     winning every tie.
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_cands as C  # noqa: E402
import gf_on_engine as E  # noqa: E402
import gf_on_popgo as P  # noqa: E402
import gf_on_popsar as SAR  # noqa: E402
import gf_on_sweep as S  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
W15 = 15   # 15 one-minute bars


def in_window_runs(days, min_move=None):
    """15-min close-to-close moves inside 13:00-15:00Z, on MINUTE bars, deduped keep-strongest."""
    runs = []
    for d in sorted(days):
        rf = days[d]["rf"]
        s, c = rf["sod"].values, rf["c"].values
        cands = []
        for i in range(len(s) - W15):
            if not (E.WIN_LO <= s[i] < E.WIN_HI):
                continue
            if s[i + W15] - s[i] != W15 * 60:
                continue
            mv = c[i + W15] - c[i]
            cands.append((abs(mv), i, mv))
        cands.sort(reverse=True)
        used = []
        for _, i, mv in cands:
            if any(abs(i - j) < W15 for j in used):
                continue
            used.append(i)
            runs.append({"day": d, "i": i, "sod": int(s[i]), "move": float(mv)})
    typ = float(np.median([abs(r["move"]) for r in runs]))
    thr = min_move if min_move is not None else 1.5 * typ
    return [r for r in runs if abs(r["move"]) >= thr], thr


def precursor(days, d, i):
    """What the 10 minutes BEFORE looked like — strictly backward-looking."""
    rf = days[d]["rf"]
    h, l, c, v = rf["h"].values, rf["l"].values, rf["c"].values, rf["v"].values
    atr = rf["atr"].values
    er = rf["er"].values
    if i < 30 or np.isnan(atr[i - 1]) or atr[i - 1] <= 0:
        return None
    pre = slice(i - 10, i)
    trs = (h[pre] - l[pre]) / atr[i - 1]
    vol = v[pre].sum()
    volbase = v[max(0, i - 70):i - 10].mean() * 10 if i > 70 else np.nan
    rngc = (h[pre].max() - l[pre].min()) / atr[i - 1]
    return {"tr_max": float(trs.max()), "tr_mean": float(trs.mean()),
            "rng10_atr": float(rngc),
            "vol_ratio": float(vol / volbase) if volbase and volbase > 0 else np.nan,
            "er": float(er[i - 1]) if not np.isnan(er[i - 1]) else np.nan,
            "atr": float(atr[i - 1]),
            "drift10_atr": float((c[i - 1] - c[i - 10]) / atr[i - 1]),
            "absdrift10_atr": float(abs(c[i - 1] - c[i - 10]) / atr[i - 1])}


def auc(pos, neg):
    """Probability a random run scores above a random non-run. 0.50 = the feature knows nothing."""
    pos = [x for x in pos if x is not None and not np.isnan(x)]
    neg = [x for x in neg if x is not None and not np.isnan(x)]
    if len(pos) < 5 or len(neg) < 5:
        return None
    a = np.array(pos)[:, None] > np.array(neg)[None, :]
    t = np.array(pos)[:, None] == np.array(neg)[None, :]
    return round(float((a.sum() + 0.5 * t.sum()) / (len(pos) * len(neg))), 3)


def main():
    days = E.load_days()
    E.attach_regimes(days)
    res = {}

    # ── 1. the footprint-vs-size test ─────────────────────────────────────────────────────
    runs, thr = in_window_runs(days)
    runs.sort(key=lambda r: -abs(r["move"]))
    print(f"in-window runs on the full lake: {len(runs)}  (threshold {thr:.0f}pt, 15-min close-to-close)")

    runset = {(r["day"], r["i"]) for r in runs}
    controls = []
    for d in sorted(days):
        rf = days[d]["rf"]
        s = rf["sod"].values
        for i in range(len(s) - W15):
            if not (E.WIN_LO <= s[i] < E.WIN_HI) or (d, i) in runset:
                continue
            if any(abs(i - j) < W15 for dd_, j in runset if dd_ == d):
                continue
            controls.append({"day": d, "i": i})
    print(f"matched in-window NON-run control windows: {len(controls)}")

    ctrl_f = [precursor(days, c["day"], c["i"]) for c in controls]
    ctrl_f = [f for f in ctrl_f if f]
    FEATS = ["tr_max", "tr_mean", "rng10_atr", "vol_ratio", "er", "absdrift10_atr"]

    levels = [("ALL runs", len(runs)), ("top 25", 25), ("top 15", 15), ("top 8", 8)]
    esc = {}
    for name, k in levels:
        sub = runs[:k]
        f = [precursor(days, r["day"], r["i"]) for r in sub]
        f = [x for x in f if x]
        row = {"n_runs": len(f), "min_move": round(min(abs(r["move"]) for r in sub), 1)}
        for feat in FEATS:
            row[feat] = {"run_median": round(float(np.nanmedian([x[feat] for x in f])), 3),
                         "ctrl_median": round(float(np.nanmedian([x[feat] for x in ctrl_f])), 3),
                         "auc": auc([x[feat] for x in f], [x[feat] for x in ctrl_f])}
        esc[name] = row
    res["escalation"] = esc
    print("\n── PRE-RUN FOOTPRINT vs RUN SIZE (AUC: 0.50 = the 10 min before a run look like any "
          "other 10 min) ──")
    print(f"{'level':<10}{'n':>4}{'min_mv':>8}" + "".join(f"{f:>14}" for f in FEATS))
    for name, row in esc.items():
        print(f"{name:<10}{row['n_runs']:>4}{row['min_move']:>8.0f}"
              + "".join(f"{str(row[f]['auc']):>14}" for f in FEATS))

    # ── 2. the census's 16 sat-out OPEN/NEWS runs, one at a time ──────────────────────────
    K, CF, MT = 2.0, 0.70, 3
    sigs_all = S.gen_signals(days, P.sig_popgo, dict(k=K, close_frac=CF, max_trades=99))
    sigs = S.gen_signals(days, P.sig_popgo, dict(k=K, close_frac=CF, max_trades=MT))
    sar_tr = SAR.run(days, sigs, stop_k=1.0, max_rev=1)
    walk = []
    for d, hm, mv in S.CENSUS_SAT_OPEN_NEWS:
        h, m = hm.split(":")
        t0 = int(h) * 3600 + int(m) * 60
        near_all = [x for x in sigs_all if x[0] == d and t0 - 300 <= x[1] <= t0 + 900]
        near_cap = [x for x in sigs if x[0] == d and t0 - 300 <= x[1] <= t0 + 900]
        tr = [t for t in sar_tr if t["day"] == d and t0 - 300 <= t["entry_sod"] <= t0 + 900]
        if tr:
            why = "FIRED" + ("" if tr[0]["dir"] == (1 if mv > 0 else -1)
                             else " — but the FIRST leg took the wrong side")
        elif t0 < 13 * 3600 + 1800:
            why = "REFUSED — run starts before 13:30Z, outside POPGO's window"
        elif not near_all:
            why = "no trigger — no 1-min bar in the run's first 15 min cleared 2xATR closing on its extreme"
        elif not near_cap:
            why = f"trigger existed but the 3-trades-a-day cap had already been spent ({len(near_all)} raw)"
        else:
            why = "FIRED"
        walk.append({"day": d, "time": hm, "move": mv, "fired": bool(tr),
                     "net": round(sum(t["net"] for t in tr), 2),
                     "dir_ok": bool(tr and tr[0]["dir"] == (1 if mv > 0 else -1)),
                     "why": why})
    res["census_walk"] = walk
    print("\n── THE 16 SAT-OUT OPEN/NEWS RUNS, ONE AT A TIME (POPSAR) ──")
    print(f"{'run':<18}{'move':>6}{'fired':>7}{'net':>9}   why")
    for w in walk:
        print(f"{w['day'][5:]} {w['time']:<12}{w['move']:>+6.0f}{('YES' if w['fired'] else 'no'):>7}"
              f"{w['net']:>+9.0f}   {w['why']}")
    caught = sum(1 for w in walk if w["fired"])
    print(f"   caught {caught}/16   net on them ${sum(w['net'] for w in walk):+.0f}")

    # cap lifted — does the mission target improve, and at what cost?
    for mt in (3, 5, 8, 99):
        sg = S.gen_signals(days, P.sig_popgo, dict(k=K, close_frac=CF, max_trades=mt))
        tr = SAR.run(days, sg, stop_k=1.0, max_rev=1)
        bmc = S.big_moves_caught([{"day": t["day"], "dir": t["dir"], "entry_sod": t["entry_sod"],
                                   "net": t["net"]} for t in tr])
        sc = E.score(tr)
        res.setdefault("cap_sweep", {})[f"max_trades={mt}"] = {
            "score": sc, "bmc": f"{bmc['caught']}/{bmc['of']}", "bmc_net": bmc["net_on_them"]}
        print(f"   max_trades={mt:<3} n={sc['n']:>3} net=${sc['net']:+7.0f} $/tr={sc['per']:>+7.2f} "
              f"big-moves-caught {bmc['caught']}/16 (${bmc['net_on_them']:+.0f})")

    # ── 3. OOS leg for POPSAR on the untouched bar-only days ──────────────────────────────
    bar_only = sorted(d for d in days if days[d]["ticks"] is None and len(days[d]["bars5"]) > 5000)

    def sar_bars(dd, sod, direction, stop_pt, time_stop, max_rev=1):
        legs, dd_ = [], direction
        t0 = sod
        for _ in range(max_rev + 1):
            t = P.simulate_bars(dd, t0, dd_, stop_pt=stop_pt, time_stop_sod=time_stop)
            if t is None:
                break
            legs.append(t)
            if t["reason"] != "STOP" or t["exit_sod"] >= time_stop - 5:
                break
            dd_ = -dd_
            t0 = t["exit_sod"]
        return None if not legs else {"net": sum(x["net"] for x in legs), "legs": len(legs),
                                      "pts": sum(x["pts"] for x in legs),
                                      "entry_sod": legs[0]["entry_sod"], "dir": legs[0]["dir"]}

    oos = []
    for d in bar_only:
        dd = days[d]
        for sod, direction, meta in P.sig_popgo(dd, k=K, close_frac=CF, max_trades=MT):
            mkey = sod // 60 * 60 - 60
            atr = dd["amap"].get(mkey, np.nan)
            if np.isnan(atr) or atr <= 0:
                continue
            t = sar_bars(dd, sod, direction, max(1.0 * atr, 4 * E.TICK), E.WIN_HI)
            if t:
                t["day"] = d
                oos.append(t)
    res["oos_bars"] = {"days": len(bar_only), "day_list": bar_only, "score": E.score(oos),
                       "by_day": E.by(oos, lambda t: t["day"])}
    sc = res["oos_bars"]["score"]
    print(f"\n── POPSAR OOS: {len(bar_only)} days with bars but NO ticks, bar-executed, stop wins "
          f"every tie ──\n   n={sc['n']} net=${sc['net']:+.0f} win={sc['win']}% $/tr={sc['per']:+.2f}")
    print("   " + ", ".join(f"{d[5:]}:{v['net']:+.0f}" for d, v in res["oos_bars"]["by_day"].items()))

    json.dump(res, open(f"{SEC}/gf_on_escalate.json", "w"), indent=1, default=float)
    print(f"\n→ {SEC}/gf_on_escalate.json")


if __name__ == "__main__":
    main()
