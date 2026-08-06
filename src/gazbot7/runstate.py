"""GAZBOT V7 — LIVE RUN DETECTION. Reports whether a directional RUN is in progress.

★ WHY THIS EXISTS (2026-08-06 router review, Mon 08-03 -> Thu 08-06).
Classifying every trade of the week — taken AND missed — by one variable explained essentially all
of the desk's P&L, and nothing else came close:

                        trades TAKEN                    missed entries (raced @2R, first-touch)
    in-run aligned      n=34   50% win  +$351 (+$10.34/tr)   n=61   67% win  +$2,141  (+$35.1/tr)
    in-run counter      n= 4    0% win   -$81                n=16    6% win    -$643
    chop / no run       n=51   16% win -$1,450 (-$28.43/tr)  n=183  27% win  -$1,517

Armed inside an aligned run the desk makes ~$10/trade; armed in chop it loses ~$28/trade. A $39/trade
spread that dwarfs gate, side and time-of-day. The router was blind to it: it adjudicated every tick on
break-trio purity and sat flat through 18 of the week's 26 runs, blocking $2,141 (1 lot) / $4,283 (2 lot)
of aligned signal while correctly saving ~$2,160 of chop damage.

★ THIS MODULE ONLY REPORTS STATE. It never decides arm/bench — that call is Claude's (operator,
2026-08-06: "claude, not python scripts, needs to arm or de-arm"). A python heuristic that flipped
switches here would recreate the mechanical ER-router the Claude tick replaced.

★ THE ASYMMETRY INVERTS INSIDE A RUN. Standing guidance is "wrongly benched is cheap, wrongly armed is
expensive — when unsure sit benched one more tick". That is right in CHOP and expensive in a RUN, and
applying it blind to which regime we are in is the whole defect. Inside a detected aligned run, BENCHED
is the expensive error.

★ REPLAYED LIVE OVER THE SAME WEEK (state recomputed at every minute from trailing bars only, no
look-ahead), then each of the 260 missed entries bucketed by what the detector said AT THAT MOMENT:

    detector says ARM   n= 20   65% win   +$729   (+$36.5/trade)
    detector says FLAT  n=240   33% win   -$747   (-$3.1/trade)

So it separates. What it ARMS is high quality — better per-trade than the +$35.1 average of all 61
in-run aligned entries — and what it skips loses money.

⚠ TWO LIMITATIONS, STATED SO NOBODY OVERSELLS THIS:
1. IT IS LATE. The window looks BACKWARD 30 minutes, so a run is only confirmed once most of it has
   happened. It captured 20 of the 61 in-run aligned entries (~34%), not all of them. The lag is
   inherent to a trailing window; catching more means a shorter confirmation window, which buys
   earlier entry at the cost of more false starts. NOT tuned here — that needs its own study.
2. IT IS IN-SAMPLE. These thresholds were derived from the very week they are scored on. The honest
   status is "promising and mechanically sound", NOT "validated". It needs forward days before the
   numbers above should be quoted as an expectation. See [[friday-findings-need-adversarial-rederivation]].

Thresholds are the ones that fell out of the 26 runs of that week; they are deliberately not tuned
finer, because a 4-day sample cannot support it. Read them as a coarse regime split, not an optimum.
"""
from __future__ import annotations

import bisect

RUN_NET_MIN = 80.0    # pt of net displacement over the window to qualify as a run
RUN_WIN_MIN = 30      # trailing window, minutes
RUN_ER_START = 0.35   # efficiency to DECLARE a run
RUN_ER_HOLD = 0.30    # efficiency to KEEP an established run alive (hysteresis, avoids flicker)
ATR_WIN_MIN = 20      # minutes for the 1-min ATR proxy


def _minute_bars(con, symbol: str, since_ts: int):
    """1-min OHLC from the raw 5s bars — the tape, not a summary."""
    return con.execute(
        "select (bar_ts-bar_ts%60) m, arg_min(open,bar_ts) o, max(high) h, min(low) l, "
        "arg_max(close,bar_ts) c, sum(volume) v from bars "
        "where symbol=? and timeframe='5s' and bar_ts>=? group by 1 order by 1",
        (symbol, since_ts)).fetchall()


def _er(closes) -> tuple[float, float]:
    """(net, efficiency). Efficiency = |net displacement| / path length travelled."""
    if len(closes) < 2:
        return 0.0, 0.0
    net = closes[-1] - closes[0]
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))) or 1.0
    return net, abs(net) / path


