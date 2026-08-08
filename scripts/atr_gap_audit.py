#!/usr/bin/env python3
"""ATR GAP AUDIT — how often has a session break inflated entry ATR, and what did it cost?

Found 2026-08-03. `deciders._atr` computes true range as
    max(high-low, |high - prev_close|, |low - prev_close|)
with no awareness that `prev_close` may be on the far side of a session halt. `MinuteBars` folds 5s
bars into 1-minute bars and never marks discontinuities, so two bars 50 hours apart sit adjacent in
the deque and the weekend gap enters true range as a single enormous bar.

Live consequence on the 2026-08-02 22:00 reopen: the gap was 283.5pt (Fri close 28,284 → Sun open
28,567.5). Two abs_veto_long lots entered at 22:02 with an implied entry ATR of 42.8 / 46.0pt while the
actual 1-minute bar was ~15pt. Because the desk's stop is 1.0xATR and its targets are R-multiples,
that ONE number mis-sized everything at once:
  * stops 43-46pt wide instead of ~15pt — 3x the intended risk
  * the quiet-tape clip (arms below ATR 22) stayed OFF, so a 15pt tape was treated as big-tape
  * the 1.0R target sat at $86-92, so a +$68 move never reached it
Both went green and gave it all back: -$180.5 combined.

This script measures how widespread that is. For every live closed trade it rebuilds the desk's own
1-minute bars from capture and computes ATR two ways:
    naive  — exactly as deciders._atr does today (gap-blind)
    clean  — identical, except a true-range term is dropped when the bar is not contiguous with its
             predecessor (>GAP_S apart). The high-low term is always kept; only the two gap terms go.
Cost is estimated on STOPPED trades only, where the stop distance is 1.0xATR by construction, so the
excess loss is (naive-clean) x VPP x qty. Untouched trades cost nothing and are reported separately.

  PYTHONPATH=src ./.venv/bin/python scripts/atr_gap_audit.py [--ratio 1.25]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime

sys.path.insert(0, "/home/alphabot/gazbot7/src")
import duckdb  # noqa: E402

GB = "/home/alphabot/gazbot7"
VPP, ATR_N = 2.0, 14
GAP_S = 90          # >90s between consecutive 1-min bars = a discontinuity, not a quiet minute
LOOKBACK_S = 3600


def bars_before(con, t_s: int):
    """The desk's own 1-minute bars, folded from 5s exactly as MinuteBars does.

    ★ Selected by COUNT, not by time window. MinuteBars is a `deque(maxlen=...)` — it holds the last N
    bars whatever their timestamps, and a session halt does not flush it. Emulating it with a 1-hour
    window was wrong and silently hid the exact case being audited: at 22:02 on a reopen, the trailing
    hour is nearly all halt, so only ~2 bars exist and the trade fell through as "no history". The live
    desk had a full 14-bar window there — reaching straight back over the weekend."""
    return con.execute(f"""
        SELECT m, h, l, c FROM (
          SELECT CAST(bar_ts/60 AS BIGINT)*60 m, MAX(high) h, MIN(low) l, ARG_MAX(close, bar_ts) c
          FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts < {t_s}
          GROUP BY 1 ORDER BY 1 DESC LIMIT {ATR_N + 1}
        ) ORDER BY m""").fetchall()


def atr_pair(rows):
    """(naive, clean, n_gap_terms_dropped). naive = today's gap-blind _atr."""
    if len(rows) < ATR_N + 1:
        return None, None, 0
    naive, clean, dropped = [], [], 0
    for i in range(1, len(rows)):
        m, h, lo, _ = rows[i]
        pm, _, _, pc = rows[i - 1]
        hl = h - lo
        contiguous = (m - pm) <= GAP_S
        naive.append(max(hl, abs(h - pc), abs(lo - pc)))
        if contiguous:
            clean.append(max(hl, abs(h - pc), abs(lo - pc)))
        else:
            clean.append(hl)      # keep the bar's own range, drop the cross-halt gap terms
            dropped += 1
    a = sum(naive[-ATR_N:]) / len(naive[-ATR_N:])
    b = sum(clean[-ATR_N:]) / len(clean[-ATR_N:])
    return a, b, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratio", type=float, default=1.25, help="flag when naive/clean exceeds this")
    a = ap.parse_args()

    sq = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    sq.row_factory = sqlite3.Row
    con = duckdb.connect()
    con.execute(f"ATTACH '{GB}/data/capture.db' AS c (READ_ONLY)")

    rows = list(sq.execute("SELECT * FROM trades WHERE closed_at IS NOT NULL ORDER BY opened_at"))
    hits, n_ok, n_nodata, excess_total = [], 0, 0, 0.0
    for t in rows:
        t0 = int(datetime.fromisoformat(t["opened_at"]).timestamp())
        naive, clean, dropped = atr_pair(bars_before(con, t0))
        if naive is None or not clean:
            n_nodata += 1
            continue
        ratio = naive / clean if clean else 1.0
        if ratio <= a.ratio:
            n_ok += 1
            continue
        excess = 0.0
        if (t["exit_reason"] or "").startswith("STOP"):
            excess = (naive - clean) * VPP * (t["qty"] or 1)   # stop = 1.0xATR by construction
            excess_total += excess
        hits.append((t, naive, clean, ratio, dropped, excess))

    print(f"\nATR GAP AUDIT — {len(rows)} closed trades  "
          f"({n_ok} clean, {len(hits)} contaminated, {n_nodata} no bar history)\n")
    if hits:
        print(f"{'opened (UTC)':<20}{'gate':<20}{'naive':>7}{'clean':>7}{'x':>6}{'gaps':>6}"
              f"{'exit':<14}{'pnl':>9}{'excess risk':>12}")
        for t, naive, clean, ratio, dropped, excess in hits:
            print(f"{t['opened_at'][:19]:<20}{t['gate']:<20}{naive:>7.1f}{clean:>7.1f}{ratio:>6.2f}"
                  f"{dropped:>6}{(t['exit_reason'] or '')[:13]:<14}{t['pnl_usd']:>9.2f}"
                  f"{('$%.0f' % excess) if excess else '—':>12}")
    print("\n" + "-" * 100)
    print(f"  contaminated trades      : {len(hits)} of {len(rows)-n_nodata} scoreable "
          f"({100*len(hits)/max(1,len(rows)-n_nodata):.1f}%)")
    print(f"  of those, STOPPED        : {sum(1 for h in hits if (h[0]['exit_reason'] or '').startswith('STOP'))}")
    print(f"  ★ excess risk taken      : ${excess_total:,.0f}  "
          f"(extra stop width forced by the inflated ATR, on stopped trades only)")
    print("-" * 100)
    print("  NOTE this is the DIRECT cost only. It does not count targets set too far to reach, or")
    print("  the quiet-tape clip failing to arm — both also keyed off the same inflated number.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
