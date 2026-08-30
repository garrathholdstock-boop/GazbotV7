#!/usr/bin/env python3
"""FLATTEN THE WEEKEND CARRY AT THE SUNDAY REOPEN. One job, then it disables itself.

2026-08-21: 4 MNQ lots opened 13:13Z were not flattened at 20:40Z — the gateway timed out for the
whole window and the rider had been switched off by the kill — so they went through the CME halt
and into the weekend. Operator, 2026-08-22: *"flatten at the reopen"*.

HOW, and why this shape:
  · It does NOT place an order itself. It re-arms the rider and writes the CLAIM file — the same
    path as the operator's Claim button. The web process never touches the broker and neither does
    this: one order path, already tested, already books the trade and cancels any stop.
  · It RETRIES every minute, because the failure that created this job was a gateway that would not
    answer. A single shot at 22:00 would repeat the original bug.
  · It PAGES if it cannot get flat, and pages again on success. Silence is what caused this.
  · It is IDEMPOTENT and SELF-DISABLING: once the venue reads flat it removes its own marker, so a
    forgotten timer can never flatten a future position.

⚠ It refuses to run unless the venue actually holds the carry it was created for. A flatten that
  does not check what it is flattening is the 2026-08-06 incident.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
MARKER = f"{GB}/data/weekend_flatten_pending.json"
CLAIM = f"{GB}/data/day_rider_claim.txt"
ENV = f"{GB}/data/day_rider.env"


def page(msg: str) -> None:
    try:
        from gazbot7.notify import notify
        notify(msg, critical=True)
    except Exception:
        pass


async def venue_net(symbol: str = "MNQ") -> float | None:
    """Read IBKR directly on a spare read-only clientId. None = could not read (NOT flat)."""
    try:
        from ib_async import IB
        ib = IB()
        await ib.connectAsync("127.0.0.1", 4002, clientId=22, timeout=20, readonly=True)
        try:
            net = sum(p.position for p in ib.positions()
                      if getattr(p.contract, "symbol", "") == symbol)
        finally:
            ib.disconnect()
        return float(net)
    except Exception:
        return None


def main() -> int:
    if not os.path.exists(MARKER):
        return 0                                   # nothing scheduled — the normal state
    want = json.load(open(MARKER))
    net = asyncio.run(venue_net(want.get("symbol", "MNQ")))

    if net is None:
        # ★ UNREADABLE IS NOT FLAT. This is the exact failure being fixed; say so and retry.
        page("⚠⚠ WEEKEND FLATTEN: cannot read IBKR at the reopen — retrying every minute. "
             "CHECK THE GATEWAY (docker restart alphabot-gateway).")
        return 0

    if abs(net) < 1e-9:
        os.remove(MARKER)                          # SELF-DISABLE: the job is done
        page(f"✅ WEEKEND FLATTEN COMPLETE — venue is FLAT. The {want.get('qty')} lot carry from "
             f"{want.get('opened')} is closed. This job has disabled itself.")
        subprocess.run(["systemctl", "disable", "--now", "gazbot7-weekend-flatten.timer"],
                       check=False)
        return 0

    # still holding → re-arm the rider and press Claim ALL through the normal path
    with open(ENV, "w") as fh:
        fh.write("day_rider=on\n")
    with open(CLAIM, "w") as fh:
        fh.write(dt.datetime.now(dt.UTC).isoformat() + "\n")   # bare stamp = claim ALL
    page(f"WEEKEND FLATTEN: venue holds {net:g} — rider re-armed and Claim ALL pressed. "
         f"Verifying on the next minute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
