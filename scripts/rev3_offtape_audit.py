#!/usr/bin/env python3
"""OFF-TAPE FILL AUDIT — is the 0.1% residual leg a real venue fill or a paper-broker artefact?

★ WHY (2026-08-30, Rev 3). SATURDAY #4 ("the biggest single item on the week") is built on a split-
fill pattern where the residual leg of an order prices at base x (1 +/- 0.001), always ADVERSE. The
play's own Kill note raises the question and does not answer it: if the 0.1% is a SIMULATION
artefact rather than a venue print, it is not a $1,170 execution bug, it is a measurement error, and
every split-fill P&L this desk has ever quoted is overstated in the same direction.

Two published figures also disagree about the same fault — Part 1.6 says $734.50 over 15 of 63
EXECUTIONS, the card and Part 3 Q3 say $1,170.50 over 20 of 116 LOTS — so this prints ONE table
with its window and its unit stated.

FOUR TESTS, each of which a real fill passes and a simulated one fails:
  1. VENUE IDENTITY  — does the residual leg carry its own IBKR execId, distinct and sequential
     with its siblings? A synthesised leg tends to reuse or fabricate one.
  2. VENUE CLOCK     — real IBKR execution times arrive with sub-second precision. A leg stamped
     on a whole second is our clock, not the venue's.
  3. TAPE CONTAINMENT— was the residual price actually printed on MNQ within +/-30s of the fill?
     (memory: assert containment per EXECUTION, never on the blended trade row.)
  4. THE FACTOR      — is 0.001 anywhere in the order path? grep the source.

  PYTHONPATH=src .venv/bin/python scripts/rev3_offtape_audit.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import re
import subprocess
import sqlite3
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

DB = "/home/alphabot/gazbot7/data/gazbot7.db"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev3_offtape.json"
VPP = 2.0
BAND = (0.00095, 0.00105)      # the 0.1% cluster, distinct from ordinary slippage
WIN_S = 30                     # tape-containment window, each side


def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    fills = [dict(r) for r in c.execute("SELECT * FROM fills ORDER BY exec_time")]

    g = collections.defaultdict(list)
    for f in fills:
        g[(f["order_id"], f["exec_time"][:19])].append(f)

    events = []
    for (oid, sec), legs in g.items():
        if len({l["price"] for l in legs}) < 2:
            continue
        buy = legs[0]["side"] == "BUY"
        base = min(l["price"] for l in legs) if buy else max(l["price"] for l in legs)
        off = [l for l in legs if BAND[0] <= abs(l["price"] / base - 1) <= BAND[1]]
        if not off:
            continue
        events.append(dict(order_id=oid, sec=sec, side=legs[0]["side"], base=base,
                           legs=legs, off=off))
    events.sort(key=lambda e: e["sec"])

    con = connect()
    rows = []
    for e in events:
        t = dt.datetime.fromisoformat(e["sec"] + "+00:00")
        ms = int(t.timestamp() * 1000)
        lo, hi = con.execute(
            "SELECT min(price), max(price) FROM ticks WHERE symbol='MNQ' AND ts_ms BETWEEN ? AND ?",
            [ms - WIN_S * 1000, ms + WIN_S * 1000]).fetchone()
        base_in = (lo is not None and lo <= e["base"] <= hi)
        for l in e["off"]:
            adverse = (l["price"] - e["base"]) if e["side"] == "BUY" else (e["base"] - l["price"])
            rows.append(dict(
                exec_time=l["exec_time"], order_id=e["order_id"], side=e["side"],
                qty=l["qty"], base=e["base"], price=l["price"],
                ratio=round(l["price"] / e["base"], 6),
                adverse_pt=round(adverse, 2), cost_usd=round(adverse * l["qty"] * VPP, 2),
                exec_id=l["exec_id"],
                subsecond=("." in l["exec_time"].split("+")[0]),
                tape_lo=lo, tape_hi=hi,
                base_on_tape=base_in,
                leg_on_tape=(lo is not None and lo <= l["price"] <= hi),
                tape_seen=(lo is not None),
                order_lots=sum(x["qty"] for x in e["legs"]),
                off_lots=sum(x["qty"] for x in e["off"]),
            ))

    ids = [r["exec_id"] for r in rows]
    res = {
        "generated": "rev3 2026-08-30",
        "n_fill_rows_total": len(fills),
        "n_events": len(events),
        "n_off_legs": len(rows),
        "exec_ids_distinct": len(set(ids)) == len(ids),
        "exec_id_format_ok": all(re.fullmatch(r"[0-9a-f]{8}\.[0-9a-f]{8}\.\d\d\.\d\d", i) for i in ids),
        "subsecond_count": sum(1 for r in rows if r["subsecond"]),
        "leg_on_tape": sum(1 for r in rows if r["tape_seen"] and r["leg_on_tape"]),
        "leg_off_tape": sum(1 for r in rows if r["tape_seen"] and not r["leg_on_tape"]),
        "base_on_tape": sum(1 for r in rows if r["tape_seen"] and r["base_on_tape"]),
        "no_tape_cover": sum(1 for r in rows if not r["tape_seen"]),
        "all_adverse": all(r["adverse_pt"] > 0 for r in rows),
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 2),
        "rows": rows,
    }

    # windowed cuts so the two published figures can be reconciled
    # ★★2026-09-04 REV2 — THE WEEK AFTER IS THE POINT OF THE RE-RUN. SATURDAY #4's own
    # verification reads "re-run the audit next Friday. A week with zero off-tape legs, or with the
    # residual priced at the tape, is the fix landing." That is a question about 08-31 .. 09-04, and
    # the window list did not contain it, so re-running the script could not answer its own play.
    for lab, lo_d, hi_d in [("report week Mon 08-24 .. Fri 08-28", "2026-08-24", "2026-08-29"),
                            ("card window 08-21 carry .. Fri close", "2026-08-21", "2026-08-29"),
                            ("the week AFTER  Mon 08-31 .. Fri 09-04", "2026-08-31", "2026-09-05"),
                            ("all time", "2026-01-01", "2026-12-31")]:
        sub = [r for r in rows if lo_d <= r["exec_time"][:10] < hi_d]
        res.setdefault("windows", {})[lab] = {
            "events": len({(r["order_id"], r["exec_time"][:19]) for r in sub}),
            "off_legs": len(sub),
            "off_lots": sum(r["qty"] for r in sub),
            "cost_usd": round(sum(r["cost_usd"] for r in sub), 2),
        }

    # test 4 — the factor, in the source
    grep = subprocess.run(["grep", "-rnE", r"0\.001|1\.001|0\.999", "--include=*.py",
                           "/home/alphabot/gazbot7/src/gazbot7/"],
                          capture_output=True, text=True)
    res["factor_in_source"] = [l for l in grep.stdout.splitlines()]

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)

    print(f"{res['n_events']} split events, {res['n_off_legs']} residual legs at 0.1%, "
          f"all adverse={res['all_adverse']}, total ${res['total_cost_usd']}")
    print(f"  distinct execIds: {res['exec_ids_distinct']}   IBKR format: {res['exec_id_format_ok']}")
    print(f"  sub-second exec_time: {res['subsecond_count']}/{res['n_off_legs']}")
    print(f"  tape: base on tape {res['base_on_tape']}, residual ON tape {res['leg_on_tape']}, "
          f"OFF tape {res['leg_off_tape']}, no cover {res['no_tape_cover']}")
    print(f"  0.001/1.001/0.999 in src/gazbot7: {len(res['factor_in_source'])} hit(s)")
    for k, v in res["windows"].items():
        print(f"  {k:42} events={v['events']:3} legs={v['off_legs']:3} lots={v['off_lots']:5.0f} "
              f"${v['cost_usd']:,.2f}")
    print("->", OUT)


if __name__ == "__main__":
    main()
