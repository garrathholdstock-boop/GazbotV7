#!/usr/bin/env python3
"""TAPE WATCHER — a headless agent reading the tape through the US session, alert-only.

Operator, 2026-08-04: "you need to setup a daily cron to have an agent monitoring the tape for the
first hour of the us open every minute. if i am asking you to do things it will distract from you
looking at the tape... and the agent interrupts you with any things that need changing".

★ WHY THIS EXISTS. On 2026-08-04 the tape broke out at ~13:35 (last-hr ER 0.02->0.40, ATR 10->21, new
day high, bias UP +559) and grind_long — the ALIGNED trend-rider — stayed benched for 17 minutes while I
was answering a question about NIPC. The 5-min durable tick DID see the break and declined anyway,
reasoning "its own book is the day's worst and one hour is not n" — which is wrong on a trend day,
because the day aggregate was dominated by the morning dead chop. The open hour is where the day is
won or lost and it is exactly when the operator is most likely to be talking to me. So the watching
must not depend on my attention.

★★ ALERT-ONLY. IT MUST NEVER WRITE gate_switches.env.
`gazbot7-router-tick.timer` already owns that file every 5 minutes. A second writer is the "two
routers" hazard CLAUDE.md warns about explicitly — two processes racing on the same switches, each
undoing the other. So this agent is READ-ONLY: it reads the tape and, if something needs changing,
writes a line to ALERTS. The live session tails that file and is interrupted in-chat; the operator gets
a Telegram push on anything critical. A human (or the session) then acts. One writer, many watchers.

★ DEDUPED. A minute-cadence watcher that re-alerts the same condition 60 times is worse than useless —
it trains everyone to ignore it. Each alert is fingerprinted and only a CHANGED fingerprint fires. The
heartbeat still records every tick to the run log so a dead watcher is visible.

★ FAIL-SAFE. Any error, timeout or unparseable answer => NO alert and a logged skip. It cannot halt the
desk, cannot move a switch, and cannot page on its own malfunction beyond one log line.

Windows (weekdays, UTC): 13:30-14:30 EVERY MINUTE (the open hour) and 14:30-20:00 EVERY 3rd MINUTE
(the afternoon fade window, added 08-04 — that is when the faders pay). Outside them it exits
immediately, so the timer can be dumb and fire every minute.

  PYTHONPATH=src .venv/bin/python scripts/open_hour_watch.py [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"
CLAUDE = "/root/.local/bin/claude"
ALERTS = f"{GB}/data/open_hour_alerts.log"     # the session tails THIS -> in-chat interrupt
RUNLOG = f"{GB}/data/open_hour_watch.log"      # heartbeat: every tick, so a dead watcher is visible
STATE = f"{GB}/data/open_hour_state.json"      # last alert fingerprint (dedup)
# ── WINDOWS + CADENCE ─────────────────────────────────────────────────────────────────────────────
# ★2026-08-04 (operator: "do both") — extended past the open hour to cover the AFTERNOON FADE window,
# because that is when the faders historically pay: exhaustion_short's 4-for-4 +$372 was afternoon
# post-trend roll-over chop, and a roll-over that forms at 16:00 was previously watched by nothing
# finer than the 5-min router tick.
# TWO CADENCES, deliberately. The open is fast and high-stakes, so every minute. The afternoon turns
# slowly — a roll-over forms over tens of minutes, not seconds — and a minute cadence there would be
# ~390 model calls a day for no extra resolution. Every 3rd minute is ~110 calls and still catches a
# turn well inside the window it matters in.
OPEN_FROM, OPEN_TO = (13, 30), (14, 30)        # UTC — every minute
PM_FROM, PM_TO = (14, 30), (20, 0)             # UTC — every 3rd minute (afternoon fade window)
PM_EVERY_MIN = 3


def sh(cmd: str, timeout: int = 60) -> str:
    env = {**os.environ, "PYTHONPATH": "src"}
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout, cwd=GB, env=env).stdout
    except Exception as e:
        return f"(read failed: {e})"


def in_window(now: dt.datetime) -> str | None:
    """'open' (every minute), 'pm' (every PM_EVERY_MIN minutes), or None = skip."""
    if now.weekday() > 4:
        return None
    hm = (now.hour, now.minute)
    if OPEN_FROM <= hm < OPEN_TO:
        return "open"
    if PM_FROM <= hm < PM_TO:
        return "pm" if now.minute % PM_EVERY_MIN == 0 else None
    return None


def features_block() -> str:
    """The geometry the ROLL-OVER test needs, which desk_view does not print.

    ★ Added because the prompt was being asked to judge "has the trend rolled over" from ER/ATR/bias
    alone. vwap_slope and ext_atr are the two numbers that actually separate a STALL AT THE HIGH (still
    5 ATR above VWAP, slope positive — what 2026-08-04 14:53 was) from a genuine ROLL-OVER (price
    returning to VWAP, slope turning negative). Asking for a verdict without showing the evidence is how
    you get a confident guess."""
    try:
        import duckdb

        sys.path.insert(0, f"{GB}/src")
        from gazbot7.deciders import Bar, compute_features
        from gazbot7.sizing import efficiency_ratio
        con = duckdb.connect()
        con.execute(f"ATTACH '{GB}/data/capture.db' AS cap (TYPE sqlite, READ_ONLY)")
        rows = con.execute("""SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
                   arg_max(close,bar_ts) cl, sum(volume) v FROM cap.bars
                WHERE symbol='MNQ' AND timeframe='5s'
                  AND bar_ts >= (SELECT max(bar_ts)-5400 FROM cap.bars
                                 WHERE symbol='MNQ' AND timeframe='5s')
                GROUP BY 1 ORDER BY 1""").fetchall()
        con.close()
        bars = [Bar(int(m), float(c), float(h), float(lo), float(c), float(v or 0))
                for m, h, lo, c, v in rows]
        if len(bars) < 20:
            return "(features unavailable: too few bars)"
        f = compute_features(bars)
        w = bars[-30:]
        rng = max(x.high for x in w) - min(x.low for x in w)
        net = w[-1].close - w[0].close
        # 5-min buckets so LOWER HIGHS (failed bounces) are visible, not just aggregates
        buckets = []
        for i in range(max(0, len(bars) - 40), len(bars), 5):
            ch = bars[i:i + 5]
            if ch:
                buckets.append(f"{dt.datetime.fromtimestamp(ch[0].ts, dt.UTC):%H:%M}"
                               f" H{max(x.high for x in ch):.0f} L{min(x.low for x in ch):.0f}"
                               f" C{ch[-1].close:.0f}")
        return (f"=== GEOMETRY (for the roll-over test) ===\n"
                f"ATR {f.atr:.1f}pt | ER30 {efficiency_ratio(bars,30):.3f} | "
                f"ER15 {efficiency_ratio(bars,15):.3f}\n"
                f"vwap_slope {f.vwap_slope_atr:+.2f}  (negative = rolling over)\n"
                f"ext_atr {f.ext_atr:+.2f}  (ATRs from VWAP; collapsing toward 0 = returning to VWAP)\n"
                f"net_atr_5 {f.net_atr_5:+.2f} | last 30m: {rng:.0f}pt range for {net:+.0f}pt net\n"
                f"5-min shape (watch for LOWER HIGHS): " + " | ".join(buckets) + "\n")
    except Exception as e:
        return f"(features unavailable: {e})"


PROMPT = """You are watching the GAZBOT V7 MNQ desk during the US session. You are a
READ-ONLY watcher: you cannot change anything. Your only job is to decide whether something needs
CHANGING RIGHT NOW and, if so, say what — a human acts on it within a minute or two.

