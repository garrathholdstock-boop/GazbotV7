#!/usr/bin/env python3
"""WHAT DID THE TAPE LOOK LIKE AT THE MOMENTS HE DECIDED IT WAS A RUN? (2026-09-24)

Operator: "so what state tells me a run?" — after a 5-scale x 16-cell grid search of the tape gave
an answer that flipped with the horizon, which is what an 80-look search on 5 sessions does.

★★★ WHY THIS IS THE BETTER QUESTION. The grid asks "what does the tape do next", of a tape that
mostly does nothing in particular. This asks what was true at the 53 moments HIS judgement fired —
and his judgement is the thing on this desk with a measured edge: +$78.27/trade at 82% on single
lots, roughly 37x the automated gates' +$2.10. Eleven months and 119 calibrations failed to
reproduce it by reverse-engineering the OUTCOME; nobody had recorded the INPUT until 2026-09-14.

⚠⚠ THIS IS AN ENTRY QUESTION, NOT AN EXIT CALIBRATION. "Claiming cannot be backtested" is a
standing result about EXITS (119 failures, do not re-run). Nothing here touches the exit.

⚠ SINGLE-LOT P&L ONLY (`pnl_1lot`). The IBKR paper engine fabricates every lot beyond the first at
exactly 0.1% adverse, so any multi-lot figure is contaminated by a price that never printed.

⚠ PULSE reconstructs over 60 days (bars). FLOW only over ~5 (ticks are pruned) — the script says
how many presses each covers rather than quietly mixing two sample sizes.

⚠⚠ DAY-CLUSTERED. n=53 presses is not 53 independent draws; several land in one session.
"""
import json
import sqlite3
import sys

import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
CAP = f"{GB}/data/capture.db"


def press_side(pressed):
    s = str(pressed).upper()
    if "|SELL|" in s or "SELL" in s.split("|")[1:2]:
        return -1
    if "|BUY|" in s:
        return 1
    return np.nan