def compute(rows) -> dict:
    """Run state from 1-min bars. ``rows`` = [(m, o, h, l, c, v), ...] ascending.

    Returns a dict the caller renders for the model:
      state    RUN | RUN-FADING | NO-RUN
      side     LONG | SHORT | None   — the ALIGNED side, i.e. the one to arm
      net/er/atr, age_min, start_ts/start_px, vol_ratio
    """
    out = {"state": "NO-RUN", "side": None, "net": 0.0, "er": 0.0, "atr": 0.0,
           "age_min": 0, "start_ts": None, "start_px": None, "vol_ratio": None,
           "bars": len(rows)}
    if len(rows) < RUN_WIN_MIN:
        out["detail"] = f"insufficient bars ({len(rows)}<{RUN_WIN_MIN})"
        return out

    closes = [r[4] for r in rows]
    tr = [r[2] - r[3] for r in rows]
    out["atr"] = round(sum(tr[-ATR_WIN_MIN:]) / min(ATR_WIN_MIN, len(tr)), 1)

    win = closes[-RUN_WIN_MIN:]
    net, er = _er(win)
    out["net"], out["er"] = round(net, 1), round(er, 3)

    if abs(net) >= RUN_NET_MIN and er >= RUN_ER_START:
        out["state"] = "RUN"
    elif abs(net) >= RUN_NET_MIN and er >= RUN_ER_HOLD:
        out["state"] = "RUN-FADING"
    else:
        # ★ one decimal, deliberately: rounding net to whole points printed "net +80pt ... needs
        # |net|>=80" for an actual 79.5, which reads as the tool contradicting itself. A near-miss
        # must LOOK like a near-miss or the next reader stops trusting the detector.
        miss = ("net" if abs(net) < RUN_NET_MIN else "ER") if abs(net) < RUN_NET_MIN or er < RUN_ER_START else "?"
        out["detail"] = (f"trailing {RUN_WIN_MIN}m net {net:+.1f}pt ER {er:.2f} "
                         f"(needs |net|>={RUN_NET_MIN:.0f} AND ER>={RUN_ER_START}) — short on {miss}")
        return out

    out["side"] = "LONG" if net > 0 else "SHORT"

    # walk the window back to find where the run began: the earliest start that still qualifies
    # at the HOLD threshold and keeps the same sign.
    best = RUN_WIN_MIN
    for w in range(RUN_WIN_MIN, len(closes) + 1):
        n2, e2 = _er(closes[-w:])
        if abs(n2) >= RUN_NET_MIN and e2 >= RUN_ER_HOLD and (n2 > 0) == (net > 0):
            best = w
        else:
            break
    out["age_min"] = best
    out["start_ts"] = int(rows[-best][0])
    out["start_px"] = round(closes[-best], 2)
    n3, e3 = _er(closes[-best:])
    out["net"], out["er"] = round(n3, 1), round(e3, 3)

    # participation: recent volume vs the session's own average. A run on collapsing volume is drift.
    vols = [r[5] for r in rows if r[5]]
    if len(vols) >= 30:
        recent = sum(vols[-10:]) / 10.0
        base = sum(vols) / len(vols)
        if base:
            out["vol_ratio"] = round(recent / base, 2)

    out["detail"] = (f"{out['state']} {out['side']} — {out['net']:+.0f}pt over {out['age_min']}m, "
                     f"ER {out['er']:.2f}, ATR {out['atr']:.0f}pt"
                     + (f", vol {out['vol_ratio']:.2f}x session avg" if out['vol_ratio'] else ""))
    return out


def render(st: dict) -> str:
    """One block for the router prompt. States the RULE but takes no action."""
    head = f"RUN STATE: {st['state']}"
    if st["side"]:
        head += f" {st['side']}"
    body = st.get("detail", "")
    if st["state"] == "NO-RUN":
        guide = ("No run in progress. Chop is where the desk bleeds (-$28.43/trade taken, and the "
                 "183 chop signals it blocked would have lost -$1,517). BENCH is correct here.")
    else:
        guide = (f"A run IS in progress. Aligned side = {st['side']}. In-run aligned trades made "
                 f"+$10.34/tr live and the aligned signals the router BLOCKED this week would have "
                 f"made +$35/tr — being flat through a run is the expensive error, not arming. "
                 f"ARM THE ALIGNED GATES and keep them armed while the run holds; bench the "
                 f"counter-trend side (in-run counter: 0-6% win rate). "
                 f"⚠ Judge participation too: a run on collapsing volume is drift, not a move.")
    return f"{head}\n  {body}\n  {guide}"
