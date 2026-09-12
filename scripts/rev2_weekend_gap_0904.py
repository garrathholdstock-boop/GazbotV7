#!/usr/bin/env python3
"""THE WEEKEND CARRY — price the open 4-lot rider long and bound the Sunday-reopen risk.

★ WHY. At 2026-09-04 21:00Z the desk went into the weekend with FOUR MNQ lots long. This prices
that position, and bounds what the 22:00Z Sunday reopen can do to it from the reopens we actually
have on tape rather than from a feeling.

★ WHERE THE TAPE COMES FROM, and why not the lake. data/tape has NO Sunday partitions at all
(SATURDAY #11 on the card) — 07-19, 07-26, 08-02, 08-09, 08-16, 08-23 and 08-30 are simply absent,
so a lake-based reopen study would silently measure Friday-close to MONDAY-open and call it a
reopen gap. capture.db DOES hold them: 5s bars, ~1,438 per Sunday from 22:00Z. Its bars table is a
60-day window, which is exactly long enough for the seven Sundays we own.

  GAP  = the first Sunday 22:00Z print minus the last Friday 21:00Z print, in points and in $ on
         the position's actual size. Signed FOR THE OPEN POSITION (a long is hurt by a gap down).
  FIRST HOUR = the worst excursion in the first 60 minutes of the reopen, because the gap alone
         understates the risk of a position with no stop at the venue (PLACE_VENUE_STOP = False).

  PYTHONPATH=src .venv/bin/python scripts/rev2_weekend_gap_0904.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import statistics

import duckdb

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/sections/rev2_weekend_gap_0904.json"
VPP = 2.0                                  # MNQ = $2.00/point. MGC would be $10.00 — not this book.


def main() -> int:
    st = json.loads(pathlib.Path(f"{GB}/data/day_rider_state.json").read_text())
    qty, entry, direction = st["qty"], st["entry"], st["direction"]
    ahead = st["ahead_pt"]

    con = duckdb.connect()
    con.execute(f"ATTACH '{GB}/data/capture.db' AS c (TYPE sqlite, READ_ONLY)")
    days = con.execute("""
        SELECT strftime(to_timestamp(bar_ts),'%Y-%m-%d') d, min(bar_ts) lo, max(bar_ts) hi
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    bydate = {d: (lo, hi) for d, lo, hi in days}

    rows = []
    for d, (lo, hi) in sorted(bydate.items()):
        if dt.date.fromisoformat(d).weekday() != 6:          # Sundays only
            continue
        fri = (dt.date.fromisoformat(d) - dt.timedelta(days=2)).isoformat()
        if fri not in bydate:
            continue
        fclose = con.execute("""
            SELECT close FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
              AND bar_ts = (SELECT max(bar_ts) FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
                            AND strftime(to_timestamp(bar_ts),'%Y-%m-%d') = ?)""", [fri]).fetchone()[0]
        sopen = con.execute("""
            SELECT open, bar_ts FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
              AND bar_ts = ?""", [lo]).fetchone()
        first_h = con.execute("""
            SELECT min(low), max(high) FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
              AND bar_ts >= ? AND bar_ts < ?""", [lo, lo + 3600]).fetchall()[0]
        gap = sopen[0] - fclose
        rows.append(dict(sunday=d, friday=fri, fri_close=fclose, sun_open=sopen[0],
                         gap_pt=round(gap, 2),
                         first_hour_low=first_h[0], first_hour_high=first_h[1],
                         worst_for_long_pt=round(first_h[0] - fclose, 2),
                         worst_for_short_pt=round(first_h[1] - fclose, 2)))
    con.close()

    gaps = [r["gap_pt"] for r in rows]
    longw = [r["worst_for_long_pt"] for r in rows]
    res = dict(
        run_at=dt.datetime.now(dt.UTC).isoformat(),
        position=dict(qty=qty, entry=entry, direction="LONG" if direction > 0 else "SHORT",
                      ahead_pt=ahead, unrealised_usd=round(ahead * qty * VPP, 2),
                      venue_ok=st["venue_ok"], venue_net_ts=st["venue_net_ts"],
                      flatten_blocked=st["flatten_blocked"], note=st["note"]),
        sundays=rows, n=len(rows),
        gap_abs_median=round(statistics.median(abs(g) for g in gaps), 2) if gaps else None,
        gap_abs_max=round(max(abs(g) for g in gaps), 2) if gaps else None,
        gap_worst_down=round(min(gaps), 2) if gaps else None,
        gap_worst_up=round(max(gaps), 2) if gaps else None,
        first_hour_worst_for_long=round(min(longw), 2) if longw else None,
        first_hour_median_for_long=round(statistics.median(longw), 2) if longw else None,
    )
    # what each of those does to THIS position, at THIS size
    res["on_this_position_usd"] = dict(
        median_gap=round(res["gap_abs_median"] * qty * VPP, 2),
        worst_gap_down=round(res["gap_worst_down"] * qty * VPP, 2),
        worst_first_hour=round(res["first_hour_worst_for_long"] * qty * VPP, 2),
        median_first_hour=round(res["first_hour_median_for_long"] * qty * VPP, 2),
    )

    p = res["position"]
    print(f"OPEN: {p['direction']} {p['qty']:.0f} @ {p['entry']:,.2f} · ahead {p['ahead_pt']:+.1f}pt "
          f"= {p['unrealised_usd']:+,.2f} USD · venue_ok={p['venue_ok']} since {p['venue_net_ts']}")
    print(f"\n{len(rows)} Sunday reopens on tape (capture.db 5s bars):")
    print(f"{'Sunday':<12}{'Fri close':>11}{'Sun open':>11}{'gap pt':>9}{'1st-hr low':>12}{'worst for a LONG':>19}")
    for r in rows:
        print(f"{r['sunday']:<12}{r['fri_close']:>11,.2f}{r['sun_open']:>11,.2f}{r['gap_pt']:>+9.2f}"
              f"{r['first_hour_low']:>12,.2f}{r['worst_for_long_pt']:>+19.2f}")
    print(f"\nmedian |gap| {res['gap_abs_median']}pt · worst gap DOWN {res['gap_worst_down']}pt · "
          f"worst first hour for a long {res['first_hour_worst_for_long']}pt")
    print(f"on {qty:.0f} lots: median gap ${res['on_this_position_usd']['median_gap']:,.2f} · "
          f"worst gap ${res['on_this_position_usd']['worst_gap_down']:,.2f} · "
          f"worst first hour ${res['on_this_position_usd']['worst_first_hour']:,.2f}")
    pathlib.Path(OUT).write_text(json.dumps(res, indent=1))
    print("->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