Reply with STRICT JSON only:
{"action":"NONE"|"ALERT","urgency":"info"|"act"|"critical","what":"<the change needed, one line>","why":"<the evidence, one line>"}

Use action NONE unless there is something specific to DO. A running commentary is noise; an alert that
merely restates the tape will be ignored and will make the next real alert less likely to be read.

WHAT WARRANTS AN ALERT — judge on the evidence in front of you, not on a checklist:
* An ALIGNED momentum gate is benched while a REAL break is underway. A real break needs all three:
  ER climbing and sustained (not one blip), vol expanding, and structure (new extreme / range break).
  ★ Do NOT accept "its full-day book is red" as a reason it should stay benched — on a trend day that
  aggregate is dominated by earlier chop. Segregate by the BREAK window. This exact error cost 17
  minutes of a +559pt trend day on 2026-08-04.
* A gate is armed into a regime that is demonstrably paying it nothing — a wall of STOPs, or a fader
  armed against a confirmed directional day.
* A counter-trend gate is armed while a clean, efficient trend runs against it.
* Position/health trouble: not flat when it should be, naked, halted, capture stale, a restart storm.
* The quiet-tape CLIP is capping profit on a trending day (ATR just under the atr_split boundary caps
  Lot A at a cash figure while the tape is running).
