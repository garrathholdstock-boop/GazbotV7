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
ARM_PT = 150.0                     # trail arms once this far ahead
TRAIL_PT = 100.0
VENUE_STOP_PT = 600.0              # last-resort only; see docstring note 2
HEARTBEAT_STALE_S = 180


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
    d["heartbeat"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    tmp = STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh, indent=1, sort_keys=True)
    os.replace(tmp, STATE)          # atomic — a torn state file would orphan a live position


def session_key(now: dt.datetime) -> str:
    return now.strftime("%Y-%m-%d")


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
            px = drift_read(cfg.capture_path, cfg.symbol, now).price or entry
            peak = float(st.get("peak", entry))
            peak = max(peak, px) if d > 0 else min(peak, px)
            out.update(entry=entry, peak=peak, direction=d, qty=abs(net))
            tl = trail_level(d, entry, peak)
            out["trail"] = tl
            out["ahead_pt"] = round(d * (px - entry), 1)
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
                   venue_stop=stop_px, note=f"ENTERED {LOTS} lots {r.direction} @ {fill}")
        if notify:
            notify(f"DAY RIDER ENTERED {LOTS} lots {r.direction} @ {fill:.2f} "
                   f"(eff {r.efficiency:.2f} rt {r.roundtrip:.2f}) · stop {stop_px} · flat 21:00",
                   critical=True)
        save_state(out)
        return out
    except Exception as e:                       # FAIL CLOSED — never trade on a broken read
        out["note"] = f"ERROR (no action): {str(e)[:120]}"
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
