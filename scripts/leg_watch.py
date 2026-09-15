#!/usr/bin/env python3
"""LEG WATCH — tell him a directional leg is running, and what legs like it have done next.

Operator, 2026-09-14: "the main one is its leaving a tunnel and either jumping hard or starting a
grind... you can give earlier alerts and say Down Grind 15 minutes, then down grind 30 minutes etc."

★ WHAT A LEG IS HERE. It begins when 8 minutes have moved >= 1 x ATR in one direction, and it lives
until price gives back RETRACE_ATR x ATR from its best point. No fixed window - which is the whole
reason this works where the first attempt did not: a 15-minute efficiency window chopped his
2h40m morning move into six fragments and reported a median leg of 8 minutes. The retrace rule is
also evaluable in real time: at any minute you know whether the leg is alive without seeing ahead.
★ THE TOLERANCE IS THE PARAMETER THAT MATTERS. At 1xATR his morning leg dies on the +20.5pt bounce
at 08:40 that he correctly held through. At 3xATR it survives, and legs come out at 17/session with
a median of 43 min / 64pt - his scale.

★★ THE ESCALATION IS THE DESIGN. One alert that waits for certainty lands after the move. So the
first notice is silent, 30 and 45 minutes are quiet lines in the log, and only 60/90/120/180 page -
and those are RARE BY CONSTRUCTION, because only 33%/16%/9%/5% of legs get that far. The throttle
is the statistic itself: the rarer the milestone, the more it has to say.

⚠⚠ DESCRIPTIVE, NEVER PREDICTIVE, AND EVERY MESSAGE SAYS SO. The four tape states all measure
49-50% forward. This reports a REFERENCE CLASS - what legs of this age have historically done next -
and forecasts nothing. The desk has been here before: tunnel_watch shipped a 1.75x excursion claim
that did not replicate and had to be withdrawn while the service ran for nine hours on it.
⚠ READ-ONLY. No order path. Asserted against the source by tests/test_leg_watch.py.
⚠ THE MULTI-SYMBOL TRAP: capture.db carries MNQ and MGC. Every query filters symbol.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.notify import dedupe_ok, notify          # noqa: E402

GB = "/home/alphabot/gazbot7"
CAPTURE = os.environ.get("GAZBOT7_CAPTURE", f"{GB}/data/capture.db")
SYMBOL = os.environ.get("LEG_SYMBOL", "MNQ")
POLL_S = float(os.environ.get("LEG_POLL_S", "30"))
START_ATR = float(os.environ.get("LEG_START_ATR", "1.0"))      # 8-min move to open a leg
START_MIN = int(os.environ.get("LEG_START_MIN", "8"))
RETRACE_ATR = float(os.environ.get("LEG_RETRACE_ATR", "3.0"))  # gives back this much -> leg over
QUIET_MILES = tuple(int(x) for x in os.environ.get("LEG_QUIET", "30,45").split(","))
LOUD_MILES = tuple(int(x) for x in os.environ.get("LEG_LOUD", "60,120,180").split(","))
# ★★2026-09-15 THE SIZE GATE, and it is what makes the alert usable at all. Measured: alerting at
# 60 minutes on every leg fires 5.5x a session, and with a message at each milestone a long leg
# produces four - about 10 messages a session, which is wallpaper. Requiring the leg to have
# travelled >= LEG_MIN_ATR x ATR cuts it to 2.3/session AND improves the content, because bigger
# legs have more left: median remaining goes 29min/29pt at >=3 ATR to 45min/57pt at >=9 ATR.
# ⚠ ONE ALERT PER LEG. The milestones above only decide WHEN it may first speak, never how often.
MIN_ATR = float(os.environ.get("LEG_MIN_ATR", "9.0"))
STALE_S = float(os.environ.get("LEG_STALE_S", "300"))
STATE = f"{GB}/data/leg_watch_state.json"
LOG = f"{GB}/data/leg_watch.log"

# ★ THE REFERENCE CLASS, FROZEN 2026-09-14. Measured on 291 sessions of front-month MNQ 1-minute
#   bars, 4,953 legs at a 3xATR retrace with >=3 ATR of travel (scripts/leg_survival.py).
#   {age: (share still alive, median MORE minutes, median MORE points, % dying within 15 min)}
#   ⚠ Re-derive before changing RETRACE_ATR — these numbers ARE that parameter.
REFCLASS = {15: (97, 29, 39, 27), 30: (70, 26, 31, 32), 45: (48, 27, 28, 32),
            60: (33, 29, 29, 31), 90: (16, 40, 37, 25), 120: (9, 58, 44, 21),
            180: (5, 98, 54, 13)}


def log(line: str) -> None:
    stamp = f"{dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%M:%SZ}"
    print(f"{stamp} {line}", flush=True)
    try:
        with open(LOG, "a") as fh:
            fh.write(f"{stamp} {line}\n")
    except OSError:
        pass


def minute_bars(lookback_min: int = 600):
    """1-minute bars from the 5s capture. READ-ONLY, and it FILTERS SYMBOL."""
    since = int(time.time()) - lookback_min * 60
    con = sqlite3.connect(f"file:{CAPTURE}?mode=ro", uri=True)
    rows = con.execute(
        "select (bar_ts/60)*60 m, max(high), min(low), "
        "       (select close from bars b2 where b2.symbol=b.symbol and b2.timeframe=b.timeframe "
        "        and (b2.bar_ts/60)*60=(b.bar_ts/60)*60 order by b2.bar_ts desc limit 1) c "
        "from bars b where symbol=? and timeframe='5s' and bar_ts >= ? group by 1 order by 1",
        (SYMBOL, since)).fetchall()
    con.close()
    return [(int(m), float(h), float(l), float(c)) for m, h, l, c in rows if c is not None]


def atr14(bars) -> float:
    if len(bars) < 15:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l = bars[i][1], bars[i][2]
        pc = bars[i - 1][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc), 0.25))
    return sum(trs[-14:]) / 14.0


def describe(age: int) -> str:
    """The honest reference class for a leg of this age — never a forecast."""
    key = max([k for k in REFCLASS if k <= age], default=15)
    alive, more_m, more_pt, dies = REFCLASS[key]
    return (f"legs still running at {key}min have historically gone another ~{more_m}min / "
            f"~{more_pt}pt (median); {dies}% ended within 15min. Only {alive}% of legs get this far. "
            f"THIS IS A REFERENCE CLASS, NOT A FORECAST — direction from here measures ~50/50.")


def main() -> int:
    log(f"leg_watch up · symbol={SYMBOL} start={START_ATR}xATR/{START_MIN}min "
        f"retrace={RETRACE_ATR}xATR quiet={QUIET_MILES} loud={LOUD_MILES}")
    leg = None
    while True:
        try:
            bars = minute_bars()
            if len(bars) < 30:
                time.sleep(POLL_S); continue
            age_s = time.time() - bars[-1][0]
            if age_s > STALE_S:
                # a dead feed and a quiet tape look identical; say which
                log(f"tape STALE ({age_s/60:.0f}min old) — not judging")
                leg = None
                time.sleep(POLL_S); continue
            a = atr14(bars)
            if a <= 0:
                time.sleep(POLL_S); continue
            closes = [b[3] for b in bars]
            now_px = closes[-1]
            if leg:
                sgn = leg["sgn"]
                if sgn * (now_px - leg["ext"]) > 0:
                    leg["ext"] = now_px
                elif sgn * (leg["ext"] - now_px) >= RETRACE_ATR * a:
                    log(f"leg OVER after {leg['age']}min, travel {sgn*(leg['ext']-leg['px0']):+.1f}pt")
                    leg = None
            if leg is None:
                if len(closes) > START_MIN:
                    mv = closes[-1] - closes[-1 - START_MIN]
                    if abs(mv) >= START_ATR * a:
                        leg = {"sgn": 1 if mv > 0 else -1, "px0": closes[-1 - START_MIN],
                               "ext": now_px, "t0": bars[-1 - START_MIN][0], "age": START_MIN,
                               "fired": []}
                        log(f"leg OPEN {'UP' if leg['sgn']>0 else 'DOWN'} "
                            f"from {leg['px0']:.2f} (silent — 17 legs/session, most die young)")
            if leg:
                leg["age"] = int((bars[-1][0] - leg["t0"]) / 60)
                sgn = leg["sgn"]
                travel = sgn * (leg["ext"] - leg["px0"])
                rate = travel / max(leg["age"], 1)
                for m in sorted(QUIET_MILES + LOUD_MILES):
                    if leg["age"] >= m and m not in leg["fired"]:
                        leg["fired"].append(m)
                        # the size gate applies to the PAGING milestones only
                        if m in LOUD_MILES and travel < MIN_ATR * a:
                            log(f"held {m}min (only {travel:.0f}pt = {travel/a:.1f} ATR, "
                                f"needs {MIN_ATR:g}) — not paging")
                            continue
                        if m in LOUD_MILES and leg.get("paged"):
                            continue                       # ONE alert per leg
                        if m in LOUD_MILES:
                            leg["paged"] = True
                        d = "UP" if sgn > 0 else "DOWN"
                        # ⚠ SIGN THE DISPLAY BY DIRECTION, not by the leg's own frame. `travel`
                        # is measured in the leg's direction so a DOWN leg that fell 36 points
                        # carries +35.8 — correct arithmetic that reads as the OPPOSITE of what
                        # happened. Caught live 2026-09-15: "DOWN LEG · 45min · +35.8pt".
                        head = (f"{d} LEG · {leg['age']}min · {sgn*travel:+.1f}pt "
                                f"({travel:.1f}pt {'up' if sgn > 0 else 'down'}) · "
                                f"{sgn*rate:+.2f}pt/min · ATR {a:.1f}")
                        if m in LOUD_MILES:
                            body = f"{head} — {describe(leg['age'])}"
                            if dedupe_ok(f"leg.{SYMBOL}.{leg['t0']}.{m}", body, cooldown_s=3600):
                                notify(body, critical=False)
                            log(f"ALERT {m}min: {head}")
                        else:
                            log(f"quiet {m}min: {head}")
            with open(STATE, "w") as fh:
                json.dump({"ts": dt.datetime.now(dt.UTC).isoformat(), "symbol": SYMBOL,
                           "leg": leg, "atr": round(a, 2)}, fh, indent=1)
        except Exception as e:                       # a watcher must never take the desk with it
            log(f"ERROR (continuing): {type(e).__name__}: {e}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main())
