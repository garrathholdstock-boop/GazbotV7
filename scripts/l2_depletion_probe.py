#!/usr/bin/env python3
"""L2 book-depletion probe — the greenfield lab's one untested stone.

Hypothesis: before a run, the FAR side of the book (the side price is about to run TOWARD) thins
out, in a way the trade tape (flow/price/volume) can't see. If true it's a LEADING signal for runs.
Before building any gate, prove the premise on the WHOLE tape (the exact test that killed AFC): does
book imbalance at time t PREDICT the forward move from t? If %continued ≈ 50% and corr ≈ 0, it's dead
like flow. If strong depletion → high %continued, that's a real leading edge to build on.

Signal: top-3 depth per side at each instant (point-in-time snapshot, ASOF). askshare = ask/(ask+bid).
askshare LOW = asks thin → book says UP; HIGH = bids thin → book says DN. Predicted dir = toward the
thin side. Forward = 1-min close move over horizon H (strictly future). Also a run-conditioned check:
were the census runs' pre-run far sides actually thinner than tape baseline?

capture.db book+bars. book coverage starts 07-21 21:33 UTC (~3.5 days). DuckDB. ⚠ short window.

  PYTHONPATH=src python scripts/l2_depletion_probe.py [--horizon 15]
"""
from __future__ import annotations

import argparse

import duckdb
import numpy as np

CAP = "/home/alphabot/gazbot7/data/capture.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=15, help="forward horizon in minutes")
    ap.add_argument("--levels", type=int, default=3, help="top-N book levels for depth")
    a = ap.parse_args()
    H, L = a.horizon, a.levels
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")

    # per-snapshot top-L depth by side (each ts_ms is one book snapshot)
    con.execute(f"""
        CREATE TABLE snap AS
        SELECT ts_ms,
               COALESCE(SUM(CASE WHEN side='bid' THEN size END),0) bid,
               COALESCE(SUM(CASE WHEN side='ask' THEN size END),0) ask
        FROM c.book WHERE symbol='MNQ' AND level<={L} GROUP BY ts_ms HAVING bid>0 AND ask>0""")
    # 1-min closes, and ASOF the latest snapshot at/just before each minute
    df = con.execute("""
        WITH m AS (SELECT (bar_ts-bar_ts%60) t, arg_max(close,bar_ts) cl FROM c.bars
                   WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1)
        SELECT m.t, m.cl, s.bid, s.ask
        FROM m ASOF JOIN snap s ON s.ts_ms <= m.t*1000
        WHERE m.t*1000 >= (SELECT min(ts_ms) FROM snap)
        ORDER BY m.t""").df()

    df["askshare"] = df.ask / (df.ask + df.bid)
    df["cl_fwd"] = df.cl.shift(-H)                      # close H minutes ahead
    df = df.dropna(subset=["cl_fwd"]).reset_index(drop=True)
    df["fwd"] = df.cl_fwd - df.cl                       # forward move (pts), strictly future
    # book-predicted direction = toward the THIN side (askshare<0.5 → UP)
    df["pred_up"] = df.askshare < 0.5
    df["fwd_dir"] = np.where(df.pred_up, df.fwd, -df.fwd)   # forward move in the predicted direction
    df["dep"] = (df.askshare - 0.5).abs()              # depletion strength (0 = balanced, .5 = one side empty)

    n = len(df)
    corr = np.corrcoef(df.askshare, df.fwd)[0, 1]
    print(f"L2 DEPLETION PREMISE STUDY — horizon {H}min · top-{L} depth · {n} minute-samples "
          f"({df.t.min()} .. book-covered)\n")
    print(f"corr(askshare, fwd {H}m) = {corr:+.3f}   "
          f"[strongly NEGATIVE = thin asks lead UP = premise HOLDS; ≈0 = dead like flow]")
    base_up = 100 * (df.fwd > 0).mean()
    print(f"baseline: P(fwd up) = {base_up:.0f}% · mean |fwd| = {df.fwd.abs().mean():.1f}pt\n")

    print("── does STRONGER depletion → higher continuation toward the thin side? ──")
    print(f"  {'depletion band':>16}{'n':>7}{'%continued':>12}{'mean fwd_dir':>14}")
    edges = [0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.51]
    for a0, a1 in zip(edges, edges[1:]):
        g = df[(df.dep >= a0) & (df.dep < a1)]
        if len(g) < 5:
            print(f"  {f'{a0:.2f}-{a1:.2f}':>16}{len(g):>7}{'—':>12}")
            continue
        cont = 100 * (g.fwd_dir > 0).mean()
        print(f"  {f'{a0:.2f}-{a1:.2f}':>16}{len(g):>7}{cont:>11.0f}%{g.fwd_dir.mean():>+13.1f}")
    print("  (flat ~50% / ~0pt across bands = the thin side does NOT predict the run — DEAD.\n"
          "   rising %continued + positive mean as depletion grows = a real leading tell.)")

    # askshare decile view (directional): low askshare should → positive fwd if premise holds
    print("── askshare buckets (low = asks thin → should run UP) ──")
    print(f"  {'askshare':>12}{'n':>7}{'mean fwd(pt)':>14}{'%up':>7}")
    for a0, a1 in [(0.0, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, 0.65), (0.65, 1.01)]:
        g = df[(df.askshare >= a0) & (df.askshare < a1)]
        if len(g) < 5:
            continue
        print(f"  {f'{a0:.2f}-{a1:.2f}':>12}{len(g):>7}{g.fwd.mean():>+13.1f}{100*(g.fwd>0).mean():>6.0f}%")

    con.close()
    print("\n(⚠ ~3.5 days of book only, in-sample. This is the PREMISE gate: if it reads dead here, do NOT "
          "build an L2 run-catcher — the book tells us no more than the tape did. If it reads alive, the "
          "next step is a book-honest backtest of a depletion-triggered entry with ER bands.)")


if __name__ == "__main__":
    main()
