#!/usr/bin/env python3
"""METER SHOWDOWN — do the 0-10 tradeability gauge and the 0-100 stay-out meter predict anything?

Operator, 2026-08-05: "run the study to make them agree."

THE PROBLEM. Two meters read the same tape and disagree — on 08-05 the gauge said 6.0 MIXED while
stay-out said 94 STAY-OUT. Both are on the desk, neither has been validated against outcomes. The
gauge has one +0.50 correlation behind it; stay-out has a THREE-DAY comparison (07-29/30 green vs
07-31 red). That is not enough to trust either, let alone to reconcile them.

★★ THIS IS A PREDICTIVE TEST, NOT A DESCRIPTION.
A meter that reads the whole day and pronounces it untradeable is post-hoc and worthless — you cannot
act on it. So both meters are computed using ONLY data up to a CUTOFF (default 14:30 UTC, one hour
after the US open) and scored against what the tape did AFTERWARDS. That is the question that matters:
at the moment you must decide, does the number tell you anything about the rest of the session?

★ OUTCOME = THE SHADOW BOOK, not live P&L. Live P&L is confounded by which gates happened to be
armed — the router benches things, so a red live day may only mean we sat out correctly. The shadow
runs every gate unbenched, so its daily total is the honest counterfactual for "was this tape worth
trading". Scored on real_pnl (tick-repriced), never ceiling_pnl.

★ THE TAPE COMES FROM THE PARQUET LAKE. capture.db now holds only 5 trading days, so SQLite alone
could not run this. The lake holds ~13 days of bars, which is also the first real use of the archive
built last night — if the lake is unreadable, this study says so rather than silently using less data.

  PYTHONPATH=src .venv/bin/python scripts/meter_showdown.py [--cutoff 14:30]
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import sqlite3
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import tradeability, untradeable  # noqa: E402
from gazbot7.deciders import Bar, _atr  # noqa: E402
from gazbot7.sizing import efficiency_ratio  # noqa: E402

GB = "/home/alphabot/gazbot7"
LAKE = f"{GB}/data/tape"


def lake_days() -> list[str]:
    return sorted(os.path.basename(f)[:-8] for f in glob.glob(f"{LAKE}/bars/MNQ/*.parquet"))


def bars_for(con, day: str, upto_ep: int) -> list[Bar]:
    """1-min bars for `day` up to `upto_ep`, from the Parquet lake."""
    f = f"{LAKE}/bars/MNQ/{day}.parquet"
    rows = con.execute(f"""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
               arg_max(close, bar_ts) c
        FROM read_parquet('{f}') WHERE timeframe='5s' AND bar_ts < {upto_ep}
        GROUP BY 1 ORDER BY 1""").fetchall()
    return [Bar(ts=int(m), open=float(c), high=float(h), low=float(lo), close=float(c), volume=1.0)
            for m, h, lo, c in rows]


def gauge_at(bars: list[Bar]):
    """tradeability.score() on the same inputs live() uses — but as of the cutoff."""
    if len(bars) < 31:
        return None
    er = efficiency_ratio(bars, 30)
    atr = _atr(bars)
    w = bars[-30:]
    cl = [x.close for x in w]
    fav = max(max(cl) - cl[0], cl[0] - min(cl))
    now = abs(cl[-1] - cl[0])
    gb = 0.0 if fav <= 0 else max(0.0, min(1.0, 1.0 - now / fav))
    return tradeability.score(er, atr, gb)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="14:30", help="UTC HH:MM — meters see only data before this")
    a = ap.parse_args()
    ch, cm = (int(x) for x in a.cutoff.split(":"))

    days = lake_days()
    if not days:
        print("Parquet lake has no MNQ bars — nothing to study.")
        return 0
    con = duckdb.connect()
    sh = sqlite3.connect(f"file:{GB}/data/shadow.db?mode=ro", uri=True)

    print(f"METER SHOWDOWN — both meters computed from data BEFORE {a.cutoff} UTC,")
    print(f"scored against SHADOW real_pnl for entries AFTER it. {len(days)} days in the lake.\n")
    print(f"{'day':<12}{'gauge':>7}{'stay-out':>10}{'  their calls':<26}{'shadow AFTER':>13}{'  verdict'}")
    rows = []
    for d in days:
        t0 = int(dt.datetime.fromisoformat(d + "T00:00:00+00:00").timestamp())
        cut = t0 + ch * 3600 + cm * 60
        bars = bars_for(con, d, cut)
        g = gauge_at(bars)
        try:
            u = untradeable.compute(f"{GB}/data/capture.db", f"{GB}/data/gazbot7.db", t0, cut)
        except Exception:
            u = {}
        # outcome: shadow book for entries AFTER the cutoff
        r = sh.execute("SELECT COUNT(*), COALESCE(SUM(x.real_pnl),0) FROM shadow_trades t "
                       "JOIN shadow_real x ON x.trade_id=t.id "
                       "WHERE CAST(t.entry_ts AS BIGINT)>=? AND CAST(t.entry_ts AS BIGINT)<? "
                       "AND x.real_pnl IS NOT NULL", (cut, t0 + 86400)).fetchone()
        n_after, pnl_after = r[0], round(r[1], 1)
        if g is None or n_after < 5:
            continue
        gs, us = g.score, u.get("score")
        if us is None:
            continue
        # what each one SAID: gauge >=6 = tradeable; stay-out < 65 = tradeable
        g_says = "TRADE" if gs >= 6 else "SIT"
        u_says = "TRADE" if us < 65 else "SIT"
        agree = "agree" if g_says == u_says else "DISAGREE"
        rows.append((d, gs, us, g_says, u_says, n_after, pnl_after))
        print(f"{d:<12}{gs:>7.1f}{us:>10}{'  ' + g_says + ' / ' + u_says + ' (' + agree + ')':<26}"
              f"{pnl_after:>+12.0f}  {'green' if pnl_after > 0 else 'RED'}")

    if len(rows) < 3:
        print(f"\nOnly {len(rows)} usable days — not enough to conclude anything. "
              f"The lake needs more history, or the cutoff excludes too much.")
        return 0

    print("\n" + "=" * 78)

    def hit(idx, thresh, lower_is_trade):
        """How often did this meter's call match the day's actual sign?"""
        ok = 0
        for r in rows:
            says_trade = (r[idx] < thresh) if lower_is_trade else (r[idx] >= thresh)
            was_green = r[6] > 0
            ok += int(says_trade == was_green)
        return ok, len(rows)

    gok, n = hit(1, 6, False)
    uok, _ = hit(2, 65, True)
    print(f"CALL ACCURACY (did 'trade / sit' match the day's actual sign?)")
    print(f"  tradeability gauge (>=6 = trade)   {gok}/{n} = {100*gok/n:.0f}%")
    print(f"  stay-out meter    (<65 = trade)    {uok}/{n} = {100*uok/n:.0f}%")
    print(f"  a coin flip would be              ~{n//2}/{n} = 50%")

    dis = [r for r in rows if r[3] != r[4]]
    print(f"\nTHEY DISAGREED on {len(dis)}/{n} days.")
    if dis:
        gw = sum(1 for r in dis if (r[3] == "TRADE") == (r[6] > 0))
        print(f"  when they disagreed, the GAUGE was right {gw}/{len(dis)}, "
              f"stay-out {len(dis)-gw}/{len(dis)}")

    # correlation of each score with the outcome
    def corr(idx):
        xs = [r[idx] for r in rows]
        ys = [r[6] for r in rows]
        mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
        num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
        dx = sum((x-mx)**2 for x in xs) ** 0.5
        dy = sum((y-my)**2 for y in ys) ** 0.5
        return num/(dx*dy) if dx and dy else 0.0

    print(f"\nCORRELATION with shadow P&L after the cutoff (sign matters, magnitude is weak at this n):")
    print(f"  tradeability gauge  {corr(1):+.2f}   (expect POSITIVE — higher = more tradeable)")
    print(f"  stay-out meter      {corr(2):+.2f}   (expect NEGATIVE — higher = stay out)")
    print(f"\n★ n={n} days. Treat anything here as a LEAD. Two meters that both land near a coin flip")
    print("  do not need reconciling — they need replacing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
