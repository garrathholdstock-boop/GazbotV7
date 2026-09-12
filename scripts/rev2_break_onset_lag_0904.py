#!/usr/bin/env python3
"""BUILD #1, ANSWERED — the lag between a break STARTING and abs_veto_short's trigger FIRING.

★ THE QUESTION. The 08-28 report named abs_veto_short's silence "the week's #1 stone": armed for
46m30s of a 328-point one-directional break and zero signals, with its two nearest signals landing
4 minutes before the arm and 5 minutes after the bench, both losing. Its hypothesis was a PHASE GAP
— "the router arms when a break is CONFIRMED; a thrust gate needs the moment a break STARTS, and on
Friday those were about 25 minutes apart" — and its play was to measure it before changing anything.
Its kill line: "if the measured lag is under ~5 minutes, the hypothesis is wrong."

★ WHY IT IS ANSWERABLE NOW AND WAS NOT THEN. On 08-28 the gate produced NO triggers, so there was no
trigger time to subtract an onset from — the report was reasoning about an absence. On 2026-09-01 it
fired TWICE and won all four legs (+$163.50). Two clean cases with real timestamps move a mechanism
question in a way a fortnight of silence cannot.

★ THE THREE CLOCKS, defined once, measured on the 250ms tape (capture.db ticks, 1-min bars built
from them so the ER/ATR match the deciders' own convention):

  ONSET    the swing extreme the move departed from — walking back from the trigger, the most
           recent 1-minute bar whose high (for a DOWN break) is the maximum of the 60 minutes
           before it. This is "the moment the break starts", the thing a thrust gate needs.
  CONFIRM  the first minute at which the open-hour watcher's own break trio is all true:
           ER(30) >= 0.35 on 1-min closes, ATR-14 >= 18, and a NEW EXTREME of the session so far.
           This is what the ROUTER waits for; it is quoted verbatim in gate_switches.env's header.
  TRIGGER  the gate's own entry, from trades.opened_at.

  PYTHONPATH=src .venv/bin/python scripts/rev2_break_onset_lag_0904.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sqlite3
import sys

import duckdb

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/sections/rev2_break_lag_0904.json"


def minute_bars(con, t0: int, t1: int):
    return con.execute("""
        SELECT (ts_ms/1000)::BIGINT - ((ts_ms/1000)::BIGINT % 60) AS m,
               min(price) lo, max(price) hi,
               arg_min(price, ts_ms) o, arg_max(price, ts_ms) c_dummy,
               arg_max(price, ts_ms) AS ignore2
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms >= ? AND ts_ms < ?
        GROUP BY 1 ORDER BY 1""", [t0 * 1000, t1 * 1000]).fetchall()


def series(con, t0: int, t1: int):
    """1-min OHLC from the tick tape. arg_max over ts_ms gives the true close."""
    return con.execute("""
        SELECT (ts_ms/1000)::BIGINT - ((ts_ms/1000)::BIGINT % 60) AS m,
               arg_min(price, ts_ms) AS o, max(price) AS h, min(price) AS l,
               arg_max(price, ts_ms) AS c
        FROM c.ticks WHERE symbol='MNQ' AND ts_ms >= ? AND ts_ms < ?
        GROUP BY 1 ORDER BY 1""", [t0 * 1000, t1 * 1000]).fetchall()


def er(closes):
    """Kaufman efficiency ratio over the window — deciders/run_census convention."""
    if len(closes) < 2:
        return 0.0
    path = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
    return abs(closes[-1] - closes[0]) / path if path else 0.0


def atr14(bars):
    """True-range ATR-14 on 1-min bars — the gate's own unit, not a mean range."""
    if len(bars) < 15:
        return 0.0
    trs = []
    for (pm, po, ph, pl, pc), (m, o, h, l, c) in zip(bars[-15:], bars[-14:]):
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs)


