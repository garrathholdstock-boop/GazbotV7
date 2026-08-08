#!/usr/bin/env python3
"""GIVE-BACK STUDY — stage 7: the verdict, and every test I could think of to kill it.

  A. desk-wide pair table: the LOADED live pair vs candidates, QUIET and US, per gate and
     summed, with n / $ per trade / $ per week / LODO / strip-best-3 / ARCH-CAP split.
  B. the INCREMENTAL test: per-band rung fitted on one half of the tape, scored on the
     other. Both directions. Against the same-protocol static fit. This is the only number
     that can say YES to a tape-adaptive R.
  C. the live-loss multiplier that kills whatever survives (desk band 1.1-3.1x).
  D. hit curves: P(reach xR before -1R), QUIET vs US — the stable view of where money is.

  PYTHONPATH=src ./.venv/bin/python scripts/adaptive_r_verdict.py
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

pd.set_option("display.width", 280)
GATES = ["grind_long", "abs_veto_long", "abs_veto_short"]
ARCH_DAYS = {"2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10",
             "2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17"}
A_GRID = ["A0.5", "A0.75", "A1.0", "A1.25", "A1.5", "A2.0", "A2.5", "A3.0", "A3.5", "A4.0"]
D_GRID = ["D10", "D15", "D20", "D25", "D30", "D40", "D50", "D60", "D80"]
B_GRID = ["A1.5", "A2.0", "A2.5", "A3.0", "A3.5", "A4.0", "A5.0", "A6.0", "tight", "k2.5", "wide"]


def robust(s: pd.DataFrame):
    """(net, LODO-worst, strip-best-3, days green / days) on a per-day basis."""
    if not len(s):
        return 0.0, 0.0, 0.0, "0/0"
    byday = s.groupby("day").pnl.sum()
    tot = byday.sum()
    lodo = min(tot - byday[d] for d in byday.index)
    strip3 = tot - byday.nlargest(3).sum()
    return tot, lodo, strip3, f"{int((byday>0).sum())}/{len(byday)}"


def kill_mult(s: pd.DataFrame, base: pd.DataFrame) -> float:
    """Smallest live-loss multiplier L (losses x L) at which the candidate stops beating
    the baseline. Both books get the same L — that is the honest form of the test."""
    for L in np.arange(1.0, 3.15, 0.05):
        c = s.pnl.where(s.pnl >= 0, s.pnl * L).sum()
        b = base.pnl.where(base.pnl >= 0, base.pnl * L).sum()
        if c <= b:
            return round(float(L), 2)
    return float("inf")


def main():
    sig, tape = load()
    ts, px, ends = tape
    with open(f"{SCR}/ar_per.pkl", "rb") as fh:
        _s, per, CUTS = pickle.load(fh)
    for r in per.values():
        r["arch"] = r.day.isin(ARCH_DAYS)

    weeks = sig.day.nunique() / 5.0        # 16 sessions = 3.2 trading weeks

    # ── A. pair table ────────────────────────────────────────────────────────────────
    def pair(gate, a, b, win):
        ra, rb = per.get((gate, a)), per.get((gate, b))
        if ra is None or rb is None:
            return None
        return pd.concat([ra[ra.win == win], rb[rb.win == win]], ignore_index=True)

    CAND = {"LOADED": None,
            "A1.0/A1.5 tight-both": ("A1.0", "A1.5"),
            "A1.5/A2.5": ("A1.5", "A2.5"),
            "A2.0/A3.0": ("A2.0", "A3.0"),
            "A3.5/A3.5 (REV3 best)": ("A3.5", "A3.5"),
            "A2.5/wide": ("A2.5", "wide"),
            "D20/D40 dollar-clip": ("D20", "D40"),
            "D15/D30 dollar-clip": ("D15", "D30"),
            "D30/D60 dollar-clip": ("D30", "D60")}

    for win in ("QUIET", "US"):
        print(f"\n{'='*130}\nPAIR TABLE — {win} window   ({sig.day.nunique()} sessions "
              f"= {weeks:.1f} trading weeks)\n{'='*130}")
        desk = {}
        for name, cell in CAND.items():
            rows = []
            allrows = []
            for gate in GATES:
                a, b = LOADED[gate] if cell is None else cell
                s = pair(gate, a, b, win)
                if s is None or not len(s):
                    continue
                net, lodo, s3, dg = robust(s)
                rows.append({"cell": name, "gate": gate, "lots": len(s), "net$": net,
                             "$/lot": s.pnl.mean(), "LODO": lodo, "strip3": s3, "days+": dg,
                             "ARCH": s[s.arch].pnl.sum(), "CAP": s[~s.arch].pnl.sum()})
                allrows.append(s)
            if not rows:
                continue
            t = pd.DataFrame(rows)
            tot = pd.concat(allrows, ignore_index=True)
            net, lodo, s3, dg = robust(tot)
            desk[name] = tot
            t.loc[len(t)] = {"cell": name, "gate": "** DESK (3 gates) **", "lots": len(tot),
                             "net$": net, "$/lot": tot.pnl.mean(), "LODO": lodo, "strip3": s3,
                             "days+": dg, "ARCH": tot[tot.arch].pnl.sum(),
                             "CAP": tot[~tot.arch].pnl.sum()}
            print(t.round(2).to_string(index=False))
            print()
        if win == "QUIET":
            print(f"{'-'*130}\nDESK SUMMARY vs LOADED — {win}\n{'-'*130}")
            base = desk["LOADED"]
            rr = []
            for name, tot in desk.items():
                net, lodo, s3, dg = robust(tot)
                rr.append({"cell": name, "lots": len(tot), "net$": net,
                           "$/lot": tot.pnl.mean(), "$/wk": net / weeks,
                           "delta vs loaded": net - base.pnl.sum(),
                           "LODO": lodo, "strip3": s3, "days+": dg,
                           "ARCH": tot[tot.arch].pnl.sum(), "CAP": tot[~tot.arch].pnl.sum(),
                           "kill x": kill_mult(tot, base) if name != "LOADED" else np.nan})
            print(pd.DataFrame(rr).round(2).to_string(index=False))

    # ── B. THE INCREMENTAL TEST ──────────────────────────────────────────────────────
    print(f"\n{'='*130}\nB. INCREMENTAL-VALUE TEST — does a tape-adaptive R beat a fixed R "
          f"OUT OF SAMPLE?\n{'='*130}")
    print("Protocol: fit on one half, score on the other. Identical protocol for both the\n"
          "ADAPTIVE fit (best rung per tape band) and the STATIC fit (one best rung overall).\n"
          "QUIET window only. Lot A grid only (Lot A is the lot the operator wants tightened).\n")

    def band_of(v, cuts):
        return int(np.searchsorted(cuts, v, "right"))

    rows = []
    for proxy in ("atr", "rr15", "rvol"):
        cuts = CUTS[proxy]
        for fit_arch in (True, False):
            fitname = "fit ARCH -> score CAP" if fit_arch else "fit CAP -> score ARCH"
            for gate in GATES:
                sub = {r: per[(gate, r)] for r in A_GRID if (gate, r) in per}
                fit = {r: d[(d.win == "QUIET") & (d.arch == fit_arch) & d[proxy].notna()]
                       for r, d in sub.items()}
                oos = {r: d[(d.win == "QUIET") & (d.arch != fit_arch) & d[proxy].notna()]
                       for r, d in sub.items()}
                # STATIC fit
                st = max(fit, key=lambda r: fit[r].pnl.sum())
                static_oos = oos[st].pnl.sum()
                # ADAPTIVE fit — best rung per band, chosen on the fit half only
                pick, ad = {}, 0.0
                for bnd in (0, 1, 2):
                    cand = {r: fit[r][fit[r][proxy].map(lambda v: band_of(v, cuts)) == bnd]
                            for r in fit}
                    cand = {r: d for r, d in cand.items() if len(d) >= 5}
                    if not cand:
                        pick[bnd] = st
                    else:
                        pick[bnd] = max(cand, key=lambda r: cand[r].pnl.sum())
                    d = oos[pick[bnd]]
                    ad += d[d[proxy].map(lambda v: band_of(v, cuts)) == bnd].pnl.sum()
                # LOADED Lot A for reference
                la = LOADED[gate][0]
                loaded_oos = oos[la].pnl.sum() if la in oos else np.nan
                rows.append({"proxy": proxy, "split": fitname, "gate": gate,
                             "loaded LotA": la, "loaded $": loaded_oos,
                             "static pick": st, "static $": static_oos,
                             "adaptive picks": "/".join(pick[b] for b in (0, 1, 2)),
                             "adaptive $": ad, "adapt - static": ad - static_oos})
    inc = pd.DataFrame(rows)
    print(inc.round(1).to_string(index=False))
    print("\nDESK TOTAL per proxy x split (sum of the 3 gates):")
    agg = inc.groupby(["proxy", "split"])[["loaded $", "static $", "adaptive $",
                                           "adapt - static"]].sum()
    print(agg.round(1).to_string())
    print(f"\nAdaptive beats static out of sample in "
          f"{int((inc['adapt - static'] > 0).sum())} of {len(inc)} gate x proxy x split cells; "
          f"total edge ${inc['adapt - static'].sum():,.0f}.")

    # ── D. hit curves ────────────────────────────────────────────────────────────────
    print(f"\n{'='*130}\nD. HIT CURVES — P(reach xR before -1R), QUIET vs US\n{'='*130}")
    hits = []
    for gate in GATES:
        for win in ("QUIET", "US"):
            row = {"gate": gate, "win": win}
            for r in ["A0.5", "A1.0", "A1.5", "A2.0", "A2.5", "A3.0", "A3.5"]:
                d = per[(gate, r)]
                d = d[d.win == win]
                row[r.replace("A", "") + "R"] = round(100 * (d.pnl > 0).mean(), 1)
                row["n"] = len(d)
            hits.append(row)
    print(pd.DataFrame(hits).to_string(index=False))


if __name__ == "__main__":
    main()
