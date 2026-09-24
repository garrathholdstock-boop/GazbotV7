#!/usr/bin/env python3
"""LOG EVERY PX/CVD GAP EPISODE SO THE RULE CAN BE JUDGED FORWARD (2026-09-24).

Operator asked for worked examples of the PX·CVD pair and produced `65·10` — a 55-point
disagreement the SHIPPED rule ignores, because bearish needs px>=85 and bullish needs px<=15. The
widest divergence of the four he named gets no colour at all. He found the hole by asking for
examples; no test had.

Pre-registered in data/prereg_gap.json. The threshold 35 is NOT FITTED — it is the minimum gap the
incumbent rule already implies (85/50 and 15/50 are both gaps of 35), so no number here was chosen
by looking at data.

⚠⚠ THE UNIT IS AN EPISODE, NEVER A MINUTE. A gap persists for many consecutive minutes; counting
minutes would score one divergence forty times and inflate n by the LENGTH of episodes rather than
their NUMBER — the same trap as counting scale-out exit rows instead of entries.

⚠ SINGLE PASS, NO BACKFILL. It evaluates the minute that ended HORIZON ago, so the outcome is
already on the tape. A log that needs a second pass to fill outcomes in is a log that silently
keeps half its rows.

⚠⚠⚠ READ-ONLY. It writes two files, both its own. No order path, no switch, no request file.
"""
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
CAP = os.environ.get("GAZBOT7_CAPTURE", f"{GB}/data/capture.db")
SERIES = f"{GB}/data/gap_series.jsonl"     # per-minute session state, rebuilt each session
LOG = f"{GB}/data/gap_log.jsonl"           # the pre-registered record: one line per EPISODE

GAP = 35.0                                  # FROZEN — see prereg_gap.json
# ⚠⚠⚠ WARM-UP. A "position in the range" is MEANINGLESS until the range exists. The first run of
# the detector produced episodes at 22:03 and 22:04 reading 100·65 and 0·100 — on a session three
# minutes old whose entire range was a couple of points. Those are arithmetic artefacts of dividing
# by a near-zero span, not divergences, and at ~28 episodes a session they would have been a
# material share of the sample.
# ★ AMENDED BEFORE ANY OUTCOME WAS LOOKED AT. The mechanism check deliberately counted episodes and
# printed NO forward numbers, precisely so a fix like this could not be a fit dressed as a repair.
# Both floors come from mechanism, not from data: an hour because a range needs time to form, and
# 20 points because MNQ's ATR runs ~10-20 and a range narrower than one ATR cannot locate anything.
WARM_MIN = 60                               # minutes of session before the detector may speak
WARM_RANGE_PT = 20.0                        # and the price range must be at least this wide
HORIZON = 30                                # primary, declared in advance
SECONDARY = (5, 15, 60)


def session_open(now: datetime) -> int:
    return int((now.replace(hour=22, minute=0, second=0, microsecond=0)
                - timedelta(days=(0 if now.hour >= 22 else 1))).timestamp())


