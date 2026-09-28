#!/usr/bin/env python3
"""THE TURN CALL — "the move that was running has probably ended, and here is the new direction."

★★★ WHY THIS EXISTS. Operator, 2026-09-28, after a 23-entry session that lost $1,882:
*"i just want a way to know reasonably that a turn has happened."* He was right that it was
answerable, and right that the threshold existed. This is it.

★★★ THE MEASUREMENT, over 100 sessions of front-month MNQ minute bars (2026-05-04..2026-09-18),
of THIS rule — the one implemented below, which FLIPS direction at every confirmed turn:

    retrace   fires/day   old direction never came back within 2h   giveback
      4xATR      32.4                 42%                              42pt
      5xATR      23.1                 47%                              51pt
      7xATR      13.3                 57%                              67pt
     10xATR       7.3                 66%                              89pt
     12xATR       5.3                 73%                             107pt
    ★15xATR       3.6                 77%                             123pt
     20xATR       2.0                 84%                             160pt

⚠⚠⚠ THE FIRST CUT OF THIS FILE CLAIMED "7xATR, 70%, 2.3 a day" AND ALL THREE NUMBERS WERE WRONG.
They came from a study that tracked retraces from a running extreme WITHOUT EVER FLIPPING DIRECTION —
a rarer event than the detector actually implements. What caught it was the test that asserts the
CLAIMED RATE against real tape: it counted 23 fires on 2026-09-28 against a claimed 2.3.
**A measurement of a rule you did not ship is not a measurement**, and the only reason it did not go
out is that the claim was written down where a test could read it.

★ WHY 15 IS THE SETTING. The operator's own framing is the constraint: there are ~3.1 real legs a day
(a ~20xATR decomposition, median 298pt over 266min) and he said, correctly, "there usually arent many".
15xATR fires 3.6 times a session — the same order as the legs themselves — at 77%. 20xATR buys 84%
but costs 160pt of a 298pt leg; 12xATR buys one more alert a day at 73%. 15 is the knee.

⚠⚠ IT IS A DETECTION, NOT A FORECAST, AND THE DISTINCTION IS NOT PEDANTRY HERE. It says the move
that WAS running has probably stopped. It does not say the new direction will run — 23% of the time
the old direction resumes, and the message says so every single time. The desk has shipped a
confident number that did not replicate before (tunnel_watch's 1.75x, withdrawn and re-derived at
1.02x), so every alert carries its own 77% AND its own 23%.

⚠ LEG AGE IS DELIBERATELY REPORTED BUT NOT USED AS A FILTER. Measured: age barely moves this number
(67% on a fresh leg, 71% on one over three hours old). It DOES strongly affect a different question —
pinpointing the exact top, where a 2xATR pullback is right 5% of the time on a fresh leg and 21% on a
four-hour-old one. So age is context for him, not a gate.

⚠⚠⚠ READ-ONLY. It writes its own log and its own state file and nothing else. No order path, no
switch file, no request file — `tests/test_turn_watch.py` asserts that against the SOURCE, the same
guard leg_watch and rider_peak_watch carry.

★ THE HOLD FRAME IS PART OF THE ALERT, because the alert exists to fix over-trading. Every message
carries what his own book says about hold time — 1-4 hours is +$86/entry over 30 entries against
-$27/entry over 67 entries under 15 minutes — so the number is in front of him at the moment he
decides, not in a report he reads later. A rule that lives only in a document is a rule the moment
never sees.

  PYTHONPATH=src .venv/bin/python scripts/turn_watch.py [--once] [--json] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.notify import dedupe_ok, notify  # noqa: E402

GB = "/home/alphabot/gazbot7"
CAPTURE = os.environ.get("GAZBOT7_CAPTURE", f"{GB}/data/capture.db")
LOG = f"{GB}/data/turn_watch.log"
SERIES = f"{GB}/data/turn_watch.jsonl"      # every call, for forward grading
STATE = f"{GB}/data/turn_watch_state.json"

SYMBOL = os.environ.get("TURN_SYMBOL", "MNQ")
POLL_S = float(os.environ.get("TURN_POLL_S", "30"))
#: ★ THE PARAMETER. 15.0 measured 77% at 3.6 fires/day. Lowering it trades reliability for earlier
#: entry along a KNOWN curve (see the table above) — a change is a deliberate move along it, and
#: `RELIABILITY` must move with it or the alert asserts a number nobody measured at that setting.
#: A test fails if RETRACE_ATR is set to a value with no measured entry.
RETRACE_ATR = float(os.environ.get("TURN_RETRACE_ATR", "15.0"))
STALE_S = float(os.environ.get("TURN_STALE_S", "300"))
WARM_MIN = int(os.environ.get("TURN_WARM_MIN", "600"))

#: The measured reliability curve FOR THE SHIPPED RULE, frozen with the run that produced it and
#: printed in the alert, so the claim travels WITH the message rather than into a doc nobody opens.
#: ⚠ This replaces a table measured on a non-flipping rule — see the docstring. Any new value here
#: needs its own measured row before it can be set.
RELIABILITY = {4.0: 42, 5.0: 47, 7.0: 57, 10.0: 66, 12.0: 73, 15.0: 77, 20.0: 84}
#: What the legs themselves look like, same 100 sessions — the hold frame.
LEG_MEDIAN_PT = 298
LEG_MEDIAN_MIN = 266
LEGS_PER_DAY = 3.1


def log(m: str) -> None:
    line = f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {m}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def minute_bars(lookback_min: int = 900):
    """1-minute bars from the 5s capture. READ-ONLY, and it FILTERS SYMBOL.

    ⚠ MD_STREAM and capture are MULTI-SYMBOL. Adding MGC once made ATR read 1848 against a true 15
    and opened live trades with $3,700 stops, so the symbol filter is not optional.
    ⚠ `bar_ts/60*60` is INTEGER division here because this is sqlite, not DuckDB — in DuckDB `/` is
    float and the same expression is a silent no-op that reads 5s bars as minutes.
    """
    since = int(time.time()) - lookback_min * 60
    con = sqlite3.connect(f"file:{CAPTURE}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select (bar_ts/60)*60 m, max(high), min(low), "
            "       (select close from bars b2 where b2.symbol=b.symbol "
            "        and b2.timeframe=b.timeframe and (b2.bar_ts/60)*60=(b.bar_ts/60)*60 "
            "        order by b2.bar_ts desc limit 1) c "
            "from bars b where symbol=? and timeframe='5s' and bar_ts >= ? "
            "group by 1 order by 1", (SYMBOL, since)).fetchall()
    finally:
        con.close()
    return [(int(m), float(h), float(lo), float(c)) for m, h, lo, c in rows if c is not None]


def atr14(bars) -> float:
    """Same formula leg_watch uses, including the 0.25 floor — one definition of ATR on this desk."""
    if len(bars) < 15:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, lo, pc = bars[i][1], bars[i][2], bars[i - 1][3]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc), 0.25))
    return sum(trs[-14:]) / 14.0


def replay(bars, atr: float):
    """Rebuild the CURRENT direction and running extreme from history.

    ★★ RESTART TRANSPARENCY, and this is not optional. The direction and the extreme are the whole
    state of this instrument; if a restart reset them, the first call after any restart would be
    measured from wherever the tape happened to be at boot. leg_watch had exactly this bug on its
    tunnel clock — six restarts in one day meant the first break could never fire, and the log
    asserted "0min quiet", which is a CLAIM and not a measurement.
    So replay the same rule over the warm-up and return the state it leaves behind.
    Returns (dirn, ext_price, ext_index, leg_start_index) or None when there is not enough tape.
    """
    cl = [b[3] for b in bars]
    if len(cl) < 30 or atr <= 0:
        return None
    dirn = 1 if cl[10] > cl[0] else -1
    ext, ext_i, leg_i = cl[10], 10, 0
    for i in range(11, len(cl)):
        if dirn * (cl[i] - ext) > 0:
            ext, ext_i = cl[i], i
        elif dirn * (ext - cl[i]) >= RETRACE_ATR * atr:
            leg_i = ext_i
            dirn = -dirn
            ext, ext_i = cl[i], i
    return dirn, ext, ext_i, leg_i


def cvd_15min(now_ts: int) -> float | None:
    """Signed aggressive volume over the last 15 minutes, or None.

    ★ CONTEXT ONLY, AND IT READS THE OPPOSITE WAY TO INTUITION. Measured across 26 turns: at the
    turn, CVD is strongly one-sided in the direction that is ENDING — sellers at their most
    aggressive AT the low. So a large reading AGAINST the new direction is the ordinary case and
    mildly corroborating; it is not a confirmation of the new direction, and the alert says so.
    ⚠ `aggressor` lives only in `ticks`, which the pruner keeps 5 DAYS. There are ~6 days of this in
    existence and there never will be more history, which is why this is reported and not relied on.
    ⚠ Values are lowercase ('buy'/'sell'/'neutral'). Comparing against uppercase returns exactly 0
    for every row and looks precisely like a clean null — it did, for a while.
    """
    try:
        con = sqlite3.connect(f"file:{CAPTURE}?mode=ro", uri=True)
        try:
            row = con.execute(
                "select sum(case when lower(aggressor)='buy' then size "
                "            when lower(aggressor)='sell' then -size else 0 end) "
                "from ticks where symbol=? and ts_ms >= ?",
                (SYMBOL, (now_ts - 15 * 60) * 1000)).fetchone()
        finally:
            con.close()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def read_state() -> dict:
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def write_state(d: dict) -> None:
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(d, fh, indent=1)
        os.replace(tmp, STATE)
    except Exception as e:
        log(f"state write failed: {type(e).__name__}: {e}")


def compose(new_dir: int, old_move: float, old_mins: int, give: float, atr: float,
            cvd: float | None) -> str:
    """The alert. Everything measured travels with it; nothing here is a forecast."""
    nd = "UP" if new_dir > 0 else "DOWN"
    od = "down" if new_dir > 0 else "up"
    pct = RELIABILITY.get(RETRACE_ATR, 70)
    parts = [
        f"🔄 TURN CALL — the {od} move looks over. New direction {nd}.",
        f"it ran {abs(old_move):.0f}pt over {old_mins}min, and price has now come back "
        f"{give:.0f}pt ({give/atr:.1f}x ATR {atr:.1f}).",
        f"MEASURED, 100 sessions: when this fires the old direction does NOT come "
        f"back within 2h {pct}% of the time. So {100-pct}% of the time it does — this is a "
        f"detection, not a forecast, and it says nothing about how far {nd} goes.",
    ]
    if cvd is not None:
        aligned = (cvd > 0) == (new_dir > 0)
        parts.append(
            f"15-min CVD {cvd:+,.0f} — {'unusually already with' if aligned else 'still with'} the "
            f"{'new' if aligned else 'OLD'} direction. "
            + ("⚠ the ordinary reading: at a turn the finishing side is at its most aggressive, so "
               "this corroborates exhaustion rather than confirming " + nd
               if not aligned else
               "the rarer reading (4 of 26 turns had CVD already flipped)."))
    parts.append(
        f"HOLD FRAME — legs run a median {LEG_MEDIAN_PT}pt over {LEG_MEDIAN_MIN}min and there are "
        f"~{LEGS_PER_DAY:.1f} a day. Your own book: 1-4h holds +$86/entry over 30 entries, "
        f"under-15min holds -$27/entry over 67. Past 4h it turns into the abandonment that cost "
        f"-$5,193 over 7 trades.")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="detect and print; never send")
    a = ap.parse_args()

    log(f"turn_watch up · symbol={SYMBOL} retrace={RETRACE_ATR}xATR "
        f"(measured {RELIABILITY.get(RETRACE_ATR,'?')}% over 100 sessions) · poll {POLL_S:.0f}s")
    st = read_state()
    dirn = st.get("dirn") or 0
    ext = st.get("ext")
    ext_ts = st.get("ext_ts") or 0
    leg_ts = st.get("leg_ts") or 0
    seeded = bool(dirn)

    while True:
        try:
            bars = minute_bars(WARM_MIN)
            if len(bars) < 30:
                log("not enough tape yet")
                if a.once:
                    return 0
                time.sleep(POLL_S); continue
            age = time.time() - bars[-1][0]
            if age > STALE_S:
                # ★ A DEAD FEED AND A MOTIONLESS TAPE LOOK IDENTICAL. Say which, and judge neither.
                log(f"tape STALE ({age/60:.0f}min old) — not judging")
                if a.once:
                    return 0
                time.sleep(POLL_S); continue
            atr = atr14(bars)
            if atr <= 0:
                if a.once:
                    return 0
                time.sleep(POLL_S); continue

            if not seeded:
                r = replay(bars, atr)
                if r is None:
                    if a.once:
                        return 0
                    time.sleep(POLL_S); continue
                dirn, ext, ei, li = r
                ext_ts, leg_ts = bars[ei][0], bars[li][0]
                seeded = True
                log(f"seeded from {len(bars)}min of tape: direction "
                    f"{'UP' if dirn > 0 else 'DOWN'}, extreme {ext:.2f} at "
                    f"{dt.datetime.fromtimestamp(ext_ts, dt.UTC):%H:%M}Z")
                write_state({"dirn": dirn, "ext": ext, "ext_ts": ext_ts, "leg_ts": leg_ts})

            px, now_ts = bars[-1][3], bars[-1][0]
            give = dirn * (ext - px)
            out = {"ts": dt.datetime.now(dt.UTC).isoformat(), "px": px, "atr": round(atr, 2),
                   "dirn": dirn, "ext": ext, "give": round(give, 2),
                   "give_atr": round(give / atr, 2), "fires_at": RETRACE_ATR}

            if dirn * (px - ext) > 0:
                ext, ext_ts = px, now_ts
                write_state({"dirn": dirn, "ext": ext, "ext_ts": ext_ts, "leg_ts": leg_ts})
                log(f"new extreme {ext:.2f} ({'UP' if dirn > 0 else 'DOWN'} leg, "
                    f"{(now_ts-leg_ts)//60}min old)")
            elif give >= RETRACE_ATR * atr:
                old_move = dirn * (ext - next((b[3] for b in bars if b[0] >= leg_ts), ext))
                old_mins = int((ext_ts - leg_ts) // 60)
                cvd = cvd_15min(now_ts)
                new_dir = -dirn
                msg = compose(new_dir, old_move, old_mins, give, atr, cvd)
                out.update(fired=True, new_dir=new_dir, old_move=round(old_move, 2),
                           old_mins=old_mins, cvd=cvd)
                log(f"TURN CALL · {'UP' if new_dir > 0 else 'DOWN'} · old move {old_move:+.0f}pt/"
                    f"{old_mins}min · gave back {give:.0f}pt ({give/atr:.1f}xATR) · cvd {cvd}")
                try:
                    with open(SERIES, "a") as fh:
                        fh.write(json.dumps(out) + "\n")
                except Exception as e:
                    log(f"series write failed: {type(e).__name__}: {e}")
                if not a.dry_run:
                    # ⚠ critical=False: this is a trading read, not a safety alarm. It must not
                    # bypass quiet hours and must not wear the 🔴 mark — at 2.3/day it would dilute
                    # the circle that exists for the four alerts that cost money if unread.
                    if dedupe_ok(f"turn.{SYMBOL}.{ext_ts}", msg, cooldown_s=1800):
                        notify(msg, critical=False, mark=False)
                # the turn becomes the new leg's start
                leg_ts = ext_ts
                dirn, ext, ext_ts = new_dir, px, now_ts
                write_state({"dirn": dirn, "ext": ext, "ext_ts": ext_ts, "leg_ts": leg_ts})
            else:
                log(f"{'UP' if dirn > 0 else 'DOWN'} leg {(now_ts-leg_ts)//60}min · "
                    f"given back {give:.0f}pt of {RETRACE_ATR*atr:.0f} needed")

            if a.json:
                print(json.dumps(out, indent=1))
            if a.once:
                return 0
            time.sleep(POLL_S)
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            log(f"loop error {type(e).__name__}: {e}")
            if a.once:
                return 1
            time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main())
