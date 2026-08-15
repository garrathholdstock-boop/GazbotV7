#!/usr/bin/env python3
"""GF UNCLASS — STEP 7: the ORACLE bound, the SEPARABILITY test, and the L2 book at board time.

The rescue failed everywhere outside ASIA. Before calling that a null, two things have to be
established, because they decide whether the next attempt is worth funding:

  A. THE ORACLE. Board only the 34 census runs, with the real exit and real costs. That is what a
     PERFECT filter would pay. If the oracle is small, no filter is worth building. If it is large,
     the entry is fine and the whole problem is separability.

  B. SEPARABILITY. At the moment of boarding, is there ANY causal variable that distinguishes a fire
     that is inside one of the 34 runs from the ~15,000 fires that are not? Tested with a plain
     AUC/rank test per feature — no model, nothing to overfit.

  C. THE L2 BOOK — the one instrument no rider study on this desk has ever opened. capture.db.book
     is MNQ, 41ms event-driven, 5 TRADING DAYS — which is exactly the census week, and every one of
     the 34 runs is in it. So the book can be tested on the runs even though it cannot be tested on
     the 49-session backtest. If the book separates and the price tape does not, that is the
     instrument the next attempt needs, and saying so IS the deliverable.

    PYTHONPATH=src .venv/bin/python scripts/gf_uncl_oracle.py
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
from gf_rider_engine import Racer, run_trades, stat, line, strip_best  # noqa: E402
from gf_rider_tape import build                                    # noqa: E402
from gf_uncl_ride import signals                                   # noqa: E402
from gf_uncl_members import census_rows                            # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CAP = "/home/alphabot/gazbot7/data/capture.db"
OUT = {}


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Rank AUC — P(a random run-fire scores above a random ordinary fire). 0.5 = no information."""
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    if len(pos) < 5 or len(neg) < 5:
        return np.nan
    allv = np.concatenate([pos, neg])
    r = pd.Series(allv).rank().to_numpy()
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def main():
    m1, s5 = build()
    racer = Racer(s5)
    sig = signals(m1, 10, 2.0)
    cr = census_rows()
    U = cr[(cr.cl == "UNCLASS") & (cr.us == "sat out")].reset_index(drop=True)

    # ══ A. THE ORACLE ═════════════════════════════════════════════════════════════════════════
    print("══ A. ORACLE — board ONLY the 34 sat-out UNCLASS runs, real exit, real costs ══")
    rows = []
    for r in U.itertuples():
        s = sig[(sig.ts >= r.ts) & (sig.ts <= r.ts + 900) & (sig.side == (1 if r.move > 0 else -1))]
        if len(s):
            rows.append(s.iloc[0].to_dict())
    ORC = pd.DataFrame(rows)
    print(f"   the thrust rule fires inside {len(ORC)}/34 of the runs (aligned with the move)")
    for sa, ta, cap in ((2.5, 6.0, 120), (3.0, 6.0, 120), (3.0, np.inf, 240), (2.0, 4.0, 120)):
        tr = run_trades(racer, ORC, stop_a=sa, targ_a=ta, cap_min=cap, cooldown_min=0)
        print("   " + line(f"oracle {sa}/{ta}/{cap}min", stat(tr),
                           f"vs ${U.ceil.sum():,.0f} hindsight ceiling"))
        OUT.setdefault("oracle", []).append(dict(cfg=f"{sa}/{ta}/{cap}", **stat(tr)))
    best = run_trades(racer, ORC, stop_a=2.5, targ_a=6.0, cap_min=120, cooldown_min=0)
    OUT["oracle_capture_pct"] = round(100 * best.net.sum() / U.ceil.sum(), 1)
    print(f"   -> a PERFECT filter on these entries banks ${best.net.sum():,.0f}, "
          f"{OUT['oracle_capture_pct']}% of the ${U.ceil.sum():,.0f} ceiling")

    # ══ B. SEPARABILITY on the price tape ═════════════════════════════════════════════════════
    print("\n══ B. SEPARABILITY — run-fires vs ordinary fires, AUC per feature (0.50 = no info) ══")
    runts = set()
    for r in U.itertuples():
        runts |= set(sig[(sig.ts >= r.ts) & (sig.ts <= r.ts + 900)].ts.tolist())
    wkm = sig[sig.day >= "2026-08-09"]                # compare like with like: census week only
    pos = wkm[wkm.ts.isin(runts)]
    neg = wkm[~wkm.ts.isin(runts)]
    print(f"   census-week fires: {len(pos)} inside a sat-out UNCLASS run, {len(neg)} not")
    feats = ["atr", "atr_pr", "er15", "rvol", "v", "net"]
    ab = []
    for f in feats:
        a = auc(pos[f].abs().to_numpy(float) if f == "net" else pos[f].to_numpy(float),
                neg[f].abs().to_numpy(float) if f == "net" else neg[f].to_numpy(float))
        print(f"   {f:<10} AUC={a:.3f}   run-median={pos[f].abs().median():>9.3f}  "
              f"ordinary-median={neg[f].abs().median():>9.3f}")
        ab.append(dict(feat=f, auc=a, run_med=float(pos[f].abs().median()),
                       ord_med=float(neg[f].abs().median())))
    OUT["separability_tape"] = ab

    # ══ C. THE L2 BOOK at board time ══════════════════════════════════════════════════════════
    print("\n══ C. THE L2 BOOK at the moment of boarding (capture.db.book, MNQ, 41ms, 5 sessions) ══")
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    bk = con.execute("""
        SELECT (ts_ms/1000)::BIGINT // 60 * 60 AS m,
               SUM(CASE WHEN side='bid' THEN size END) AS bid,
               SUM(CASE WHEN side='ask' THEN size END) AS ask,
               COUNT(*) AS nev
        FROM c.book WHERE symbol='MNQ' AND level<=3 GROUP BY 1 ORDER BY 1""").df()
    con.close()
    bk["imb"] = (bk.bid - bk.ask) / (bk.bid + bk.ask)
    print(f"   book minutes available: {len(bk):,}  "
          f"({pd.to_datetime(bk.m, unit='s', utc=True).dt.strftime('%m-%d').nunique()} sessions)")
    # the book minute BEFORE the fill — the fill is at t, so read t-60 (strictly causal)
    j = wkm.copy()
    j["m"] = j["ts"] - 60
    j = j.merge(bk[["m", "imb", "bid", "ask", "nev"]], on="m", how="left")
    j["far"] = np.where(j.side > 0, j.ask, j.bid)
    j["near"] = np.where(j.side > 0, j.bid, j.ask)
    j["far_share"] = j.far / (j.far + j.near)         # <0.5 = the side price runs INTO is thin
    j["imb_signed"] = j.imb * j.side                  # >0 = book leans the way we are going
    jp, jn = j[j.ts.isin(runts)], j[~j.ts.isin(runts)]
    print(f"   fires with a book read: {j.far_share.notna().sum()}/{len(j)}  "
          f"(run-fires {jp.far_share.notna().sum()}/{len(jp)})")
    br = []
    for f in ("far_share", "imb_signed", "nev"):
        a = auc(jp[f].to_numpy(float), jn[f].to_numpy(float))
        print(f"   {f:<12} AUC={a:.3f}   run-median={jp[f].median():>8.3f}  ordinary-median={jn[f].median():>8.3f}")
        br.append(dict(feat=f, auc=a, run_med=float(jp[f].median()), ord_med=float(jn[f].median())))
    OUT["separability_book"] = br

    # does a book cut actually make money on the census week's eligible fires?
    print("\n   -- a book-conditioned rider on the census week (n is tiny; this is a SIGNAL, not a result) --")
    for thr, nm in ((0.48, "far_share < 0.48 (running into thin depth)"),
                    (0.52, "far_share < 0.52")):
        s = j[j.far_share < thr]
        if len(s) < 20:
            print(f"   {nm:<44} n={len(s)} SKIPPED")
            continue
        tr = run_trades(racer, s, stop_a=2.5, targ_a=6.0, cap_min=120)
        print("   " + line(nm, stat(tr)))
        OUT.setdefault("book_rider", []).append(dict(cut=nm, **stat(tr)))
    base_wk = run_trades(racer, wkm, stop_a=2.5, targ_a=6.0, cap_min=120)
    print("   " + line("no book cut (census week, all eligible)", stat(base_wk)))
    OUT["census_week_unfiltered"] = stat(base_wk)

    json.dump(OUT, open(f"{SEC}/gf_uncl_oracle.json", "w"), indent=1, default=float)
    print(f"\n-> {SEC}/gf_uncl_oracle.json")


if __name__ == "__main__":
    main()
