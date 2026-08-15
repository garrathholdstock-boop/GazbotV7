#!/usr/bin/env python3
"""REV2 issue — the gold census shipped with an EMPTY order-book column on all 74 runs.

`run_census.py` reads its book column from `capture.db.book`, which is MNQ-ONLY (IBKR allows
three depth subscriptions, so gold's L2 goes to `depth.db.depth_snap` instead). On MGC the
query therefore returned nothing and every row printed an em-dash — with a column header still
explaining what the reader was supposed to be seeing.

This fills the column from the right table, with the same definition the MNQ census uses:

    book = far-side depth / (far-side + near-side), levels 1-3, over the 30 seconds BEFORE the
    run starts. Price ran UP → the far side is the asks. Below 0.50 = the side price ran toward
    was already thin, i.e. the book telegraphed the move.

⚠ The two instruments are NOT the same measurement and the fragment says so where the column
lives: capture.db.book is 41 ms and event-driven, depth.db is a 250 ms SAMPLE, so gold's column
cannot see a fleeting quote that Nasdaq's can.

  PYTHONPATH=src ./.venv/bin/python scripts/rev2_mgc_census_book.py [--write]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sqlite3
import statistics

FRAG = "/home/alphabot/gazbot7/reports/friday_v7/sections/movement1_census_MGC.html"
DEPTH = "/home/alphabot/gazbot7/data/depth.db"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_mgc_book.json"
ROW = re.compile(
    r'<tr><td class="ln">(\d\d-\d\d \d\d:\d\d)</td><td>(UP|DN)</td>(.*?)</tr>', re.S)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(f"file:{DEPTH}?mode=ro", uri=True)
    html = pathlib.Path(FRAG).read_text()
    rows, out = ROW.findall(html), []
    print(f"{len(rows)} census rows")

    for tm, direction, _rest in rows:
        ts = int(dt.datetime.strptime("2026-" + tm, "%Y-%m-%d %H:%M")
                 .replace(tzinfo=dt.UTC).timestamp())
        r = con.execute(
            "SELECT sum(COALESCE(bid1s,0)+COALESCE(bid2s,0)+COALESCE(bid3s,0)), "
            "       sum(COALESCE(ask1s,0)+COALESCE(ask2s,0)+COALESCE(ask3s,0)), count(*) "
            "FROM depth_snap WHERE symbol='MGC' AND ts_ms < ? AND ts_ms >= ?",
            (ts * 1000, (ts - 30) * 1000)).fetchone()
        bid, ask, n = (r[0] or 0.0), (r[1] or 0.0), r[2]
        far, near = (ask, bid) if direction == "UP" else (bid, ask)
        share = (far / (far + near)) if (far + near) else None
        out.append({"time": tm, "dir": direction, "snaps": n,
                    "book": None if share is None else round(share, 2)})
    con.close()

    have = [o for o in out if o["book"] is not None]
    print(f"populated {len(have)}/{len(out)} rows  "
          f"(median snapshots in the 30s window: "
          f"{statistics.median([o['snaps'] for o in out]):.0f})")
    if have:
        v = [o["book"] for o in have]
        thin = sum(1 for x in v if x < 0.50)
        print(f"  far-side share: median {statistics.median(v):.3f}  "
              f"min {min(v):.2f}  max {max(v):.2f}  "
              f"— thin (<0.50) before {thin}/{len(v)} runs ({100*thin/len(v):.0f}%)")
        for d in ("UP", "DN"):
            s = [o["book"] for o in have if o["dir"] == d]
            if s:
                print(f"  {d}: n={len(s)} median {statistics.median(s):.3f}  "
                      f"thin {sum(1 for x in s if x < 0.5)}/{len(s)}")
    json.dump(out, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}")

    if a.write:
        it = iter(out)

        def sub(m):
            o = next(it)
            body = m.group(3)
            val = "&mdash;" if o["book"] is None else f"{o['book']:.2f}"
            # the Book cell is the 4th-from-last <td> on the row (…Flow, Amp, Book, Cluster)
            cells = re.findall(r"<td[^>]*>.*?</td>", body, re.S)
            cells[-2] = f'<td class="num">{val}</td>'
            return (f'<tr><td class="ln">{m.group(1)}</td><td>{m.group(2)}</td>'
                    + "".join(cells) + "</tr>")

        pathlib.Path(FRAG).write_text(ROW.sub(sub, html))
        print(f"patched the Book column in {FRAG}")


if __name__ == "__main__":
    main()