* ★ A ROLL-OVER HAS FORMED and the fader that trades it is benched. This is the one thing you are asked
  to watch FOR rather than against, because the afternoon fade is where exhaustion_short earns (it went
  4-for-4 for +$372 on 2026-07-30 fading post-trend roll-over chop). Judge it on the GEOMETRY block, and
  the bar is deliberately high — ALL of:
    - vwap_slope has turned NEGATIVE (or is collapsing hard toward 0 from a positive trend value), AND
    - ext_atr is collapsing toward 0, i.e. price is genuinely RETURNING to VWAP, AND
    - the 5-min shape shows LOWER HIGHS / failed bounces, not just a flat range.
  ★★ A STALL AT THE HIGH IS NOT A ROLL-OVER. On 2026-08-04 at 14:53 the trend had clearly stopped
  (40min: +13pt across a 97pt range, ATR 29->15) yet price was still +5.27 ATR ABOVE VWAP with
  vwap_slope +2.95. That is churn at the high, and exhaustion's own shadow was flat (-$9.5/9tr) through
  it. Do NOT alert on a stall.
  ★★ AND CHECK IT COULD EVEN TRADE: exhaustion_short runs veto_counter_regime=True, so it SKIPS shorts
  fired into a local up-trend. While the local regime still reads up, arming it is a no-op — alerting to
  arm a gate that will then self-veto wastes the alert and teaches everyone to ignore the next one.
  (grind_long was armed for 24 minutes on 08-04 and produced zero signals for the analogous reason.)
  Also weigh that benching faders against a directional day is the most robustness-tested behaviour on
  this desk (+$810 non-overlap, n=25) — so the roll-over must be genuine, not hoped for.

DELIBERATELY NOT YOUR JOB: retuning R multiples, proposing new gates, or second-guessing a bench that
has a stated standing reason. Read the switches file's comments — a gate benched for a verdicted reason
(rgv_short) or pinned after a failed acceptance replay (nipc) should NOT be alerted on.

CONTEXT:
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore the time window")
    a = ap.parse_args()

    now = dt.datetime.now(dt.UTC)
    phase = in_window(now)
    if not a.force and phase is None:
        return 0
    phase = phase or "forced"

    desk = sh(f"{PY} scripts/desk_view.py", timeout=120)
    recent = sh(f"{PY} scripts/recent_trades.py", timeout=60)
    if "DAY BIAS" not in desk:
        with open(RUNLOG, "a") as fh:
            fh.write(f"{now:%Y-%m-%dT%H:%M:%SZ} SKIP desk read failed\n")
        return 0

    ctx = f"{desk}\n\n{features_block()}\n=== RECENT TRADES ===\n{recent}\n"
    if a.dry_run:
        print(ctx[:3000])
        return 0

    try:
        r = subprocess.run([CLAUDE, "-p", PROMPT + ctx, "--allowedTools", ""],
                           capture_output=True, text=True, timeout=200,
                           env={**os.environ, "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin"})
        raw = (r.stdout or "").strip()
        s, e = raw.find("{"), raw.rfind("}")
        v = json.loads(raw[s:e + 1])
    except Exception as ex:
        with open(RUNLOG, "a") as fh:
            fh.write(f"{now:%Y-%m-%dT%H:%M:%SZ} SKIP verdict failed: {ex}\n")
        return 0

    act = str(v.get("action", "NONE")).upper()
    urg = str(v.get("urgency", "info")).lower()
    what, why = str(v.get("what", ""))[:300], str(v.get("why", ""))[:300]
    with open(RUNLOG, "a") as fh:
        fh.write(f"{now:%Y-%m-%dT%H:%M:%SZ} [{phase}] {act} {urg} {what}\n")

    if act != "ALERT" or not what:
        return 0

    # ── dedup: only a CHANGED alert fires, else a minute cadence produces 60 identical pages ──
    fp = hashlib.sha256(f"{urg}|{what}".encode()).hexdigest()[:12]
    prev = None
    try:
        prev = json.load(open(STATE)).get("fp")
    except Exception:
        pass
    if fp == prev:
        return 0
    try:
        json.dump({"fp": fp, "ts": now.isoformat(timespec="seconds")}, open(STATE, "w"))
    except Exception:
        pass

    line = f"{now:%H:%M:%S}Z TAPE-WATCH/{phase} [{urg.upper()}] {what} — {why}"
    with open(ALERTS, "a") as fh:      # the session's Monitor tails this => in-chat interrupt
        fh.write(line + "\n")
    if urg in ("act", "critical"):
        try:
            subprocess.run([PY, "-c",
                            "import sys; from gazbot7.notify import notify; notify(sys.argv[1], critical=%s)"
                            % (urg == "critical"), f"OPEN-HOUR: {what} ({why})"],
                           cwd=GB, env={**os.environ, "PYTHONPATH": "src"}, timeout=30)
        except Exception:
            pass
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
