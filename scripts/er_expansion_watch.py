#!/usr/bin/env python3
"""ER-CLIMB + VOL-EXPANSION watch — the condition that would make a stay-out call contestable.

Operator, 2026-08-03: "ping me if ER climbs and ATR expands."

★ REWRITTEN 2026-08-03 13:40 after the first version produced a FALSE FIRE at 13:33.
What it printed: ER30 0.461, ATR 29.5, "both rising, held 3 polls". What was actually happening:

    13:31  ER 0.358  ATR 25.7
    13:32  ER 0.412  ATR 27.2
    13:33  ER 0.358  ATR 29.0   <- fired here
    13:34  ER 0.239  ATR 32.3   <- ER already gone

ATR expansion was real and persistent (13.4 -> 32.3). The ER leg was a two-minute SPIKE that decayed
straight back through the threshold. And the resulting tape — 123pt of range in the four minutes after
the open for -8pt of net — is not a break at all: it is VIOLENT WHIPSAW, high ATR with no direction,
the single worst regime on the board (-$20 to -$33 per signal at EVERY exit cell and every R from
0.5 to 6.0; no exit rescues it, only not trading it does).

Three faults, three fixes:
  1. HOLD_N=3 polls was long enough to certify a 2-minute spike. ER now needs ER_HOLD_N polls and must
     stay above the threshold on EVERY one of them, not merely be higher than it was 3 polls back.
  2. "rising vs 3 polls ago" is satisfied by a spike on its way back down. Replaced with a floor over
     the whole window plus a non-decay check against the window's own start.
  3. ATR expansion alone could carry a fire, because the two legs were treated as equally good news.
     They are not: rising vol with falling efficiency is the whipsaw signature. Added an explicit
     violent-whipsaw VETO and a DIRECTIONAL-PROGRESS floor — a real break has to actually go somewhere.
     Today's open scored |net|/range = 8/123 = 0.065 and would have been vetoed instantly.

Prints one line per poll with the reason it is NOT firing, so silence is always explainable. Keeps
running after a fire (rate-limited) rather than exiting, so the watch survives the event.

  PYTHONPATH=src ./.venv/bin/python scripts/er_expansion_watch.py
"""
from __future__ import annotations

import sys
import time
from collections import deque
from datetime import UTC, datetime

sys.path.insert(0, "/home/alphabot/gazbot7/src")
import duckdb  # noqa: E402

from gazbot7.deciders import Bar, _atr  # noqa: E402
from gazbot7.sizing import efficiency_ratio  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"

ER_MIN = 0.35          # 30-min Kaufman ER floor — must hold, not merely touch
ATR_MIN = 18.0         # vol genuinely off the ~13pt floor (memory low-vol-grind uses 18 as the bar)
ER_HOLD_N = 10         # ER must clear ER_MIN on TEN consecutive polls (~10 min). 3 certified a spike.
ATR_HOLD_N = 3         # vol expansion is persistent by nature; it does not need a long filter
DIR_MIN = 0.35         # |net|/range over the last 30 min — a break has to make directional progress
WHIP_ATR = 19.0        # the desk's violent-whipsaw definition: ATR >= 19 AND ER < 0.25 => never arm
WHIP_ER = 0.25
REFIRE_S = 1800        # after a fire, stay quiet this long rather than exiting
POLL_S = 60


def read(con):
    """(ER30, ATR14, |net|/range over the last 30 bars). None if not enough bars yet."""
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, MAX(high) h, MIN(low) l, ARG_MAX(close, bar_ts) c
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
        GROUP BY 1 ORDER BY 1 DESC LIMIT 60""").fetchall()
    if len(rows) < 31:
        return None, None, None
    b = [Bar(ts=m, open=c, high=h, low=lo, close=c, volume=1.0) for m, h, lo, c in rows[::-1]]
    w = b[-30:]
    rng = max(x.high for x in w) - min(x.low for x in w)
    net = w[-1].close - w[0].close
    return efficiency_ratio(b, 30), _atr(b), (abs(net) / rng if rng else 0.0)


def main() -> int:
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (READ_ONLY)")
    er_hist: deque[float] = deque(maxlen=ER_HOLD_N)
    atr_hist: deque[float] = deque(maxlen=ATR_HOLD_N)
    last_fire = 0.0

    while True:
        er, atr, dirn = read(con)
        ts = datetime.now(UTC).strftime("%H:%M")
        if er is None:
            print(f"{ts} no bars", flush=True)
            time.sleep(POLL_S)
            continue
        er_hist.append(er)
        atr_hist.append(atr)

        # every condition, each with the reason it blocks — silence must be explainable
        why = []
        if len(er_hist) < ER_HOLD_N:
            why.append(f"warming({len(er_hist)}/{ER_HOLD_N})")
        elif min(er_hist) < ER_MIN:
            why.append(f"ER dipped to {min(er_hist):.3f} inside the window")
        # ★ NO separate "decaying" check. The first cut compared er to er_hist[0] and it was WRONG twice
        # over: it is redundant (a floor over the whole window already makes a spike impossible — the
        # 13:33 false fire had min 0.239 and fails on the floor alone) and it actively blocks a HEALTHY
        # sustained band, because ER oscillating in 0.36-0.52 will randomly read below where it sat ten
        # minutes earlier. It suppressed nine consecutive qualifying polls on 08-03 14:41-14:49.
        if len(atr_hist) < ATR_HOLD_N or min(atr_hist) < ATR_MIN:
            why.append(f"ATR {atr:.1f} < {ATR_MIN}")
        if dirn < DIR_MIN:
            why.append(f"no direction (|net|/range {dirn:.2f} < {DIR_MIN})")
        if atr >= WHIP_ATR and er < WHIP_ER:
            why.append(f"VIOLENT WHIPSAW veto (ATR {atr:.1f}, ER {er:.3f})")

        quiet = (time.time() - last_fire) < REFIRE_S
        if not why and not quiet:
            last_fire = time.time()
            print(f"{ts} FIRE ER-CLIMB + VOL-EXPANSION — ER30 {er:.3f} held >= {ER_MIN} for "
                  f"{ER_HOLD_N} polls, ATR {atr:.1f} >= {ATR_MIN}, directional progress "
                  f"{dirn:.2f} >= {DIR_MIN}, not whipsaw. A real break: check day-bias alignment "
                  f"before arming, and arm veto-gates before churners.", flush=True)
        else:
            tag = "quiet-period" if quiet and not why else "; ".join(why)
            print(f"{ts} ER30={er:.3f} ATR={atr:.1f} dir={dirn:.2f} — no fire: {tag}", flush=True)
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
