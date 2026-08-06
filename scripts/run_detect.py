#!/usr/bin/env python
"""Live RUN-STATE read for the router — is a directional run in progress right now?

Reads the RAW tape (5s bars -> 1-min OHLC) and reports state only. It NEVER flips a switch:
the arm/bench decision belongs to Claude (operator 2026-08-06). See gazbot7/runstate.py for the
week-long evidence that made this the desk's primary regime discriminator.

Usage:  PYTHONPATH=src .venv/bin/python scripts/run_detect.py [--json] [--lookback-min N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

import duckdb  # noqa: E402

from gazbot7.runstate import compute, render, _minute_bars  # noqa: E402

GB = "/home/alphabot/gazbot7"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lookback-min", type=int, default=240,
                    help="minutes of tape to load (default 240; needs >=30 to decide)")
    a = ap.parse_args()

    now = dt.datetime.now(dt.UTC)
    since = int((now - dt.timedelta(minutes=a.lookback_min)).timestamp())
    con = duckdb.connect()
    con.execute(f"ATTACH '{os.path.join(GB,'data','capture.db')}' AS c (READ_ONLY)")
    con.execute("use c")
    rows = _minute_bars(con, "MNQ", since)
    st = compute(rows)

    if st.get("start_ts"):
        st["start_utc"] = dt.datetime.fromtimestamp(st["start_ts"], dt.UTC).strftime("%H:%M")
    if a.json:
        print(json.dumps(st, indent=1))
    else:
        print(render(st))
        if st.get("start_utc"):
            print(f"  run began {st['start_utc']}Z at {st['start_px']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
