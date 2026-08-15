#!/usr/bin/env python3
"""OPEN-NEWS greenfield — VSURGE, the candidate the ESCALATION pointed at.

The escalation measured which pre-run features actually separate a run from an ordinary 10 minutes
in the same window, and how that separation behaves as the runs get bigger:

    feature          all 78 runs   top 25   top 15   top 8
    pre-run VOLUME       0.703      0.769    0.848    0.883      <- monotone, and strong
    pre-run ER           0.560      0.603    0.675    0.721      <- monotone
    pre-run price RANGE  0.536      0.568    0.490    0.522      <- knows nothing, at any size

POPGO/POPSAR trigger on the price RANGE column — the one that is flat at 0.5. That is exactly why
POPSAR earns well but catches only 2 of the census's 16 sat-out runs: it is a good trade that is not
the trade we were sent to find. VSURGE triggers on the VOLUME column instead.

  VSURGE  trigger:  at or after 13:00Z, the last 10 minutes' VOLUME >= v x the per-minute mean of the
                    previous 60 minutes, and the 30-min ER >= er_min
          direction: the sign of the last 10 minutes' drift
          entry:    first tick after the triggering minute closes
          stop:     stop_k x ATR14
          exit:     flat 15:00Z
          costs:    $1.50 round trip ($3.00 if run stop-and-reverse)
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_engine as E  # noqa: E402
import gf_on_popsar as SAR  # noqa: E402
import gf_on_sweep as S  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"


def sig_vsurge(dd, *, v=1.8, er_min=0.0, max_trades=3, lo=13 * 3600, hi=E.WIN_HI, cool=600):
    rf = dd["rf"]
    s = rf["sod"].values
    c, vol = rf["c"].values, rf["v"].values.astype(float)
    atr, er = rf["atr"].values, rf["er"].values
    out = []
    last = -10 ** 9
    for i in range(70, len(s)):
        t = int(s[i]) + 60                      # the bar CLOSES 60s after it starts
        if not (lo <= t < hi) or len(out) >= max_trades or t - last < cool:
            continue
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        base = vol[i - 70:i - 10].mean()
        if not base or base <= 0:
            continue
        ratio = vol[i - 9:i + 1].sum() / (10 * base)
        if ratio < v:
            continue
        e = er[i]
        if np.isnan(e) or e < er_min:
            continue
        drift = c[i] - c[i - 10]
        if drift == 0:
            continue
        out.append((t, 1 if drift > 0 else -1,
                    {"vol_ratio": float(ratio), "er": float(e), "drift": float(drift)}))
        last = t
    return out


def main():
    days = E.load_days()
    E.attach_regimes(days)
    res = {}

    # ── grid: how surged, how efficient, and outright vs stop-and-reverse ─────────────────
    grid = {}
    for v in (1.4, 1.6, 1.8, 2.2, 2.6):
        for erm in (0.0, 0.20, 0.30):
            sg = S.gen_signals(days, sig_vsurge, dict(v=v, er_min=erm, max_trades=3))
            out = E.score(S.exec_signals(days, sg, stop_mode="atr", stop_k=1.0,
                                         time_stop=E.WIN_HI))
            sar = E.score(SAR.run(days, sg, stop_k=1.0, max_rev=1))
            bmc = S.big_moves_caught([{"day": t["day"], "dir": t["dir"],
                                       "entry_sod": t["entry_sod"], "net": t["net"]}
                                      for t in SAR.run(days, sg, stop_k=1.0, max_rev=1)])
            grid[f"v{v}|er{erm}"] = {"outright": out, "sar": sar, "bmc": f"{bmc['caught']}/16"}
    res["grid"] = grid
    print("── VSURGE grid ──")
    print(f"{'cfg':<14}{'n':>4}{'outright $':>12}{'$/tr':>8}{'SAR $':>10}{'$/tr':>8}{'bmc':>7}")
    for lbl, g in grid.items():
        print(f"{lbl:<14}{g['outright']['n']:>4}{g['outright']['net']:>+12.0f}"
              f"{str(g['outright']['per']):>8}{g['sar']['net']:>+10.0f}{str(g['sar']['per']):>8}"
              f"{g['bmc']:>7}")

    V, ERM, SK = 1.8, 0.20, 1.0
    sigs = S.gen_signals(days, sig_vsurge, dict(v=V, er_min=ERM, max_trades=3))
    outright = S.exec_signals(days, sigs, stop_mode="atr", stop_k=SK, time_stop=E.WIN_HI)
    sar = SAR.run(days, sigs, stop_k=SK, max_rev=1)
    res["spec"] = {"v": V, "er_min": ERM, "stop_k": SK, "window": "13:00-15:00Z",
                   "exit": "flat 15:00Z", "cooldown_s": 600}

    for nm, tr in (("outright", outright), ("sar", sar)):
        blk = {"headline": E.score(tr), "by_regime": E.by(tr, lambda t: t["regime"]),
               "by_dir": E.by(tr, lambda t: "LONG" if t["dir"] > 0 else "SHORT"),
               "by_day": E.by(tr, lambda t: t["day"])}
        srt = sorted(tr, key=lambda t: -t["net"])
        for kk in (1, 3, 5):
            blk[f"strip_{kk}"] = E.score(srt[kk:])
        loo = {d: E.score([t for t in tr if t["day"] != d]) for d in sorted({t["day"] for t in tr})}
        blk["loo"] = {"days": len(loo), "min_net": min(v["net"] for v in loo.values()),
                      "n_negative": sum(1 for v in loo.values() if v["net"] < 0)}
        ds = sorted({t["day"] for t in tr})
        cut = len(ds) // 2
        blk["half_split"] = {"first": E.score([t for t in tr if t["day"] in set(ds[:cut])]),
                             "second": E.score([t for t in tr if t["day"] in set(ds[cut:])])}
        blk["bmc"] = S.big_moves_caught([{"day": t["day"], "dir": t["dir"],
                                          "entry_sod": t["entry_sod"], "net": t["net"]} for t in tr])
        res[nm] = blk
        h = blk["headline"]
        print(f"\n═══ VSURGE {nm}  v={V} er>={ERM} stop={SK}xATR flat 15:00Z")
        print(f"    n={h['n']} net=${h['net']:+.0f} win={h['win']}% $/tr={h['per']:+.2f}")
        print(E.table(blk["by_regime"], "regime"))
        print(f"    strip-1 ${blk['strip_1']['net']:+.0f}  strip-3 ${blk['strip_3']['net']:+.0f}  "
              f"strip-5 ${blk['strip_5']['net']:+.0f}")
        print(f"    LOO worst ${blk['loo']['min_net']:+.0f} ({blk['loo']['n_negative']}/{blk['loo']['days']} neg)"
              f"   halves ${blk['half_split']['first']['net']:+.0f}/${blk['half_split']['second']['net']:+.0f}"
              f"   bmc {blk['bmc']['caught']}/16")

    # ── nulls ─────────────────────────────────────────────────────────────────────────────
    import gf_on_null as N
    rng = np.random.default_rng(131)
    real = res["sar"]["headline"]["net"]
    cf = [E.score(SAR.run(days, N.rand_dir(sigs, rng), stop_k=SK, max_rev=1))["net"] for _ in range(200)]
    per = {}
    for d, *_ in sigs:
        per[d] = per.get(d, 0) + 1
    rc = []
    for _ in range(200):
        rs = [(d, int(rng.integers(E.WIN_LO, E.WIN_HI)), int(rng.choice([-1, 1])), {})
              for d in per for _ in range(per[d])]
        rc.append(E.score(SAR.run(days, rs, stop_k=SK, max_rev=1))["net"])
    res["nulls"] = {
        "coinflip": {"median": round(float(np.median(cf)), 2),
                     "p90": round(float(np.percentile(cf, 90)), 2),
                     "pct_beating_real": round(100 * float(np.mean([x >= real for x in cf])), 1)},
        "random_clock": {"median": round(float(np.median(rc)), 2),
                         "p90": round(float(np.percentile(rc, 90)), 2),
                         "pct_beating_real": round(100 * float(np.mean([x >= real for x in rc])), 1)},
        "real": real}
    n = res["nulls"]
    print(f"\n    NULLS (on the SAR form)  real ${real:+.0f}")
    print(f"      coinflip median ${n['coinflip']['median']:+.0f} — {n['coinflip']['pct_beating_real']}% beat it")
    print(f"      random-clock median ${n['random_clock']['median']:+.0f} — "
          f"{n['random_clock']['pct_beating_real']}% beat it")

    json.dump(res, open(f"{SEC}/gf_on_vsurge.json", "w"), indent=1, default=float)
    print(f"\n→ {SEC}/gf_on_vsurge.json")


if __name__ == "__main__":
    main()
