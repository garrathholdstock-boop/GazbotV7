#!/usr/bin/env python3
"""GF UNCLASS — STEP 8: close the two loose ends before the verdict.

  1. The book cut `far_share < 0.48` made +$735 on the census week while the unfiltered fires made
     +$107. Its AUC was 0.496 — a coin flip — so the cut CANNOT be causal and the money must be
     luck. That is an assertion until it is placebo-controlled. Control it.
  2. The oracle used the ASIA exit (2.5/6R). The run population may want a different one. Sweep the
     exit on the 33 run-boards to find the BEST POSSIBLE honest capture of the $4,097 ceiling —
     the number that says whether a perfect filter is worth building at all.

    PYTHONPATH=src .venv/bin/python scripts/gf_uncl_close.py
"""
from __future__ import annotations

import json
import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gf_rider_engine import Racer, run_trades, stat, line, placebo, strip_best  # noqa: E402
from gf_rider_tape import build                                    # noqa: E402
from gf_uncl_ride import signals                                   # noqa: E402
from gf_uncl_members import census_rows                            # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CAPDB = "/home/alphabot/gazbot7/data/capture.db"
OUT = {}


def main():
    m1, s5 = build()
    racer = Racer(s5)
    sig = signals(m1, 10, 2.0)
    wkm = sig[sig.day >= "2026-08-09"].reset_index(drop=True)
    cr = census_rows()
    U = cr[(cr.cl == "UNCLASS") & (cr.us == "sat out")].reset_index(drop=True)

    # ── 1. placebo the book cut ───────────────────────────────────────────────────────────────
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAPDB}' AS c (TYPE sqlite, READ_ONLY)")
    bk = con.execute("""SELECT (ts_ms/1000)::BIGINT // 60 * 60 AS m,
               SUM(CASE WHEN side='bid' THEN size END) bid, SUM(CASE WHEN side='ask' THEN size END) ask
        FROM c.book WHERE symbol='MNQ' AND level<=3 GROUP BY 1""").df()
    con.close()
    j = wkm.copy()
    j["m"] = j["ts"] - 60
    j = j.merge(bk, on="m", how="left")
    j["far"] = np.where(j.side > 0, j.ask, j.bid)
    j["near"] = np.where(j.side > 0, j.bid, j.ask)
    j["far_share"] = j.far / (j.far + j.near)
    EX = dict(stop_a=2.5, targ_a=6.0, cap_min=120)
    cut = j[j.far_share < 0.48]
    tr = run_trades(racer, cut, **EX)
    pl = placebo(racer, j[j.far_share.notna()], len(cut), 300, **EX)
    print("══ 1. IS THE BOOK CUT REAL? (far_share < 0.48, census week) ══")
    print("   " + line("far_share < 0.48", stat(tr), f"strip3=${strip_best(tr,3):,.0f}"))
    print(f"   placebo — discard the SAME {len(cut)} fires at random, 300 reps: "
          f"mean ${pl['per_mean']:.2f}/tr, p95 ${pl['per_p95']:.2f}, sd of net ${pl['net_sd']:,.0f}")
    verdict = "BEATS its placebo p95" if stat(tr)["per"] > pl["per_p95"] else "FAILS its placebo"
    print(f"   -> {verdict}")
    OUT["book_cut"] = dict(actual=stat(tr), placebo=pl, verdict=verdict,
                           strip3=float(strip_best(tr, 3)))

    # ── 2. the oracle exit sweep ──────────────────────────────────────────────────────────────
    print("\n══ 2. ORACLE EXIT SWEEP — board ONLY the 34 runs; what is the best honest capture? ══")
    rows = []
    for r in U.itertuples():
        s = sig[(sig.ts >= r.ts) & (sig.ts <= r.ts + 900) & (sig.side == (1 if r.move > 0 else -1))]
        if len(s):
            rows.append(s.iloc[0].to_dict())
    ORC = pd.DataFrame(rows)
    ceil = float(U.ceil.sum())
    best = None
    print(f"   {'stop':>5}" + "".join(f"{('inf' if not np.isfinite(t) else f'{t:g}R'):>14}" for t in
                                      (2.0, 3.0, 4.0, 5.0, 6.0, np.inf)))
    for sa in (1.5, 2.0, 2.5, 3.0, 4.0):
        cells = []
        for ta in (2.0, 3.0, 4.0, 5.0, 6.0, np.inf):
            t = run_trades(racer, ORC, stop_a=sa, targ_a=ta, cap_min=120, cooldown_min=0)
            st = stat(t)
            cells.append(f"${st['net']:>7,.0f}({st['n']:>2d})")
            OUT.setdefault("oracle_grid", []).append(dict(stop=sa, targ=None if not np.isfinite(ta) else ta, **st))
            if best is None or st["net"] > best[0]:
                best = (st["net"], sa, ta, st)
        print(f"   {sa:>5}" + "".join(f"{c:>14}" for c in cells))
    print(f"\n   BEST ORACLE CELL: stop={best[1]} targ={best[2]}  net=${best[0]:,.0f} on n={best[3]['n']} "
          f"= {100*best[0]/ceil:.1f}% of the ${ceil:,.0f} hindsight ceiling")
    OUT["oracle_best"] = dict(stop=best[1], targ=None if not np.isfinite(best[2]) else best[2],
                              **best[3], pct_of_ceiling=round(100 * best[0] / ceil, 1), ceiling=ceil)

    # what the hindsight ceiling actually assumes vs what a path-honest trade can take
    mfe = []
    for r in U.itertuples():
        s = sig[(sig.ts >= r.ts) & (sig.ts <= r.ts + 900) & (sig.side == (1 if r.move > 0 else -1))]
        if not len(s):
            continue
        e = s.iloc[0]
        fw = m1[(m1.ts >= e.ts) & (m1.ts <= e.ts + 7200)]
        if not len(fw):
            continue
        best_pt = (fw.h.max() - e.entry) if e.side > 0 else (e.entry - fw.l.min())
        mfe.append(dict(tm=r.tm, ceil=r.ceil, mfe_usd=best_pt * 2.0,
                        frac=100 * best_pt * 2.0 / r.ceil))
    M = pd.DataFrame(mfe)
    print(f"\n   ORACLE-OF-ORACLES: even selling the exact 2h high after boarding, the 33 boarded runs "
          f"are worth ${M.mfe_usd.sum():,.0f} vs the ${ceil:,.0f} census ceiling "
          f"({100*M.mfe_usd.sum()/ceil:.0f}%) — median run gives back {100-M.frac.median():.0f}% "
          f"of its headline number to the late board.")
    OUT["mfe_bound"] = dict(total=float(M.mfe_usd.sum()), ceiling=ceil,
                            pct=round(100 * M.mfe_usd.sum() / ceil, 1))

    json.dump(OUT, open(f"{SEC}/gf_uncl_close.json", "w"), indent=1, default=float)
    print(f"\n-> {SEC}/gf_uncl_close.json")


if __name__ == "__main__":
    main()