def main():
    d = pd.read_csv(f"{GB}/data/operator_reads_labelled.csv")
    d = d[d.kind == "buy"].copy()                      # ENTRIES only, never the claims
    d["dir"] = d.pressed.map(press_side)
    d["ts"] = pd.to_datetime(d.ts, utc=True, format="mixed")
    # ⚠⚠ NEVER `.astype("int64") // 10**9` ON A DATETIME SERIES. `format="mixed"` parses to
    # datetime64[us], not [ns], so that divides by a thousand too many and every timestamp lands in
    # 1970. It failed SILENTLY — the bar queries simply matched nothing and reported 0/38
    # reconstructions, which reads as "no data" rather than "wrong epoch".
    d["t"] = d.ts.map(lambda x: int(x.timestamp()))
    d["d"] = d.ts.dt.date

    # ★★★ THE LABEL IS REBUILT FROM THE ENTRY, NOT TAKEN FROM `pnl_1lot`.
    # ⚠⚠⚠ `pnl_1lot` CANNOT CONTAIN A LOSS. It sums the trades rows with qty==1, and those are the
    # LADDER RUNGS — TARGET_100 / TARGET_200 only fire in profit BY CONSTRUCTION. Verified on the
    # live book since 09-15: qty==1 is 36 rows, 36 wins, 0 losses; the losses live in the qty==4
    # closes (57 rows, 37 losses, -$10,461.50). So the "labelled" set is 53 winners and zero
    # losers, and `operator_reads_join.py` prints "the question is now answerable: what separates
    # his winners from his losers?" over a column with no losers in it.
    # ★ An ENTRY's P&L is the SUM OF ALL ITS EXIT ROWS. The rows in `trades` are scale-out exits of
    #   one decision — the desk's own rule, which the join violates.
    c0 = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    tr = pd.read_sql("SELECT qty,entry_price,pnl_usd,opened_at FROM trades WHERE gate='day_rider' "
                     "AND (data_quality IS NULL OR data_quality='')", c0)
    c0.close()
    tr["t0"] = pd.to_datetime(tr.opened_at, utc=True, format="mixed").map(lambda x: int(x.timestamp()))
    lab = []
    for t in d["t"]:
        near = tr[(tr.t0 >= t - 30) & (tr.t0 <= t + 300)]
        lab.append(float(near.pnl_usd.sum()) if len(near) else np.nan)
    d["pnl_entry"] = lab
    d = d.dropna(subset=["pnl_entry", "dir"]).copy()
    d["pnl_1lot"] = d["pnl_entry"]          # everything downstream reads the honest column
    d["win"] = (d.pnl_entry > 0).astype(float)

    c = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    pulse, flow = [], []
    for t in d["t"]:
        m0 = t - (t % 60)
        cur = c.execute("SELECT COALESCE(SUM(volume),0) FROM bars WHERE symbol='MNQ' AND "
                        "timeframe='5s' AND bar_ts>=? AND bar_ts<?", (m0 - 60, m0)).fetchone()[0]
        prev = [r[1] for r in c.execute(
            "SELECT CAST(bar_ts/60 AS INT) mm, COALESCE(SUM(volume),0) FROM bars WHERE "
            "symbol='MNQ' AND timeframe='5s' AND bar_ts>=? AND bar_ts<? GROUP BY mm",
            (m0 - 16 * 60, m0 - 60)).fetchall()]
        prev = [v for v in prev if v > 0]
        pulse.append(cur / sorted(prev)[len(prev) // 2]
                     if len(prev) >= 8 and sorted(prev)[len(prev) // 2] else np.nan)
        r = c.execute("SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size END),0), "
                      "COALESCE(SUM(CASE WHEN aggressor='sell' THEN size END),0) FROM ticks "
                      "WHERE symbol='MNQ' AND ts_ms>=? AND ts_ms<?",
                      ((t - 120) * 1000, t * 1000)).fetchone()
        tot = (r[0] or 0) + (r[1] or 0)
        flow.append(((r[0] - r[1]) / tot) if tot else np.nan)
    c.close()
    d["pulse"], d["flow"] = pulse, flow
    d["flow_aligned"] = d.flow * d["dir"]        # + = the aggressors leaned HIS way

    print(f"HIS PRESSES — {len(d)} labelled entries across {d.d.nunique()} sessions "
          f"({d.ts.min():%Y-%m-%d} to {d.ts.max():%Y-%m-%d})")
    print(f"  winners {int(d.win.sum())} · losers {int(len(d)-d.win.sum())} · "
          f"win rate {100*d.win.mean():.1f}% · median $/press {d.pnl_1lot.median():+.2f} "
          f"· total {d.pnl_1lot.sum():+.2f}")
    print(f"  PULSE reconstructed for {d.pulse.notna().sum()}/{len(d)} (bars, 60d)")
    print(f"  FLOW  reconstructed for {d.flow.notna().sum()}/{len(d)} (ticks, PRUNED AT 5 DAYS)\n")

    print(f"{'feature':<18} {'winners (median)':>18} {'losers (median)':>18} {'n w/l':>10}")
    print("-" * 68)
    for f, lab in [("pulse", "PULSE"), ("flow_aligned", "FLOW (his way)"), ("atr", "ATR"),
                   ("pos_in_range", "POS IN RANGE"), ("vwap_stretch", "VWAP STRETCH")]:
        x = d.dropna(subset=[f])
        w, l = x[x.win == 1][f], x[x.win == 0][f]
        if len(w) < 3 or len(l) < 3:
            print(f"{lab:<18} {'(too few)':>18}")
            continue
        print(f"{lab:<18} {w.median():>18.3f} {l.median():>18.3f} {f'{len(w)}/{len(l)}':>10}")

    # ⚠ A SPLIT CHOSEN AFTER SEEING THE DATA IS NOT A TEST. Reported as description only.
    print("\nPRESSES SPLIT BY PULSE AT ENTRY (descriptive — this split was chosen after looking):")
    x = d.dropna(subset=["pulse"])
    for lo, hi, lab in [(0, 1.0, "pulse <1.0  quiet"), (1.0, 1.5, "pulse 1.0-1.5"),
                        (1.5, 99, "pulse >=1.5 expanding")]:
        s = x[(x.pulse >= lo) & (x.pulse < hi)]
        if len(s) < 3:
            print(f"  {lab:<24} n={len(s)}  (too few)")
            continue
        print(f"  {lab:<24} n={len(s):>3}  win {100*s.win.mean():>5.1f}%  "
              f"median ${s.pnl_1lot.median():>+7.2f}  total ${s.pnl_1lot.sum():>+9.2f}  "
              f"({s.d.nunique()} sessions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
