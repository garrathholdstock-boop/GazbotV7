#!/usr/bin/env python3
"""EFFICIENCY RATIO, BY BAR SIZE — because "no trend day" is not a fact until you name the ruler.

★ WHY (2026-08-30, Rev 3). The report quotes three different ER sets for the SAME five sessions:
the headline "0.017 to 0.032", Part 1.6 §5 "0.002 to 0.059", and Part 3 Q5's 5-minute path where
W35's best day is 0.101. Q5 diagnosed the cause itself — ER is net-move / path-travelled, and
path-travelled depends entirely on the bar you sample it with, so "ER >= 0.15" counts 0, 6, 18, 27
or 34 trend days on the same tape depending purely on bar size — and then the headline was left
uncorrected while at least four recommendations are gated on the definition.

This prints the week's five sessions at every bar size the desk uses, on ONE definition:
    ER = |close(last) - close(first)| / sum(|close(i) - close(i-1)|)   over the session's bars
RTH session = 13:30-20:00Z. Whole day = the desk's own 22:00Z-to-22:00Z Paris boundary.

  PYTHONPATH=src .venv/bin/python scripts/rev3_er_by_barsize.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev3_er_barsize.json"
DAYS = ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]
SIZES = [("5s", 5), ("1m", 60), ("5m", 300), ("15m", 900), ("30m", 1800)]
TREND_BAR = 0.15    # the desk's own "this is a trend" line


def er(px):
    if len(px) < 3:
        return None
    path = sum(abs(px[i] - px[i - 1]) for i in range(1, len(px)))
    return abs(px[-1] - px[0]) / path if path else None


def main():
    con = connect()
    res = {"definition": "|net close-to-close| / sum(|bar-to-bar close moves|)",
           "trend_bar": TREND_BAR, "days": {}}
    for d in DAYS:
        day = dt.date.fromisoformat(d)
        rth0 = int(dt.datetime.combine(day, dt.time(13, 30), dt.UTC).timestamp())
        rth1 = int(dt.datetime.combine(day, dt.time(20, 0), dt.UTC).timestamp())
        wd0 = int((dt.datetime.combine(day, dt.time(22, 0), dt.UTC) - dt.timedelta(days=1)).timestamp())
        wd1 = int(dt.datetime.combine(day, dt.time(22, 0), dt.UTC).timestamp())
        row = {}
        for lab, sec in SIZES:
            for span, a, b in (("rth", rth0, rth1), ("whole_day", wd0, wd1)):
                px = [r[1] for r in con.execute(
                    "SELECT ts_ms//? AS b, arg_max(price, ts_ms) FROM ticks WHERE symbol='MNQ' "
                    "AND ts_ms>=? AND ts_ms<? GROUP BY b ORDER BY b",
                    [sec * 1000, a * 1000, b * 1000]).fetchall()]
                v = er(px)
                row[f"{span}_{lab}"] = None if v is None else round(v, 4)
                row[f"{span}_{lab}_bars"] = len(px)
        res["days"][d] = row
    # how many "trend days" the same week has at each bar size
    res["trend_days_by_barsize"] = {
        lab: {span: sum(1 for d in DAYS
                        if (res["days"][d][f"{span}_{lab}"] or 0) >= TREND_BAR)
              for span in ("rth", "whole_day")}
        for lab, _ in SIZES}
    json.dump(res, open(OUT, "w"), indent=1)

    hdr = "day        " + "".join(f"{lab:>9}" for lab, _ in SIZES)
    for span in ("rth", "whole_day"):
        print(f"\n=== {span} ===\n{hdr}")
        for d in DAYS:
            print(f"{d} " + "".join(f"{res['days'][d][f'{span}_{lab}']:>9}" for lab, _ in SIZES))
        print("trend days" + "".join(f"{res['trend_days_by_barsize'][lab][span]:>9}" for lab, _ in SIZES)
              + f"   (ER >= {TREND_BAR})")
    print("\n->", OUT)


if __name__ == "__main__":
    main()
