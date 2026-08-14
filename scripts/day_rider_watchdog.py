#!/usr/bin/env python3
"""DAY RIDER WATCHDOG — flatten if the strategy service dies holding a position.

★ THIS IS THE SAFETY LAYER THAT ACTUALLY MATTERS. The day-rider holds 2 lots for up to 7 hours with no
tradeable stop (measured: a 400pt stop costs $3,451 of expectancy and has a WORSE worst-day than running
naked, because it kills the winner that drew 511pt and recovered). So the danger is NOT price — it is
`gazbot7-day-rider.timer` dying, or the box rebooting, with 2 lots open and nothing managing them.

That exact failure has happened on this desk: a LONG bled -$400 over three hours after a silent auditor
skip, and separately an orphan stop drove a phantom position into a drift-halt. Those are the precedents
this file exists for.

★ HOW IT DECIDES, and why it is a separate process on a separate IBKR client: it compares the VENUE
against the strategy's heartbeat. If the venue holds a position and `day_rider_state.json` has not been
stamped within HEARTBEAT_STALE_S, nobody is managing that position -> flatten it and page the operator.
Being independent is the point — a hung strategy service cannot also stop this from running, the same
reasoning eod_flatten.py uses for holding its own client.

★ IT ONLY EVER FLATTENS. It cannot open, size, or reverse anything. The worst a bug here can do is close
a position early, which costs money; the worst the absence of it can do is carry an unmanaged position
through the night, which is the thing the operator has ruled out absolutely ("never hold overnight.
ever"). Those are not symmetric, so this fails toward flat.

★ AND IT FLATTENS ON A STALE HEARTBEAT EVEN IF THE POSITION LOOKS FINE. A position nobody is watching is
the hazard, regardless of whether it is currently green — that was the lesson of the naked-position
incident, where the P&L looked survivable right up until it did not.

  PYTHONPATH=src .venv/bin/python scripts/day_rider_watchdog.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.config import RunConfig                     # noqa: E402
from gazbot7.day_rider import HEARTBEAT_STALE_S, STATE   # noqa: E402
from gazbot7.safety import safe_flatten_verdict          # noqa: E402

WATCHDOG_CLIENT_ID = 5      # core=0, md=2, day_rider=4, eod=6, checks=8 — 5 is free
LOG = "/home/alphabot/gazbot7/data/day_rider_watchdog.log"


def hb_age_s(now: dt.datetime) -> float | None:
    """Seconds since the strategy last stamped its state, or None if it is NOT actually managing.

    ★ A FRESH TIMESTAMP IS NOT ENOUGH. Found live: a clientId collision made the strategy's venue
    connection fail; it correctly took no action and still wrote a fresh heartbeat, which this watchdog
    would have read as "managed". So `venue_ok` must also be true — the strategy has to have actually
    reached the broker on that tick. Anything else counts as unmanaged and gets flattened, because a
    position nobody can see is the exact hazard this file exists for."""
    try:
        with open(STATE) as fh:
            st = json.load(fh)
        if not st.get("venue_ok"):
            return None
        return (now - dt.datetime.fromisoformat(st["heartbeat"])).total_seconds()
    except Exception:
        return None


def log(msg: str) -> None:
    """★ NEVER FAIL SILENTLY. First run created this log as root while the service runs as alphabot,
    so every write failed inside a bare `except: pass` — the watchdog executed correctly and left no
    trace, which is indistinguishable from not running at all. A safety component whose audit trail
    can vanish is not a safety component. Falls back to stderr, which systemd captures in the journal,
    so the record survives any file-permission problem."""
    line = f"{dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%M:%SZ} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception as e:
        print(f"{line}  [LOGFILE UNWRITABLE: {e}]", file=sys.stderr, flush=True)


async def run(dry: bool) -> int:
    from ib_async import ContFuture, IB, MarketOrder
    now = dt.datetime.now(dt.UTC)
    cfg = RunConfig()
    age = hb_age_s(now)
    ib = IB()
    try:
        await ib.connectAsync(cfg.host, cfg.port, clientId=WATCHDOG_CLIENT_ID,
                              readonly=False, timeout=15)
        await asyncio.sleep(0.8)
        (contract,) = await ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))
        net = sum(p.position for p in ib.positions() if p.contract.symbol == cfg.symbol)
    except Exception as e:
        log(f"SKIP venue read failed: {str(e)[:100]}")
        return 0
    try:
        if abs(net) < 1e-9:
            log(f"ok flat (heartbeat {'never' if age is None else f'{age:.0f}s'})")
            return 0
        # ⚠ A position exists. The ONLY safe state is a fresh heartbeat proving someone owns it.
        if age is not None and age <= HEARTBEAT_STALE_S:
            log(f"ok position {net} managed (heartbeat {age:.0f}s)")
            return 0
        why = "no heartbeat ever" if age is None else f"heartbeat stale {age:.0f}s"
        # ★2026-08-06 — OWNERSHIP GATE. This watchdog exists to rescue the DAY-RIDER's position when
        # the strategy stops managing it. It does NOT exist to flatten the account. The tournament
        # shares account DUQ191770 and the same MNQ contract, and on 2026-08-06 the strategy's own
        # hard-flat sold 2 tournament lots it had never opened — cascading into an 11-minute drift
        # halt, a transient naked short and two fictitious target wins in the trade record.
        # This file had the identical blind spot and was passive only by luck: with day_rider=off the
        # strategy still stamps a fresh heartbeat, so `age` stayed fresh. Stop that service and this
        # watchdog would have flattened the tournament on its next 2-minute tick.
        # A stale heartbeat means OUR position is unmanaged; it says nothing about someone else's.
        # So require the state to claim the position before firing, and ALARM otherwise.
        try:
            with open(STATE) as fh:
                _st = json.load(fh)
        except Exception:
            _st = {}
        if not (_st.get("entered") and not _st.get("closed")):
            log(f"ALARM position {net} unmanaged ({why}) but day-rider state says it is NOT ours "
                f"(entered={_st.get('entered')}, closed={_st.get('closed')}) — NOT acting")
            try:
                # ★2026-08-14 deduped for the same reason as day_rider.py's twin message: this is a
                # 60s oneshot, so a standing unowned position would repeat a CRITICAL every minute
                # until someone acted. Cooldown is much shorter than the rider's 6h — this fires only
                # when the rider is ALSO unmanaged, which is a genuinely odd state worth re-stating —
                # and the text carries `net`, so a size change re-alarms immediately.
                from gazbot7.notify import dedupe_ok, notify
                msg = (f"⚠ DAY RIDER WATCHDOG: venue holds {net} MNQ and the day-rider is unmanaged "
                       f"({why}), but that position is NOT the day-rider's. NOT flattening — it "
                       f"belongs to another desk on this account. Check the tournament.")
                if dedupe_ok("day_rider_watchdog.unowned_unmanaged", msg, cooldown_s=1800):
                    notify(msg, critical=True)
            except Exception:
                pass
            return 0
        v = safe_flatten_verdict(net)     # fire ONLY what the venue holds, in its direction
        if v is None:
            log(f"ALARM position {net} unmanaged ({why}) but no safe verdict — NOT acting")
            return 0
        log(f"FLATTEN position {net} unmanaged ({why}) -> {v[0]} {v[1]}" + (" [dry-run]" if dry else ""))
        if not dry:
            ib.placeOrder(contract, MarketOrder(v[0], v[1]))
            await asyncio.sleep(2.0)
            try:
                from gazbot7.notify import notify
                notify(f"DAY RIDER WATCHDOG flattened {net} lots — {why}. "
                       f"The strategy service was not managing the position.", critical=True)
            except Exception:
                pass
        return 0
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return asyncio.run(run(a.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