def main() -> int:
    db = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    sigs = db.execute(
        "SELECT DISTINCT opened_at, side, entry_price FROM trades "
        "WHERE gate LIKE 'abs_veto_short%' AND closed_at >= '2026-08-31' "
        "AND data_quality IS NULL ORDER BY opened_at").fetchall()
    db.close()
    if not sigs:
        print("no abs_veto_short signals in the window — nothing to measure.")
        return 1

    con = duckdb.connect()
    con.execute(f"ATTACH '{GB}/data/capture.db' AS c (TYPE sqlite, READ_ONLY)")

    out = []
    for opened_at, side, px in sigs:
        trig = dt.datetime.fromisoformat(opened_at)
        tt = int(trig.timestamp())
        # three hours of context before the trigger is plenty for a 60-min lookback plus onset
        bars = series(con, tt - 3 * 3600, tt + 60)
        idx = {m: i for i, (m, *_) in enumerate(bars)}
        tmin = tt - tt % 60
        i_tr = idx.get(tmin, len(bars) - 1)
        down = side == "SHORT"

        # ── ONSET: walk back for the most recent 60-min extreme in the move's origin direction
        onset = None
        for i in range(i_tr, 14, -1):
            win = bars[max(0, i - 60):i + 1]
            if not win:
                continue
            ext = max(b[2] for b in win) if down else min(b[3] for b in win)
            here = bars[i][2] if down else bars[i][3]
            if here == ext:
                onset = bars[i]
                break

        # ── CONFIRM: first minute at or before the trigger where the watcher's trio is true
        confirm = None
        sess0 = int(dt.datetime(trig.year, trig.month, trig.day, 0, 0, tzinfo=dt.UTC).timestamp())
        for i in range(30, i_tr + 1):
            w = bars[max(0, i - 29):i + 1]
            e = er([b[4] for b in w])
            a = atr14(bars[max(0, i - 20):i + 1])
            sess = [b for b in bars[:i + 1] if b[0] >= sess0]
            if not sess:
                continue
            newext = (bars[i][3] == min(b[3] for b in sess)) if down else \
                     (bars[i][2] == max(b[2] for b in sess))
            if e >= 0.35 and a >= 18 and newext:
                confirm = (bars[i][0], round(e, 3), round(a, 1))
                break

        row = dict(
            trigger=trig.isoformat(), side=side, entry=px,
            onset=dt.datetime.fromtimestamp(onset[0], dt.UTC).isoformat() if onset else None,
            onset_px=onset[2] if (onset and down) else (onset[3] if onset else None),
            onset_to_trigger_min=round((tt - onset[0]) / 60, 1) if onset else None,
            confirm=dt.datetime.fromtimestamp(confirm[0], dt.UTC).isoformat() if confirm else None,
            confirm_er=confirm[1] if confirm else None,
            confirm_atr=confirm[2] if confirm else None,
            onset_to_confirm_min=round((confirm[0] - onset[0]) / 60, 1) if (confirm and onset) else None,
            confirm_to_trigger_min=round((tt - confirm[0]) / 60, 1) if confirm else None,
            move_pt=round((onset[2] - px) if (onset and down) else ((px - onset[3]) if onset else 0), 2),
        )
        out.append(row)

    con.close()

    # ── the fourth clock: when the ROUTER actually armed and benched the gate. Read from the
    # router's own trial log rather than from the journal or the switch file's mtime, because those
    # three disagree by design — the log under-reports (it is timer-driven) and the journal
    # over-reports. The `changed:` dict is the router's own record of the write it made.
    import re as _re
    log = pathlib.Path(f"{GB}/data/router_trial_log.txt").read_text(errors="replace")
    switches = []
    for blk in _re.split(r"(?m)^(?=\d{4}-\d{2}-\d{2}T)", log):
        m = _re.match(r"(\S+) \| \w+ \| \w+ \| changed: ([^|]*)\|", blk)
        if not m or "abs_veto_short" not in m.group(2):
            continue
        if any(r["trigger"][:10] == m.group(1)[:10] for r in out):
            switches.append((m.group(1), m.group(2).strip()))
    for t, ch in switches:
        print("ROUTER SWITCH", t, ch)

    for r in out:
        print(json.dumps(r, indent=1))
    lags = [r["onset_to_trigger_min"] for r in out if r["onset_to_trigger_min"] is not None]
    gaps = [r["onset_to_confirm_min"] for r in out if r["onset_to_confirm_min"] is not None]
    res = dict(run_at=dt.datetime.now(dt.UTC).isoformat(), rows=out, router_switches=switches,
               median_onset_to_trigger_min=sorted(lags)[len(lags) // 2] if lags else None,
               median_onset_to_confirm_min=sorted(gaps)[len(gaps) // 2] if gaps else None)
    print("\nmedian onset→trigger:", res["median_onset_to_trigger_min"], "min")
    print("median onset→confirm:", res["median_onset_to_confirm_min"], "min")
    pathlib.Path(OUT).write_text(json.dumps(res, indent=1))
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
