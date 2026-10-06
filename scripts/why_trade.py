#!/usr/bin/env python3
"""WHY DID IT BUY AND SELL — the day's tape picture with every reason attached.

★★★ Operator, 2026-10-06: *"well what we need to see is where he is buying and exiting on
the TAPE picture for the day. that tells us exactly what the improvement is."* and *"cant
claude make a record of why he bought or sold? surely thats possible."*

**IT ALREADY DID, AND NOBODY HAD LOOKED.** Every decision the harness has ever made stored a
free-text `reason` beside its action — 138 per simulated day, ~5,600 across the three
iterations — and each trade record carries an `entry_reason` of its own. The data was there
from the first run; what was missing was anything that put it next to the picture. That is
the whole of this script.

★ IT PRINTS THE SNAKE FIRST. The operator's standing instruction on this project is that the
shape outranks the metrics (*"the numbers are secondary. first review is looking at the image
of the snake"*), and that single change — showing the model the shape instead of the metrics
— took a simulated Monday from −$400 to +$352 and 14 trades to 4. So the reasons go UNDER the
picture, never instead of it.

⚠ `side` is the STRING "LONG"/"SHORT" in these records, not ±1. An ad-hoc version of this
report tested `side == 1`, silently fell through to "SHORT" on every row, and printed nine
longs labelled as shorts directly above the reasons describing them as longs. A mislabelled
side in a trading report is worse than no report.
⚠ READ-ONLY: reads artefacts, prints. Writes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap

GB = "/home/alphabot/gazbot7"
SIM = f"{GB}/reports/sim_week_recursive"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")


def report(tag: str, day: str, shape: bool = True) -> None:
    import sim_week_recursive as SW
    import snake_page as SP
    p = f"{SIM}/{tag}_hold_{day}.json"
    if not os.path.exists(p):
        p = f"{SIM}/{tag}_train_{day}.json"
    if not os.path.exists(p):
        print(f"  no artefact for {tag} {day}")
        return
    r = json.load(open(p))
    err = sum(1 for c in r["calls"] if c.get("error"))
    print("#" * 112)
    print(f"# {tag}  {day}   ${r['net_usd']:+,.2f} over {len(r['trades'])} trades"
          + (f"   ⚠ POISONED {err}/{len(r['calls'])} calls errored"
             if err / max(1, len(r["calls"])) > 0.10 else ""))
    print("#" * 112)
    if shape:
        bars, _ = SW.load_day(day)
        print(SP.page(bars, r["trades"], day))
    print()
    print("=" * 112)
    print("  WHY — the reason recorded at each entry and exit, in its own words")
    print("=" * 112)
    byts = {c["ts"]: c for c in r["calls"]}
    for i, t in enumerate(r["trades"], 1):
        side = str(t.get("side", "?"))            # ⚠ a STRING, never ±1
        print(f"\n  {i}. {side:<5} {t['opened'][11:16]}Z → {t['closed'][11:16]}Z  "
              f"{t['entry']:,.2f} → {t['exit']:,.2f}  ${t['pnl_usd']:+,.2f}  "
              f"held {t.get('held_min', 0):.0f}min  peak {t.get('peak_pt', 0):+.1f}pt  "
              f"[{t.get('why', '')}]")
        er = t.get("entry_reason") or (byts.get(t["opened"], {}) or {}).get("reason")
        xr = (byts.get(t["closed"], {}) or {}).get("reason")
        for lab, txt in (("ENTRY", er), ("EXIT ", xr)):
            if txt:
                print(textwrap.fill(" ".join(str(txt).split()), 104,
                                    initial_indent=f"       {lab}: ",
                                    subsequent_indent="              "))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("day")
    ap.add_argument("--iters", default="1,2,3")
    ap.add_argument("--no-shape", action="store_true")
    a = ap.parse_args()
    for it in a.iters.split(","):
        report(f"loop{it.strip()}", a.day, shape=not a.no_shape)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
