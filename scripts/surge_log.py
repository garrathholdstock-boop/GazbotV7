#!/usr/bin/env python3
"""LOG EVERY SURGE WITH ITS PULSE AND FLOW, SO THE QUESTION CAN EVENTUALLY BE ANSWERED.

★★★2026-09-24. Operator: "i feel like i need 1 and 2. shows me if a surge is backed and real."
The meters are live on the TRADE tab and they are DESCRIPTIVE. Whether "backed" also means
"continues" is a separate claim, and on our data it is unproven:

    surge = |1-min move| >= 12.5pt (90th pct), 5 sessions, n=170, next 5 minutes:
      BACKED   pulse>=1.5 & flow aligned   n=80  median +5.25pt  57.5% extended
      unbacked pulse<1.5  & flow aligned   n=68  median +0.50pt  51.5% extended
      flow OPPOSING the move               n=22  median -1.12pt  45.5% extended

That ORDERS correctly and it is NOT A RESULT. Five sessions, and minutes inside a session are not
independent draws — this desk's own history is that a 57% hit rate on n=80 clustered in 5 days is
exactly where direction studies come to die.

⚠⚠⚠ AND IT CANNOT BE SETTLED BY LOOKING BACKWARDS. `aggressor` lives only in `ticks`, and
`prune_capture` keeps ticks for FIVE DAYS. There is no history to widen the study with and there
never will be. Either the readings are written down as they happen or the question stays open
forever. That is the whole reason this file exists.

⚠ PRE-REGISTERED so the answer cannot be fitted after the fact — data/prereg_surge.json fixes the
surge definition, the cells, the horizon and the verdict rule BEFORE the data exists. Do not tune
the 1.5x or the 12.5pt: changing either restarts the count at zero.

⚠⚠ READ-ONLY. It writes one file, its own log. No order path, no switch, no request file.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
LOG = f"{GB}/data/surge_log.jsonl"
CAP = os.environ.get("GAZBOT7_CAPTURE", f"{GB}/data/capture.db")

# ⚠ FROZEN by data/prereg_surge.json. These are not knobs.
SURGE_PT = 12.5          # 90th percentile of the 1-minute move over the sample it was set on
PULSE_BACKED = 1.5
FLOW_ALIGNED = 0.15
HORIZON_MIN = 5


def _minute(c, m0, m1):
    r = c.execute("SELECT MIN(bar_ts) a, MAX(bar_ts) b, COALESCE(SUM(volume),0) v, COUNT(*) n "
                  "FROM bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>=? AND bar_ts<?",
                  (m0, m1)).fetchone()
    if not r or not r["n"]:
        return None
    o = c.execute("SELECT open FROM bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>=? "
                  "AND bar_ts<? ORDER BY bar_ts LIMIT 1", (m0, m1)).fetchone()
    cl = c.execute("SELECT close FROM bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>=? "
                   "AND bar_ts<? ORDER BY bar_ts DESC LIMIT 1", (m0, m1)).fetchone()
    return {"open": o["open"], "close": cl["close"], "vol": r["v"]}


def main() -> int:
    from gazbot7.session import is_open
    now = datetime.now(UTC)
    if not is_open(now):
        return 0
    c = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    t = int(now.timestamp())
    # ★ The minute that ENDED HORIZON_MIN ago — so its forward outcome is already on the tape and
    #   this never has to come back and fill one in. A log that needs a second pass is a log that
    #   silently keeps half its rows.
    m0 = (t - (t % 60)) - (HORIZON_MIN + 1) * 60
    cur = _minute(c, m0, m0 + 60)
    if not cur:
        c.close()
        return 0
    move = cur["close"] - cur["open"]
    if abs(move) < SURGE_PT:
        c.close()
        return 0
    # already logged?
    try:
        with open(LOG) as fh:
            if any(json.loads(l).get("m") == m0 for l in fh if l.strip()):
                c.close()
                return 0
    except FileNotFoundError:
        pass
    prev = [r["v"] for r in c.execute(
        "SELECT CAST(bar_ts/60 AS INT) mm, COALESCE(SUM(volume),0) v FROM bars WHERE symbol='MNQ' "
        "AND timeframe='5s' AND bar_ts>=? AND bar_ts<? GROUP BY mm", (m0 - 15 * 60, m0)).fetchall()]
    prev = [v for v in prev if v > 0]
    if len(prev) < 8:
        c.close()
        return 0
    base = sorted(prev)[len(prev) // 2]
    r = c.execute("SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size END),0) b, "
                  "COALESCE(SUM(CASE WHEN aggressor='sell' THEN size END),0) s FROM ticks "
                  "WHERE symbol='MNQ' AND ts_ms>=? AND ts_ms<?",
                  (m0 * 1000, (m0 + 60) * 1000)).fetchone()
    tot = (r["b"] or 0) + (r["s"] or 0)
    fwd = _minute(c, m0 + HORIZON_MIN * 60, m0 + (HORIZON_MIN + 1) * 60)
    c.close()
    if not tot or not base or not fwd:
        return 0
    d = 1 if move > 0 else -1
    flow = ((r["b"] or 0) - (r["s"] or 0)) / tot
    row = {"m": m0, "iso": datetime.fromtimestamp(m0, UTC).isoformat(),
           "move_pt": round(move, 2), "dir": d,
           "pulse": round(cur["vol"] / base, 3), "flow": round(flow, 3),
           "backed": bool(cur["vol"] / base >= PULSE_BACKED and flow * d >= FLOW_ALIGNED),
           # ⚠ CONTINUATION IS SIGNED BY THE SURGE'S OWN DIRECTION. Storing a raw price delta would
           #   need re-signing at read time and one forgotten sign flips the whole verdict.
           "cont_pt": round((fwd["close"] - cur["close"]) * d, 2)}
    fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
    with os.fdopen(fd, "a") as fh:
        fh.write(json.dumps(row) + "\n")
    try:
        os.chmod(LOG, 0o666)     # root and alphabot both run desk jobs — see notify_operator._record
    except OSError:
        pass
    print(f"surge {row['iso']} {move:+.1f}pt pulse {row['pulse']:.2f}x flow {flow:+.2f} "
          f"backed={row['backed']} cont {row['cont_pt']:+.2f}pt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
