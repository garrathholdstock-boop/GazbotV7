#!/usr/bin/env python3
"""THE DAILY LOSS LIMIT — the highest-value change measured on this desk, and it needs no edge.

★ WHY. The single-lot book's losses are SINGLE-SESSION DOMINATED: worst day -$817 against a median
losing day of -$242 (3.4x), and the FIVE WORST DAYS ARE 52% OF ALL LOSS. Applying a $250 limit
retrospectively takes the book from +$35/day to +$87/day on 43 sessions. Every professional hard
rule in the industry is on LOSS, never on win rate or target; Topstep's own figure is that "over 63%
of traders have lost account in a single day".

⚠⚠ THE LEVEL WAS SELECTED ON THOSE 43 SESSIONS AND IS THEREFORE OVERFIT UNTIL PROVEN FORWARD. That
is precisely why it is pre-registered (data/prereg_daily_loss_limit.json) and frozen: $250, not
tunable, for 60 forward sessions. Tighter looked monotonically better in backtest, which usually
means "stop trading" is the optimum and is exactly the shape that does not survive contact.

★★★ IT CAN ONLY EVER BENCH. This script writes `off` and never `on`, asserted by
tests/test_daily_loss_limit.py against the SOURCE — including that this file contains no order-path
vocabulary at all, which is why the paragraph describes those actions instead of naming them. It
places no orders, closes no position, and does not touch the rider: an open position keeps its
existing exits and the 20:40Z hard exit remains the floor. The desk has been bitten before by a protective mechanism that disarmed the desk it was
protecting ([[a-cross-desk-kill-disarms-the-desk-it-is-protecting]]) — so this one is DELIBERATELY
self-clearing: `gazbot7-gate-reactivate` arms every `off` gate at 22:00Z, so a bench lasts until the
next session opens and no human release is required.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys

GB = "/home/alphabot/gazbot7"
SWITCH = f"{GB}/data/gate_switches.env"
STATE = f"{GB}/data/daily_loss_limit_state.json"
LOG = f"{GB}/data/router_trial_log.txt"
GATES = ("grind_long", "capitulation_long", "abs_veto_long",
         "exhaustion_short", "abs_veto_short", "rgv_short")
LIMIT_USD = 250.0          # ★ FROZEN 2026-09-13. Changing it restarts the forward count at zero.


def session_pnl(now: dt.datetime) -> tuple[float, int]:
    """Realised P&L for the CME session in progress. A session starts at the 22:00Z reopen, so
    anything after 22:00 belongs to the NEXT calendar day's session — getting this wrong would
    reset the limit in the middle of a losing session, which is the one moment it must not."""
    start = now.replace(hour=22, minute=0, second=0, microsecond=0)
    if now.hour < 22:
        start -= dt.timedelta(days=1)
    c = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    row = c.execute("select coalesce(sum(pnl_usd),0), count(*) from trades "
                    "where closed_at is not null and closed_at >= ?",
                    (start.isoformat(),)).fetchone()
    return float(row[0]), int(row[1])


def bench_all(reason: str) -> list[str]:
    """Write `off` to every gate. NEVER writes `on` — that is the whole safety property."""
    with open(SWITCH) as fh:
        lines = fh.readlines()
    changed, out = [], []
    for ln in lines:
        k = ln.split("=", 1)[0].strip()
        if k in GATES and not ln.strip().endswith("=off"):
            changed.append(k)
            out.append(f"{k}=off\n")
        else:
            out.append(ln)
    if changed:
        tmp = SWITCH + ".tmp"
        with open(tmp, "w") as fh:
            fh.writelines(out)
        os.replace(tmp, SWITCH)
        with open(LOG, "a") as fh:
            fh.write(f"{dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%M:%SZ} DAILY LOSS LIMIT: {reason} — "
                     f"benched {', '.join(changed)}\n")
    return changed


def main() -> int:
    now = dt.datetime.now(dt.UTC)
    pnl, n = session_pnl(now)
    prev = {}
    try:
        prev = json.load(open(STATE))
    except Exception:
        pass
    sess = (now - dt.timedelta(hours=22)).date().isoformat()
    fired = prev.get("session") == sess and prev.get("fired")
    state = {"ts": now.isoformat(), "session": sess, "pnl_usd": round(pnl, 2),
             "trades": n, "limit": LIMIT_USD, "fired": bool(fired)}

    if pnl <= -LIMIT_USD and not fired:
        changed = bench_all(f"session P&L ${pnl:,.2f} <= -${LIMIT_USD:,.0f} after {n} trades")
        state.update(fired=True, fired_at=now.isoformat(), benched=changed)
        try:
            sys.path.insert(0, f"{GB}/src")
            from gazbot7.notify import notify
            notify(f"DAILY LOSS LIMIT HIT — session P&L ${pnl:,.2f} after {n} trades. "
                   f"All six gates benched; they re-arm at the 22:00Z reopen. Open positions keep "
                   f"their exits and the 20:40Z hard exit is unchanged. No position was closed.",
                   critical=True)
        except Exception as e:
            state["notify_error"] = str(e)[:120]
    with open(STATE, "w") as fh:
        json.dump(state, fh, indent=1)
    print(json.dumps(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
