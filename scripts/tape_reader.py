#!/usr/bin/env python3
"""THE TAPE READER — phase 1: it watches an open position, judges, and touches NOTHING.

★ WHY IT EXISTS. Operator, 2026-09-12, asking for the third time: "why cant the desk monitor the
  tape like i do. look at the whole day and make an intelligent decision."
  The honest answer was that the desk ALREADY reads the tape intelligently — the router, 5-min
  cadence, 290 graded calls (GOOD 82 / BAD 27 / CHURN 36 / NEUTRAL 145) — but it is wired to the
  one lever that cannot make money: arm and bench. It can never claim, cut, hold or add. And it is
  handed a pre-digested dashboard (15 segment bars, an ER, an ATR), not the DAY.
  This reads the day and decides about the POSITION IN FRONT OF IT.

★★★ IT HAS NO ORDER PATH AND MUST NEVER HAVE ONE. It writes exactly one file — its own log. It
  writes NONE of the rider's request files (the claim and buy flags an inotify unit executes 0.02s
  after they appear) and none of the switch or kill files. tests/test_tape_reader.py asserts that
  against the SOURCE — including that those names do not appear here at all, which is why this
  paragraph describes them instead of naming them. Phase 2 (one lot, claim/cut only, never add) is
  a separate decision that only forward grading can earn.

★★ EVERY INPUT CARRIES ITS AGE. The defect this is built not to repeat: on 2026-09-12 the router
  wrote "healthy, not halted" in 25 of 40 ticks while the execution engine was dead in a
  127-restart boot loop, because it read a health file as a FLAG and never aged it. An input
  older than its cadence is reported as STALE in the prompt, never silently used.

⚠ THE 119 CALIBRATIONS. Eleven months of studies tried to reproduce the operator's manual claims
  with a LEVEL — $100 to $600, ATR-scaled, two-lot — and every one lost. That is why this is not
  another level. It is the reader, given the day, asked the question he answers.
"""
from __future__ import annotations

import argparse, json, os, subprocess, sys
import datetime as dt

GB = "/home/alphabot/gazbot7"
PY_BIN = f"{GB}/.venv/bin/python"
LOG = f"{GB}/data/tape_reader_log.jsonl"
# Same isolation as the router: the headless call runs OUTSIDE the repo so no CLAUDE.md and no
# auto-memory can reach it. A reader that has read the desk's own conclusions is not independent.
CTX = "/var/lib/gazbot7/router_ctx"
CLAUDE = "/root/.local/bin/claude"
DECISIONS = ("HOLD", "CLAIM", "CUT", "ADD")


def _age(path: str) -> float | None:
    try:
        return dt.datetime.now(dt.UTC).timestamp() - os.path.getmtime(path)
    except OSError:
        return None


def _bars(minutes: int, tf_s: int = 60, symbol: str = "MNQ"):
    """5s capture -> tf_s bars. Aggregated here rather than trusting a 1min table that may not
    exist: capture.db's retention is PER TABLE and its timeframes are not guaranteed."""
    import duckdb
    con = duckdb.connect()
    con.execute(f"attach '{GB}/data/capture.db' as c (read_only)")
    lo = int(dt.datetime.now(dt.UTC).timestamp()) - minutes * 60
    return con.execute(f"""
        select (bar_ts/{tf_s})::bigint*{tf_s} t, first(open order by bar_ts) o,
               max(high) h, min(low) l, last(close order by bar_ts) c, sum(volume) v
        from c.bars where symbol='{symbol}' and timeframe='5s' and bar_ts >= {lo}
        group by 1 order by 1""").df()


