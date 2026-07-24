#!/usr/bin/env python3
"""Is abs_veto_55s REAL? — robustness battery on the shadow variant before a Monday promotion.

abs_veto_55s = thrust + a 55s delayed-entry absorption veto (skip a thrust that gets absorbed). It's
#1 on the shadow board, but a top-line total can be one lucky week or one regime. This stress-tests it:
  1. Headline stats (n, net, win%, avg W/L, worst, expectancy, max drawdown).
  2. PER-DAY consistency — is the edge spread, or 1-2 lucky days carrying it?
  3. REGIME split (ER at entry, 30-min) — does it hold in chop AND trend, or only one?
  4. WALK-FORWARD halves — first half vs second half of its history (out-of-sample proxy).
  5. HEAD-TO-HEAD vs the un-vetoed thrust (thrust_loose) over the SAME window — is the veto's
     incremental edge consistent, or noise?
Tick-repriced real_pnl only. DuckDB. Read-only.

  PYTHONPATH=src python scripts/abs_veto_robustness.py
"""
from __future__ import annotations

import duckdb

SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
VAR = "abs_veto_55s"
BASE = "thrust_loose"   # the un-vetoed thrust — the veto's incremental edge is VAR minus this


def stats(rows):
    """rows = list of real_pnl. Returns dict of headline stats + max drawdown on the equity curve."""
    n = len(rows)
    if not n:
        return None
    net = sum(rows)
    w = [p for p in rows if p > 0]
    losses = [p for p in rows if p <= 0]
    eq, peak, dd = 0.0, 0.0, 0.0
    for p in rows:
        eq += p
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return dict(n=n, net=net, winpct=100 * len(w) / n, avgW=sum(w) / len(w) if w else 0,
                avgL=sum(losses) / len(losses) if losses else 0, worst=min(rows), exp=net / n, maxdd=dd)


def line(label, rows):
    s = stats(rows)
    if not s:
        print(f"  {label:20} (no trades)")
        return
    print(f"  {label:20} n={s['n']:>3}  net=${s['net']:>+6.0f}  win={s['winpct']:>3.0f}%  "
          f"avgW=${s['avgW']:>+5.0f} avgL=${s['avgL']:>+5.0f}  worst=${s['worst']:>+5.0f}  "
          f"exp=${s['exp']:>+5.1f}/tr  maxDD=${s['maxdd']:>+6.0f}")


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{SHADOW}' AS s (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    # 30-min ER at each entry (regime split), reused from the filter-check pattern
    con.execute("""
        CREATE TABLE feat AS
        WITH m1 AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c
                    FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1),
        st AS (SELECT m, c, abs(c-lag(c) OVER w) step FROM m1 WINDOW w AS (ORDER BY m))
        SELECT m, abs(c-first_value(c) OVER w30)/NULLIF(SUM(step) OVER w30,0) er
        FROM st WINDOW w30 AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")

    def pull(strat):
        return con.execute(f"""
            WITH t AS (SELECT entry_ts, id FROM s.shadow_trades WHERE strategy='{strat}')
            SELECT t.entry_ts, r.real_pnl, f.er,
                   strftime(to_timestamp(t.entry_ts + 7200), '%m-%d') AS pday
            FROM t JOIN s.shadow_real r ON r.trade_id=t.id
            ASOF LEFT JOIN feat f ON f.m <= t.entry_ts
            ORDER BY t.entry_ts""").fetchall()

    v = pull(VAR)
    if not v:
        print(f"no {VAR} trades.")
        return
    b = pull(BASE)
    con.close()
    vp = [r[1] for r in v]

    print(f"═══ ROBUSTNESS: {VAR} (tick-repriced real_pnl) ═══\n")
    print("1) HEADLINE")
    line(VAR, vp)

    print("\n2) PER-DAY (is it spread, or 1-2 lucky days?)")
    days = {}
    for _ts, p, _er, d in v:
        days.setdefault(d, []).append(p)
    for d in sorted(days):
        dp = days[d]
        print(f"     {d}: {len(dp):>2}tr  ${sum(dp):>+6.0f}  ({100*sum(1 for x in dp if x>0)/len(dp):>3.0f}% win)")
    green = sum(1 for d in days.values() if sum(d) > 0)
    print(f"     → {green}/{len(days)} days green; top day = ${max(sum(d) for d in days.values()):+.0f}, "
          f"worst day = ${min(sum(d) for d in days.values()):+.0f}")

    print("\n3) REGIME (ER at entry: chop<0.18 · trend>=0.18)")
    line("chop (ER<0.18)", [r[1] for r in v if r[2] is not None and r[2] < 0.18])
    line("trend (ER>=0.18)", [r[1] for r in v if r[2] is not None and r[2] >= 0.18])

    print("\n4) WALK-FORWARD (first half vs second half by trade order)")
    h = len(vp) // 2
    line("first half", vp[:h])
    line("second half", vp[h:])

    print(f"\n5) HEAD-TO-HEAD vs un-vetoed {BASE} (same board, overlapping window)")
    line(VAR, vp)
    line(BASE, [r[1] for r in b])
    print(f"     → veto's incremental edge = ${sum(vp) - sum(r[1] for r in b):+.0f} "
          f"(abs_veto_55s − thrust_loose, whole board)")
    print("\n⚠ 1-lot shadow sims, tick-repriced. ~9-day one-summer-regime sample — a LEAD, not proof;")
    print("  the forward shadow run (it trades live observe-only) is the real out-of-sample test.")


if __name__ == "__main__":
    main()
