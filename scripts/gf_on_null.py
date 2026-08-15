#!/usr/bin/env python3
"""OPEN-NEWS greenfield — THE NULL BATTERY. Run BEFORE believing any candidate.

The sweep handed back big numbers on a `time-only` exit, and the day-shuffle placebo was strongly
positive too. Both are the classic signature of an edge that lives in the TAPE, not the SIGNAL. So:

  DRIFT-LONG / DRIFT-SHORT   same entry clock, direction FORCED — measures the window's own drift
  COINFLIP                   same entry clock, direction drawn at random, 200 draws
  RANDOM-CLOCK               random entry times in-window, direction drawn at random

If a coin flip on the same clock books most of the money, the candidate's DIRECTION call is worth
nothing and the number belongs to the exit + the drift.
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import gf_on_cands as C  # noqa: E402
import gf_on_engine as E  # noqa: E402
import gf_on_sweep as S  # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"


def force_dir(sigs, d):
    return [(a, b, d, m) for a, b, _, m in sigs]


def rand_dir(sigs, rng):
    return [(a, b, int(rng.choice([-1, 1])), m) for a, b, _, m in sigs]


def rand_clock(days, sigs, rng):
    tdays = sorted({d for d, *_ in sigs})
    per = {}
    for d, *_ in sigs:
        per[d] = per.get(d, 0) + 1
    out = []
    for d in tdays:
        for _ in range(per[d]):
            out.append((d, int(rng.integers(E.WIN_LO, E.WIN_HI)), int(rng.choice([-1, 1])),
                        {"rng": 40.0}))
    return out


def main():
    days = E.load_days()
    E.attach_regimes(days)
    prs = sorted(x for x in (C.preopen_range(days[d]) for d in days if days[d]["ticks"] is not None)
                 if x is not None)
    sqz = prs[len(prs) // 3]

    SPEC = {
        "ORX":    (C.sig_orx,    {},                 "range", 1.0,  "trail1.5/1", E.WIN_HI),
        "VPOP":   (C.sig_vpop,   {},                 "atr",   1.0,  "time-only",  E.WIN_HI),
        "SQZGO":  (C.sig_sqzgo,  dict(pct_cut=sqz),  "range", 0.5,  "time-only",  E.WIN_HI + 3600),
        "FBURST": (C.sig_fburst, {},                 "atr",   2.0,  "tgt3R",      E.WIN_HI),
        "VWRC":   (C.sig_vwrc,   {},                 "atr",   2.0,  "time-only",  E.WIN_HI + 3600),
    }
    rng = np.random.default_rng(23)
    out = {}
    for name, (sg, skw, smode, sk, ename, ts) in SPEC.items():
        ekw = dict(next(v for n, v in S.EXITS if n == ename))
        sigs = S.gen_signals(days, sg, skw)

        def go(ss, slip=1.0):
            return E.score(S.exec_signals(days, ss, stop_mode=smode, stop_k=sk, time_stop=ts,
                                          slip_ticks=slip, **ekw))

        real = go(sigs)
        dl, ds = go(force_dir(sigs, +1)), go(force_dir(sigs, -1))
        cf = [go(rand_dir(sigs, rng)) for _ in range(60)]
        rc = [go(rand_clock(days, sigs, rng)) for _ in range(60)]
        cfn = [s["net"] for s in cf]
        rcn = [s["net"] for s in rc]
        out[name] = {
            "cfg": f"stop{sk}|{ename}|to{ts // 3600}:00",
            "real": real,
            "drift_long": dl, "drift_short": ds,
            "coinflip": {"draws": len(cfn), "median": round(float(np.median(cfn)), 2),
                         "mean": round(float(np.mean(cfn)), 2),
                         "p90": round(float(np.percentile(cfn, 90)), 2),
                         "pct_beating_real": round(100 * float(np.mean([x >= real["net"] for x in cfn])), 1)},
            "random_clock": {"draws": len(rcn), "median": round(float(np.median(rcn)), 2),
                             "mean": round(float(np.mean(rcn)), 2),
                             "p90": round(float(np.percentile(rcn, 90)), 2),
                             "pct_beating_real": round(100 * float(np.mean([x >= real["net"] for x in rcn])), 1)},
        }
        o = out[name]
        print(f"\n═══ {name}  {o['cfg']}")
        print(f"   REAL          n={real['n']:>4}  net=${real['net']:+9.0f}  $/tr={real['per']}")
        print(f"   drift LONG    n={dl['n']:>4}  net=${dl['net']:+9.0f}  $/tr={dl['per']}")
        print(f"   drift SHORT   n={ds['n']:>4}  net=${ds['net']:+9.0f}  $/tr={ds['per']}")
        print(f"   COINFLIP      median ${o['coinflip']['median']:+9.0f}  p90 ${o['coinflip']['p90']:+.0f}"
              f"  — {o['coinflip']['pct_beating_real']}% of flips beat the real signal")
        print(f"   RANDOM CLOCK  median ${o['random_clock']['median']:+9.0f}  p90 ${o['random_clock']['p90']:+.0f}"
              f"  — {o['random_clock']['pct_beating_real']}% beat the real signal")

    json.dump(out, open(f"{SEC}/gf_on_null.json", "w"), indent=1, default=float)
    print(f"\n→ {SEC}/gf_on_null.json")


if __name__ == "__main__":
    main()