def context(symbol: str = "MNQ") -> tuple[str, dict]:
    """THE WHOLE DAY, as text. Not a summary — the thing he actually looks at."""
    import numpy as np
    now = dt.datetime.now(dt.UTC)
    facts: dict = {"ts": now.isoformat(), "symbol": symbol}
    L = [f"TAPE READER · {symbol} · {now:%Y-%m-%d %H:%M:%S}Z"]

    # ★★ THE SESSION COMES FIRST, ALWAYS. Without this the reader does what the router did on
    # 2026-09-12: builds "the day so far" out of Friday's tape on a Saturday and calls it live.
    # An empty tape and a shut venue are the SAME observation until something says which.
    sys.path.insert(0, f"{GB}/src")
    from gazbot7.session import is_open, minutes_to_next_open
    venue_open = is_open(now)
    facts["venue_open"] = venue_open
    if not venue_open:
        mins = minutes_to_next_open(now)
        L += ["", f"⛔ THE VENUE IS SHUT. It reopens in {mins/60:.1f} hours"
                  f" ({mins:.0f} min). Everything below is the LAST session's tape, not a live one."
                  " There is no decision to make on a shut venue: answer HOLD with confidence 0.0"
                  " unless you are explicitly told this is a replay."]

    m1 = _bars(24 * 60, 60, symbol)
    if m1.empty:
        return "\n".join(L + ["", "NO BARS AT ALL in the last 24h."]), {**facts, "error": "no bars"}
    bar_age = now.timestamp() - float(m1.t.iloc[-1])
    facts["bar_age_s"] = bar_age
    if bar_age > 300:
        L += ["", f"⚠ THE LAST BAR IS {bar_age/60:.0f} MINUTES OLD"
                  + (" — consistent with the shut venue above." if not venue_open else
                     " AND THE VENUE IS OPEN. That is a DEAD FEED, not a quiet tape."
                     " Judge nothing; say so.")]
    px = float(m1.c.iloc[-1])
    open_s = 13 * 3600 + 30 * 60
    today = m1[(m1.t % 86400 >= open_s)] if (now.hour * 3600 + now.minute * 60) >= open_s else m1
    sess = today if len(today) > 5 else m1.tail(120)
    hi, lo = float(sess.h.max()), float(sess.l.min())
    o = float(sess.o.iloc[0])
    rng = max(hi - lo, 1e-9)
    vwap = float((sess.c * sess.v).sum() / max(sess.v.sum(), 1e-9))
    tr = np.maximum(m1.h - m1.l, 0.25).rolling(14).mean()
    atr = float(tr.iloc[-1])
    facts.update(price=px, day_open=o, day_high=hi, day_low=lo, vwap=vwap, atr=atr,
                 pos_in_range=(px - lo) / rng)

    L += ["", "THE DAY SO FAR",
          f"  open {o:.2f} · now {px:.2f} ({px-o:+.2f} on the session)",
          f"  range {lo:.2f} — {hi:.2f} = {rng:.1f}pt · price sits at "
          f"{100*(px-lo)/rng:.0f}% of it",
          f"  VWAP {vwap:.2f} · price is {(px-vwap)/max(atr,1e-9):+.2f} ATR from it",
          f"  ATR(14, 1min) {atr:.2f}pt · session bars {len(sess)}"]

    m5 = _bars(6 * 60, 300, symbol).tail(24)
    if m5.empty:      # an empty block must SAY it is empty; a blank section reads as "nothing to see"
        m5 = _bars(48 * 60, 300, symbol).tail(24)
        L += ["", "THE LAST SIX HOURS ARE EMPTY — showing the most recent 24 five-minute bars that"
                  " EXIST instead. Read the timestamps: they may not be today."]
    else:
        L += ["", "THE LAST SIX HOURS, 5-min bars (oldest first) — read the STRUCTURE, not the "
                  "numbers"]
    for _, r in m5.iterrows():
        t = dt.datetime.fromtimestamp(r.t, dt.UTC)
        body = "+" if r.c >= r.o else "-"
        L.append(f"  {t:%H:%M}  o{r.o:9.2f} h{r.h:9.2f} l{r.l:9.2f} c{r.c:9.2f} {body} "
                 f"vol{int(r.v):>6}")

    # ── the REAL detector, never a hand-rolled one (a re-derived detector once fabricated +$819)
    try:
        # ★ THE REAL PIPELINE, not an approximation of it. drift.read() cannot be used here — it
        # returns "no read" outside 13:30-21:00Z by design, and this reader runs whenever a position
        # is open. So we do exactly what read() does internally: raw 5s rows -> _minute_bars ->
        # compute. Re-aggregating minute bars myself is how a hand-rolled detector once fabricated
        # +$819 on this desk; _minute_bars' own docstring says it MUST match the backtest exactly.
        import sqlite3
        from gazbot7.drift import _minute_bars, compute
        day0 = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        con = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
        rows = con.execute(
            "select bar_ts, high, low, close from bars where symbol=? and timeframe='5s' "
            "and bar_ts >= ? order by bar_ts", (symbol, day0 + open_s)).fetchall()
        if not rows:
            raise RuntimeError(f"no 5s rows since {open_s//3600}:30Z today (venue shut?)")
        d = compute(_minute_bars([(a, float(b), float(c2), float(d2)) for a, b, c2, d2 in rows]))
        facts["drift"] = {"confirmed": bool(d.confirmed), "direction": d.direction,
                          "minutes": d.minutes}
        L += ["", f"DRIFT (the desk's own detector, called causally): confirmed={d.confirmed} "
                  f"dir={d.direction} on {d.minutes} minutes"]
    except Exception as e:
        # ⚠ LOUD, never silent. A detector that fails quietly is indistinguishable from one that
        # says "no read", and the desk has shipped that confusion before.
        L += ["", f"⚠ DRIFT FAILED TO COMPUTE: {type(e).__name__}: {e}. Treat direction as UNKNOWN."]
        facts["drift_error"] = f"{type(e).__name__}: {e}"

    # ── the position, with every input's AGE stated
    st_p = f"{GB}/data/day_rider_state.json"
    age = _age(st_p)
    try:
        st = json.load(open(st_p))
    except Exception:
        st = {}
    stale = " ⚠ STALE — do not treat as current" if (age or 1e9) > 180 else ""
    L += ["", f"THE POSITION (day_rider_state.json, written {age:.0f}s ago{stale})"
          if age is not None else "THE POSITION: state file MISSING"]
    L += [f"  {json.dumps(st, indent=2)}"]
    facts["position"] = st
    facts["state_age_s"] = age

    L += ["", "THE LADDER (what the desk is already trying to do): four lots bank $100/$200/$400/"
          "$600 = 50/100/200/300pt at $2/pt. Reach rates over 231 sessions: 77.5% / 58.0% / 29.4% "
          "/ ~15%. The hard flat at 20:40Z is the ONLY automatic protection — there is no stop."]
    return "\n".join(L), facts


