#!/usr/bin/env python3
"""WALK LAST WEEK FORWARD, ONE DAY AT A TIME, AND LET CLAUDE LEARN BETWEEN DAYS.

★★★ Operator: *"build it like we are going to do it. day by day. do monday. let claude self review
his performance and take into account improvements for tuesday. then do tuesday. full review,
improve for wednesday etc."*

So this is not a strategy backtest. **It is a backtest OF THE RECURSIVE LOOP** — the thing he asked
for at the start ("i want it to get smarter every night"), run against five days we already have the
tape for, so the question "does the learning actually compound?" gets an answer this weekend instead
of in a month.

    Mon: trade causally, every 5 min  ->  review own decisions  ->  write LESSONS
    Tue: trade with the brief + Monday's lessons  ->  review  ->  lessons
    ... through Friday

⚠⚠⚠ AND A CONTROL ARM HE DID NOT ASK FOR, WITHOUT WHICH THE WHOLE EXERCISE IS UNFALSIFIABLE.
If P&L rises Mon->Fri we cannot tell learning from a tape that simply got easier. So the same five
days are ALSO run with the lessons WITHHELD — identical prompts, identical tape, no memory between
days. **The claim "it got smarter" is the LEARNED arm minus the CONTROL arm, never the slope of the
learned arm alone.** [[a-control-is-supposed-to-lose]]: on this desk a P&L sort once put the
no-flip control top of a kill pile.

──────────────────────────────────────────────────────────────────────────────────────────────────
HIS SPEC, as given, and every number here is his rather than mine
  WINDOW     06:00Z - 13:30Z   "8am paris is the start", stop at the US open. His own book:
                               04:00-13:30Z is 57% win / 30min holds against 50% / 12min after it.
  TARGET     20 points minimum ("if we miss most of it, you can still jump in late for 20-30
                               points and make $200") = 20pt x 4 lots x $2 = $160.
  STYLE      CONFIRMATION, never anticipation. "i watch that the leg has turned and is grinding up
                               or down the other way and i jump in." Late is FINE.
  MATERIAL   the whole day's narrative, not a metric at one moment. "what has happened so far? it
                               ground down for 8 hours, then up for 4 now its starting down again."
  JUDGEMENT  Claude's, not a formula. "claude needs to be involved for judgement you cant python
                               this." Claude makes the ENTER and the EXIT call.

⚠⚠ CAUSALITY IS THE WHOLE VALIDITY OF THIS FILE. At step T the context is built from bars with
bar_ts <= T and NOTHING ELSE. No peak, no future bar, no end-of-day knowledge. The day review may
use only that day's tape. Reading a peak once produced 866 winners from 866 trades on this desk, and
a resample that labelled the left edge leaked the decision minute itself. `_assert_causal()` checks
every context block before it is sent and raises rather than warns.

⚠ FILLS ARE DELIBERATELY PESSIMISTIC. The decision at the close of a 5-min bar fills at THAT CLOSE
plus half the spread against us, and a round turn is charged $1.50/lot. We do NOT model the paper
engine's 0.1% fabrication because that is an artefact of the simulator we are replacing, not a real
cost — but we also never assume a better price than printed.
⚠ The simulator, not Claude, enforces: one position at a time, no adds, and a FORCED FLAT at 13:30Z.
  Those are the operator's own constraints and a judgement call may not override them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sqlite3
import statistics as st

GB = "/home/alphabot/gazbot7"
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
OUT = f"{GB}/reports/sim_week_recursive"

WIN_START_MIN = 6 * 60          # 06:00Z = 08:00 Paris
WIN_END_MIN = 13 * 60 + 30      # 13:30Z = the US cash open
STEP_MIN = 5
LOTS = 4
VPP = 2.0                       # $ per point per lot for MNQ
FEE_RT = 1.50                   # per lot round turn — venue truth over 487 fills
HALF_SPREAD_PT = 0.125          # MNQ ticks 0.25; charge half against us each way
MIN_TARGET_PT = 20.0            # HIS minimum

DAYS = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]


# ── tape ────────────────────────────────────────────────────────────────────────────────────────

def load_day(day: str):
    """5s bars from 22:00Z the previous evening to 13:30Z, so the overnight grind is part of the
    story. Returns (minute_bars, session_open_epoch).

    ⚠ The session is anchored at 22:00Z — the same anchor as the dashboard's session high/low. The
    shipped tape_reader anchors 'the day' at 13:30Z, the US open, which is AFTER every entry he made
    on his best day (06:16, 07:24, 08:52, 09:27, 09:33, 10:08). It was reasoning about a session he
    had already finished trading.
    """
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    sess_open = d0 - 2 * 3600                      # 22:00Z previous day
    end = d0 + WIN_END_MIN * 60
    con = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
    rows = con.execute(
        "SELECT bar_ts, high, low, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
        "AND bar_ts >= ? AND bar_ts < ? ORDER BY bar_ts", (sess_open, end)).fetchall()
    agg: dict[int, list] = {}
    for ts, h, l, c in rows:
        m = (ts // 60) * 60
        a = agg.setdefault(m, [h, l, c])
        a[0] = max(a[0], h)
        a[1] = min(a[1], l)
        a[2] = c                                   # last close in the minute
    bars = [(m, float(v[0]), float(v[1]), float(v[2])) for m, v in sorted(agg.items())]
    return bars, sess_open


def atr14(bars) -> float:
    if len(bars) < 15:
        return 0.0
    trs = []
    for i in range(len(bars) - 14, len(bars)):
        h, l, pc = bars[i][1], bars[i][2], bars[i - 1][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc), 0.25))
    return sum(trs) / 14.0


def legs(bars, retrace_atr: float = 15.0):
    """THE SNAKE, causally. A leg ends only when price has given back retrace_atr x ATR from its
    extreme — so at any moment the CURRENT leg is unconfirmed and that is stated honestly.

    ⚠ 15xATR is used because arm 6 measured the alternatives: leg_watch's frozen 3xATR gives 27-46
    legs a session (not a snake, and it overlaps itself), while 15xATR gives 2-6 with a median of 4
    — which is what he means by "5 straight lines in the snake".
    Returns (confirmed_legs, current_leg) where a leg is (dir, start_i, end_i, points, minutes).
    """
    if len(bars) < 30:
        return [], None
    atr = atr14(bars) or 1.0
    thr = retrace_atr * atr
    out = []
    dirn = 1 if bars[10][3] > bars[0][3] else -1
    start_i, ext, ext_i = 0, bars[10][3], 10
    for i in range(11, len(bars)):
        c = bars[i][3]
        if dirn * (c - ext) > 0:
            ext, ext_i = c, i
        elif dirn * (ext - c) >= thr:
            out.append((dirn, start_i, ext_i,
                        dirn * (ext - bars[start_i][3]),
                        (bars[ext_i][0] - bars[start_i][0]) // 60))
            start_i, dirn, ext, ext_i = ext_i, -dirn, c, i
    cur = (dirn, start_i, len(bars) - 1,
           dirn * (bars[-1][3] - bars[start_i][3]),
           (bars[-1][0] - bars[start_i][0]) // 60)
    return out, cur


# ── the context Claude sees ─────────────────────────────────────────────────────────────────────

def _assert_causal(bars_upto, now_epoch: int) -> None:
    """⚠⚠⚠ THE ONE CHECK THAT MAKES THIS FILE WORTH ANYTHING. Raises, never warns."""
    if bars_upto and bars_upto[-1][0] > now_epoch:
        raise AssertionError(f"LOOK-AHEAD: bar {bars_upto[-1][0]} is after now {now_epoch}")


def context(bars_upto, now_epoch: int, pos: dict | None, lessons: str) -> str:
    _assert_causal(bars_upto, now_epoch)
    now = dt.datetime.fromtimestamp(now_epoch, dt.UTC)
    atr = atr14(bars_upto)
    px = bars_upto[-1][3]
    conf, cur = legs(bars_upto)
    L = [f"MNQ · {now:%Y-%m-%d %H:%M}Z · 08:00 Paris to the US open is the window",
         f"price {px:.2f} · ATR(14,1m) {atr:.2f}pt · {len(bars_upto)} minutes of tape since 22:00Z",
         "",
         "THE DAY SO FAR — THIS IS THE THING TO READ. The sequence, not the last number."]
    if conf:
        for i, (d, si, ei, pts, mins) in enumerate(conf, 1):
            t0 = dt.datetime.fromtimestamp(bars_upto[si][0], dt.UTC)
            t1 = dt.datetime.fromtimestamp(bars_upto[ei][0], dt.UTC)
            L.append(f"  leg {i}: {'UP  ' if d > 0 else 'DOWN'} {abs(pts):>6.0f}pt over "
                     f"{mins:>4.0f}min   {t0:%H:%M} -> {t1:%H:%M}Z   (CONFIRMED turned)")
    else:
        L.append("  no leg has confirmed a turn yet this session")
    d, si, ei, pts, mins = cur
    t0 = dt.datetime.fromtimestamp(bars_upto[si][0], dt.UTC)
    L += [f"  NOW:   {'UP  ' if d > 0 else 'DOWN'} {abs(pts):>6.0f}pt over {mins:>4.0f}min   "
          f"{t0:%H:%M}Z -> now   (RUNNING, not yet confirmed turned)",
          "",
          f"  so: {len(conf)} confirmed leg(s) behind us, and the current one has run "
          f"{mins:.0f} minutes for {abs(pts):.0f}pt."]

    L += ["", "THE WHOLE SESSION IN 15-MIN BARS (oldest first) — read the shape"]
    step = 15
    for k in range(0, len(bars_upto) - step + 1, step):
        blk = bars_upto[k:k + step]
        t = dt.datetime.fromtimestamp(blk[0][0], dt.UTC)
        o, h, l, c = blk[0][3], max(b[1] for b in blk), min(b[2] for b in blk), blk[-1][3]
        L.append(f"  {t:%H:%M}  o{o:9.2f} h{h:9.2f} l{l:9.2f} c{c:9.2f} {'+' if c >= o else '-'}")

    if pos:
        ahead = pos["dir"] * (px - pos["entry"])
        L += ["", f"YOUR POSITION: {'LONG' if pos['dir'] > 0 else 'SHORT'} {LOTS} from "
                  f"{pos['entry']:.2f}, opened {pos['opened']:%H:%M}Z "
                  f"({(now - pos['opened']).total_seconds() / 60:.0f} min ago)",
              f"  it is {ahead:+.1f}pt = ${ahead * LOTS * VPP:+,.0f} before costs",
              f"  peak favourable so far {pos['peak']:+.1f}pt"]
    else:
        L += ["", "YOU ARE FLAT."]

    mins_left = WIN_END_MIN - (now.hour * 60 + now.minute)
    L += ["", f"⏱ {mins_left} minutes left in the window. At 13:30Z you are flattened "
              f"automatically, whatever you say."]
    if lessons:
        L += ["", "WHAT YOU LEARNED ON THE PREVIOUS DAYS OF THIS WEEK", lessons]
    return "\n".join(L)


BRIEF = f"""You are trading MNQ for a discretionary trader whose method you must follow exactly.

