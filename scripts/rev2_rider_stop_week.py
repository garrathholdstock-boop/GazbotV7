#!/usr/bin/env python3
"""REV2 — what the day rider's NO-STOP decision cost on THIS week's tape.

★ WHY. The rider is the bigger book. It moved the account by −$1,576.94 this week and owns the
week's single biggest loss. It still runs NAKED — `src/gazbot7/day_rider.py:102`,
`PLACE_VENUE_STOP = False`, "★★★ NO STOP. Operator, 2026-08-20". That is the operator's call and it
was taken on 231 lake sessions, not on a week. But Rev 1 of this report carried NOTHING fresh about
it: the only place it was discussed was Part 1.6, which did not regenerate and is quarantined behind
a banner the reader is explicitly told not to carry conclusions out of. A standing decision that is
never re-priced is indistinguishable from one nobody is watching. This prices it.

★ METHOD. Every rider POSITION of the report week (grouped by opened_at + entry price + side),
raced forward on MNQ trade ticks from the lake, at k x the ATR THE RIDER ITSELF FROZE AT ENTRY
(`arm_atr` in its own state file, read out of the systemd journal — not a modelled ATR):

    k in 0.5 / 0.75 / 1.0 / 1.25 / 1.5 / 2.0 / 3.0, plus NAKED = what actually happened.

One stop for the whole position. The first tick trading at or through it closes every leg still open
at that instant at the stop price; legs already closed keep their real exit. $2.00/point, $1.50 per
round trip per lot, charged either way. `trades.pnl_usd` is ALREADY NET of fees, so the naked
baseline is a plain sum of it — never `pnl_usd - fees_usd`, which double-charges.

★ THE CARRY. The 4-lot position opened 2026-08-21T13:13:06Z and closed by hand on 08-24 is included
and is the whole story. It is raced from its entry through to its real close, INCLUDING the ~49h CME
halt, during which no stop can fill — so the race pauses where the tape does, which is exactly the
point: a stop is not protection when the market is shut.

★★ AND THE THING THAT CAME OUT OF WRITING IT: THE ENTRY PRICES ARE NOT ON THE TAPE.
The first version of this script had a stop out at the entry SECOND on five of thirteen positions,
which is not a stop grid, it is an artefact. The cause is in the fills, not the code: every rider
entry this week is a SPLIT order whose residual leg is priced at base x (1 +/- 0.001) ADVERSE — the
known off-tape-fill pattern — and the trades row records the fill-VWAP of the two. 2026-08-26
13:44:06 bought 1 lot at 29,301.00 (on tape) and 3 at 29,330.00 (never traded within +/-10s), for a
booked entry of 29,322.75; 2026-08-28 12:39:06 bought 1 at 29,635.25 and 3 at 29,664.75. A stop
placed k x ATR under a price the market never printed is under water before the position exists.
So the grid below is raced off the ON-TAPE base price of each entry event, and the off-tape audit is
reported separately because it is worth more than the grid is.

  PYTHONPATH=src .venv/bin/python scripts/rev2_rider_stop_week.py
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect                                          # noqa: E402

DB = "file:/home/alphabot/gazbot7/data/gazbot7.db?mode=ro"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_rider_stop_week_0828.json"
MULT, FEE = 2.0, 1.50
WIDTHS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]

# arm_atr the rider FROZE at entry, read out of its own state snapshots in the systemd journal:
#   journalctl -u gazbot7-day-rider --since '2026-08-24' -o cat | grep -E '"(entry|arm_atr)"'
# 0.0 means the rider never armed a trail on that position (a manual entry, or one that never
# reached the arming threshold) — those are raced on a tape-measured ATR-14 instead and FLAGGED.
ARM_ATR = {
    "2026-08-21T13:13:06+00:00":        0.00,     # the carry — never armed
    "2026-08-25T13:38:06.744509+00:00": 30.62,
    "2026-08-26T13:44:06.794147+00:00": 36.25,
    "2026-08-27T07:20:06.837680+00:00":  0.00,
    "2026-08-27T13:34:06.865688+00:00":  0.00,
    "2026-08-27T13:35:06.928686+00:00":  0.00,
    "2026-08-27T13:42:06.824761+00:00": 39.31,
    "2026-08-27T16:58:06.815876+00:00":  8.30,
    "2026-08-27T17:03:06.894649+00:00":  8.38,
    "2026-08-28T12:39:06.838350+00:00":  0.00,
    "2026-08-28T13:54:06.910048+00:00": 23.00,
    "2026-08-28T14:47:06.821105+00:00": 20.95,
    "2026-08-28T15:01:06.826288+00:00": 15.12,
}


def ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).timestamp() * 1000)


def atr14_at(con, t_ms: int) -> float:
    """TRUE-RANGE ATR-14 on the 14 completed 1-minute bars before t_ms — the fallback when the rider
    never froze one. True range, not bar range: a gap between bars is real risk and a mean-range
    measure understates it, which is exactly how a stop grid ends up bounded below the MAE."""
    rows = con.execute(f"""
        SELECT min(ts_ms) t, max(price) hi, min(price) lo, last(price ORDER BY ts_ms) cl
        FROM ticks WHERE symbol='MNQ' AND ts_ms BETWEEN {t_ms - 20 * 60_000} AND {t_ms}
        GROUP BY ts_ms // 60000 ORDER BY 1""").fetchall()
    if len(rows) < 6:
        return 0.0
    rows = rows[-15:]
    trs = [max(h - lo, abs(h - rows[i][3]), abs(lo - rows[i][3]))
           for i, (_, h, lo, _c) in enumerate(rows[1:])]
    return round(sum(trs) / len(trs), 2) if trs else 0.0


