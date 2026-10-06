#!/usr/bin/env python3
"""THE SHADOW RUNNER — iteration 2's rule set, forward, on LIVE tape, placing NOTHING.

★★★ WHY IT EXISTS. `sim_week_recursive.py` scored **$620/day over 10 holdout days** it had
never trained on or reviewed, and it can only trade the PAST: it replays `capture.db`. So
the harness that produced the number cannot produce another one. This is the same harness
pointed at `now`.

⚠⚠⚠ READ-ONLY, AND THAT IS THE POINT. It writes exactly two files, both its own — a log
and a state file. It names no `gate_switches.env`, no `day_rider_buy.txt`, no
`day_rider_claim.txt`, opens no broker connection and places no order.
`tests/test_shadow_runner.py` asserts every one of those against the SOURCE, the way
`tape_reader` and `turn_watch` are asserted. Wiring this to the buttons is an ORDER PATH
and needs the operator's explicit say-so; his standing rule on the tape reader is that
Phase 2 "must be EARNED by the forward grading", and this is the grading.

★★ IT IMPORTS THE SIM RATHER THAN COPYING IT. The brief, the shape-first context, the
JSON parser, the leg detector and the fill model all come from `sim_week_recursive`. A
second copy would drift, and then a forward number would be a forward test of the copy
instead of a forward test of the thing that scored $620 —
[[the-labs-tape-is-not-productions-tape]] and [[day-rider-closed-latch-consumes-session]]
("call the real detector") in one. It reads the SAME `bars` table the sim read, so the
lab's tape and production's tape are the same tape by construction.

★ THE RULES ARE FROZEN at `rules.txt` as iteration 2 left them. A forward test whose
rules get rewritten nightly is not a forward test of iteration 2 — it is iteration 3 with
extra steps. The nightly review still runs, but its output is LOGGED AS COMMENTARY and
changes nothing. Unfreezing is a deliberate act.

⚠ A DEAD CLI IS NOT A FLAT DAY. On 2026-10-03 two days of iteration 1's training week
errored on 125/138 and 138/138 calls; the second booked exactly $0.00 and read as a quiet
session in every summary I looked at, and the nightly review then wrote rules from it. So
every day record here carries `calls`, `errors` and `error_rate`, and a day over
`POISON_RATE` is stamped `poisoned: true` and must not be scored.

⚠ NEVER HOLD OVERNIGHT, mirrored from the desk's own rule: the simulated book is closed at
the window end, and a position may never survive into the next session key.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
sys.path.insert(0, f"{GB}/scripts")

import sim_week_recursive as S                      # noqa: E402  the real harness, not a copy

STATE = f"{GB}/data/shadow_runner_state.json"
LOG = f"{GB}/data/shadow_runner.jsonl"
DAYLOG = f"{GB}/reports/shadow_runner"
RULES = f"{GB}/reports/recursive_loop/rules.txt"
POISON_RATE = 0.10
ALARM_STREAK = 3                 # three identical failures is a fault, not a blip


def _page(msg: str) -> None:
    """Non-critical, holds past quiet hours. A shadow experiment never buzzes him at 3am."""
    try:
        import time
        from gazbot7.notify import notify, in_quiet_hours
        held = False
        while in_quiet_hours(dt.datetime.now(dt.UTC)):
            held = True
            time.sleep(300)
        notify(msg + ("\n(held past quiet hours)" if held else ""),
               critical=False, mark=False, weekend_ok=True)
    except Exception as e:                      # an alarm that crashes the runner is worse
        log(f"could not page: {type(e).__name__}: {e}")


def preflight() -> str | None:
    """Is the thing that makes every decision actually there? Returns a fault or None.

    ⚠ This exists because the answer was NO for a whole trading day and every other
    signal read healthy: systemd exited 0, the state file advanced, the day record parsed.
    [[an-instrument-that-reports-healthy-about-something-it-does-not-check]].
    """
    if not os.access(S.CLAUDE, os.X_OK):
        return f"the claude binary is not executable at {S.CLAUDE}"
    if not os.path.exists(RULES):
        return f"the frozen rule set is missing at {RULES}"
    return None


def log(m: str) -> None:
    print(f"{dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%M:%SZ} shadow: {m}", flush=True)


# ── the session, anchored at 22:00Z exactly as the sim anchors it ────────────────────────

def session_key(now: dt.datetime) -> str:
    """The trading date this instant belongs to. 22:00Z opens TOMORROW's session."""
    d = now.date() + (dt.timedelta(days=1) if now.hour >= 22 else dt.timedelta())
    return d.isoformat()


