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


def page(msg: str, critical: bool = True, *, dedupe_key: str | None = None,
         cooldown_s: float = 1800.0) -> None:
    """Alert the operator. With `dedupe_key`, a STEADY-STATE condition pages once, not forever.

    ★★★2026-08-22 THIS SERVICE RUNS EVERY 30 SECONDS AND HAD NO DEDUPE. An unresolved breach paged
    49 times in two hours (plus retries on 15s notify timeouts) and the operator asked it to stop —
    which is the failure mode the desk already has a rule for: a correct decision repeated every
    tick is an ALARM OUTAGE, because the channel becomes noise and the next real alert is missed.

    Semantics come from notify.dedupe_ok, deliberately:
      · keyed on the SITUATION (the message text), so +4 -> +6 unaccounted re-alarms IMMEDIATELY
        rather than hiding behind the cooldown — the size changing is new information;
      · FAILS OPEN — any error in the dedupe store sends the alert;
      · re-alarms every `cooldown_s` while the condition persists, so a breach can never go quiet.
    The KILL is untouched: suppression applies to the MESSAGE only, never to the action. The desk
    still stops on every tick that confirms a breach.
    """
    if dedupe_key is not None:
        try:
            sys.path.insert(0, f"{GB}/src")
            from gazbot7.notify import dedupe_ok
            if not dedupe_ok(dedupe_key, msg, cooldown_s=cooldown_s):
                return
        except Exception:
            pass                      # FAIL OPEN — never let the deduper swallow a safety alert
    try:
        subprocess.run([PY, "-c", "import sys; from gazbot7.notify import notify; "
                                  "notify(sys.argv[1], critical=sys.argv[2]=='1')",
                        msg[:900], "1" if critical else "0"],
                       cwd=GB, env={**os.environ, "PYTHONPATH": "src"}, timeout=30)
    except Exception:
        pass


STOP_TYPES = ("STP", "STP LMT", "TRAIL", "TRAIL LIMIT", "MIT")


def orphan_stops(net: float, orders: list[dict]) -> list[dict]:
    """Working protective orders with nothing behind them.

    ★★2026-08-13 — THE INVERSE AUDIT. The desk has always asked "does every SLOT have a stop?"; it
    has never asked "does every STOP have a position?" An order belonging to no position is
    invisible to a per-slot auditor, and that is exactly the thing that fires unattended: on 08-06 a
    leftover stop triggered with no position behind it and OPENED A NAKED SHORT, booked six hours
    later as a gate trade nobody placed.
    It happened again today and sat live for ~2h: the day-rider's 600pt venue stop (orderId 49,
    SELL 2 STP @ 29424.25) outlived the position it protected — the operator claimed at 14:26 and
    nothing cancelled the stop. eod_flatten TRIED at the flatten and got `Error 10147: not found`,
    which is IBKR saying "not yours to cancel" (it runs as clientId 6, the order belonged to
    clientId 4) — a permissions error that reads exactly like an all-clear.
    ★ Note the cross-desk position reconcile could not have caught this: it watches POSITIONS, and
    an orphan order is not a position until the moment it becomes one.

    A stop is legitimate only if it REDUCES exposure: SELL against a long, BUY against a short, and
    no more than the position size. Everything else would OPEN or ADD.
    """
    bad = []
    for o in orders:
        if (o.get("type") or "").upper() not in STOP_TYPES:
            continue
        qty = abs(float(o.get("qty") or 0))
        act = (o.get("action") or "").upper()
        if abs(net) < 0.5:
            bad.append({**o, "why": "venue is FLAT — this stop can only OPEN a position"})
        elif net > 0 and act != "SELL":
            bad.append({**o, "why": f"BUY stop against a LONG {net:g} — would ADD, not protect"})
        elif net < 0 and act != "BUY":
            bad.append({**o, "why": f"SELL stop against a SHORT {net:g} — would ADD, not protect"})
        elif qty > abs(net) + 0.5:
            bad.append({**o, "why": f"stop qty {qty:g} exceeds the position {abs(net):g} — the "
                                    f"excess would open the other way"})
    return bad


