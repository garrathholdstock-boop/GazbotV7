#!/usr/bin/env python3
"""Paris-midnight auto-reactivation — a gate turned off is off FOR THE DAY only.

The intraday off-switch (data/gate_switches.env) stops a gate's new entries, but nothing expired
it: a gate set off just stayed off until someone flipped it back (rgv_short sat off ~2 days,
2026-07-21→23). Operator rule (2026-07-23): an off lasts 1 day and auto-reactivates at Paris
midnight (the desk's trading-day boundary — daily P&L rolls there too). Run by a systemd timer at
00:00 Europe/Paris (DST-handled by systemd). Idempotent: nothing off → no write, no noise. A
LONGER hold (e.g. a relegation candidate) is the Saturday roster action, not this switch.

  python scripts/reactivate_gates.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.telegram_bot import reactivate_all  # noqa: E402

SWITCH = "/home/alphabot/gazbot7/data/gate_switches.env"


def run() -> int:
    try:
        with open(SWITCH) as f:
            text = f.read()
    except OSError as e:
        print(f"reactivate_gates: no switch file ({e}) — nothing to do")
        return 0
    new, reactivated = reactivate_all(text)
    if not reactivated:
        print("reactivate_gates: no gates off — nothing to do")
        return 0
    tmp = SWITCH + ".tmp"
    with open(tmp, "w") as f:
        f.write(new)
    os.replace(tmp, SWITCH)  # atomic; the tournament re-reads live (no restart)
    msg = f"gates auto-reactivated at Paris midnight (1-day off expired): {', '.join(reactivated)}"
    print(f"reactivate_gates: {msg}")
    try:
        from gazbot7.notify import notify
        notify(f"V7 — {msg}. Re-off any you want held (a longer hold is the Saturday roster call).",
               critical=False)
    except Exception as e:
        print(f"reactivate_gates: notify skipped ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