HIS METHOD, in his words:
  "i watch that the leg has turned and is grinding up or down the other way and i jump in."
  He is a CONFIRMATION trader. He does NOT try to catch the turn. Being late is FINE:
  "its not urgent to jump in. if we miss most of it, you can still jump in late for 20-30 points
  and make $200."
  "the gentle grind of asia and london is very friendly to this type of trading."

WHAT TO READ: the DAY'S STRUCTURE, not a metric at this moment. "what has happened so far? it
ground down for 8 hours, then up for 4 now its starting down again." The leg sequence is given to
you above — use it.

YOUR TARGET: {MIN_TARGET_PT:.0f} points minimum ({MIN_TARGET_PT * LOTS * VPP:.0f} dollars at {LOTS} lots). You do not need
the whole leg. You need 20-30 points of a leg that is already going your way.

CONSTRAINTS YOU CANNOT OVERRIDE (the simulator enforces them):
  · one position at a time, {LOTS} lots, no adding
  · the window is 06:00Z-13:30Z and you are flattened at 13:30Z regardless
  · 3 to 6 trades a day is the target band. The tape offers about 3 real legs a day. Twenty-three
    entries in one session lost $1,882; six entries the next day made $1,788.
  · NEVER enter against the direction of the leg that is currently running. Measured on his own
    book: with the leg +$87/entry, against it -$244/entry, and on his losing days entries against
    the leg won 1 of 17.