async def venue_snapshot(cfg: RunConfig):
    """(net, orders) in ONE read-only connection. None net on ANY doubt — never guess, and never
    return 0.0 as a stand-in for "could not read", which would make a naked position look flat.

    Positions and orders come from the SAME snapshot on purpose: fetching them separately would let
    a fill land between the two and manufacture a phantom orphan.
    """
    try:
        from ib_async import IB, ContFuture
    except Exception:
        return None, None
    ib = IB()
    try:
        await ib.connectAsync(cfg.host, cfg.port, clientId=RECON_CLIENT_ID,
                              readonly=True, timeout=15)
        await asyncio.sleep(1.0)
        await ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))
        await ib.reqAllOpenOrdersAsync()
        await asyncio.sleep(0.8)
        net = sum(p.position for p in ib.positions() if p.contract.symbol == cfg.symbol)
        orders = [{"id": t.order.orderId, "client": t.order.clientId, "action": t.order.action,
                   "type": t.order.orderType, "qty": t.order.totalQuantity,
                   "aux": t.order.auxPrice, "status": t.orderStatus.status}
                  for t in ib.openTrades()
                  if getattr(t.contract, "symbol", None) == cfg.symbol
                  and t.orderStatus.status not in ("Cancelled", "ApiCancelled", "Filled")]
        return net, orders
    except Exception:
        return None, None
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

    net1, orders1 = asyncio.run(venue_snapshot(cfg))
    r1 = deskrecon.reconcile(net1)
    orph1 = orphan_stops(net1, orders1) if (net1 is not None and orders1 is not None) else []
    result = {"ts": datetime.now(UTC).isoformat(timespec="seconds"),
              "read1": {"venue": net1, "ok": r1.ok, "breach": r1.breach,
                        "unaccounted": r1.unaccounted, "summary": r1.summary(),
                        "reasons": r1.reasons, "orders": len(orders1 or []),
                        "orphan_stops": orph1}}

    if (r1.breach or orph1) and not a.dry_run:
        # ★ SECOND, INDEPENDENT READ. A fresh connection a few seconds later — not a re-use of the
        # first snapshot, which would confirm nothing. A fill in flight resolves; an orphan does not.
        # This confirms BOTH faults: a bracket's stop can exist for a moment before its parent
        # fills, which looks identical to an orphan on a single read.
        time.sleep(SECOND_READ_DELAY_S)
        net2, orders2 = asyncio.run(venue_snapshot(cfg))
        r2 = deskrecon.reconcile(net2)
        orph2 = orphan_stops(net2, orders2) if (net2 is not None and orders2 is not None) else []
        result["read2"] = {"venue": net2, "breach": r2.breach, "unaccounted": r2.unaccounted,
                           "summary": r2.summary(), "orphan_stops": orph2}
        confirmed = (r2.breach and r1.unaccounted is not None and r2.unaccounted is not None
                     and abs(r1.unaccounted - r2.unaccounted) < 0.5)
        result["confirmed"] = confirmed
        if confirmed:
            reason = f"unaccounted {r2.unaccounted:+g} lots — {r2.summary()}"
            actions = bench_everything(reason)
            result["actions"] = actions
            page(f"⚠⚠ GAZBOT CROSS-DESK BREACH — {reason}. BOTH DESKS STOPPED: "
                 f"{'; '.join(actions)}. IBKR is the truth and it does not match our books. "
                 f"Check TWS; release with scripts/desk_reconcile.py --release.",
                 dedupe_key="reconcile_breach")
        elif r1.breach:
            result["note"] = "not confirmed on the second read — treated as a position-change race"
        if not confirmed:
            # ★ RE-ARM ON RESOLUTION. A cooldown must suppress a CONTINUING condition, never a NEW
            # occurrence of one — otherwise a breach that clears and returns inside 30 minutes is
            # silent, which is precisely the alert you most need.
            try:
                sys.path.insert(0, f"{GB}/src")
                from gazbot7.notify import dedupe_clear
                dedupe_clear("reconcile_breach")
            except Exception:
                pass

        # ★ ORPHAN STOPS ALARM BUT DO NOT KILL, and this asymmetry is deliberate. An unaccounted
        # POSITION means a book is lying and nobody may trade. An orphan ORDER means the books may
        # be perfectly right and a stop was simply not cleaned up — stopping both desks for that is
        # disproportionate. It still pages critical, because this is what opened a naked short on
        # 08-06 and what sat live for two hours on 08-13.
        # It does NOT cancel, either: this service is read-only by construction (clientId 8,
        # readonly=True) so that it can be trusted to run unattended. Cancelling is a human call —
        # and note the owning clientId matters, since eod_flatten's cancel failed with Error 10147
        # ("not yours") and that read as an all-clear.
        both = [o for o in orph2 if any(o["id"] == p["id"] for p in orph1)]
        result["orphans_confirmed"] = both
        if both:
            desc = "; ".join(f"#{o['id']} client{o['client']} {o['action']} {o['type']} "
                             f"{o['qty']:g} @ {o['aux']} — {o['why']}" for o in both)
            page(f"⚠⚠ GAZBOT ORPHAN STOP — a working order with nothing behind it: {desc}. "
                 f"This is the 08-06 shape: it can FIRE and open a naked position. Cancel it as its "
                 f"OWNING clientId — another client gets Error 10147 which looks like success.",
                 dedupe_key="reconcile_orphan")

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(("BREACH " if r1.breach else "ok     ") + r1.summary()
              + f"  | {len(orders1 or [])} working order(s)")
        for x in r1.reasons:
            print(f"  · {x}")
        for o in orph1:
            print(f"  ! ORPHAN STOP #{o['id']} client{o['client']} {o['action']} {o['type']} "
                  f"{o['qty']:g} @ {o['aux']} — {o['why']}")
        if "actions" in result:
            print("  ACTIONS: " + "; ".join(result["actions"]))
    try:
        with open(STATE, "w") as fh:
            json.dump(result, fh, indent=1)
    except Exception:
        pass
    return 1 if (r1.breach or orph1) else 0


if __name__ == "__main__":
    sys.exit(main())