PROMPT = """You are reading a live futures tape for a solo operator, and you judge ONE thing: the
position in front of you, right now.

He does this himself and it is the best-performing exit this desk has: three manual claims on
2026-08-19 booked +$726 in 23 minutes. Eleven months of studies tried to reproduce those claims with
a fixed LEVEL — $100 to $600, ATR-scaled, two-lot — and all 119 calibrations LOST. He is not
claiming at a dollar figure. He is reading an impulse exhausting. That is what you are being asked
to do, and it is why you are given the day rather than a dashboard.

RULES OF JUDGEMENT
- You are judging THIS position on THIS tape. Not a strategy, not a backtest.
- HOLD is a real answer and usually the right one. Say it plainly when the move is still working.
- CLAIM means bank lots NOW because the impulse is exhausting — not because a number was reached.
- CUT means this is going wrong and getting worse; reduce.
- ADD is available but you must justify it against the fact that the desk's own research has never
  found an automated entry that pays.
- If an input is marked STALE, say so and lower your confidence. A stale flag read as current is
  how this desk once reported "healthy" for three hours while its engine was dead.
- If the tape does not tell you anything, say HOLD with low confidence. Inventing a read is worse
  than admitting there isn't one.

Answer with ONLY this JSON and nothing else:
{"decision":"HOLD|CLAIM|CUT|ADD","lots":<int 0-4>,"confidence":<0.0-1.0>,
 "reason":"<two sentences, plain English, naming what in the tape decided it>",
 "what_would_change_my_mind":"<one sentence>"}
"""


def decide(ctx: str, timeout: int = 180) -> dict:
    os.makedirs(CTX, exist_ok=True)
    try:
        p = subprocess.run([CLAUDE, "-p", PROMPT + "\n\n=== THE TAPE ===\n" + ctx],
                           cwd=CTX, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "HOME": "/root"})
        raw = (p.stdout or "").strip()
        i, j = raw.find("{"), raw.rfind("}")
        if i < 0 or j < 0:
            return {"error": "no JSON in reply", "raw": raw[:400]}
        d = json.loads(raw[i:j+1])
        if d.get("decision") not in DECISIONS:
            return {"error": f"invalid decision {d.get('decision')!r}", "raw": raw[:400]}
        return d
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="run even when flat (for grading dry runs)")
    ap.add_argument("--symbol", default="MNQ")
    a = ap.parse_args()

    ctx, facts = context(a.symbol)
    holding = bool(facts.get("position", {}).get("entered")) and \
        not facts.get("position", {}).get("closed")
    if not holding and not a.force:
        # Not an error and not silent: a reader that logs nothing while idle is dead-or-idle and
        # nothing can tell which — the desk's #1 failure mode, 7 instances in 4 days.
        rec = {"ts": facts["ts"], "skipped": "flat — nothing to judge"}
    else:
        d = decide(ctx)
        rec = {"ts": facts["ts"], "holding": holding, "facts": facts, "decision": d}
    with open(LOG, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec.get("decision", rec), indent=1)[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