def entry_events(dbpath: str) -> dict:
    """exec_time -> (on-tape BASE price, off-tape lots, total lots, adverse $) per fill event.

    A split order's residual leg is priced base x (1 +/- 0.001) ADVERSE. `base` is the leg that IS
    on the tape (verified: every base below sits inside the tape's +/-10s range and every off leg
    does not). The stop grid must be raced off base, not off the booked fill-VWAP."""
    c = sqlite3.connect(dbpath, uri=True)
    ev: dict = {}
    for t, side, q, px in c.execute(
            "SELECT exec_time, side, qty, price FROM fills ORDER BY exec_time"):
        ev.setdefault((t, side), []).append((q, px))
    c.close()
    out = {}
    for (t, side), legs in ev.items():
        prices = {p for _, p in legs}
        base = min(prices) if side == "BUY" else max(prices)
        off = [(q, p) for q, p in legs if p != base]
        out[t] = dict(base=base, side=side,
                      lots=sum(q for q, _ in legs),
                      off_lots=sum(q for q, _ in off),
                      adverse=round(sum(q * abs(p - base) * MULT for q, p in off), 2))
    return out


def main() -> int:
    db = sqlite3.connect(DB, uri=True)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute(
        "SELECT id,side,qty,entry_price,exit_price,opened_at,closed_at,pnl_usd,exit_reason "
        "FROM trades WHERE data_quality IS NULL AND gate LIKE 'day_rider%' "
        "AND closed_at >= '2026-08-24' ORDER BY opened_at, closed_at")]
    db.close()

    pos: dict = {}
    for r in rows:
        pos.setdefault((r["opened_at"], r["entry_price"], r["side"]), []).append(r)

    ev = entry_events(DB)
    con = connect(symbol="MNQ")
    out, tot = [], {"NAKED": 0.0, **{f"k={k}": 0.0 for k in WIDTHS}}

    for (opened, entry_booked, side), legs in sorted(pos.items()):
        # ★ race off the ON-TAPE base price, not the booked fill-VWAP (see the docstring).
        e = ev.get(opened[:19] + "+00:00") or ev.get(opened)
        entry = e["base"] if e else entry_booked
        t0 = ms(opened)
        t1 = max(ms(l["closed_at"]) for l in legs)
        arm = ARM_ATR.get(opened, 0.0)
        measured = False
        if arm <= 0:
            arm, measured = atr14_at(con, t0), True
        d = 1 if side == "LONG" else -1
        lots = sum(l["qty"] for l in legs)
        naked = round(sum(l["pnl_usd"] for l in legs), 2)

        tk = con.execute(
            f"SELECT ts_ms, price FROM ticks WHERE symbol='MNQ' "
            f"AND ts_ms BETWEEN {t0} AND {t1} ORDER BY ts_ms").fetchall()

        cell = {}
        for k in WIDTHS:
            stop = entry - d * k * arm
            hit_ms = next((ts for ts, px in tk
                           if (px <= stop if d > 0 else px >= stop)), None)
            if hit_ms is None:
                cell[f"k={k}"] = dict(net=naked, stopped=False, when=None)
                continue
            net = 0.0
            for l in legs:
                if ms(l["closed_at"]) <= hit_ms:
                    net += l["pnl_usd"]                       # already out at its real exit
                else:
                    net += (stop - entry) * d * l["qty"] * MULT - FEE * l["qty"]
            cell[f"k={k}"] = dict(net=round(net, 2), stopped=True,
                                  when=dt.datetime.fromtimestamp(hit_ms / 1000, dt.UTC)
                                  .strftime("%m-%d %H:%M:%SZ"))

        out.append(dict(opened=opened, entry_booked=entry_booked, entry_on_tape=entry,
                        off_tape_lots=(e or {}).get("off_lots", 0),
                        off_tape_adverse=(e or {}).get("adverse", 0.0),
                        side=side, lots=lots, legs=len(legs),
                        arm_atr=arm, atr_measured=measured, naked=naked,
                        widths={k: v["net"] for k, v in cell.items()},
                        stopped={k: v["when"] for k, v in cell.items()}))
        tot["NAKED"] += naked
        for k in WIDTHS:
            tot[f"k={k}"] += cell[f"k={k}"]["net"]

    tot = {k: round(v, 2) for k, v in tot.items()}
    best = max(((k, v) for k, v in tot.items() if k != "NAKED"), key=lambda t: t[1])
    ex_carry = {k: round(v - next(p["widths"].get(k, p["naked"]) if k != "NAKED" else p["naked"]
                                  for p in out if p["opened"].startswith("2026-08-21")), 2)
                for k, v in tot.items()}
    audit = dict(
        events=sum(1 for p in out if p["off_tape_lots"]),
        positions=len(out),
        lots=round(sum(p["lots"] for p in out), 0),
        off_tape_lots=round(sum(p["off_tape_lots"] for p in out), 0),
        adverse_usd=round(sum(p["off_tape_adverse"] for p in out), 2))
    res = dict(positions=out, week_total=tot, week_total_ex_carry=ex_carry,
               off_tape_audit_entries_only=audit,
               best_width=best[0], best_total=best[1],
               naked=tot["NAKED"], delta_best_vs_naked=round(best[1] - tot["NAKED"], 2))
    print(json.dumps(res, indent=2))
    open(OUT, "w").write(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
