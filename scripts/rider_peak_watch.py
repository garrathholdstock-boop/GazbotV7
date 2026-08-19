#!/usr/bin/env python3
"""RIDER PEAK WATCH — tell the operator, in real time, that there is money on the table.

★2026-08-19. Built after a day the operator claimed $726 by hand in 23 minutes, and said the thing
that mattered: *"i watched that one today and it went up to $550 and then started dropping in real
time."* The desk could not help him do that. The rider's own tick is `*:*:05` — **once a MINUTE** —
so the finest resolution anything on this desk had on an open position was 60 seconds. A 137-point
impulse that peaks and rolls over inside two minutes is invisible at that cadence.

**Why this is Python and not Claude.** The judgement call — when to claim — stays with the operator;
eleven months of testing says every fixed automated exit loses money while his manual claims are the
biggest winners in the book. What he lacks is not judgement, it is PRESENCE. This process supplies
presence at 1 Hz for the price of a socket read. No model, no token that can expire, no latency.

**WHAT IT DOES NOT DO.** It cannot place, cancel or close an order. It imports no order path. Its
entire output is Telegram text. That boundary is deliberate and must survive any future edit: a
notifier that dies is a missed message, an actor that dies is a naked position.

The alert ladder, exactly as specified by the operator:
  1. **ARM** — the first time open P&L crosses ARM_USD ($200). Sent `critical=True`: this is the
     "stop what you are doing and look at the chart" message.
  2. **RUNGS** — one ping per new $STEP_USD ($50) high-water mark thereafter. Never on the way down,
     so a chopping position cannot machine-gun the channel.
  3. **GIVE-BACK** — peak minus current >= GIVEBACK_USD. This is the one that answers "$550 then
     started dropping". It re-arms only on a NEW high, so it fires at most once per peak.

★ THE MULTI-SYMBOL TRAP. MD_STREAM carries MNQ *and* MGC — verified live at build time (`bar:MNQ`
  and `bar:MGC` both present). Folding MGC into an MNQ reader is precisely what once made ATR read
  1848 against a true 15 and opened live trades with $3,700 stops. Every message is filtered on
  `body["symbol"]` before it is looked at.

★ AN INSTRUMENT THAT REPORTS HEALTHY ABOUT WHAT IT NEVER CHECKS is this desk's signature failure, and
  a peak watcher is a perfect host for it: if the tape goes quiet the operator simply receives no
  pings, which is indistinguishable from a calm market. So silence is itself alarmed — holding a
  position with no tape for BLIND_S seconds pages once, critically.

★ VENUE TRUTH OUTRANKS OUR BOOK. `day_rider_state.json` is written once a minute, so after a MANUAL
  claim it can still say "open" for up to 60s. The desk reconciler writes the venue net every 30s;
  if the venue is flat, this process shuts up immediately regardless of what our own state claims.
  That check can only ever SILENCE an alert, never manufacture one.

P&L convention, verified against the booked trade 13:39→13:50 (entry 29607.50, exit 29470.75,
SHORT 2) which the venue booked at exactly $544.00:
    gross = (last - entry) * direction * qty * $2/pt      136.75 * 2 * 2 = $547.00
    net   = gross - $1.50/RT * qty                                - $3.00 = $544.00
⚠ $2/pt is PER LOT. Mixing the per-lot and per-position figures is what produced a "$200 claim" that
  actually banked $100 in an earlier study. The unit test pins this against the real trade.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

GB = "/home/alphabot/gazbot7"
STATE = f"{GB}/data/day_rider_state.json"
RECON = f"{GB}/data/desk_reconcile_state.json"
LOG = f"{GB}/data/rider_peak_watch.log"

SYMBOL = os.environ.get("PEAK_SYMBOL", "MNQ")
ARM_USD = float(os.environ.get("PEAK_ARM_USD", "200"))
STEP_USD = float(os.environ.get("PEAK_STEP_USD", "50"))
GIVEBACK_USD = float(os.environ.get("PEAK_GIVEBACK_USD", "75"))   # 0 disables
BLIND_S = float(os.environ.get("PEAK_BLIND_S", "90"))
PT_USD = 2.0          # MNQ, PER LOT
FEE_RT = 1.50         # per lot, round trip
RECON_MAX_AGE = 120.0  # older than this and the venue check is not evidence either way


def open_pnl(last: float, entry: float, direction: int, qty: float) -> float:
    """Net open P&L in dollars, fees included — the number the operator sees booked."""
    return (last - entry) * direction * qty * PT_USD - FEE_RT * qty


@dataclass
class Ladder:
    """The pure alert decision. No I/O, so the boundaries are testable and pinned."""

    arm_usd: float = ARM_USD
    step_usd: float = STEP_USD
    giveback_usd: float = GIVEBACK_USD
    armed: bool = False
    peak: float = 0.0
    last_rung: float = 0.0
    gb_peak: float = 0.0          # the peak at which a give-back was last announced
    seen: bool = False

    def reset(self) -> None:
        self.armed = False
        self.peak = 0.0
        self.last_rung = 0.0
        self.gb_peak = 0.0
        self.seen = False

    def update(self, pnl: float) -> list[tuple[str, str]]:
        """Feed one live P&L. Returns [(kind, detail)] — usually empty."""
        out: list[tuple[str, str]] = []
        if not self.seen:
            self.seen = True
            self.peak = pnl
        new_high = pnl > self.peak
        if new_high:
            self.peak = pnl

        if not self.armed:
            if self.peak >= self.arm_usd:
                self.armed = True
                # Round DOWN to the rung actually reached, so a jump straight to $380 does not then
                # re-announce $250/$300/$350 on the way past.
                self.last_rung = math.floor(self.peak / self.step_usd) * self.step_usd
                out.append(("ARM", f"{self.peak:.0f}"))
            return out

        if new_high:
            rung = math.floor(self.peak / self.step_usd) * self.step_usd
            if rung > self.last_rung:
                self.last_rung = rung
                out.append(("RUNG", f"{rung:.0f}"))

        if self.giveback_usd > 0 and self.peak > self.gb_peak:
            if self.peak - pnl >= self.giveback_usd:
                self.gb_peak = self.peak
                out.append(("GIVEBACK", f"{self.peak - pnl:.0f}"))
        return out


def _read_json(path: str) -> dict:
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _venue_is_flat() -> bool:
    """VENUE TRUTH. True only when the reconciler FRESHLY says nobody holds anything."""
    try:
        age = time.time() - os.path.getmtime(RECON)
    except OSError:
        return False
    if age > RECON_MAX_AGE:
        return False                      # stale is not evidence — do not silence on it
    d = _read_json(RECON).get("read1", {})
    return d.get("ok") is True and d.get("venue") == 0


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def main() -> int:
    import zmq

    from gazbot7.ipc import MD_STREAM
    from gazbot7.notify import notify

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.connect(MD_STREAM)
    sock.setsockopt_string(zmq.SUBSCRIBE, "tape")
    sock.setsockopt(zmq.RCVTIMEO, 2000)
    log(f"START symbol={SYMBOL} arm=${ARM_USD:.0f} step=${STEP_USD:.0f} "
        f"giveback=${GIVEBACK_USD:.0f} blind={BLIND_S:.0f}s  (READ-ONLY: no order path)")

    lad = Ladder()
    last_tape = time.time()
    blind_sent = False
    holding = False

    while True:
        try:
            try:
                frames = sock.recv_multipart()
                topic, body = frames[0].decode(), json.loads(frames[1])
            except zmq.Again:
                # ★ SILENCE IS ALARMED. No tape while holding is not a calm market.
                if holding and time.time() - last_tape > BLIND_S and not blind_sent:
                    blind_sent = True
                    notify(f"⚠ RIDER PEAK WATCH IS BLIND — no {SYMBOL} tape for "
                           f"{time.time()-last_tape:.0f}s while the rider holds a position. "
                           f"You are NOT being watched. Check gazbot7-md.", critical=True)
                    log("BLIND")
                continue

            if topic != "tape" or body.get("symbol") != SYMBOL:
                continue        # ★ MD_STREAM IS MULTI-SYMBOL
            last = body.get("last")
            if last is None:
                continue
            last_tape = time.time()
            blind_sent = False

            st = _read_json(STATE)
            live = bool(st.get("entered")) and not bool(st.get("closed"))
            if live and _venue_is_flat():
                live = False    # the venue outranks our book

            if not live:
                if holding:
                    log(f"FLAT — session peak was ${lad.peak:.0f}")
                    holding = False
                    lad.reset()
                continue

            entry = float(st.get("entry") or 0.0)
            direction = int(st.get("direction") or 0)
            qty = float(st.get("qty") or 0.0)
            if not entry or not direction or not qty:
                continue
            if not holding:
                holding = True
                lad.reset()
                log(f"HOLDING {'SHORT' if direction < 0 else 'LONG'} {qty:g} @ {entry}")

            pnl = open_pnl(float(last), entry, direction, qty)
            side = "SHORT" if direction < 0 else "LONG"
            for kind, detail in lad.update(pnl):
                if kind == "ARM":
                    msg = (f"🔴 RIDER +${detail} — ABOVE ${ARM_USD:.0f}. START WATCHING.\n"
                           f"{side} {qty:g} @ {entry:.2f} · now {last:.2f}\n"
                           f"pings every ${STEP_USD:.0f} from here")
                    notify(msg, critical=True)
                elif kind == "RUNG":
                    notify(f"📈 RIDER PEAK ${detail} (now ${pnl:.0f}) · "
                           f"{side} @ {entry:.2f} → {last:.2f}", critical=True)
                else:
                    notify(f"⚠️ RIDER OFF THE HIGH — peak ${lad.peak:.0f}, now ${pnl:.0f} "
                           f"(−${detail}) · {last:.2f}\nIt has stopped making new highs.",
                           critical=True)
                log(f"{kind} {detail} pnl={pnl:.0f} peak={lad.peak:.0f} last={last}")

        except KeyboardInterrupt:
            log("STOP")
            return 0
        except Exception as e:      # a notifier must never die — a dead watcher is a silent one
            log(f"ERR {type(e).__name__}: {e}")
            time.sleep(1.0)


if __name__ == "__main__":
    raise SystemExit(main())
