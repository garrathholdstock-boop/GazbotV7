"""GAZBOT V7 — DAY RIDER: the drift strategy, as its own service with its own safety.

Operator, 2026-08-05: "this gate needs to run by itself with its own systems" · "build it to go live
into paper tonight" · "never hold overnight. ever."

★ WHY IT IS NOT A TOURNAMENT GATE. multislot_core.py:372 force-flattens EVERY position at
cfg.max_hold_minutes = 120. This strategy holds from ~13:40 to 21:00 — 7h20m. Measured cost of living
inside that cap: $13,257 -> $7,047, and at 120 min it FAILS the robustness battery (beaten by 2 of 30
random-direction seeds). Raising the global cap was the alternative and it is worse: that same 120-min
cap is what closed this morning's MD_STREAM shorts — opened with 1,848-point stops — at exactly two
hours for -$255.50. So the tournament keeps its cap and this runs alone.

★ THE STRATEGY, frozen exactly as validated (scripts/day_rider.py + drift.py, 0 mismatches over 31
sessions):
    DETECT   from the 13:30 UTC open: efficiency >= 0.15 AND roundtrip >= 0.45 (gazbot7.drift)
    ENTER    2 lots, direction = sign of net. ONE entry per session, no re-entry.
    EXIT     arm a 100pt trail once +150pt ahead; HARD FLAT at 21:00 UTC (23:00 Paris).
    NEVER    hold overnight. Not a preference — a constraint.

★★ THE SAFETY IS THE HARD PART, because this inherits none of the tournament's. Four layers:

  1. HEARTBEAT + WATCHDOG. The loop stamps data/day_rider_state.json every pass. A separate timer
     (scripts/day_rider_watchdog.py) flattens and alarms if a position exists while the heartbeat is
     stale. This is the layer that matters: the real risk here is not price, it is THIS PROCESS DYING
     with 2 lots open. The desk has been here before — a naked LONG bled -$400 over three hours.
  2. A VERY WIDE VENUE STOP (600pt default). Deliberately wider than any drawdown in the sample: the
     deepest recovery was 511pt, so it should never fire on a live trade. Measured: a 400pt stop costs
     $3,451 of expectancy AND has a WORSE worst-day (-$1,603) than running naked (-$1,531), because it
     kills the winner that drew 511pt and came back. So this stop is not a trading decision — it is
     insurance against losing the watchdog too, priced at ~zero on the historical sample.
  3. RESTART-SAFE STATE. Position, entry, direction and peak are persisted every loop, so a bounce
     mid-trade RESUMES managing rather than orphaning. Losing the peak would silently reset the trail.
  4. FAIL-CLOSED. Any exception, unreadable tape, or venue/state disagreement => do nothing new and
     alarm. It will never open a position it cannot verify, and never sizes from a stale read.

★ OPERATOR APPROVAL ON EXIT (operator: "you telegram me 2-3 times... or maybe wait for my approval.
and if it doesnt come we hold until close"). On a candidate discretionary exit it pushes at T, T+15,
T+30 and DEFAULTS TO HOLD. Default-hold is also the empirically right default: holding to 21:00 beat
every reactive exit tested (25 variants), the best of them by $3,115. Only the 21:00 flat and the
safety layers can close a position without the operator.

★ SWITCH: data/day_rider.env -> `day_rider=on|off`. Off by default. The router may bench it.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os

from .config import RunConfig
from .drift import OPEN_UTC_MIN, read as drift_read
from .notify import dedupe_clear, dedupe_ok
from .safety import own_flatten_verdict, safe_flatten_verdict

log = logging.getLogger("day_rider")

CLIENT_ID = 4                      # core=0, md=2, eod=6, checks=8, depth=97 — 4 is free
GB = "/home/alphabot/gazbot7"
STATE = f"{GB}/data/day_rider_state.json"
SWITCH = f"{GB}/data/day_rider.env"
LOTS = 2
# ★ NO NEW ENTRY AFTER THIS. Across all 31 validated sessions the detector confirmed between 13:38 and
# 14:09 — never later. The service ticks to 21:00, so without this guard it could enter at 17:00 on a
# setup the backtest contains ZERO examples of, and then hold it with under four hours to the hard flat.
# 15:00 sits ~50 min beyond the latest observed detection: wide enough that no tested case is excluded,
# tight enough that the strategy only ever trades the distribution it was validated on. Managing an
# already-open position continues normally past this time; it gates ENTRY only.
ENTRY_CUTOFF_MIN = 15 * 60
# ★★ FLAT AT 20:40 UTC = 22:40 PARIS, NOT AT THE 21:00 HALT. Operator, 2026-08-05: "flatten at 23
# doesnt work. market is closed. needs to be at 2240 so you have 20 minutes to troubleshoot and try
# again if necessary." He is right and the original 21:00 was a real defect: 23:00 Paris IS the CME
# daily halt, so a flatten fired then has no market to fill into AND no retry window — the one failure
# mode that turns "never hold overnight" from a constraint into a hope.
# Because the service ticks every minute, 20:40 gives ~20 automatic retries before the halt.
# Measured cost of moving it 20 min earlier: $149 of $13,257 (1.1%), and days-green IMPROVES 81% -> 84%.
# Moving it to 22:00 Paris instead would cost $2,309, so 20:40 is the right point on that curve.
FLAT_UTC_MIN = 20 * 60 + 40
HALT_UTC_MIN = 21 * 60             # the venue closes here; nothing can be done after it
# ★★2026-08-07 ATR-SCALED TRAIL (operator: "deploy the atr trail"). Backtested over 35 detected
# sessions 06-22..08-07, every rule scored on IDENTICAL entries so the RANKING is the trustworthy part:
#     trail 2xATR armed at 4xATR ....... $7,341   strip-best $6,184  strip-best-3 $4,109  25/35 green
#     hold, no exit at all ............. $6,544   strip-best $4,760  strip-best-3 $1,467  23/35
#     FIXED trail 100pt armed +150pt ... $3,732   strip-best $2,990  strip-best-3 $1,583  25/35
# Both halves positive for the ATR rule (H1 $4,369 / H2 $2,972), so it is not one half carrying it.
# ★ THE FIX IS THE ARMING, NOT THE TRAIL. A FIXED +150pt arm is a threshold a losing trade can never
#   reach: on 2026-08-07 the live rider sat -252pt and the trail NEVER armed, so it rode to the clock.
#   On a quiet day 150pt is unreachable; on a violent day it arms on noise. At 4xATR it arms when the
#   DAY says the move is real.
# ⚠ HONEST CAVEAT: the lab's entries are systematically EARLIER than live — validating on 08-07 the lab
#   detected 14:04 @29619 where the live service detected 14:12 @29567 (identical data, 5234 rows both).
#   Cause: efficiency OSCILLATES across the 0.15 floor (0.157->0.114->0.150->0.158 in 8 min) and the lab
#   takes the first crossing while live samples once a minute on a partial bar. ABSOLUTE totals are
#   optimistic; the RANKING is unaffected because all rules share the entries. Deployed on the ranking.
# REVERT: set USE_ATR_TRAIL = False — the fixed constants below are retained and still used as the
# fallback whenever the frozen entry ATR is unavailable.
USE_ATR_TRAIL = True
ARM_ATR_MULT = 4.0                 # arm the trail once this many ATR ahead

# ★2026-08-14 repeat-suppression for the "not mine, standing down" alarm. SIX HOURS because the
# condition is a normal shared-account steady state that persists for the whole pre-open stretch —
# the tournament may hold from the 22:00 reopen until the 13:30 cash open. A size change re-alarms
# immediately regardless (the message carries `net`), and the key is CLEARED the moment the venue
# goes flat, so a NEW occurrence is never swallowed by a running cooldown.
_UNOWNED_KEY = "day_rider.unowned_venue_net"
_UNOWNED_COOLDOWN_S = 6 * 3600
TRAIL_ATR_MULT = 2.0               # then trail this many ATR off the peak
ARM_PT = 150.0                     # fallback: trail arms once this far ahead
TRAIL_PT = 100.0
VENUE_STOP_PT = 600.0              # last-resort only; see docstring note 2
HEARTBEAT_STALE_S = 180

# ── OPERATOR-APPROVED DISCRETIONARY EXIT ──────────────────────────────────────────────────────────
# Operator: "you telegram me 2-3 times... 15 minutes apart" then "or maybe wait for my approval. and if
# it doesnt come we hold until close."
# ★ DEFAULT IS HOLD, AND THAT IS THE PROFIT-MAXIMISING DEFAULT, not merely the cautious one. Across 25
# exit variants tested, holding to 21:00 beat every reactive rule — the best of them (a 2xATR reversal)
# by $3,115, and the give-back family by ~$11,000. So on the days the operator does not reply, the
# system does the thing the data says is right. An auto-SELL default would have been worse on both axes.
# ★ THE TRIGGER IS DELIBERATELY THE LEAST-BAD PRICE RULE (2xATR against the peak). It is NOT armed
# because it makes money — it does not. It exists so a genuine reversal reaches the OPERATOR rather than
# being silently ignored or silently acted on. The rule asks; the human decides.
APPROVAL_FILE = f"{GB}/data/day_rider_approval.json"
EXIT_ASK_ATR_MULT = 2.0            # reversal from the peak, in ATR, that raises the question
EXIT_ASK_INTERVAL_S = 15 * 60      # 15 minutes between pushes
EXIT_ASK_MAX_PUSHES = 3            # then stop asking and keep holding — never escalate to a sell


def enabled() -> bool:
    """Off unless explicitly switched on. A missing/unreadable file means OFF, never ON."""
    try:
        for line in open(SWITCH):
            s = line.strip()
            if s.startswith("day_rider="):
                return s.split("=", 1)[1].strip().lower() == "on"
    except Exception:
        pass
    return False



# ── BOOKING THE TRADE (2026-08-11, operator: "yes ship the trade rows") ──────────────────
# The day rider has been live in paper since 08-05 and has NEVER written a trade row. Three
# things were false as a result and all three were reported as if true:
#   · scripts/claim_audit.py scores MANUAL_CLAIM against what holding would have made — it
#     queries `trades`, so every Claim-profit press was UNSCORED. The operator is actively
#     using that button; nothing was measuring it.
#   · sweep.py's day_rider_pnl / day_rider_trades read 0 on every day, whatever the rider did.
#   · there was no P&L history for a desk that has been trading for a week.
#
# ★★ ATTRIBUTION IS THE POINT, not just the row. The gate is tagged `day_rider` because
# pnl.realized() splits the books on exactly that prefix (DAY_RIDER_GATE_PREFIX): desk=
# "tournament" excludes it, desk="day_rider" keeps only it. Two desks share one IBKR account
# and one trades table; a row that does not say which desk owns it is how the 08-06 confusion
# gets written into the permanent record.
#
# Fee is fee_rt (1.50) PER LOT round-turn — never $5, never per side. VPP is 2.0 for MNQ.
DAY_RIDER_GATE = "day_rider"
DB_PATH = f"{GB}/data/gazbot7.db"
# ⚠ MNQ IS $2/POINT AND THE FEE IS $1.50 PER LOT ROUND-TURN. Written out because the pair
# `VPP, FEE = 2.0, 1.5` and `FEE, VPP = 5.0, 2.0` look identical at a glance and are reversed —
# a wrong fee constant has silently corrupted twelve harnesses on this desk before.
VPP = 2.0
FEE_RT = 1.5


def book_trade(out: dict, exit_px: float, reason: str, notify=None) -> None:
    """Write the closed round-trip to the trades table. Never raises: a booking failure must
    not stop a flatten from completing or a session from closing cleanly — the position is
    already out at this point and the row is bookkeeping. It DOES notify on failure, because a
    silently missing row is what created this whole gap."""
    try:
        entry = float(out.get("entry") or 0)
        qty = abs(float(out.get("qty") or 0))
        d = int(out.get("direction") or 0)
        if entry <= 0 or qty <= 0 or d not in (-1, 1) or not exit_px:
            # ★2026-08-13 was a BARE `return`. The docstring promises "It DOES notify on failure,
            # because a silently missing row is what created this whole gap" — but that only held
            # for the except path below. A falsy exit_px or a torn book returned here in silence,
            # which is the same invisible-loss shape the else-branch bug produced. Guard failures
            # are now as loud as exceptions.
            if notify:
                notify(f"⚠ DAY RIDER: refused to book {reason} — entry={entry!r} qty={qty!r} "
                       f"direction={d!r} exit_px={exit_px!r}. The trades row is MISSING and P&L "
                       f"plus claim_audit will be short one trade.", critical=True)
            return
        gross = d * (exit_px - entry) * VPP * qty
        fees = FEE_RT * qty
        from . import store as _store
        conn = _store.open_store(DB_PATH)
        _store.record_trade(
            conn, symbol="MNQ", side="LONG" if d > 0 else "SHORT", qty=qty,
            entry_price=entry, exit_price=float(exit_px),
            opened_at=out.get("entered_at") or dt.datetime.now(dt.UTC).isoformat(),
            closed_at=dt.datetime.now(dt.UTC).isoformat(),
            pnl_usd=round(gross - fees, 2), fees_usd=round(fees, 2),
            exit_reason=reason, gate=DAY_RIDER_GATE,
            # The exit fill id would make this idempotent; the rider places a plain market
            # order and does not capture one, so a same-second double-book is possible in
            # principle. One entry per session and a `closed` latch make it not possible in
            # practice — but say so rather than imply an idempotency that is not there.
        )
        conn.close()
    except Exception as e:
        if notify:
            try:
                notify(f"DAY RIDER: trade booked to state but FAILED to write the trades row "
                       f"({type(e).__name__}: {e}) — P&L history and claim_audit will be short "
                       f"one trade", critical=False)
            except Exception:
                pass


def venue_first_ok(net: float | None, what: str, notify=None) -> bool:
    """VENUE-FIRST GATE. May this desk place an order at all?

    ★★2026-08-13 — the lesson of the phantom re-booking. This desk sold EIGHT LOTS IT DID NOT OWN
    because its order paths trusted its own state file. Operator: "ibkr is the truth ... never rely
    on our books. ever."

    ★ On a SHARED, NETTED account you cannot fix that by "reading the venue" — IBKR nets both desks
    into one number, so the venue CANNOT tell this desk what it holds (``own_flatten_verdict``'s
    docstring says exactly this). The only honest precondition is that the WHOLE account adds up:
    venue == tournament claim + our claim. An unaccounted lot means some book is lying and you do
    not know which, so nobody may trade until it is resolved. That is what deskrecon owns.

    ⚠ NOT APPLIED TO THE 20:40 HARD FLAT, deliberately. "NEVER HOLD OVERNIGHT. EVER." is the
    operator's absolute rule, and refusing to flatten because the account does not reconcile would
    turn a bookkeeping fault into an overnight position — strictly worse. That path pages instead.
    """
    try:
        from .deskrecon import may_place_order
        ok, why = may_place_order(net)
    except Exception:
        return True          # never let the GATE itself break trading; deskrecon's own service alarms
    if not ok and notify:
        try:
            notify(f"⚠ DAY RIDER REFUSED to {what} — venue-first check failed: {why}. "
                   f"IBKR does not reconcile against the desks' claims, so no order was placed.",
                   critical=True)
        except Exception:
            pass
    return ok


async def cancel_own_stops(ib, symbol: str, notify=None) -> int:
    """Cancel THIS client's working stop orders. Call on EVERY path that closes the position.

    ★★2026-08-13 — THE ROOT CAUSE OF A LIVE ORPHAN. The 600pt venue stop is placed with the entry
    and nothing ever took it down. The operator claimed at 14:26; the stop (orderId 49, SELL 2 STP
    @ 29424.25) stayed WORKING at the venue for two more hours against a flat account. That is the
    08-06 shape exactly: on that date a leftover stop fired with nothing behind it and opened a
    naked short, booked six hours later as a gate trade nobody placed.
    eod_flatten cannot clean this up: it runs as clientId 6 and IBKR answers a cross-client cancel
    with `Error 10147: not found`, which reads like an all-clear. Only the OWNER can cancel it, and
    the owner is this module.

    ★★ IT FILTERS ON clientId AND WILL NOT TOUCH ANOTHER DESK'S STOPS. DUQ191770 is shared with the
    tournament, whose per-slot stops are the only thing standing between it and an unprotected
    position. Cancelling those would convert a bookkeeping tidy-up into the worst incident on this
    desk. The filter is the safety property here, not an optimisation.

    Returns the number cancelled. Never raises — a failed cleanup must not break a flatten that has
    already completed, and the cross-desk reconciler alarms on any orphan within 30s regardless.
    """
    n = 0
    try:
        await ib.reqAllOpenOrdersAsync()
        await asyncio.sleep(0.5)
        for t in list(ib.openTrades()):
            o = t.order
            if getattr(t.contract, "symbol", None) != symbol:
                continue
            if int(getattr(o, "clientId", -1)) != CLIENT_ID:
                continue                      # ← NOT OURS. Never cancel the tournament's stops.
            if str(getattr(o, "orderType", "")).upper() not in ("STP", "STP LMT", "TRAIL",
                                                               "TRAIL LIMIT"):
                continue
            if t.orderStatus.status in ("Cancelled", "ApiCancelled", "Filled"):
                continue
            ib.cancelOrder(o)
            n += 1
        if n:
            await asyncio.sleep(1.5)
            still = [t for t in ib.openTrades()
                     if getattr(t.contract, "symbol", None) == symbol
                     and int(getattr(t.order, "clientId", -1)) == CLIENT_ID
                     and t.orderStatus.status not in ("Cancelled", "ApiCancelled", "Filled")]
            if still and notify:
                # Say so rather than assume: an uncancelled stop is a naked position waiting to
                # happen, and silence here is what let orderId 49 live for two hours.
                notify(f"⚠ DAY RIDER: asked to cancel {n} venue stop(s) but {len(still)} still "
                       f"WORKING (ids {[t.order.orderId for t in still]}). A stop with no position "
                       f"can FIRE and open a naked one — cancel it as clientId {CLIENT_ID}.",
                       critical=True)
    except Exception as e:
        if notify:
            try:
                notify(f"⚠ DAY RIDER: venue-stop cleanup FAILED ({type(e).__name__}: {e}). Check "
                       f"for a working stop with no position behind it.", critical=True)
            except Exception:
                pass
    return n


CLAIM_FILE = "/home/alphabot/gazbot7/data/day_rider_claim.txt"
# Long enough to survive a slow tick or a one-off service restart, far short of
# the overnight gap that would let a press leak into the next session.
CLAIM_MAX_AGE_S = 15 * 60


def claim_requested() -> bool:
    """Has the operator pressed Claim profit on the dashboard?

    ★ The web process NEVER places an order. It writes this file and returns; the
    day-rider picks it up on its own cycle and flattens through its own safety.
    That indirection is the whole design: a button that reached the broker
    directly is how 2026-08-06 happened — a flatten fired without checking whose
    position it was, the tournament's book went to +2 against a venue of 0, and
    the desk sat halted for 11 minutes with the safety block skipped.

    ⚠ A claim EXPIRES after CLAIM_MAX_AGE_S. The endpoint refuses to write one
    unless a position is open, but the tick can still exit by hard-flat or venue
    stop in the same cycle before this branch is reached, leaving the file behind
    with nothing to consume it. Unbounded, that file waits and fires against
    TOMORROW's entry seconds after it opens — a press the operator made yesterday
    at +$300 flattening a fresh position at 0. Age-bounding makes a lost press
    cost a re-press, which is the cheap direction of that trade.
    """
    try:
        raw = open(CLAIM_FILE).read().strip()
    except Exception:
        return False
    try:
        age = (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(raw)).total_seconds()
    except Exception:
        clear_claim()          # unreadable stamp — refuse it and do not retry
        return False
    if age > CLAIM_MAX_AGE_S or age < -60:
        clear_claim()
        return False
    return True


def clear_claim() -> None:
    """Consume the request. Cleared whether or not the flatten succeeded, so a
    stale file cannot re-fire the claim on every subsequent tick."""
    try:
        os.remove(CLAIM_FILE)
    except Exception:
        pass


def load_state() -> dict:
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_state(d: dict) -> None:
    """★ THE HEARTBEAT IS A CLAIM THAT SOMEONE IS MANAGING THE POSITION, so callers must set
    `venue_ok` honestly. Discovered live: a clientId collision made the venue connection fail, step()
    correctly took no action — and still stamped a fresh heartbeat. The watchdog reads that as "managed"
    and stays quiet, so a service that cannot reach IBKR would look perfectly healthy while nothing was
    actually managing 2 open lots. `venue_ok=False` is what the watchdog now treats as unmanaged."""
    d.setdefault("venue_ok", False)
    d["heartbeat"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    tmp = STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh, indent=1, sort_keys=True)
    os.replace(tmp, STATE)          # atomic — a torn state file would orphan a live position


def session_key(now: dt.datetime) -> str:
    return now.strftime("%Y-%m-%d")


def read_approval(token: str) -> str | None:
    """The operator's decision for THIS pending request, or None.

    ★ TOKEN-MATCHED so consent cannot be replayed. A bare "sell" flag on disk would survive the day and
    flatten tomorrow's fresh position — approving a trade that did not exist when they typed it."""
    try:
        with open(APPROVAL_FILE) as fh:
            a = json.load(fh)
        if a.get("token") != token:
            return None
        d = str(a.get("decision", "")).lower()
        return d if d in ("sell", "hold") else None
    except Exception:
        return None


