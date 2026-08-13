#!/usr/bin/env python3
"""CROSS-DESK RECONCILER — read IBKR, hold every desk to the invariant, kill both on a breach.

★★ THE 2026-08-13 INCIDENT IN ONE LINE: the day-rider sold 8 lots it did not own, booked +$1,551 of
profit that never existed, and no component on the box was responsible for noticing — because every
guard was PER-DESK. The tournament's reconcile fired and halted, but only itself; the rider had no
invariant at all; and the one cross-desk detector was throwing NameError with an undeployed fix.
IBKR said the day was −$25.50 while the books said +$835.

This is the missing owner. It is the ONLY component that asks: does IBKR agree with the SUM of every
desk's claim?

★ AUTHORITY. On a CONFIRMED breach it stops BOTH desks — writes data/desk_kill.json, benches every
gate, and switches the day-rider off. That is deliberately more authority than any single desk has,
because an unaccounted lot means at least one book is lying and you do not know which. It NEVER
re-arms anything: releasing the kill is a human decision, because the whole point is that automated
state was untrustworthy.

★ TWO INDEPENDENT VENUE READS BEFORE ACTING. Claims and the venue are sampled at different instants,
so every position change opens a window where they legitimately disagree — router_watch.py's
mismatch check false-fired twice that way on 08-12. A real orphan persists across reads; a race does
not. So a breach must be seen twice, on venue snapshots taken seconds apart, with the SAME
imbalance.

★ READ-ONLY AT THE VENUE. It connects on its own clientId (8, reserved for checks) with
readonly=True, so it cannot place or cancel an order even by accident. It stops desks by switch
files, never by trading. Flattening stays a human/eod_flatten decision.

★ FAIL-CLOSED, ASYMMETRICALLY. Cannot read the venue or a claim → block new orders (the desks call
deskrecon.may_place_order) but do NOT kill; a transient file read must never take the desk down.
Only a confirmed NUMERIC breach kills.

  PYTHONPATH=src scripts/desk_reconcile.py [--json] [--dry-run] [--release]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import deskrecon  # noqa: E402
from gazbot7.config import RunConfig  # noqa: E402

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"
SWITCHES = f"{GB}/data/gate_switches.env"
DR_ENV = f"{GB}/data/day_rider.env"
STATE = f"{GB}/data/desk_reconcile_state.json"
RECON_CLIENT_ID = 8          # reserved for checks (core=0, md=2, rider=4, watchdog=5, eod=6)
SECOND_READ_DELAY_S = 6.0


def page(msg: str, critical: bool = True) -> None:
    try:
        subprocess.run([PY, "-c", "import sys; from gazbot7.notify import notify; "
                                  "notify(sys.argv[1], critical=sys.argv[2]=='1')",
                        msg[:900], "1" if critical else "0"],
                       cwd=GB, env={**os.environ, "PYTHONPATH": "src"}, timeout=30)
    except Exception:
        pass


async def venue_net(cfg: RunConfig) -> float | None:
    """IBKR truth for the symbol. None on ANY doubt — never guess, and never return 0.0 as a
    stand-in for "could not read", which would make a naked position look like a flat account."""
    try:
        from ib_async import IB, ContFuture
    except Exception:
        return None
    ib = IB()
    try:
        await ib.connectAsync(cfg.host, cfg.port, clientId=RECON_CLIENT_ID,
                              readonly=True, timeout=15)
        await asyncio.sleep(1.0)
        await ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))
        return sum(p.position for p in ib.positions() if p.contract.symbol == cfg.symbol)
    except Exception:
        return None
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


def bench_everything(reason: str) -> list[str]:
    """Stop both desks. Benching-only: this NEVER writes `=on` and never places an order."""
    done = []
    try:
        lines, changed = [], False
        with open(SWITCHES) as fh:
            for ln in fh:
                if "=" in ln and not ln.lstrip().startswith("#") and ln.rstrip().endswith("=on"):
                    lines.append(ln.rstrip()[:-3] + "=off\n")
                    changed = True
                else:
                    lines.append(ln)
        if changed:
            tmp = SWITCHES + ".tmp"
            with open(tmp, "w") as fh:
                fh.writelines(lines)
            os.replace(tmp, SWITCHES)
            done.append("all gates benched")
    except Exception as e:
        done.append(f"gate bench FAILED ({e})")
    try:
        with open(DR_ENV) as fh:
            cur = fh.read()
        if "day_rider=on" in cur:
            tmp = DR_ENV + ".tmp"
            with open(tmp, "w") as fh:
                fh.write("day_rider=off\n")
            os.replace(tmp, DR_ENV)
            done.append("day-rider switched off")
    except Exception as e:
        done.append(f"day-rider off FAILED ({e})")
    try:
        tmp = deskrecon.KILL + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"active": True, "reason": reason,
                       "at": datetime.now(UTC).isoformat(timespec="seconds"),
                       "release": "scripts/desk_reconcile.py --release (a HUMAN decision)"}, fh)
        os.replace(tmp, deskrecon.KILL)
        done.append("kill file written")
    except Exception as e:
        done.append(f"kill file FAILED ({e})")
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="assess and print; never kill, never page")
    ap.add_argument("--release", action="store_true",
                    help="clear the kill file (human decision — does NOT re-arm any gate)")
    a = ap.parse_args()
    cfg = RunConfig()

    if a.release:
        try:
            os.remove(deskrecon.KILL)
            print("kill released — gates and the day-rider stay OFF; re-arm them deliberately")
            page("GAZBOT cross-desk kill RELEASED by hand. Gates and day-rider remain OFF — "
                 "re-arm deliberately.", critical=False)
        except FileNotFoundError:
            print("no kill file — nothing to release")
        return 0

    net1 = asyncio.run(venue_net(cfg))
    r1 = deskrecon.reconcile(net1)
    result = {"ts": datetime.now(UTC).isoformat(timespec="seconds"),
              "read1": {"venue": net1, "ok": r1.ok, "breach": r1.breach,
                        "unaccounted": r1.unaccounted, "summary": r1.summary(),
                        "reasons": r1.reasons}}

    if r1.breach and not a.dry_run:
        # ★ SECOND, INDEPENDENT READ. A fresh connection a few seconds later — not a re-use of the
        # first snapshot, which would confirm nothing. A fill in flight resolves; an orphan does not.
        time.sleep(SECOND_READ_DELAY_S)
        net2 = asyncio.run(venue_net(cfg))
        r2 = deskrecon.reconcile(net2)
        result["read2"] = {"venue": net2, "breach": r2.breach, "unaccounted": r2.unaccounted,
                           "summary": r2.summary()}
        confirmed = (r2.breach and r1.unaccounted is not None and r2.unaccounted is not None
                     and abs(r1.unaccounted - r2.unaccounted) < 0.5)
        result["confirmed"] = confirmed
        if confirmed:
            reason = f"unaccounted {r2.unaccounted:+g} lots — {r2.summary()}"
            actions = bench_everything(reason)
            result["actions"] = actions
            page(f"⚠⚠ GAZBOT CROSS-DESK BREACH — {reason}. BOTH DESKS STOPPED: "
                 f"{'; '.join(actions)}. IBKR is the truth and it does not match our books. "
                 f"Check TWS; release with scripts/desk_reconcile.py --release.")
        else:
            result["note"] = "not confirmed on the second read — treated as a position-change race"

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(("BREACH " if r1.breach else "ok     ") + r1.summary())
        for x in r1.reasons:
            print(f"  · {x}")
        if "actions" in result:
            print("  ACTIONS: " + "; ".join(result["actions"]))
    try:
        with open(STATE, "w") as fh:
            json.dump(result, fh, indent=1)
    except Exception:
        pass
    return 1 if r1.breach else 0


if __name__ == "__main__":
    sys.exit(main())
