#!/usr/bin/env python3
"""L2 book DYNAMICS probe — depletion RATE + run-imminence (volatility), not the resting LEVEL.

The resting far-side depth LEVEL didn't predict runs. Different question: does the SPEED the book
thins (a derivative) carry a tell the level can't? Two signals, two hypotheses:

  A. DIRECTIONAL — d_askshare over Δ seconds. Rapid ask-thinning (askshare dropping fast) → price
     about to run UP into the vanishing offers. corr(d_askshare, fwd) strongly NEG = a real lead.
  B. RUN-IMMINENCE (volatility, direction-agnostic) — d_total_depth% over Δ. When BOTH sides thin
     fast, a break may be imminent. Does the fastest-thinning bucket precede the BIGGEST |moves| /
     the census runs? A run *detector* (a label feeding the router/shadow), even if not a direction.

Point-in-time top-3 depth (ASOF per second) from capture.db book (52.7M rows, 07-21 21:33→07-25).
Forward = 1-min close move over H. Rate window Δ. DuckDB. ⚠ ~3.5 days, in-sample.

  PYTHONPATH=src python scripts/l2_dynamics_probe.py [--delta 30] [--horizon 15]
"""
from __future__ import annotations

import argparse

import duckdb
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta", type=int, default=30, help="rate window in seconds")
    ap.add_argument("--horizon", type=int, default=15, help="forward horizon in minutes")
    ap.add_argument("--levels", type=int, default=3)
    a = ap.parse_args()
    D, H, L = a.delta, a.horizon, a.levels
    con = duckdb.connect()
    con.execute("ATTACH '/home/alphabot/gazbot7/data/capture.db' AS c (TYPE sqlite, READ_ONLY)")

    con.execute(f"""
        CREATE TABLE snap AS
        SELECT ts_ms,
               COALESCE(SUM(CASE WHEN side='bid' THEN size END),0) bid,
               COALESCE(SUM(CASE WHEN side='ask' THEN size END),0) ask
        FROM c.book WHERE symbol='MNQ' AND level<={L} GROUP BY ts_ms HAVING bid>0 AND ask>0""")
    # per-second book state (ASOF latest snapshot ≤ second) over the covered window
    sec = con.execute("""
        WITH sp AS (SELECT DISTINCT CAST(ts_ms/1000 AS BIGINT) s FROM snap)
        SELECT sp.s, x.bid, x.ask FROM sp ASOF JOIN snap x ON x.ts_ms <= sp.s*1000 ORDER BY sp.s""").df()
    # 1-min closes for the forward move
    bars = con.execute("""SELECT (bar_ts-bar_ts%60) t, arg_max(close,bar_ts) cl FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1 ORDER BY t""").df()
    con.close()

    s = sec.set_index("s")
    s["askshare"] = s.ask / (s.ask + s.bid)
    s["total"] = s.ask + s.bid
    s = s.reindex(range(int(s.index.min()), int(s.index.max()) + 1)).ffill()
    s["d_ask"] = s.askshare - s.askshare.shift(D)                    # Δ askshare over D sec
    s["d_tot"] = (s.total - s.total.shift(D)) / s.total.shift(D)     # fractional Δ total depth

    b = bars.set_index("t")
    b["fwd"] = b.cl.shift(-H) - b.cl
    b = b.join(s[["askshare", "d_ask", "d_tot"]], how="inner").dropna(subset=["fwd", "d_ask", "d_tot"])
    b = b[b.index >= int(sec.s.min())]
    n = len(b)
    print(f"L2 DYNAMICS — rate Δ{D}s · horizon {H}min · top-{L} · {n} minute-samples\n")

    # A — directional depletion RATE
    cA = np.corrcoef(b.d_ask, b.fwd)[0, 1]
    b["pred_up"] = b.d_ask < 0                                       # asks thinning faster → up
    b["fwd_dir"] = np.where(b.pred_up, b.fwd, -b.fwd)
    print(f"A· DIRECTIONAL  corr(d_askshare, fwd) = {cA:+.3f}   [strong NEG = fast ask-thinning leads UP]")
    print(f"  {'|d_askshare| band':>18}{'n':>7}{'%continued':>12}{'mean fwd_dir':>14}")
    b["adr"] = b.d_ask.abs()
    for lo_e, hi_e in [(0, .02), (.02, .05), (.05, .10), (.10, .20), (.20, 1)]:
        g = b[(b.adr >= lo_e) & (b.adr < hi_e)]
        if len(g) < 5:
            continue
        print(f"  {f'{lo_e:.2f}-{hi_e:.2f}':>18}{len(g):>7}{100*(g.fwd_dir>0).mean():>11.0f}%{g.fwd_dir.mean():>+13.1f}")

    # B — run-imminence: does fast TOTAL thinning precede bigger |moves|?
    b["afwd"] = b.fwd.abs()
    cB = np.corrcoef(-b.d_tot, b.afwd)[0, 1]                         # -d_tot = thinning rate (positive = thinning)
    print(f"\nB· RUN-IMMINENCE  corr(total-thinning rate, |fwd|) = {cB:+.3f}   "
          f"[POS = fast thinning precedes bigger moves = a run detector]")
    print(f"  baseline mean |fwd {H}m| = {b.afwd.mean():.1f}pt")
    print(f"  {'total-depth Δ%':>16}{'n':>7}{'mean|fwd|':>11}{'P(|fwd|>60pt)':>15}")
    qs = b.d_tot.quantile([0, .2, .4, .6, .8, 1.0]).values
    labels = ["fastest-thin", "thinning", "flat", "building", "fastest-build"]
    for k in range(5):
        g = b[(b.d_tot >= qs[k]) & (b.d_tot <= qs[k + 1])]
        if len(g) < 5:
            continue
        print(f"  {labels[k]:>16}{len(g):>7}{g.afwd.mean():>10.1f}{100*(g.afwd>60).mean():>14.0f}%")
    print("\n(A green/strong signal here = a genuinely new leading tell in the book DYNAMICS. "
          "Rate/derivative is what real run-detection keys on — worth the look regardless of the level result.)")


if __name__ == "__main__":
    main()