ANSWER WITH ONE JSON OBJECT AND NOTHING ELSE:
{{"action":"ENTER_LONG|ENTER_SHORT|EXIT|HOLD|WAIT","confidence":0.0-1.0,"reason":"<one sentence>"}}
  ENTER_* only when flat. EXIT or HOLD only when holding. WAIT when flat and not interested.
Be decisive but do not manufacture trades: WAIT is the right answer most of the time."""


def ask(prompt: str, timeout: int = 180) -> dict:
    try:
        p = subprocess.run([CLAUDE, "-p", prompt], cwd=OUT, capture_output=True,
                           text=True, timeout=timeout,
                           env={**os.environ, "HOME": "/root"})
        raw = (p.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return {"action": "WAIT", "error": f"timeout {timeout}s"}
    except Exception as e:
        return {"action": "WAIT", "error": f"{type(e).__name__}: {e}"}
    # brace-balanced first object — the tape_reader lesson: first-brace-to-last-brace ate 934 of
    # 966 failures because the model adds prose after the JSON
    for s_i in range(len(raw)):
        if raw[s_i] != "{":
            continue
        depth, in_str, esc = 0, False, False
        for k in range(s_i, len(raw)):
            ch = raw[k]
            if in_str:
                esc = (ch == "\\") if not esc else False
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        o = json.loads(raw[s_i:k + 1])
                    except Exception:
                        break
                    if isinstance(o, dict) and "action" in o:
                        return o
                    break
    return {"action": "WAIT", "error": "no parseable action", "raw": raw[:400]}


def run_day(day: str, lessons: str, arm: str, resume: bool = True) -> dict:
    """One session, causally, every STEP_MIN minutes. Returns the day's record."""
    path = f"{OUT}/{arm}_{day}.json"
    if resume and os.path.exists(path):
        return json.load(open(path))
    bars, _ = load_day(day)
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    pos, trades, calls = None, [], []
    for m in range(WIN_START_MIN, WIN_END_MIN, STEP_MIN):
        now_epoch = d0 + m * 60
        upto = [b for b in bars if b[0] <= now_epoch]
        if len(upto) < 60:
            continue
        px = upto[-1][3]
        if pos:
            pos["peak"] = max(pos["peak"], pos["dir"] * (px - pos["entry"]))
        d = ask(BRIEF + "\n\n=== THE TAPE ===\n"
                + context(upto, now_epoch, pos, lessons))
        act = d.get("action", "WAIT")
        calls.append({"ts": dt.datetime.fromtimestamp(now_epoch, dt.UTC).isoformat(),
                      "px": px, "action": act, "conf": d.get("confidence"),
                      "reason": (d.get("reason") or "")[:300], "error": d.get("error"),
                      "holding": bool(pos)})
        if pos is None and act in ("ENTER_LONG", "ENTER_SHORT"):
            dirn = 1 if act == "ENTER_LONG" else -1
            pos = {"dir": dirn, "entry": px + dirn * HALF_SPREAD_PT, "peak": 0.0,
                   "opened": dt.datetime.fromtimestamp(now_epoch, dt.UTC),
                   "reason": (d.get("reason") or "")[:200]}
        elif pos is not None and act == "EXIT":
            trades.append(_close(pos, px, now_epoch, "CLAUDE_EXIT"))
            pos = None
    if pos is not None:                    # the forced flat the simulator owns, not Claude
        last = [b for b in bars if b[0] <= d0 + WIN_END_MIN * 60][-1]
        trades.append(_close(pos, last[3], last[0], "WINDOW_CLOSE_1330Z"))
    rec = {"day": day, "arm": arm, "trades": trades, "calls": calls,
           "net_usd": round(sum(t["pnl_usd"] for t in trades), 2)}
    os.makedirs(OUT, exist_ok=True)
    json.dump(rec, open(path, "w"), indent=1, default=str)
    return rec


