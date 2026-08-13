"""CROSS-DESK RECONCILE — the one owner of ``venue == tournament + day_rider``.

★★ WHY THIS EXISTS (LIVE INCIDENT 2026-08-13). The day-rider sold EIGHT LOTS IT DID NOT OWN and
booked $1,551 of profit that never existed, while IBKR's own executions put the day at −$25.50
against books claiming +$835. Operator: *"ibkr is the truth. this is something gazbot v5 got right.
never rely on our books. ever."*

Every guard that should have caught it was per-desk and therefore blind:

* the tournament's ``reconcile`` runs about every SECOND and DID fire (drift → halt at 15:53) — but
  on ``drift`` the whole safety block is skipped (max-hold / naked-audit / re-protect / stop-breach
  all sit behind ``!= "drift"``), and it has no authority over the other desk anyway;
* the day-rider had NO reconcile invariant at all — it used the shared account net as a proxy for
  "do I have a position", which is exactly the thing a netted account cannot tell you;
* ``multislot_core._foreign_net()`` decides what is "not ours" by reading the DAY-RIDER'S OWN
  self-reported state file — two books vouching for each other, with no independent truth;
* the only cross-desk detector (``router_watch.py``'s DESK-MISMATCH) was throwing NameError, and the
  fix sat un-deployed in a file while the service ran 23h-old code in memory.

★★★ THE KEY INSIGHT, and why "just read the venue" is not enough. IBKR nets every desk on DUQ191770
into ONE number, so a desk CANNOT read its own position from the venue — the information is not
there. `own_flatten_verdict()` says as much in its docstring. Therefore on a shared account
**venue-first means: nobody may act unless the venue fully reconciles against the sum of every
desk's claim.** An unaccounted lot means at least one book is lying, and you do not know which — so
no desk may trade until it is resolved. That invariant is this module.

★ FAIL-CLOSED, WITH AN ASYMMETRY THAT MATTERS.
  · Cannot verify (stale claim, unreadable file, no venue read) → ``ok=False`` → block NEW orders,
    but do NOT kill. A transient file read must never take the desk down.
  · CONFIRMED numeric breach (an unaccounted lot seen on two INDEPENDENT venue reads) → ``breach``
    → kill both desks. Two reads because the claims and the venue are sampled at different instants,
    so any position change opens a window where they legitimately disagree; a real orphan persists
    across reads, a race does not. (Same two-tick confirmation router_watch.py adopted on 08-12
    after it false-fired twice.)

Pure and side-effect free on purpose — the service that pages and kills is scripts/desk_reconcile.py,
and the desks import ``verdict()`` to gate their own order paths. One invariant, one implementation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

GB = "/home/alphabot/gazbot7"
STATUS = f"{GB}/data/status.json"
DR_STATE = f"{GB}/data/day_rider_state.json"
KILL = f"{GB}/data/desk_kill.json"

# A claim older than this is not a claim. The tournament writes status.json every cycle (~1s) and the
# rider heartbeats every minute, so these are generous by an order of magnitude — the point is to
# catch a DEAD writer, not a slow one.
TOURN_MAX_AGE_S = 120.0
RIDER_MAX_AGE_S = 180.0
EPS = 0.5          # lots; venue and claims are whole contracts, so anything >= 1 is a real lot


@dataclass
class Recon:
    ok: bool = False                  # every input fresh AND the invariant holds
    breach: bool = False              # a real unaccounted lot (only ever set with fresh inputs)
    venue_net: float | None = None
    tournament: float | None = None
    rider: float | None = None
    unaccounted: float | None = None
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> str:
        v = "?" if self.venue_net is None else f"{self.venue_net:+g}"
        t = "?" if self.tournament is None else f"{self.tournament:+g}"
        r = "?" if self.rider is None else f"{self.rider:+g}"
        u = "?" if self.unaccounted is None else f"{self.unaccounted:+g}"
        return f"venue {v} = tournament {t} + rider {r} → unaccounted {u}"


def _age_s(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        return (now - datetime.fromisoformat(str(iso))).total_seconds()
    except Exception:
        return None


def tournament_claim(now: datetime, path: str | None = None) -> tuple[float | None, str]:
    """Net lots the TOURNAMENT says it holds, from its own slot ledger.

    Returns (None, why) when the claim cannot be trusted — a missing file, a stale write, or a slot
    row we cannot parse. None is not zero: "I do not know" must never read as "flat", which is the
    mistake that let a naked position look like an idle desk.
    """
    # ★ Resolved at CALL time, never as a default argument. A default binds the module global at
    # IMPORT time, so redirecting deskrecon.STATUS afterwards silently had no effect and the
    # function kept reading the live desk — caught by tests/test_deskrecon.py before deploy. The
    # same early-binding trap would defeat any attempt to point this at a replay or a fixture.
    path = path or STATUS
    try:
        with open(path) as fh:
            s = json.load(fh)
    except Exception as e:
        return None, f"status.json unreadable ({type(e).__name__})"
    age = _age_s(s.get("ts"), now)
    if age is None:
        return None, "status.json has no parseable ts"
    if age > TOURN_MAX_AGE_S:
        return None, f"status.json STALE ({age:.0f}s > {TOURN_MAX_AGE_S:.0f}s) — tournament dead?"
    net = 0.0
    for slot in (s.get("protection") or {}).get("slots") or []:
        try:
            qty = abs(float(slot.get("qty") or 0.0))
            side = str(slot.get("side") or "").upper()
            if qty <= 0 or side not in ("LONG", "SHORT"):
                return None, f"unparseable slot {slot!r}"
            net += qty if side == "LONG" else -qty
        except Exception:
            return None, f"unparseable slot {slot!r}"
    return net, "ok"


def rider_claim(now: datetime, path: str | None = None) -> tuple[float | None, str]:
    """Net lots the DAY-RIDER says it holds.

    ★ `closed` is honoured here — and that is the whole point. On 08-13 the rider's manage guard
    tested `entered` without `closed`, so a closed position kept being managed and re-sold. A claim
    of "entered but closed" is a claim of ZERO, not of qty.
    """
    path = path or DR_STATE
    try:
        with open(path) as fh:
            st = json.load(fh)
    except Exception as e:
        return None, f"day_rider_state unreadable ({type(e).__name__})"
    age = _age_s(st.get("heartbeat"), now)
    if age is None:
        return None, "day_rider_state has no parseable heartbeat"
    if age > RIDER_MAX_AGE_S:
        return None, f"day_rider_state STALE ({age:.0f}s) — rider dead or switched off?"
    if not st.get("entered") or st.get("closed"):
        return 0.0, "ok (flat)"
    try:
        qty = abs(float(st.get("qty") or 0.0))
        direction = int(st.get("direction") or 0)
    except Exception:
        return None, "unparseable qty/direction"
    if qty <= 0 or direction not in (-1, 1):
        return None, f"claims open but qty={st.get('qty')!r} direction={st.get('direction')!r}"
    return direction * qty, "ok"


def reconcile(venue_net: float | None, now: datetime | None = None) -> Recon:
    """The invariant. ``venue_net`` is IBKR truth for the symbol; None means we could not read it."""
    now = now or datetime.now(UTC)
    r = Recon(venue_net=venue_net)
    t, twhy = tournament_claim(now)
    d, dwhy = rider_claim(now)
    r.tournament, r.rider = t, d
    if twhy != "ok":
        r.reasons.append(f"tournament claim: {twhy}")
    if not dwhy.startswith("ok"):
        r.reasons.append(f"rider claim: {dwhy}")
    if venue_net is None:
        r.reasons.append("no venue read — IBKR truth unavailable")
    if venue_net is None or t is None or d is None:
        # Cannot assert the invariant. Block new orders; do NOT kill.
        return r
    r.unaccounted = round(venue_net - (t + d), 4)
    if abs(r.unaccounted) >= EPS:
        r.breach = True
        r.reasons.append(
            f"{r.unaccounted:+g} lots at the venue belong to NO desk — {r.summary()}")
        return r
    r.ok = True
    return r


def kill_active(path: str | None = None) -> tuple[bool, str]:
    """Is a cross-desk kill in force? Fail-CLOSED: an unreadable-but-present kill file counts as
    active, because the file only ever exists when something has already gone wrong."""
    import os
    path = path or KILL
    if not os.path.exists(path):
        return False, ""
    try:
        with open(path) as fh:
            k = json.load(fh)
        if not k.get("active"):
            return False, ""
        return True, str(k.get("reason") or "cross-desk reconcile breach")
    except Exception:
        return True, "desk_kill.json present but unreadable — treating as ACTIVE"


def may_place_order(venue_net: float | None, now: datetime | None = None) -> tuple[bool, str]:
    """The gate every order path should call. True only when a kill is not in force AND the venue
    fully reconciles against every desk's claim.

    This is what "venue-first" means on a SHARED account: a desk cannot read its own position out of
    a netted number, so the only honest precondition for trading is that the whole account adds up.
    """
    active, why = kill_active()
    if active:
        return False, f"CROSS-DESK KILL active: {why}"
    r = reconcile(venue_net, now)
    if r.ok:
        return True, "reconciled"
    return False, "; ".join(r.reasons) or "cannot verify the venue against desk claims"
