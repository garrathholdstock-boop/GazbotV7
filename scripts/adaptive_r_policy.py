#!/usr/bin/env python3
"""GIVE-BACK STUDY — stage 6: tape bands, the adaptive policy, and the INCREMENTAL test.

Four things happen here.

1. TAPE BANDS derived from the data's own quantiles (terciles of the QUIET-window entry
   population), for THREE competing proxies: ATR14 (the incumbent), realised 15-min range,
   and RVOL. No round numbers imposed.

2. THE LADDER PER BAND — for each gate x proxy x band, every exit rule as its own
   sequential single-lot slot. This is where a tape-adaptive R would show up: if the best
   rung MOVES across bands, there is something to route on; if it does not, there isn't.

3. THE FIXED-DOLLAR CONTROL. The desk's R is ALREADY ATR-proportional, so a fixed R
   auto-shrinks in dollars on quiet tape. A fixed-DOLLAR clip is the operator's literal
   mental model and the purest form of "more than ATR-proportional tightening". If the
   dollar clip cannot beat the fixed R, the extra tightening is not there.

4. THE INCREMENTAL-VALUE TEST, done HONESTLY: the per-band winner is picked on ONE half of
   the tape and scored on the OTHER. An in-sample adaptive policy always beats an
   in-sample static one — it has more free parameters. Only the out-of-sample number
   decides. ARCH = 10 sessions 07-06..07-17, CAP = 6 sessions 07-24..07-31.

  PYTHONPATH=src ./.venv/bin/python scripts/adaptive_r_policy.py
"""
from __future__ import annotations

import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from adaptive_r_sim import SCR, day_of, load_tape, session_ends, simulate, window_of  # noqa: E402
from adaptive_r_sweep import LOADED, load  # noqa: E402

pd.set_option("display.width", 260)

A_RULES = ["A0.5", "A0.75", "A1.0", "A1.25", "A1.5", "A2.0", "A2.5", "A3.0", "A3.5", "A4.0"]
D_RULES = ["D10", "D15", "D20", "D25", "D30", "D40", "D50", "D60", "D80"]
B_RULES = ["A1.5", "A2.0", "A2.5", "A3.0", "A3.5", "A4.0", "A5.0", "A6.0", "tight", "k2.5", "wide"]
ALL = sorted(set(A_RULES + D_RULES + B_RULES))
GATES = ["grind_long", "abs_veto_long", "abs_veto_short"]      # rgv_short: n=8 quiet, dropped
ARCH_END = "2026-07-18"


def score(sig, tape, gate, rule_of, mask=None):
    ts, px, ends = tape
    g = sig[sig.gate == gate].sort_values("dec_ms")
    r = simulate(g, rule_of, ts, px, ends)
    if not len(r):
        return r
    r["win"] = r.dec_ms.map(window_of)
    r["day"] = r.dec_ms.map(day_of)
    return r if mask is None else r[mask(r)]


def bands_for(s: pd.Series, k=3):
    qs = [s.quantile(i / k) for i in range(1, k)]
    return [round(float(x), 2) for x in qs]


def band_of(v, cuts):
    return int(np.searchsorted(cuts, v, "right"))


def main():
    sig, tape = load()
    ts, px, ends = tape
    quiet = sig[sig.win == "QUIET"]

    # ── 1. bands from the data's own quantiles ───────────────────────────────────────
    print("=" * 100)
    print("TAPE BANDS — terciles of the QUIET-window entry population (derived, not imposed)")
    print("=" * 100)
    CUTS = {}
    for proxy in ("atr", "rr15", "rvol"):
        CUTS[proxy] = bands_for(quiet[proxy].dropna())
        print(f"{proxy:6} terciles at {CUTS[proxy]}   "
              f"(min {quiet[proxy].min():.2f} / med {quiet[proxy].median():.2f} / "
              f"max {quiet[proxy].max():.2f})")
    # correlation between the proxies — is anything NOT just ATR under another name?
    print("\nproxy correlation (Spearman, QUIET entries):")
    print(quiet[["atr", "rr15", "rvol", "vrate"]].corr(method="spearman").round(3).to_string())

    # ── 2/3. ladder per band, per proxy ──────────────────────────────────────────────
    allres = {}
    for rule in ALL:
        r = simulate(sig.sort_values("dec_ms"), lambda _r, k=rule: k, ts, px, ends)
        r["win"] = r.dec_ms.map(window_of)
        r["day"] = r.dec_ms.map(day_of)
        allres[rule] = r
    # NB: the walk above is desk-wide-sequential across gates; redo per gate (live = per slot)
    per = {}
    for gate in GATES:
        g = sig[sig.gate == gate].sort_values("dec_ms")
        for rule in ALL:
            r = simulate(g, lambda _r, k=rule: k, ts, px, ends)
            if not len(r):
                continue
            r["win"] = r.dec_ms.map(window_of)
            r["day"] = r.dec_ms.map(day_of)
            for proxy in ("atr", "rr15", "rvol"):
                mp = dict(zip(g.dec_ms, g[proxy]))
                r[proxy] = r.dec_ms.map(mp)
            per[(gate, rule)] = r
    with open(f"{SCR}/ar_per.pkl", "wb") as fh:
        pickle.dump((sig, per, CUTS), fh)

    for proxy in ("atr", "rr15", "rvol"):
        cuts = CUTS[proxy]
        print(f"\n{'='*100}\nQUIET WINDOW — best rung by {proxy.upper()} band  "
              f"(cuts {cuts})\n{'='*100}")
        for gate in GATES:
            rows = []
            for rule in ALL:
                r = per.get((gate, rule))
                if r is None:
                    continue
                q = r[(r.win == "QUIET") & r[proxy].notna()].copy()
                q["band"] = q[proxy].map(lambda v: band_of(v, cuts))
                for bnd, s in q.groupby("band"):
                    rows.append({"rule": rule, "band": bnd, "n": len(s),
                                 "net$": s.pnl.sum(), "$/fill": s.pnl.mean()})
            t = pd.DataFrame(rows)
            if not len(t):
                continue
            print(f"\n  {gate}")
            piv = t.pivot_table(index="rule", columns="band", values="$/fill")
            npv = t.pivot_table(index="rule", columns="band", values="n")
            piv = piv.reindex([r for r in ALL if r in piv.index])
            show = piv.round(2).astype(str) + " (" + npv.reindex(piv.index).astype(int).astype(str) + ")"
            print(show.to_string())
            best = piv.idxmax()
            print(f"    best rung per band: {dict(best)}")


if __name__ == "__main__":
    main()