def window_min(now: dt.datetime, key: str) -> int:
    """Minutes from the session date's 00:00Z. Negative before midnight."""
    d0 = dt.datetime.fromisoformat(key + "T00:00:00+00:00")
    return int((now - d0).total_seconds() // 60)


def live_bars(key: str, now_epoch: int):
    """Minute bars from 22:00Z the evening before up to NOW — never past it.

    Same table, same timeframe and the same 22:00Z anchor as `S.load_day`. The only
    difference is the right edge, which is the whole point.
    """
    d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
    sess_open = d0 - 2 * 3600
    con = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
    rows = con.execute(
        "SELECT bar_ts, high, low, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
        "AND bar_ts >= ? AND bar_ts <= ? ORDER BY bar_ts",
        (sess_open, now_epoch)).fetchall()
    con.close()
    agg: dict[int, list] = {}
    for ts, h, l, c in rows:
        m = (ts // 60) * 60
        a = agg.setdefault(m, [h, l, c])
        a[0] = max(a[0], h)
        a[1] = min(a[1], l)
        a[2] = c
    return [(m, float(v[0]), float(v[1]), float(v[2])) for m, v in sorted(agg.items())]


# ── state ───────────────────────────────────────────────────────────────────────────────

def load_state(key: str) -> dict:
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    if st.get("key") != key:
        # a new session NEVER inherits a position — the overnight rule, and the
        # day_rider `closed` latch lesson: a stale session key eats the next day
        st = {"key": key, "pos": None, "done": [], "calls": 0, "errors": 0,
              "closed_out": False}
    return st


def save_state(st: dict) -> None:
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)                          # atomic; a half-written state is a lie


def append(rec: dict) -> None:
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")


# ── one tick ────────────────────────────────────────────────────────────────────────────

def tick(now: dt.datetime | None = None, dry: bool = False) -> dict:
    now = now or dt.datetime.now(dt.UTC)
    key = session_key(now)
    mod = window_min(now, key)
    st = load_state(key)
    out = {"ts": now.isoformat(), "session": key, "window_min": mod}

    fault = preflight()
    if fault:
        out["skip"] = f"PREFLIGHT FAILED: {fault}"
        if not st.get("alarmed"):
            st["alarmed"] = True
            _page(f"⚠ SHADOW RUNNER CANNOT RUN — {fault}\nsession {key}. "
                  "No orders are involved; the day will be unscoreable.")
            if not dry:
                save_state(st)
        return out
    if now.weekday() >= 5 and not (now.weekday() == 6 and now.hour >= 22):
        out["skip"] = "weekend — the venue is halted"
        return out
    if mod < S.WIN_START_MIN:
        out["skip"] = f"before the window ({S.WIN_START_MIN // 60:02d}:00Z)"
        return out

    bars = live_bars(key, int(now.timestamp()))
    if len(bars) < 30:
        out["skip"] = f"only {len(bars)} minute bars — tape too thin to read"
        return out
    px = bars[-1][3]
    age_s = int(now.timestamp()) - bars[-1][0]
    if age_s > 600:
        # a shut venue and a dead feed produce the same silence — the tape_reader rule
        out["skip"] = f"tape is {age_s}s stale — declining rather than reading a dead feed"
        return out

    # ── past the window: close the simulated book and write the day ──────────────────
    if mod >= S.WIN_END_MIN:
        if st["pos"] and not st["closed_out"]:
            st["done"].append(S._close(st["pos"], px, int(now.timestamp()), "WINDOW_END"))
            st["pos"] = None
        if not st["closed_out"]:
            st["closed_out"] = True
            rec = write_day(st, bars, key)
            out["day_written"] = rec["net_usd"]
            out["poisoned"] = rec["poisoned"]
            if not dry:
                save_state(st)
        else:
            out["skip"] = "window closed, day already written"
        return out

    # ── a decision ───────────────────────────────────────────────────────────────────
    rules = open(RULES).read() if os.path.exists(RULES) else ""
    prompt = S.BRIEF + "\n\n" + S.context(
        bars, int(now.timestamp()), st["pos"], rules, done=st["done"], self_aware=True)
    d = S.ask(prompt)
    st["calls"] += 1
    if d.get("error"):
        st["errors"] += 1
        st["streak"] = st.get("streak", 0) + 1
    else:
        st["streak"] = 0

    # ⚠⚠⚠ AN INSTRUMENT THAT FAILS IDENTICALLY ALL DAY AND TELLS NOBODY. On 2026-10-05 this
    # made 138 of 138 calls fail with the SAME FileNotFoundError, exited 0 every time,
    # wrote a well-formed day record, and the operator found out only because he asked.
    # The poison flag correctly labelled the day — but labelling after the fact is not the
    # same as being told while the day can still be saved. A repeated identical failure is
    # the one thing that must escalate, so this pages ONCE per streak, never per tick
    # ([[a-correct-decision-repeated-every-tick-is-an-alarm-outage]] — dedupe on the
    # SITUATION, not the message).
    if st["streak"] == ALARM_STREAK and not st.get("alarmed"):
        st["alarmed"] = True
        _page(f"⚠ SHADOW RUNNER IS FAILING EVERY CALL — {st['streak']} in a row\n"
              f"{d.get('error')}\n"
              f"session {key}, {st['errors']}/{st['calls']} calls errored so far.\n"
              "The day will be stamped POISONED and must not be scored. Nothing is at "
              "risk — this runner places no orders.")
    act = (d.get("action") or "WAIT").upper()
    out.update({"px": px, "action": act, "reason": (d.get("reason") or "")[:300],
                "error": d.get("error"), "calls": st["calls"], "errors": st["errors"]})

    if not dry:
        st = apply_action(st, act, px, int(now.timestamp()), out)
        out["position"] = None if not st["pos"] else {
            "side": st["pos"]["side"], "entry": st["pos"]["entry"]}
        out["net_usd_today"] = round(sum(t["pnl_usd"] for t in st["done"]), 2)
        out["trades_today"] = len(st["done"])
        save_state(st)
        append(out)
    return out


def apply_action(st: dict, act: str, px: float, epoch: int, out: dict) -> dict:
    """The SIMULATED book. Charges half-spread each way and $1.50/lot round turn.

    ⚠ It never asks the broker anything and never writes a request. The real fill model is
    worse than this in one known way the sim cannot reproduce: the IBKR paper engine
    fabricates 0.1% adverse on every lot beyond the first, which is why the live number
    will come in under this one even on identical decisions.
    """
    if act in ("ENTER_LONG", "ENTER_SHORT") and not st["pos"]:
        side = 1 if act == "ENTER_LONG" else -1
        st["pos"] = {"side": side, "entry": px + side * S.HALF_SPREAD_PT,
                     "opened": epoch}
    elif act in ("EXIT", "CLAIM", "CUT") and st["pos"]:
        st["done"].append(S._close(st["pos"], px, epoch, act))
        st["pos"] = None
    return st


def write_day(st: dict, bars, key: str) -> dict:
    os.makedirs(DAYLOG, exist_ok=True)
    calls, errs = st["calls"], st["errors"]
    rate = (errs / calls) if calls else 1.0
    rec = {"day": key, "arm": "shadow_live_iter2_rules",
           "trades": st["done"], "net_usd": round(sum(t["pnl_usd"] for t in st["done"]), 2),
           "calls": calls, "errors": errs, "error_rate": round(rate, 4),
           "poisoned": rate > POISON_RATE,
           "rules_sha": _sha(RULES)}
    json.dump(rec, open(f"{DAYLOG}/{key}.json", "w"), indent=1)
    log(f"day {key} written: ${rec['net_usd']:+,.2f} over {len(st['done'])} trades, "
        f"{errs}/{calls} calls errored" + ("  ⚠ POISONED" if rec["poisoned"] else ""))
    return rec


def _sha(p: str) -> str:
    import hashlib
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]
    except Exception:
        return "missing"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="one tick (what the timer calls)")
    ap.add_argument("--dry", action="store_true", help="decide and print, persist nothing")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.status:
        st = load_state(session_key(dt.datetime.now(dt.UTC)))
        print(json.dumps(st, indent=1))
        for f in sorted(os.listdir(DAYLOG)) if os.path.isdir(DAYLOG) else []:
            r = json.load(open(f"{DAYLOG}/{f}"))
            print(f"  {r['day']}  ${r['net_usd']:>+9,.2f}  {len(r['trades']):>2} tr  "
                  f"{r['errors']}/{r['calls']} err" + ("  POISONED" if r["poisoned"] else ""))
        return 0

    out = tick(dry=a.dry)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
