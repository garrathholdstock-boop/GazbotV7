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
from datetime import datetime, timezone

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.telegram_bot import apply_gate_switch as _apply  # noqa: E402
from gazbot7.telegram_bot import reactivate_all  # noqa: E402

SWITCH = "/home/alphabot/gazbot7/data/gate_switches.env"

# ★2026-08-01 (audit FIX): gates this nightly job must NEVER auto-arm. The 1-day-expiry rule
# assumes an "off" is an intraday ROUTER bench of a gate that has already earned its place. It is
# WRONG for a gate that has never been accepted: nipc_* shipped BENCHED because its acceptance
# replay (scripts/nipc_replay.py) failed to reproduce the lab (+$264/n=159 vs +$2,676/n=171), and
# gate_switches.env says in plain text "SHIPS BENCHED — the operator arms it after reviewing".
# Without this, the 00:00 Europe/Paris timer (22:00 UTC — i.e. the Sunday reopen minute) silently
# flips them to on and a never-validated construct trades live. The Telegram /on command and
# telegram_bot.reactivate_all are untouched, so the operator can still arm them by hand.
# Revert: HOLD = frozenset().
#
# ★2026-08-01 (operator, explicit): "every gate we have should re-enable for the midnight open. then
# the router manages." So HOLD is EMPTY by policy — no gate is exempt from the 1-day rule. rgv_short was
# briefly held here and has been released: its week-long bench now lives in the ROUTER's standing
# guidance (scripts/router_tick_durable.py) instead, which is the right home for it — the router re-reads
# the regime every 5 min and can bench it again straight after the midnight re-arm.
# Rationale for the policy: the midnight re-arm is the SESSION reopen on quiet overnight tape, ~15h
# before the 13:30 UTC cash open. We have no regime read at 22:00, so starting armed and letting the
# router bench on evidence beats starting benched on yesterday's opinion. The "arm veto-gates only"
# lesson applies to the VIOLENT CASH OPEN, not to the midnight reopen — different tape, different call.
# NOTE this job is genuinely dangerous for a NEVER-VALIDATED gate: it flips every =off to =on with no
# idea why the gate was off. If a future gate ships benched pending review, hold it HERE, not in a
# comment — nothing reads comments. (nipc_* was held here until the operator armed it on 08-01.)
# ★2026-08-03 — nipc_* held. This is the documented EXCEPTION to the operator's "every gate re-enables
# at midnight" policy: that rule assumes an "off" is an intraday ROUTER bench of a gate that has earned
# its place. nipc is benched for DIAGNOSIS — its live signals diverge from the shipped decider by $655
# in the opposite direction, so every further session adds data that cannot count toward its n>=40
# review. The 22:00 job re-armed it once already tonight because the warning was written as a COMMENT
# in gate_switches.env and nothing reads comments. Holding it here is the only mechanism that works.
# Remove once the divergence is diagnosed and the replay reproduces live within a stated tolerance.
HOLD: frozenset = frozenset({"nipc_long", "nipc_short"})


def run() -> int:
    try:
        with open(SWITCH) as f:
            text = f.read()
    except OSError as e:
        print(f"reactivate_gates: no switch file ({e}) — nothing to do")
        return 0
    new, reactivated = reactivate_all(text)
    if HOLD & set(reactivated):    # ★ re-bench the held gates, then keep the ORIGINAL text if
        held = sorted(HOLD & set(reactivated))   # they were the only things this run would arm
        for g in held:
            new = _apply(new, g, "off")
        reactivated = [g for g in reactivated if g not in HOLD]
        print(f"reactivate_gates: HELD (not auto-armed): {', '.join(held)}")
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
