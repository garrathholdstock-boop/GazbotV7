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
from .drift import CLOSE_UTC_MIN, OPEN_UTC_MIN, read as drift_read
from .safety import safe_flatten_verdict

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
ARM_PT = 150.0                     # trail arms once this far ahead
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


def trail_level(direction: int, entry: float, peak: float) -> float | None:
    """The trail, or None while it is not yet armed. Pure, so it is unit-testable."""
    ahead = direction * (peak - entry)
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

        # ── 1. THE HARD FLAT. Runs before anything else, unconditionally. ────────────────
        if mod >= CLOSE_UTC_MIN or mod < OPEN_UTC_MIN:
            if abs(net) > 1e-9:
                v = safe_flatten_verdict(net)
                if v:
                    from ib_async import MarketOrder
                    ib.placeOrder(contract, MarketOrder(v[0], v[1]))
                    await asyncio.sleep(2.0)
                    out["closed"] = True
                    out["note"] = "21:00 hard flat — never overnight"
                    if notify:
                        notify(f"DAY RIDER flat at the 21:00 clock ({v[0]} {v[1]})", critical=True)
            else:
                out["note"] = "outside 13:30-21:00 — flat, idle"
            save_state(out)
            return out

        # ── 2. MANAGE an open position (restart-safe: peak comes from state) ─────────────
        if abs(net) > 1e-9 and st.get("entered"):
            d = 1 if net > 0 else -1
            entry = float(st.get("entry", 0.0))
            rr = drift_read(cfg.capture_path, cfg.symbol, now)
            px = rr.price or entry
            if rr.atr > 0:
                out["entry_atr"] = round(rr.atr, 2)
            peak = float(st.get("peak", entry))
            peak = max(peak, px) if d > 0 else min(peak, px)
            out.update(entry=entry, peak=peak, direction=d, qty=abs(net))
            tl = trail_level(d, entry, peak)
            out["trail"] = tl
            out["ahead_pt"] = round(d * (px - entry), 1)

            # ── OPERATOR-APPROVAL EXIT — ask up to 3x, 15 min apart, DEFAULT HOLD ──────────
            atr_now = float(out.get("entry_atr", st.get("entry_atr", 0.0)) or 0.0)
            pend = dict(st.get("pending_exit") or {})
            if pend.get("token"):
                dec = read_approval(pend["token"])
                if dec == "sell":
                    v = safe_flatten_verdict(net)
                    if v:
                        from ib_async import MarketOrder
                        ib.placeOrder(contract, MarketOrder(v[0], v[1]))
                        await asyncio.sleep(2.0)
                        out["closed"] = True
                        out["pending_exit"] = None
                        out["note"] = "OPERATOR-APPROVED exit"
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

            if tl is not None and ((px <= tl) if d > 0 else (px >= tl)):
                v = safe_flatten_verdict(net)
                if v:
                    from ib_async import MarketOrder
                    ib.placeOrder(contract, MarketOrder(v[0], v[1]))
                    await asyncio.sleep(2.0)
                    out["closed"] = True
                    out["note"] = f"trail hit at {tl:.1f} (peak {peak:.1f})"
                    if notify:
                        notify(f"DAY RIDER trail exit @ {tl:.1f}, peak {peak:.1f}", critical=False)
            else:
                out["note"] = ("riding · trail " + (f"{tl:.1f}" if tl else
                               f"not armed (need +{ARM_PT:.0f}, at {d*(px-entry):+.0f})"))
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
                   entry_atr=round(r.atr, 2), venue_stop=stop_px,
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