def build(op: int, until: int):
    """Per-minute (ts, price, cvd, px_pos, cvd_pos) for the session so far.

    ⚠ The positions use the running high/low AS THEY WERE AT THAT MINUTE — never the session's
    final range. Using the finished range would let the rule see the rest of the day, which is the
    look-ahead that has quietly invalidated studies on this desk before.
    """
    c = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    ticks = c.execute("SELECT CAST(ts_ms/60000 AS INT) m, "
                      "SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' "
                      "THEN -size ELSE 0 END) d FROM ticks WHERE symbol='MNQ' AND ts_ms>=? "
                      "AND ts_ms<? GROUP BY m ORDER BY m", (op * 1000, until * 1000)).fetchall()
    bars = dict(c.execute("SELECT CAST(bar_ts/60 AS INT) m, MAX(close) FROM bars WHERE "
                          "symbol='MNQ' AND timeframe='5s' AND bar_ts>=? AND bar_ts<? GROUP BY m",
                          (op, until)).fetchall())
    c.close()
    cvd = 0.0
    phi = plo = chi = clo = None
    out = []
    seen = 0            # ⚠ minutes SEEN, not minutes kept — `len(out)` would never reach the
                        #   warm-up because nothing is appended until the warm-up passes.
    for m, d in ticks:
        cvd += d or 0.0
        p = bars.get(m)
        if p is None:
            continue
        phi = p if phi is None else max(phi, p)
        plo = p if plo is None else min(plo, p)
        chi = cvd if chi is None else max(chi, cvd)
        clo = cvd if clo is None else min(clo, cvd)
        seen += 1
        # ⚠ the warm-up is applied HERE, so a cold minute never even becomes a candidate
        if phi > plo and chi > clo and seen >= WARM_MIN and (phi - plo) >= WARM_RANGE_PT:
            out.append({"m": m, "px": p, "cvd": cvd,
                        "px_pos": 100 * (p - plo) / (phi - plo),
                        "cvd_pos": 100 * (cvd - clo) / (chi - clo)})
    return out


def lean(row):
    g = row["px_pos"] - row["cvd_pos"]
    if abs(g) < GAP:
        return 0, g
    return (-1 if g > 0 else 1), g          # px ahead of cvd => BEARISH lean => -1


def incumbent(row):
    """The SHIPPED two-threshold rule, scored on the same episode. ⚠ A CONTROL IS SUPPOSED TO
    LOSE, but it must be MEASURED, not assumed: replacing a live rule with one that merely matches
    it is churn."""
    p, c = row["px_pos"], row["cvd_pos"]
    if p >= 85 and c <= 50:
        return -1
    if p <= 15 and c >= 50:
        return 1
    return 0


def main() -> int:
    from gazbot7.session import is_open
    now = datetime.now(UTC)
    if not is_open(now):
        return 0
    op = session_open(now)
    t = int(now.timestamp())
    rows = build(op, t)
    if len(rows) < HORIZON + 3:
        return 0
    idx = {r["m"]: i for i, r in enumerate(rows)}
    # ★ the minute whose outcome is ALREADY on the tape
    target_m = (t // 60) - HORIZON - 1
    i = idx.get(target_m)
    if i is None or i == 0:
        return 0
    cur, prev = rows[i], rows[i - 1]
    d_cur, gap = lean(cur)
    d_prev, _ = lean(prev)
    # an EPISODE STARTS when the lean appears, or flips sign
    if d_cur == 0 or d_cur == d_prev:
        return 0
    try:
        with open(LOG) as fh:
            if any(json.loads(l).get("m") == target_m for l in fh if l.strip()):
                return 0
    except FileNotFoundError:
        pass
    fwd = {}
    for h in (HORIZON,) + SECONDARY:
        j = idx.get(target_m + h)
        # ⚠ signed by the lean: a bearish lean scores a FALL as positive
        fwd[f"fwd{h}"] = round((rows[j]["px"] - cur["px"]) * d_cur, 2) if j is not None else None
    row = {"m": target_m, "iso": datetime.fromtimestamp(target_m * 60, UTC).isoformat(),
           "px": cur["px"], "cvd": round(cur["cvd"]),
           "px_pos": round(cur["px_pos"], 1), "cvd_pos": round(cur["cvd_pos"], 1),
           "gap": round(gap, 1), "lean": d_cur,
           "incumbent": incumbent(cur),        # scored on the SAME minute, for the comparison
           **fwd}
    fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
    with os.fdopen(fd, "a") as fh:
        fh.write(json.dumps(row) + "\n")
    try:
        os.chmod(LOG, 0o666)     # root and alphabot both run desk jobs
    except OSError:
        pass
    print(f"gap episode {row['iso']} {row['px_pos']:.0f}·{row['cvd_pos']:.0f} "
          f"gap {gap:+.0f} lean {'BEAR' if d_cur < 0 else 'BULL'} "
          f"incumbent={row['incumbent']} fwd{HORIZON}={row[f'fwd{HORIZON}']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