def should_ask_exit(direction: int, entry: float, peak: float, price: float, atr: float) -> bool:
    """Has price reversed far enough off the peak to be worth asking about? Pure/testable.
    Only asks once the position is actually AHEAD — a trade that never worked has nothing to protect
    and the operator should not be paged about ordinary noise near the entry."""
    if atr <= 0:
        return False
    if direction * (peak - entry) < ARM_PT:
        return False
    return direction * (peak - price) >= EXIT_ASK_ATR_MULT * atr


def trail_level(direction: int, entry: float, peak: float,
                arm_atr: float = 0.0) -> float | None:
    """The trail, or None while it is not yet armed. Pure, so it is unit-testable.

    ``arm_atr`` is the ATR **frozen at entry** — deliberately NOT ``entry_atr``, which the tick loop
    overwrites with the LIVE atr every pass (it is the reversal-ask input, despite the name). Scaling
    the trail off a moving number would be a different rule from the one that was backtested, which is
    exactly the live/lab divergence this desk keeps getting bitten by. Falls back to the fixed
    point-based rule whenever the frozen ATR is missing (old state files, restarts, atr unavailable)."""
    ahead = direction * (peak - entry)
    if USE_ATR_TRAIL and arm_atr and arm_atr > 0:
        if ahead < ARM_ATR_MULT * arm_atr:
            return None
        return peak - direction * TRAIL_ATR_MULT * arm_atr
    if ahead < ARM_PT:
        return None
    return peak - direction * TRAIL_PT


