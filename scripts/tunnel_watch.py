#!/usr/bin/env python3
"""TUNNEL WATCH — tell the operator when the tape leaves a compression.

★2026-09-02. Built from the operator's own read of the tape: *"it will run and then hover around
vwap for a while. then run again."* Measured, and he is right about the STRUCTURE — see below. He
is not right that the break tells you which way, and this process is deliberately built so it
cannot imply that it does.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT WAS MEASURED (MNQ 1-minute bars, 2025-09-14 → 2026-08-18, 322,300 bars / 240 sessions)
────────────────────────────────────────────────────────────────────────────────────────────────
A 2-state Gaussian HMM on log per-minute TRUE RANGE separates the tape cleanly and STABLY:

    quiet  mean TR  5.14pt        P(stay quiet)  0.9912
    active mean TR 14.62pt        P(stay active) 0.9913

Contiguous quiet runs are the "tunnels". There are ~5.6 per session, median 68 minutes long and
~81 points (8.5 ATR) wide, and the tape is inside one ~60% of the time. Those figures held across
independent 1-month and 3-month windows, so the structure is real and not a fit artefact.

★ WHAT THE BREAK IS WORTH — and it is ONE thing, not two:
  · MAGNITUDE — ★★★ WITHDRAWN 2026-09-03, DID NOT REPLICATE. This read "~1.75x a matched-hour
    control (MFE 5.75 ATR vs 3.27)". Re-derived on the same 240 sessions with THESE parameters and
    this break definition, matched-hour control, racing from the END of the break bar, one break
    per tunnel: **1.02x in ATR, 1.08x in points** (n=752). Six control definitions across MNQ and
    MGC span 0.82-1.32x and none reaches 1.75x. See scripts/tunnel_fit_mgc.py and
    reports/tunnel_mgc/. A break says the tape woke up; it does not say the next hour is big.
  · DIRECTION — REFUTED, twice, and the second time it was WORSE than a coin flip. First-passage
    in the break's own direction: P(favourable barrier first) = 0.436 / 0.466 / 0.477 at ±1 / ±1.5
    / ±2 ATR, against a control of 0.504 / 0.506 / 0.510 (n=280, 3 months). 91% of breaks return
    inside the tunnel, median 3 minutes. Most breaks are pokes.
  · VOLUME — grades SIZE, never side. The break bar runs ~3.1x the tunnel's own median minute and
    MFE rises monotonically across volume quartiles (3.96 → 8.44 ATR) — but the MFE/MAE ratio stays
    ~1.0, and the HIGHEST volume quartile has the WORST continuation (0.329 at ±1 ATR). Heavy
    volume at a break looks like absorption, not ignition — the same shape that killed AFC, which
    "fires LATE, buying exhaustion".

⚠⚠ THEREFORE THIS ALARM CARRIES NO DIRECTIONAL OPINION. It reports which way price left the range
   because that is an observed fact the operator can see anyway, and it states the measured
   continuation probability NEXT TO IT so the number cannot quietly become a recommendation. A
   meter that hints at a direction it has not earned is worse than no meter — every directional
   test run for this operator has come back a coin flip, and the desk has a standing rule about it.

   The division of labour this is built around: the tape supplies TIMING and SIZE, on which it is
   measurably informative. The operator supplies DIRECTION, at which he is 65% over 20 positions
   while the tape is 50%. ⚠ 2026-09-03: with the 1.75x magnitude claim withdrawn, that division of
   labour loses its arithmetic — the tape supplies TIMING, and timing alone has not been shown to
   be worth anything here. This service is kept running because a state change is a real
   observation the operator asked to see, NOT because an edge was measured. Whether it stays is
   his call and it is recorded as an open question, not settled.

────────────────────────────────────────────────────────────────────────────────────────────────
BOUNDARIES
────────────────────────────────────────────────────────────────────────────────────────────────
⚠ READ-ONLY BY CONSTRUCTION. No ib_async, no order path, no INTENTS socket, no writes to any
  switch or book. Its entire output is Telegram text. tests/test_tunnel_watch.py asserts this
  against the source. A notifier that dies is a missed message; an actor that dies is a position.

★ ONLINE FILTERING, NEVER SMOOTHING. The state estimate uses the forward pass only — information
  up to now. Viterbi/Baum-Welch smoothing would re-label the PAST using the FUTURE, which is
  exactly the look-ahead that makes a backtest lie. The parameters below were fitted offline; this
  process never refits.

★ THE MULTI-SYMBOL TRAP. capture.db carries MNQ and MGC. Every query filters symbol='MNQ'. Folding
  MGC into an MNQ reader once made ATR read 1848 against a true 15 and opened live trades with
  $3,700 stops.

★ LAB TAPE vs PRODUCTION TAPE — CHECKED, not assumed. The model was fitted on lake `1min` bars but
  runs here on capture.db 5s bars aggregated to 1m. Verified on 33,285 overlapping minutes:
  corr(TR)=0.9995, identical median TR (11.0pt), 99.9% identical closes, volume ratio 1.000. The
  parameters transfer. Re-run that check if either feed changes.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, UTC

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from gazbot7.notify import notify, dedupe_ok          # noqa: E402  (stdlib-only path first)

CAPTURE = os.environ.get("GAZBOT7_CAPTURE", "/home/alphabot/gazbot7/data/capture.db")
SYMBOL = "MNQ"

# ── the fitted model (offline, 11 months, 322,300 bars) ───────────────────────
# Emissions are Gaussian on log(true range in points). Index 0 is the QUIET state.
QUIET, ACTIVE = 0, 1
MU = (1.636534, 2.682335)
SD = (0.509254, 0.523180)
A = ((0.991211, 0.008789),
     (0.008722, 0.991278))

POLL_S = float(os.environ.get("TUNNEL_POLL_S", "20"))
# A tunnel shorter than this is not what the operator is describing; it is noise between two
# impulses. 5.6 breaks/session is too many to act on, and an alarm nobody can act on is an
# alarm channel outage. ⚠ THIS IS A NOISE CONTROL, NOT A VALIDATED FILTER — no measurement says
# short tunnels break differently (they do not: <30m scored 0.435, in line with everything else).
MIN_TUNNEL_MIN = int(os.environ.get("TUNNEL_MIN_MIN", "25"))
# The follow-up. ⚠ EXPLICITLY UNVALIDATED — see confirm_note().
CONFIRM_MIN = int(os.environ.get("TUNNEL_CONFIRM_MIN", "10"))
MAX_ALERTS_PER_SESSION = int(os.environ.get("TUNNEL_MAX_ALERTS", "6"))
STALE_S = float(os.environ.get("TUNNEL_STALE_S", "300"))


def session_key(ts: datetime) -> str:
    """CME session runs 22:00Z -> 21:00Z; shift by +2h so one session gets one date."""
    return (ts + timedelta(hours=2)).date().isoformat()


def read_minutes(limit: int = 400):
    """1-minute bars from the live 5s capture. READ-ONLY connection.

    ★ Aggregated in Python from raw 5s rows so the CLOSE is the real last print of the minute.
      An earlier version selected only high/low and approximated the previous close as the
      midpoint — which changes the true-range definition away from the one the model was FITTED
      on, and a model run on a different feature than it was fitted on is the desk's documented
      lab-tape-vs-production-tape failure. The check that the two feeds agree (corr 0.9995) is
      only worth anything if the FEATURE is computed the same way on both.

    ★ `bar_ts - (bar_ts % 60)`, never float division by 60 — SQLite `/` is float and that
      expression is a silent NO-OP which once read 5s bars as "1m" for hours.
    """
    uri = f"file:{CAPTURE}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as c:
        rows = c.execute(
            """select bar_ts - (bar_ts % 60) as m, bar_ts, high, low, "close", volume
               from bars
               where symbol = ? and bar_ts >= ?
               order by bar_ts""",
            (SYMBOL, int(time.time()) - limit * 60),
        ).fetchall()
    out = {}
    for m, bts, hi, lo, cl, vol in rows:
        b = out.get(m)
        if b is None:
            out[m] = {"m": int(m), "hi": float(hi), "lo": float(lo),
                      "close": float(cl), "_last": bts, "vol": float(vol or 0)}
        else:
            b["hi"] = max(b["hi"], float(hi))
            b["lo"] = min(b["lo"], float(lo))
            b["vol"] += float(vol or 0)
            if bts >= b["_last"]:
                b["_last"] = bts
                b["close"] = float(cl)
    bars = [out[k] for k in sorted(out)]
    # the last minute is still forming — drop it so a partial bar cannot fire anything
    return bars[:-1]


def true_range(bars):
    """Wilder true range on the REAL close — the same feature the HMM was fitted on."""
    out = []
    prev_close = None
    for b in bars:
        tr = b["hi"] - b["lo"]
        if prev_close is not None:
            tr = max(tr, abs(b["hi"] - prev_close), abs(b["lo"] - prev_close))
        out.append(max(tr, 1e-6))
        prev_close = b["close"]
    return out


def _emit(v, k):
    """v is LOG true range. MU/SD were fitted in log space; passing raw points here scores every
    minute as ACTIVE, no tunnel is ever found and the service runs green and silent forever.
    That bug shipped and was caught only because test_states_separate_quiet_from_active EXECUTES
    the model. Hence _log_tr() below: the conversion lives inside, where a caller cannot omit it."""
    z = (v - MU[k]) / SD[k]
    return math.exp(-0.5 * z * z) / (SD[k] * math.sqrt(2 * math.pi)) + 1e-300


def _log_tr(tr):
    return math.log(max(float(tr), 1e-9))


def filter_states(trs):
    """FORWARD filtering only — P(state_t | data up to t). Causal by construction.

    Takes RAW true ranges in points and logs them internally, so no caller can forget.
    Returns the per-bar posterior of the QUIET state. Deliberately NOT Viterbi: smoothing would
    relabel the past using the future, which is the look-ahead that makes a live signal a lie.
    """
    trs = [_log_tr(t) for t in trs]
    a = [0.5 * _emit(trs[0], 0), 0.5 * _emit(trs[0], 1)]
    s = sum(a); a = [v / s for v in a]
    post = [a[QUIET]]
    for v in trs[1:]:
        nxt = [(a[0] * A[0][k] + a[1] * A[1][k]) * _emit(v, k) for k in (0, 1)]
        s = sum(nxt) or 1e-300
        a = [x / s for x in nxt]
        post.append(a[QUIET])
    return post


def find_tunnel(bars, post):
    """The CURRENT tunnel: the contiguous run of quiet minutes ending at the last closed bar.

    Returns None when the tape is active now — there is no tunnel to leave.
    """
    if not post or post[-1] < 0.5:
        return None
    i = len(post) - 1
    while i > 0 and post[i - 1] >= 0.5:
        i -= 1
    seg = bars[i:]
    if len(seg) < 2:
        return None
    return {"start": i, "n": len(seg),
            "hi": max(x["hi"] for x in seg), "lo": min(x["lo"] for x in seg),
            "vol_med": sorted(x["vol"] for x in seg)[len(seg) // 2]}


def confirm_note(held: bool) -> str:
    """⚠ The follow-up is NOT a validated signal and must never be phrased as one.

    Re-anchoring the race 10 minutes after the break (a pure time shift, conditioned on nothing)
    scored P(continuation)=0.540 at ±2 ATR, n=274, against 0.477 at the break itself. Standard
    error ~0.03, so that is ~1.3 SE from a coin flip, and it was one cell of eight searched. A
    proper confirmation test — a rule computable at t+N, measured forward from t+N — is running
    separately. Until that returns, this line is an OBSERVATION about what price did, nothing more.
    """
    return ("still outside after %dm" % CONFIRM_MIN) if held else ("back inside within %dm" % CONFIRM_MIN)


def build_message(side, tunnel_n, width, mid, vol_ratio, atr, held_min) -> str:
    """The alert text. Extracted so a test can EXECUTE it — the numbers in here are the entire
    product of this service, and a claim nobody re-derives is how the last one survived a month.

    ★★★2026-09-03 THE "1.75x" CLAIM IS WITHDRAWN. It was the whole justification for this alert and
    it does not replicate. Re-derived on the SAME 240 sessions with this service's OWN parameters
    and its own break definition, against a matched-hour control, racing from the END of the break
    bar and counting one break per tunnel: the next 60 minutes run **1.02x** the control in ATR and
    **1.08x** in points. Six control definitions were tried across MNQ and MGC (any minute / quiet
    minutes / active minutes, in ATR and in points) and the ratio never left 0.82-1.32x. Nothing
    reaches 1.75x. The most likely source of the original is normalising the break's excursion by a
    PRE-break ATR while the control used its own contemporaneous one — that mixes two yardsticks
    and still only reaches 1.13x.
    The DIRECTION half held up and is kept: 0.459 / 0.513 / 0.499 at ±1 / ±1.5 / ±2 ATR against a
    control of 0.494 / 0.498 / 0.497 (n=752 breaks).

    So what this alert now says is what it can defend: the tape LEFT a compression. That is an
    observation about the present, not a forecast about the next hour.
    """
    return (
        f"MNQ LEFT A COMPRESSION — {side}\n"
        f"tunnel {tunnel_n}m / {width:.0f}pt wide · broke at {mid:.0f}\n"
        f"volume {vol_ratio:.1f}x the tunnel's own minute · ATR {atr:.1f}pt\n"
        f"outside {held_min}m ({confirm_note(held_min >= CONFIRM_MIN)})\n"
        # No history lesson in the alert: the withdrawal is recorded in this file, in the tests
        # and in SESSIONS. What he needs at 3am is what the number IS, not what it used to be.
        f"⚠ NO EDGE MEASURED — a STATE CHANGE, not a forecast.\n"
        f"Next 60m runs 1.0x a normal minute of this hour · direction "
        f"0.46-0.51 vs 0.50 random (n=752). Your call, as always."
    )


def main() -> int:
    seen_session = None
    alerts = 0
    armed = None          # the tunnel we last alerted on
    print("tunnel_watch: started (READ-ONLY; no order path)", flush=True)
    while True:
        try:
            bars = read_minutes()
            if len(bars) < 40:
                time.sleep(POLL_S); continue
            age = time.time() - (bars[-1]["m"] + 60)
            now = datetime.now(UTC)
            sk = session_key(now)
            if sk != seen_session:
                seen_session, alerts, armed = sk, 0, None
            if age > STALE_S:
                # venue shut or feed dead. Say nothing — an absence of tape is not a measurement
                # of it, and this process must never manufacture an event out of silence.
                time.sleep(POLL_S); continue

            trs = true_range(bars)
            post = filter_states(trs)
            tun = find_tunnel(bars, post)

            # ── still inside a tunnel: remember it, say nothing ──────────────
            if tun is not None:
                if tun["n"] >= MIN_TUNNEL_MIN:
                    armed = {"hi": tun["hi"], "lo": tun["lo"], "n": tun["n"],
                             "vol_med": tun["vol_med"], "start_m": bars[tun["start"]]["m"]}
                time.sleep(POLL_S); continue

            # ── the tape is ACTIVE. Did it leave a tunnel we were watching? ──
            if armed is None or alerts >= MAX_ALERTS_PER_SESSION:
                time.sleep(POLL_S); continue

            last = bars[-1]
            mid = (last["hi"] + last["lo"]) / 2.0
            up = last["hi"] > armed["hi"]
            dn = last["lo"] < armed["lo"]
            if not (up or dn):
                time.sleep(POLL_S); continue

            side = "UP" if up and not dn else ("DOWN" if dn and not up else "BOTH SIDES")
            width = armed["hi"] - armed["lo"]
            atr = sum(trs[-14:]) / min(14, len(trs))
            vr = (last["vol"] / armed["vol_med"]) if armed["vol_med"] else float("nan")
            # how long has it been outside?
            held_min = 0
            for bb in reversed(bars):
                if bb["hi"] > armed["hi"] or bb["lo"] < armed["lo"]:
                    held_min += 1
                else:
                    break

            msg = build_message(side, armed["n"], width, mid, vr, atr, held_min)
            # ★ Dedupe on the SITUATION (this tunnel, this side), not on the text — the numbers in
            #   the message move every poll, and keying on text would defeat suppression entirely.
            #   dedupe_ok FAILS OPEN: any error sends. A missed alarm is the expensive direction.
            key = f"tunnel.{sk}.{armed['start_m']}.{side}"
            if dedupe_ok(key, key, cooldown_s=3600):
                notify(msg, critical=False)
                alerts += 1
                print(f"[{now.isoformat()}] ALERT {side} tunnel={armed['n']}m "
                      f"width={width:.0f} vol={vr:.1f}x", flush=True)
                armed = None
        except Exception as e:                       # never die on a bad poll
            print(f"tunnel_watch: {type(e).__name__}: {e}", flush=True)
        time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main())