def _close(pos, px, epoch, why) -> dict:
    exit_px = px - pos["dir"] * HALF_SPREAD_PT
    pts = pos["dir"] * (exit_px - pos["entry"])
    gross = pts * LOTS * VPP
    return {"side": "LONG" if pos["dir"] > 0 else "SHORT",
            "entry": round(pos["entry"], 2), "exit": round(exit_px, 2),
            "opened": pos["opened"].isoformat(),
            "closed": dt.datetime.fromtimestamp(epoch, dt.UTC).isoformat(),
            "held_min": round((epoch - pos["opened"].timestamp()) / 60, 1),
            "points": round(pts, 2), "peak_pt": round(pos["peak"], 2),
            "pnl_usd": round(gross - FEE_RT * LOTS, 2), "why": why,
            "entry_reason": pos.get("reason", "")}


REVIEW = """You traded MNQ today using the method below. Review YOUR OWN decisions honestly and
write what you will do differently tomorrow.

⚠ You may ONLY use today's tape and today's decisions. You do not know what happens tomorrow.
⚠ Be specific and actionable. "Be more patient" is useless. "I exited three trades inside 10
  minutes for under 20 points; the leg ran another 60 minutes each time — hold until the leg's
  structure breaks, not until the first pullback" is useful.
⚠ If you traded too much, say so with the count. If you entered against the running leg, say which
  trade. If you waited through a clean confirmed turn, name the time.
⚠ Do NOT invent a rule you cannot apply from the material you are given. You see the leg sequence,
  the session shape, your position and the clock. Nothing else.

Answer with 3 to 6 numbered lessons, each one sentence, no preamble."""