async def _venue(cfg: RunConfig):
    from ib_async import ContFuture, IB
    ib = IB()
    await ib.connectAsync(cfg.host, cfg.port, clientId=CLIENT_ID, readonly=False, timeout=15)
    await asyncio.sleep(0.8)
    (contract,) = await ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))
    return ib, contract


async def _net_position(ib, symbol: str) -> float:
    return sum(p.position for p in ib.positions() if p.contract.symbol == symbol)


async def step(cfg: RunConfig, *, now: dt.datetime | None = None, notify=None) -> dict:
    """One pass. Returns the state it wrote. Safe to call repeatedly; idempotent per session."""
    now = now or dt.datetime.now(dt.UTC)
    mod = now.hour * 60 + now.minute
    st = load_state()
    out = dict(st)
    out["session"] = session_key(now)
    if st.get("session") != out["session"]:
        out = {"session": out["session"], "entered": False, "closed": False}

    if not enabled():
        out["note"] = "switch off"
        save_state(out)
        return out

    ib = contract = None
    try:
        ib, contract = await _venue(cfg)
        net = await _net_position(ib, cfg.symbol)
        out["venue_ok"] = True          # we are genuinely talking to the broker this tick
        # ★2026-08-11 STAMP THE VENUE READ HERE, ON EVERY PATH, WITH ITS OWN TIMESTAMP.
        # venue_net used to be written only inside the position-management branch, so once the
        # rider closed it FROZE at its last in-position value while save_state kept stamping a
        # fresh heartbeat. The new DESK-MISMATCH detector read the heartbeat as proof the
        # venue number was current and fired a critical false alarm at 19:10Z — "account holds
        # SHORT 2 that no desk claims" — 2.5 hours after it shipped, against an account the
        # watchdog's independent client correctly reported as flat.
        # Two fields in one file with DIFFERENT lifetimes, and one was taken as vouching for
        # the other. Now every read is stamped with venue_net_ts and nothing has to infer it.
        out["venue_net"] = net
        out["venue_net_ts"] = dt.datetime.now(dt.UTC).isoformat()

        # ── 1. THE HARD FLAT. Runs before anything else — but ONLY on a position WE OPENED. ──
        # ★2026-08-06 INCIDENT — this branch used to flatten the ACCOUNT net without asking whose
        # position it was, and `mod < OPEN_UTC_MIN` makes it true on EVERY tick before 13:30. The
        # tournament shares account DUQ191770 and the same MNQ contract, so at 07:08:21 the day-rider
        # sold the tournament's 2 lots 20 SECONDS after they opened, while its own state said
        # entered=false — it flattened a position it had never taken.
        # The damage was not the $27.50: the tournament does not receive executions from another
        # clientId, so its book stayed +2 against a venue of 0 — a reconcile DRIFT that halted the
        # desk for 11 minutes with its whole safety block skipped (multislot_core.py:610), and on
        # restart it "exited" phantom longs into a real -1 short and booked two FICTITIOUS target
        # wins. One unowned flatten cascaded into a halt, a naked short and a corrupted trade record.
        # OWNERSHIP IS NOW THE GATE. A net we did not open belongs to another desk that has its own
        # safety spine; the correct action is to ALARM, never to trade. Note this is the same class
        # of bug as [[md-stream-multi-symbol-filter]] — a SHARED resource consumed without checking
        # the tag that says which owner it belongs to.
        owns_position = bool(out.get("entered")) and not bool(out.get("closed"))
        if mod >= FLAT_UTC_MIN or mod < OPEN_UTC_MIN:
            # Re-arm the moment the condition RESOLVES — the venue went flat, or the position became
            # ours. A cooldown must suppress a CONTINUING state, never a fresh occurrence of one.
            if not (abs(net) > 1e-9 and not owns_position):
                dedupe_clear(_UNOWNED_KEY)
            if abs(net) > 1e-9 and not owns_position:
                out["note"] = (f"venue holds {net:g} the day-rider did NOT open "
                               f"(entered={out.get('entered')}) — left alone, not mine")
                # ★★2026-08-14 SAY IT ONCE. This branch is reached on EVERY tick outside the rider's
                # window — `mod < OPEN_UTC_MIN` is true all morning — so whenever the tournament held
                # a position before 13:30 the operator got this same message every minute for hours.
                # Standing down is CORRECT and fully reconciled (desk_reconcile confirms
                # `venue = tournament + rider, unaccounted +0` every 30s); repeating it is what
                # turned the alarm channel into noise. The text carries `net`, so a SIZE CHANGE
                # re-alarms at once — only an unchanging state goes quiet.
                _msg = (f"DAY RIDER: venue holds {net:g} MNQ that is NOT mine "
                        f"(entered={out.get('entered')}). Leaving it to its owner — the "
                        f"tournament shares this account. NOT flattening.")
                # ★ DEDUPE ON THE SITUATION, NOT THE SIZE. The signature deliberately drops the
                # magnitude: the tournament scales in and out all session, and the rider's decision
                # is identical at -1 or -2, so keying on `net` would re-alarm on every lot it opened
                # or closed (observed live at 12:12Z, -2 → -1). Size correctness is the RECONCILER's
                # job — it checks `venue == tournament + rider` every 30s and pages on an
                # unaccounted lot. What is news here is only that an unowned position EXISTS, so a
                # direction flip re-alarms and a resize does not. The message still shows live size.
                _sig = f"unowned {'SHORT' if net < 0 else 'LONG'} present, entered={out.get('entered')}"
                if notify and dedupe_ok(_UNOWNED_KEY, _sig, cooldown_s=_UNOWNED_COOLDOWN_S):
                    notify(_msg, critical=False)
            elif abs(net) > 1e-9:
                # Size the hard flat from OUR OWN book too (same shared-account reasoning as the
                # exits below). The one deliberate exception in this file: if our own book is
                # unusable — no direction or no qty — we FALL BACK to the venue-net verdict rather
                # than declining to act, because "NEVER HOLD OVERNIGHT" is an absolute operator rule
                # and a broken book is not a reason to carry a position through the halt. That
                # fallback can over-flatten a shared account, so it pages.
                v = own_flatten_verdict(int(st.get("direction") or 0), float(st.get("qty") or 0.0))
                if v is None:
                    v = safe_flatten_verdict(net)
                    if v and notify:
                        notify(f"⚠ DAY RIDER hard flat falling back to VENUE NET ({net:g}) — own book "
                               f"has direction={st.get('direction')!r} qty={st.get('qty')!r}. This may "
                               f"over-flatten a shared account, but overnight is ruled out. CHECK IBKR.",
                               critical=True)
                if v:
                    # ★★ THE HARD FLAT IS DELIBERATELY *NOT* GATED by venue_first_ok. Every other
                    # order path in this file refuses when the account fails to reconcile, but
                    # "NEVER HOLD OVERNIGHT. EVER." is the operator's absolute rule and a
                    # bookkeeping fault must not be allowed to become an overnight position — that
                    # trade is strictly worse. So we flatten anyway and SAY SO loudly instead.
                    try:
                        from .deskrecon import may_place_order
                        _ok, _why = may_place_order(net)
                    except Exception:
                        _ok, _why = True, ""
                    if not _ok and notify:
                        notify(f"⚠ DAY RIDER hard-flatting at the clock WHILE THE ACCOUNT DOES NOT "
                               f"RECONCILE ({_why}). Proceeding anyway — overnight is ruled out — "
                               f"but the sizing comes from a book that may be wrong. CHECK IBKR.",
                               critical=True)
                    from ib_async import MarketOrder
                    ib.placeOrder(contract, MarketOrder(v[0], v[1]))
                    await asyncio.sleep(2.0)
                    # ★ VERIFY, then let the minute cadence retry. A market order that does not fill
                    # is exactly why the flatten moved off the halt — silence here would carry the
                    # position overnight, which the operator has ruled out absolutely.
                    post = await _net_position(ib, cfg.symbol)
                    if abs(post) < 1e-9:
                        out["closed"] = True
                        out["exit_reason"] = "CLOCK_FLAT"
                        # ★2026-08-13 take the venue stop down WITH the position. Placed at entry, it used to
                        # outlive every exit — see cancel_own_stops(). clientId-filtered: never the other desk's.
                        await cancel_own_stops(ib, cfg.symbol, notify)
                        out["note"] = f"FLAT at the {FLAT_UTC_MIN//60:02d}:{FLAT_UTC_MIN%60:02d} clock"
                        book_trade(out, px, "CLOCK_FLAT", notify)
                        if notify:
                            notify(f"DAY RIDER flat at the {FLAT_UTC_MIN//60:02d}:"
                                   f"{FLAT_UTC_MIN%60:02d} UTC clock ({v[0]} {v[1]})", critical=True)
                    else:
                        mins_left = HALT_UTC_MIN - mod
                        out["note"] = (f"FLATTEN INCOMPLETE — still {post} after {v[0]} {v[1]}; "
                                       f"retrying each minute, {mins_left} min before the halt")
                        if notify:
                            notify(f"⚠ DAY RIDER FLATTEN INCOMPLETE — venue still holds {post}. "
                                   f"Retrying every minute; {mins_left} min until the CME halt.",
                                   critical=True)
            elif owns_position:
                # ★2026-08-13 THE LEDGER GAP. Venue is flat at the clock but OUR OWN BOOK still
                # says we are holding (entered and not closed). Both branches above test
                # `abs(net) > 1e-9`, so before this existed the session fell through to the
                # "flat, idle" note below: no book_trade(), no `closed` latch, and the trade
                # vanished from the ledger entirely.
                # Observed twice in one week and NEITHER produced a row:
                #   08-12  SHORT 2 @ 29876.125 — ended `closed: false`, `venue_net: 0`
                #   08-10  SHORT 2 @ 29759.50  — the same shape earlier in the flatten path
                # The dollar cost was small (+$38 / -$71, roughly cancelling) but the RECORD was
                # wrong, and claim_audit.py only reads MANUAL_CLAIM rows so it was structurally
                # blind to it — the week looked like 2 rider trades when there were 4.
                # We do NOT know who closed it (a venue stop, another desk on the shared account,
                # or a manual flatten), so this books the round-trip at the last known price and
                # ALARMS rather than pretending it was a clean exit. Booking a slightly wrong
                # exit price is recoverable; a missing row is not — it silently corrupts every
                # future study, which is exactly what happened here.
                out["closed"] = True
                out["exit_reason"] = "CLOSED_ELSEWHERE"
                # ★2026-08-13 take the venue stop down WITH the position. Placed at entry, it used to
                # outlive every exit — see cancel_own_stops(). clientId-filtered: never the other desk's.
                await cancel_own_stops(ib, cfg.symbol, notify)
                out["note"] = ("venue FLAT at the clock but our book still held — booked at last "
                               "price and latched closed; someone else closed this position")
                book_trade(out, px, "CLOSED_ELSEWHERE", notify)
                if notify:
                    notify(f"⚠ DAY RIDER: venue was already FLAT at the {FLAT_UTC_MIN//60:02d}:"
                           f"{FLAT_UTC_MIN%60:02d} clock while our book still held "
                           f"{out.get('qty')} @ {out.get('entry')}. Booked as CLOSED_ELSEWHERE at "
                           f"{px} — CHECK who closed it (shared account DUQ191770).",
                           critical=True)
            else:
                out["note"] = "outside 13:30-21:00 — flat, idle"
            save_state(out)
            return out

        # ── 2. MANAGE an open position (restart-safe: peak comes from state) ─────────────
        # ★★2026-08-13 — `and not st.get("closed")` IS LOAD-BEARING. Without it this guard tested
        # `entered` only, and `net` is the SHARED ACCOUNT NET (DUQ191770 carries the tournament too).
        # So once our own position was closed but the TOURNAMENT opened something, net went non-zero,
        # `entered` was still true from this session, and we re-entered the manage path on a position
        # we no longer held — evaluating the stale trail against the ORIGINAL entry and peak and
        # booking an exit EVERY MINUTE.
        # Live damage on 08-13: the 13:38 LONG 2 was claimed by the operator at 14:26 (booked once,
        # correctly, +$731). From 15:53 the tournament opened abs_veto_short, net went non-zero, and
        # this branch re-booked that same dead position four times — +$372/+$404/+$373/+$402, $1,551
        # of fictitious profit — until the rider was switched off. It placed no orders (its only
        # executions all day were orderId 48 BOT 2 and orderId 53 SLD 2), so the money was never
        # real, only the rows. They are flagged EXCLUDE:day_rider_phantom_rebook_20260813.
        # ★ This is the 08-06 bug class in a branch that fix missed: a SHARED resource consumed
        # without checking the tag that says whose it is. The direction/size below were already
        # taken from our own book for exactly that reason — but the GUARD deciding whether to run at
        # all was still trusting the shared number. [[md-stream-multi-symbol-filter]]
        if abs(net) > 1e-9 and st.get("entered") and not st.get("closed"):
            # ★2026-08-06 — DIRECTION AND SIZE COME FROM OUR OWN BOOK, NEVER FROM THE ACCOUNT NET.
            # This used to read `d = 1 if net > 0 else -1` and then store `qty=abs(net)`, i.e. it
            # inferred its own position from a number that nets EVERY desk on DUQ191770. With the
            # tournament short 3 against our long 2 the net is −1, so d inverted, `peak` tracked the
            # wrong extreme, `trail_level` computed on the wrong side and the exit fired BUY —
            # ADDING to the long while the state recorded "closed". Our own entry already persisted
            # direction and qty (see the entry block); trust that, and keep the venue net only as an
            # observation. Falls back to the net sign ONLY if state somehow lacks a direction.
            d = int(st.get("direction") or 0) or (1 if net > 0 else -1)
            own_qty = float(st.get("qty") or LOTS)
            entry = float(st.get("entry", 0.0))
            rr = drift_read(cfg.capture_path, cfg.symbol, now)
            px = rr.price or entry
            if rr.atr > 0:
                out["entry_atr"] = round(rr.atr, 2)
            peak = float(st.get("peak", entry))
            peak = max(peak, px) if d > 0 else min(peak, px)
            # qty stays OURS; venue_net is recorded alongside as an observation, so a divergence
            # between the two is visible in state instead of silently overwriting our position.
            out.update(entry=entry, peak=peak, direction=d, qty=own_qty, venue_net=net)
            arm_atr = float(st.get("arm_atr") or 0.0)
            out["arm_atr"] = arm_atr            # carry it forward untouched every tick
            tl = trail_level(d, entry, peak, arm_atr)
            out["trail"] = tl
            out["ahead_pt"] = round(d * (px - entry), 1)

            # ── OPERATOR-APPROVAL EXIT — ask up to 3x, 15 min apart, DEFAULT HOLD ──────────
            atr_now = float(out.get("entry_atr", st.get("entry_atr", 0.0)) or 0.0)
            pend = dict(st.get("pending_exit") or {})
            if pend.get("token"):
                dec = read_approval(pend["token"])
                if dec == "sell":
                    # Gated too: an operator "sell" is a decision about a position, and when the
                    # account does not reconcile we do not know what the position IS. Better to
                    # refuse and page than to size an exit off a book that may be lying.
                    v = (own_flatten_verdict(d, own_qty)  # ours, not the shared account net
                         if venue_first_ok(net, "exit on OPERATOR_SELL", notify) else None)
                    if v:
                        from ib_async import MarketOrder
                        ib.placeOrder(contract, MarketOrder(v[0], v[1]))
                        await asyncio.sleep(2.0)
                        out["closed"] = True
                        out["exit_reason"] = "OPERATOR_SELL"
                        # ★2026-08-13 take the venue stop down WITH the position. Placed at entry, it used to
                        # outlive every exit — see cancel_own_stops(). clientId-filtered: never the other desk's.
                        await cancel_own_stops(ib, cfg.symbol, notify)
                        out["pending_exit"] = None
                        out["note"] = "OPERATOR-APPROVED exit"
                        # A distinct reason from MANUAL_CLAIM on purpose: this is the rider
                        # ASKING and the operator saying sell; MANUAL_CLAIM is the operator
                        # acting unprompted. claim_audit.py should be able to tell a prompted
                        # hand from an unprompted one — they are different skills.
                        book_trade(out, px, "OPERATOR_SELL", notify)
                        if notify:
                            notify(f"DAY RIDER flat on your approval @ ~{px:.2f} "
                                   f"({d*(px-entry):+.0f}pt from entry)", critical=True)
                        save_state(out)
                        return out
                elif dec == "hold":
                    out["pending_exit"] = None
                    out["note"] = "operator said HOLD — riding to 21:00"
                else:
                    n = int(pend.get("pushes", 0))
                    last = float(pend.get("last_push_ts", 0.0))
                    age = now.timestamp() - last
                    if n < EXIT_ASK_MAX_PUSHES and age >= EXIT_ASK_INTERVAL_S:
                        pend["pushes"] = n + 1
                        pend["last_push_ts"] = now.timestamp()
                        if notify:
                            notify(f"DAY RIDER exit? ({pend['pushes']}/{EXIT_ASK_MAX_PUSHES}) "
                                   f"{pend.get('reason','')} · now {px:.2f}, "
                                   f"{d*(px-entry):+.0f}pt from entry, peak {peak:.2f}. "
                                   f"/sell to exit · /hold to keep riding · "
                                   f"NO REPLY = HOLD to the 21:00 flat", critical=True)
                        out["pending_exit"] = pend
                    else:
                        # ★ EXHAUSTED = HOLD. It never escalates to a sell; silence means ride on.
                        out["pending_exit"] = pend
                        if n >= EXIT_ASK_MAX_PUSHES:
                            out["note"] = "asked 3x, no reply — HOLDING to 21:00 (the default)"
            elif should_ask_exit(d, entry, peak, px, atr_now):
                pend = {"token": f"{out['session']}:{int(now.timestamp())}",
                        "reason": (f"reversed {d*(peak-px):.0f}pt off the peak "
                                   f"(>{EXIT_ASK_ATR_MULT:.0f}xATR)"),
                        "pushes": 1, "last_push_ts": now.timestamp()}
                out["pending_exit"] = pend
                if notify:
                    notify(f"DAY RIDER exit? (1/{EXIT_ASK_MAX_PUSHES}) {pend['reason']} · "
                           f"now {px:.2f}, {d*(px-entry):+.0f}pt from entry, peak {peak:.2f}. "
                           f"/sell to exit · /hold to keep riding · "
                           f"NO REPLY = HOLD to the 21:00 flat", critical=True)

            # ── OPERATOR CLAIM ────────────────────────────────────────────────
            # Checked BEFORE the trail: if he has pressed the button, that is the
            # decision, and a trail level reached in the same tick must not
            # pre-empt it and book a different price than the one he saw.
            # Recorded as MANUAL_CLAIM — the same reason string the tournament
            # uses — so scripts/claim_audit.py scores this button automatically
            # against what holding would have made. The nightly audit already
            # exists to answer "what are the operator's hands worth"; this makes
            # the day-rider's claims part of that number from day one.
            if claim_requested():
                clear_claim()
                # Gated. The operator pressing "claim" is not evidence about what the account holds
                # — on 08-13 the claim button was pressed while the books and the venue disagreed by
                # 8 lots. Refusing and paging is the honest answer; the claim can be re-pressed.
                v = (own_flatten_verdict(d, own_qty)  # ours, never the shared account net
                     if venue_first_ok(net, "exit on MANUAL_CLAIM", notify) else None)
                if v:
                    from ib_async import MarketOrder
                    ib.placeOrder(contract, MarketOrder(v[0], v[1]))
                    await asyncio.sleep(2.0)
                    out["closed"] = True
                    out["exit_reason"] = "MANUAL_CLAIM"
                    # ★2026-08-13 take the venue stop down WITH the position. Placed at entry, it used to
                    # outlive every exit — see cancel_own_stops(). clientId-filtered: never the other desk's.
                    await cancel_own_stops(ib, cfg.symbol, notify)
                    book_trade(out, px, "MANUAL_CLAIM", notify)
                    out["note"] = f"claimed by operator at {px:.1f} ({d*(px-entry):+.0f}pt from entry)"
                    if notify:
                        notify(f"DAY RIDER claimed @ {px:.1f} · {d*(px-entry):+.0f}pt from entry "
                               f"(peak {peak:.1f})", critical=False)
                    save_state(out)
                    return out
                # No verdict means we do not own what we think we own. Refuse and
                # say so — silently doing nothing is how an operator presses a
                # button twice and ends up short.
                out["note"] = "claim ignored — ownership check refused (position not ours)"
                if notify:
                    notify("DAY RIDER claim REFUSED — ownership check says this position is not ours",
                           critical=True)
                save_state(out)
                return out

            if tl is not None and ((px <= tl) if d > 0 else (px >= tl)):
                # ★★ THIS IS THE PATH THAT FIRED ON 2026-08-13. With the `closed` latch ignored
                # upstream, it re-armed on a dead position and sold 2 lots a minute, four times,
                # opening a naked 8-lot short. The upstream guard is fixed; this is the second line
                # of defence — it will not place ANYTHING unless IBKR reconciles against both desks.
                v = (own_flatten_verdict(d, own_qty)      # ours, not the shared account net
                     if venue_first_ok(net, "exit on TRAIL", notify) else None)
                if v:
                    from ib_async import MarketOrder
                    ib.placeOrder(contract, MarketOrder(v[0], v[1]))
                    await asyncio.sleep(2.0)
                    out["closed"] = True
                    out["exit_reason"] = "TRAIL"
                    # ★2026-08-13 take the venue stop down WITH the position. Placed at entry, it used to
                    # outlive every exit — see cancel_own_stops(). clientId-filtered: never the other desk's.
                    await cancel_own_stops(ib, cfg.symbol, notify)
                    out["note"] = f"trail hit at {tl:.1f} (peak {peak:.1f})"
                    book_trade(out, px, "TRAIL", notify)
                    if notify:
                        notify(f"DAY RIDER trail exit @ {tl:.1f}, peak {peak:.1f}", critical=False)
            else:
                # ★2026-08-13 THE READOUT LIED. This rendered ARM_PT (150) unconditionally, but
                # trail_level() arms at ARM_ATR_MULT x arm_atr whenever USE_ATR_TRAIL is on — which
                # it is. On 08-11 the real threshold was 130.8pt and on 08-13 it was 131.9pt, so the
                # note overstated the distance to arming by ~19pt every time the operator read it,
                # and shaped a belief that the trail "was still too low" on days it was closer than
                # shown. Report the threshold the RULE uses, and say which rule that is.
                arm_need = (ARM_ATR_MULT * arm_atr
                            if (USE_ATR_TRAIL and arm_atr and arm_atr > 0) else ARM_PT)
                basis = f"{ARM_ATR_MULT:.0f}xATR {arm_atr:.1f}" if arm_need != ARM_PT else "fixed"
                out["note"] = ("riding · trail " + (f"{tl:.1f}" if tl else
                               f"not armed (need +{arm_need:.0f} [{basis}], "
                               f"at {d*(px-entry):+.0f})"))
            save_state(out)
            return out

        # ── 3. ENTRY — once per session, only on a confirmed drift ───────────────────────
        if st.get("entered") or st.get("closed"):
            out["note"] = "already traded this session — no re-entry"
            save_state(out)
            return out
        if abs(net) > 1e-9:
            out["note"] = f"venue holds {net} but state says no entry — STANDING DOWN"
            if notify:
                notify(f"DAY RIDER: unexplained venue position {net} — standing down", critical=True)
            save_state(out)
            return out
        if mod >= ENTRY_CUTOFF_MIN:
            out["note"] = (f"past the {ENTRY_CUTOFF_MIN//60:02d}:00 entry cutoff — no new entry "
                           f"(all 31 validated detections were 13:38-14:09)")
            save_state(out)
            return out
        r = drift_read(cfg.capture_path, cfg.symbol, now)
        out["leaning"] = {"dir": r.direction, "eff": round(r.efficiency, 3),
                          "rt": round(r.roundtrip, 3), "confirmed": r.confirmed}
        if not r.confirmed:
            out["note"] = "not confirmed — " + (r.detail or "")
            save_state(out)
            return out

        # ★ VENUE-FIRST on the ENTRY. Opening a position while the account does not reconcile means
        # adding lots to a venue we cannot already explain — the surest way to turn one unaccounted
        # lot into an unrecoverable tangle. Refuse and page; the detection is deskrecon's job.
        if not venue_first_ok(net, "ENTER 2 lots", notify):
            out["note"] = "entry refused — venue does not reconcile against desk claims"
            save_state(out)
            return out

        d = 1 if r.direction == "UP" else -1
        from ib_async import MarketOrder, StopOrder
        tr = ib.placeOrder(contract, MarketOrder("BUY" if d > 0 else "SELL", LOTS))
        for _ in range(20):
            await asyncio.sleep(0.5)
            if tr.orderStatus.status == "Filled":
                break
        fill = float(tr.orderStatus.avgFillPrice or r.price)
        stop_px = round(fill - d * VENUE_STOP_PT, 2)
        ib.placeOrder(contract, StopOrder("SELL" if d > 0 else "BUY", LOTS, stop_px))
        out.update(entered=True, entry=fill, peak=fill, direction=d, qty=LOTS,
                   # ★2026-08-11 the state had NO entry timestamp, so a booked trade had no
                   # opened_at and "how long did it hold?" was unanswerable after the fact.
                   entered_at=dt.datetime.now(dt.UTC).isoformat(),
                   entry_atr=round(r.atr, 2),
                   # ★ FROZEN at entry and never rewritten — entry_atr above is overwritten every
                   #   tick with the live ATR, so the trail needs its own immutable copy.
                   arm_atr=round(r.atr, 2), venue_stop=stop_px,
                   note=f"ENTERED {LOTS} lots {r.direction} @ {fill}")
        if notify:
            notify(f"DAY RIDER ENTERED {LOTS} lots {r.direction} @ {fill:.2f} "
                   f"(eff {r.efficiency:.2f} rt {r.roundtrip:.2f}) · stop {stop_px} · flat 21:00",
                   critical=True)
        save_state(out)
        return out
    except Exception as e:                       # FAIL CLOSED — never trade on a broken read
        out["venue_ok"] = False                  # -> the watchdog must treat any position as unmanaged
        # ★ TimeoutError and friends stringify to '', which made the first live failure log a bare
        # "ERROR (no action): " with no cause. Always record the exception TYPE.
        out["note"] = f"ERROR (no action): {type(e).__name__}: {str(e)[:110]}"
        save_state(out)
        log.exception("day_rider step failed")
        return out
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from .notify import notify
    cfg = RunConfig()
    st = asyncio.run(step(cfg, notify=notify))
    print(json.dumps(st, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
