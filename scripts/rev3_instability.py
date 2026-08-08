#!/usr/bin/env python3
"""REV-3b — THE HAZARD: how unstable is a PARTIALLY FORMED minute, and what does it cost?

Exposing ``MinuteBars._cur`` makes every feature partially formed.  Two distinct effects, measured
separately because they pull in opposite directions:

  1. ATR UNDERSTATEMENT.  A half-formed bar's high-low is smaller than the finished bar's, so an
     ATR-14 computed WITH it is biased LOW.  Every feature the desk uses is ATR-NORMALISED
     (net_atr_5, ext_atr, vwap_slope_atr), so a low ATR INFLATES all of them and the gate can fire
     on arithmetic rather than on tape.  Measured as ATR(partial)/ATR(closed) by elapsed second.
  2. TRIGGER FLICKER.  Even with ATR held on completed bars (the NipcTracker discipline), the
     forming close wanders, so a gate fires at second 10 and the tape walks it back.

★ The flicker test has to separate EARLY from FALSE, or it measures nothing.  A fast fire that the
slow layer confirms a minute later is EARLY — that is the entire point of the build.  A fast fire
the slow layer NEVER confirms is FALSE.  So: for each fast fire EPISODE (a run of consecutive
firing 5s reads counted once), does the SLOW gate fire at any of the next K minute closes?
Reported by elapsed bucket and by trigger margin, because the magnitude filter is the knob that is
supposed to fix exactly this.

  PYTHONPATH=src ./.venv/bin/python scripts/rev3_instability.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import rev3_two_layer as R

OUT = f"{R.SCRATCH}/rev3_instability.json"
K_CONFIRM = 3          # minutes the slow layer is given to confirm a fast fire


def main():
    atr_b: dict[int, list] = {}
    # episodes[gate] = list of (elapsed, margin, confirmed_within_K, atr, day, u)
    eps = {t: [] for t in R.GATES}
    for day in R.DAYS:
        d = R.build_day(day)
        rows = d["rows"]
        # slow read published at each minute close, keyed by the minute it describes
        slow_by_min: dict[int, tuple] = {}
        for r in rows:
            if r[2]:
                slow_by_min[r[0] - 65] = r
        for r in rows:
            if r[6] > 0 and r[15]["atr_p"] > 0:
                atr_b.setdefault(int(r[1]), []).append(r[15]["atr_p"] / r[6])
        # does the slow gate fire at minute close m?  (precompute per gate)
        slow_fire = {t: {} for t in R.GATES}
        for m, r in slow_by_min.items():
            for tag in R.GATES:
                sb, _ = R.gate_margin(tag, r[14], r[12], r[11])
                slow_fire[tag][m] = sb
        for tag in R.GATES:
            prev = False
            for r in rows:
                u, elapsed = r[0], r[1]
                fb, fm = R.gate_margin(tag, r[15], r[12], r[11])
                if fb and not prev:                      # first read of an episode
                    m = u - elapsed
                    conf = any(slow_fire[tag].get(m + 60 * k, False) for k in range(0, K_CONFIRM + 1))
                    eps[tag].append((int(elapsed), fm, conf, r[6], day, u))
                prev = fb
        print(f"scanned {day}", flush=True)

    atr_tab = {e: dict(n=len(v), mean=round(float(np.mean(v)), 4),
                       p10=round(float(np.percentile(v, 10)), 4),
                       p90=round(float(np.percentile(v, 90)), 4),
                       share_under_90=round(float(np.mean(np.array(v) < 0.90)), 4))
               for e, v in sorted(atr_b.items())}

    def tab(rows_, keyf, keys):
        out = {}
        for k in keys:
            sel = [x for x in rows_ if keyf(x) == k]
            n = len(sel)
            out[k] = dict(n=n, false=sum(1 for x in sel if not x[2]),
                          false_rate=round(sum(1 for x in sel if not x[2]) / n, 4) if n else None)
        return out

    EB = [(5, 10), (15, 20), (25, 30), (35, 40), (45, 60)]

    def eb(x):
        for lo, hi in EB:
            if lo <= x[0] <= hi:
                return f"{lo}-{hi}s"
        return "?"

    MB = [(1.0, 1.15), (1.15, 1.3), (1.3, 1.5), (1.5, 2.0), (2.0, 99)]

    def mb(x):
        for lo, hi in MB:
            if lo <= x[1] < hi:
                return f"{lo}-{hi}x"
        return "?"

    res = dict(atr_partial_vs_closed=atr_tab, k_confirm=K_CONFIRM,
               by_elapsed={t: tab(eps[t], eb, [f"{a}-{b}s" for a, b in EB]) for t in R.GATES},
               by_margin={t: tab(eps[t], mb, [f"{a}-{b}x" for a, b in MB]) for t in R.GATES},
               totals={t: dict(n=len(eps[t]), false=sum(1 for x in eps[t] if not x[2]),
                               false_rate=round(sum(1 for x in eps[t] if not x[2]) / len(eps[t]), 4)
                               if eps[t] else None) for t in R.GATES})
    with open(OUT, "w") as f:
        json.dump(res, f)

    print("\n── 1. ATR(partial)/ATR(closed) by elapsed second of the forming minute ──")
    print(f"{'elapsed':>8}{'n':>8}{'mean':>8}{'p10':>8}{'p90':>8}{'<0.90':>8}")
    for e in (5, 15, 25, 35, 45, 60):
        v = atr_tab[e]
        print(f"{e:>8}{v['n']:>8}{v['mean']:>8.3f}{v['p10']:>8.3f}{v['p90']:>8.3f}{v['share_under_90']:>8.1%}")

    print(f"\n── 2. FALSE-FIRE rate of fast episodes (slow layer never confirms within {K_CONFIRM} min) ──")
    print(f"{'gate':<17}{'n eps':>7}{'false':>7}{'rate':>7}   by elapsed bucket")
    for t in R.GATES:
        tt = res["totals"][t]
        by = "  ".join(f"{k}:{v['false_rate']:.0%}/{v['n']}" if v["n"] else f"{k}:-"
                       for k, v in res["by_elapsed"][t].items())
        print(f"{t:<17}{tt['n']:>7}{tt['false']:>7}"
              f"{(tt['false_rate'] if tt['false_rate'] is not None else 0):>7.0%}   {by}")
    print("\n── 3. same, by TRIGGER MARGIN (the magnitude filter's job) ──")
    for t in R.GATES:
        by = "  ".join(f"{k}:{v['false_rate']:.0%}/{v['n']}" if v["n"] else f"{k}:-"
                       for k, v in res["by_margin"][t].items())
        print(f"{t:<17} {by}")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