def review_day(rec: dict, lessons_so_far: str) -> str:
    t = rec["trades"]
    L = [f"DAY: {rec['day']}   net ${rec['net_usd']:+,.2f} over {len(t)} trade(s)"]
    for x in t:
        L.append(f"  {x['side']:5} {x['opened'][11:16]}->{x['closed'][11:16]}Z "
                 f"{x['held_min']:>5.0f}min  {x['points']:+7.1f}pt  ${x['pnl_usd']:+8.2f}  "
                 f"peak {x['peak_pt']:+.0f}pt  [{x['why']}]  entry: {x['entry_reason'][:90]}")
    acts = {}
    for c in rec["calls"]:
        acts[c["action"]] = acts.get(c["action"], 0) + 1
    L += ["", f"your {len(rec['calls'])} five-minute calls: {acts}"]
    errs = sum(1 for c in rec["calls"] if c.get("error"))
    if errs:
        L.append(f"⚠ {errs} of your calls failed to parse and defaulted to WAIT")
    if lessons_so_far:
        L += ["", "the lessons you were already carrying into today:", lessons_so_far]
    out = ask(REVIEW + "\n\n=== WHAT YOU DID ===\n" + "\n".join(L), timeout=240)
    return out.get("reason") or out.get("lessons") or json.dumps(out)[:1500]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("learned", "control", "both"), default="both")
    ap.add_argument("--days", default=",".join(DAYS))
    ap.add_argument("--fresh", action="store_true", help="ignore cached day files")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    days = a.days.split(",")
    arms = ("learned", "control") if a.arm == "both" else (a.arm,)

    summary = {}
    for arm in arms:
        lessons, rows = "", []
        for day in days:
            rec = run_day(day, lessons if arm == "learned" else "", arm, resume=not a.fresh)
            rows.append(rec)
            print(f"  {arm:8} {day}  net ${rec['net_usd']:+9,.2f}  "
                  f"{len(rec['trades'])} trade(s)")
            if arm == "learned":
                lp = f"{OUT}/lessons_{day}.txt"
                if os.path.exists(lp) and not a.fresh:
                    new = open(lp).read()
                else:
                    new = review_day(rec, lessons)
                    open(lp, "w").write(new)
                lessons = (lessons + "\n" + new).strip()
        summary[arm] = rows
        tot = sum(r["net_usd"] for r in rows)
        ntr = sum(len(r["trades"]) for r in rows)
        print(f"  {arm:8} WEEK  net ${tot:+,.2f} over {ntr} trades "
              f"({ntr/len(days):.1f}/day)")
        print()

    if len(arms) == 2:
        lw = [r["net_usd"] for r in summary["learned"]]
        cw = [r["net_usd"] for r in summary["control"]]
        print("=== DID THE LEARNING DO ANYTHING? ===")
        print(f"  learned week ${sum(lw):+,.2f}   control week ${sum(cw):+,.2f}   "
              f"difference ${sum(lw)-sum(cw):+,.2f}")
        print("  ⚠ FIVE DAYS IS FIVE DAYS. A difference here is a reason to run it again on more")
        print("    weeks, never a validated improvement — and the control exists precisely because")
        print("    a rising learned arm alone would be unfalsifiable.")
    json.dump(summary, open(f"{OUT}/summary.json", "w"), indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
