"""E112 - the LIVE desk (hybrid_robot v1.02+LOCK) replayed on unseen days, call for call (spec reports/recursive_loop/E112_change.txt).

Claude is asked with the live prompt every 5 min; the press is gated exactly as live (with the frozen detector's leg, 05:00 Paris veto,
rider flat); the rider (4 lots all out at +37.5pt, no stop, 20:40Z flat), RECONCILE_SIM and the +$1,000 LOCK are simulated inline because
their state feeds back into what Claude is shown. One JSON per (arm, day) under reports/e112/, resumable; a day with > 10% errored calls
is re-run. Read-only on the desk.

    nice -n 10 .venv/bin/python reports/recursive_loop/E112_code/replay.py --arm v102 --days 2025-10-01,...
    nice -n 10 .venv/bin/python reports/recursive_loop/E112_code/replay.py --arm v102 --arm v102R=path/to/R.txt --days ...
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import sys
import time

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import duckdb  # noqa: E402
import mil_labels as ML  # noqa: E402
import sim_week_recursive as S  # noqa: E402
import leg_robot as L  # noqa: E402
import hybrid_robot as H  # noqa: E402

UTC = dt.timezone.utc
OUT = f"{GB}/reports/e112"
BACKFILL = f"{GB}/data/tape/bars/MNQ/backfill_1min.parquet"
SHA = "af0ace53e6dc9faa"
TARGET, THRU, HALF = 37.5, 0.25, S.HALF_SPREAD_PT
LOTS, PV, FEE = 4, 2.0, 1.50
LOCK = H.LOCK_USD
FLAT_MIN = 20 * 60 + 40
POISON = 0.10
# OVERNIGHT GUARDS (E112 A0): the replay shares the operator's subscription with the LIVE robot.
#  - no replay call inside the live window: a day is not STARTED after E112_STOP_AT (default 01:45Z) and a running day
#    ABORTS (unsaved, re-run later) at 01:58Z, so nothing competes with the live robot's 02:00Z..13:30Z calls;
#  - STREAK_ABORT consecutive errored calls (quota / rate limit) abort the whole run, so a dry allowance is not burned on retries.
STREAK_ABORT = 15
LIVE_START = (21, 0)    # A4: a running day aborts at 21:00Z so the 5-hour usage window is clear before the live desk's 02:00Z calls
_abort = {"why": None}
ALLOW_LIVE = {"on": os.environ.get("E118_ALLOW_LIVE_HOURS") == "1"}   # operator 2026-10-26: run during live hours, guarded by _live_robot_erroring + budget


class Abort(Exception):
    pass


def _avail_mb() -> int:
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemAvailable:"):
            return int(ln.split()[1]) // 1024
    return 0


LIVE_LOG = f"{GB}/data/hybrid_robot.jsonl"
_budget = {"max": int(os.environ.get("E112_MAX_CALLS", "0")) or None, "used": 0}


def _live_robot_erroring() -> str | None:
    """E118 A1: replays may run inside live hours only while the LIVE robot's own calls succeed. Returns a reason if its latest
    decision (within 15 min) errored - the usage window is the live desk's first."""
    try:
        with open(LIVE_LOG, "rb") as f:
            f.seek(0, 2); f.seek(max(0, f.tell() - 20000))
            tail = f.read().decode(errors="ignore").splitlines()
        for ln in reversed(tail):
            if '"event": "DECISION"' in ln:
                r = json.loads(ln)
                age = dt.datetime.now(UTC).timestamp() - dt.datetime.fromisoformat(r["at"]).timestamp()
                return f"live robot's last decision errored ({r.get('error')})" if r.get("error") and age < 900 else None
    except Exception:
        return None
    return None


def _live_window(now=None) -> bool:
    n = now or dt.datetime.now(UTC)
    return (n.hour, n.minute) >= LIVE_START or n.hour * 60 + n.minute < 13 * 60 + 35
MODEL_NOTE = "CLI default (measured 2026-10-25: claude-sonnet-5-5), no ANTHROPIC_MODEL override - as the live service"

_cache: dict[str, list] = {}

# E118 (2026-10-26): arms that run the LIVE v1.03 setup (MIL cap 2) with a target policy. Any other label runs as before (v1.02 rules).
#   target   = the all-out target in points;  decay = (minutes, lower target): the target drops to `lower` once `minutes` have passed since the fill.
ARM_CFG = {
    "v103":    {"milcap": 2, "target": 37.5, "decay": None},
    "v103T30": {"milcap": 2, "target": 30.0, "decay": None},
    "v103D":   {"milcap": 2, "target": 37.5, "decay": (30, 25.0)},
    "v103B":   {"milcap": 2, "target": 37.5, "decay": None, "brief": "desk"},      # E119: the Desk Brief instead of BRIEF_V2
}
from gazbot7 import desk_brief as DB  # noqa: E402
WINDOW_NOTE = ("This window is when you may ENTER. It does NOT close the real position: that closes only at +37.5 points or at 20:40Z.")


def day_bars(day: str) -> list:
    """1-min (bar_ts, high, low, close) from 22:00Z the evening before to 21:00Z, from the MNQ backfill."""
    if day not in _cache:
        d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
        rows = duckdb.connect().execute(
            f"SELECT bar_ts, high, low, close FROM read_parquet('{BACKFILL}') WHERE timeframe='1min' "
            "AND bar_ts >= ? AND bar_ts < ? ORDER BY bar_ts", [d0 - 7200, d0 + 21 * 3600]).fetchall()
        _cache[day] = [(int(t), float(h), float(l), float(c)) for t, h, l, c in rows]
    return _cache[day]


ML.minute_bars = day_bars          # leg_robot.series_for -> the detector reads the same 1-min tape
MECH = DB.mechanics_from_robot(H) | {"exit_live": False}     # the replayed desk: Claude's EXIT never closes the rider (as live, hybrid_exit_live=off)


def ride(bars: list, op: int, dirn: int, fill: float, d0: int, target: float = TARGET, decay: tuple | None = None) -> dict:
    """the rider after a press at decision time op: all four lots out at the target from the fill, else the 20:40Z flat.
    decay=(m, lower): the target becomes `lower` for bars that open >= m minutes after the decision (E118)."""
    flat_t = d0 + FLAT_MIN * 60
    path = [b for b in bars if op <= b[0] < flat_t]
    mae, marks = 0.0, []
    for t, h, l, c in path:
        adv = (fill - l) if dirn > 0 else (h - fill)
        mae = max(mae, adv)
        T = decay[1] if decay and t >= op + decay[0] * 60 else target
        tgt = fill + dirn * (T + THRU)
        if (h >= tgt) if dirn > 0 else (l <= tgt):
            return {"exit_ts": t + 60, "exit_px": fill + dirn * T, "why": f"TARGET_{T:g}", "mae": round(mae, 2),
                    "pnl": round(LOTS * PV * T - LOTS * FEE, 2), "marks": marks}
        marks.append((t + 60, round(LOTS * PV * dirn * (c - fill), 2)))
    last = path[-1] if path else (op, fill, fill, fill)
    pts = dirn * (last[3] - fill)
    return {"exit_ts": last[0] + 60, "exit_px": last[3], "why": "FLAT_2040Z", "mae": round(mae, 2),
            "pnl": round(LOTS * PV * pts - LOTS * FEE, 2), "marks": marks}


def run_day(arm: str, rules: str, day: str) -> dict:
    path = f"{OUT}/{arm}_{day}.json"
    if os.path.exists(path):
        prev = json.load(open(path))
        c = prev.get("calls") or []
        if prev.get("skipped") or (c and sum(1 for x in c if x.get("error")) / len(c) <= POISON):
            return prev
        print(f"  {arm} {day}: re-running ({sum(1 for x in c if x.get('error'))}/{len(c)} errored)", flush=True)
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    page_bars, _ = S.load_day(day)
    bars = day_bars(day)
    cfg = ARM_CFG.get(arm)
    rec = {"arm": arm, "day": day, "rules_sha": hashlib.sha256(rules.encode()).hexdigest()[:12], "model": MODEL_NOTE, "cfg": cfg,
           "brief_sha": hashlib.sha256(S.brief_for("v2").encode()).hexdigest()[:16], "calls": [], "presses": [], "sim_done": []}
    if len(page_bars) < 600:
        rec["skipped"] = f"only {len(page_bars)} page bars (holiday/short session)"
        json.dump(rec, open(path, "w"), indent=1, default=str)
        return rec
    series_all = L.series_for(dt.date.fromisoformat(day))
    pos, done, rider, realised, lock, streak = None, [], None, 0.0, None, 0
    last_op = d0 + S.WIN_START_MIN * 60 - S.STEP_MIN * 60
    for m in range(S.WIN_START_MIN, S.WIN_END_MIN, S.STEP_MIN):
        op = d0 + m * 60
        # rider bookkeeping up to op: a finished position books its P&L; equity is marked at every 1-min close
        if rider and rider["exit_ts"] <= op:
            realised += rider["pnl"]; rider["closed"] = True; rider = None
        if lock is None:
            open_marks = [v for t, v in (rider["marks"] if rider else []) if last_op < t <= op]
            touch = realised >= LOCK or any(realised + v >= LOCK for v in open_marks)
            if touch:
                lock = dt.datetime.fromtimestamp(op, UTC).isoformat()
        last_op = op
        if lock:
            break                                   # live: DAY_LOCKED -> no Claude call for the rest of the session
        upto = [b for b in page_bars if b[0] + 60 <= op]
        if len(upto) < 60:
            continue
        S._assert_causal(upto, op)
        px = upto[-1][3]
        if pos and rider is None:                   # RECONCILE_SIM: the rider is flat, the sim position is dropped unbooked
            rec.setdefault("reconciled", []).append({"ts": dt.datetime.fromtimestamp(op, UTC).isoformat(), "dir": pos["dir"]})
            pos = None
        if pos:
            pos["peak"] = max(pos["peak"], pos["dir"] * (px - pos["entry"]))
            seg = [b[3] for b in upto if pos["last_ts"] < b[0] <= op]
            if seg:
                pos["peak_1m"] = max(pos["peak_1m"], max(pos["dir"] * (c - pos["entry"]) for c in seg))
            pos["last_ts"] = op
            pos["peak"] = max(pos["peak"], pos["peak_1m"])
        if _abort["why"]:
            raise Abort(_abort["why"])
        if _live_window() and not ALLOW_LIVE["on"]:
            raise Abort("live window reached - day abandoned unsaved, re-run after 13:35Z")
        if ALLOW_LIVE["on"] and (why := _live_robot_erroring()):
            _abort["why"] = why
            raise Abort(why)
        if _budget["max"] and _budget["used"] >= _budget["max"]:
            _abort["why"] = f"call budget {_budget['max']} used"
            raise Abort(_abort["why"])
        _budget["used"] += 1
        if cfg and cfg.get("brief") == "desk":
            mil_now = H.mil_pivot(L.confirmed_turns([b for b in series_all if b[0] + 60 <= op]), op - 60)
            st_ = {"now_utc": dt.datetime.fromtimestamp(op, UTC).strftime("%H:%MZ"), "mins_to_us_open": max(0, (d0 + 13 * 3600 + 1800 - op) // 60),
                   "mil_dir": mil_now[1] if mil_now else None, "mil_cap": cfg["milcap"],
                   "mil_claims": sum(1 for q in rec["presses"] if mil_now and q.get("mil_pivot") == mil_now[0] and q["why"].startswith("TARGET") and q["exit_ts"] <= op),
                   "day_usd": realised, "lock_usd": LOCK, "holding": rider is not None}
            brief_txt, stamp = DB.build(MECH, st_)
            rec["brief"] = stamp
            d = S.ask(brief_txt + "\n\n=== THE TAPE ===\n"
                      + S.context(upto, op, pos, rules, done, True, band=False, leg_list=False, mil=False, card=False, window_note=WINDOW_NOTE))
        else:
            d = S.ask(S.brief_for("v2") + "\n\n=== THE TAPE ===\n"
                      + S.context(upto, op, pos, rules, done, True, band=False, leg_list=False, mil=False, card=False))
        act = d.get("action", "WAIT")
        streak = streak + 1 if d.get("error") else 0
        if streak >= STREAK_ABORT:
            _abort["why"] = f"{streak} consecutive errored calls (last: {str(d.get('error'))[:120]}) - quota or rate limit?"
            raise Abort(_abort["why"])
        call = {"ts": dt.datetime.fromtimestamp(op, UTC).isoformat(), "px": px, "action": act, "conf": d.get("confidence"),
                "reason": (d.get("reason") or "")[:400], "error": d.get("error"), "sim_holding": bool(pos), "rider_holding": bool(rider)}
        if pos is None and act in ("ENTER_LONG", "ENTER_SHORT"):
            dirn = 1 if act == "ENTER_LONG" else -1
            pos = {"dir": dirn, "entry": px + dirn * HALF, "peak": 0.0, "peak_1m": 0.0, "last_ts": op,
                   "opened": dt.datetime.fromtimestamp(op, UTC), "reason": (d.get("reason") or "")[:200]}
            series = [b for b in series_all if b[0] + 60 <= op]
            turns = L.confirmed_turns(series) if len(series) >= 200 else []
            dd = H.det_dir(turns, op - 60)
            cut = L.veto_cutoff(op)
            mil = H.mil_pivot(turns, op - 60) if cfg and dd == dirn else None
            claims = sum(1 for q in rec["presses"] if mil and q.get("mil_pivot") == mil[0] and q["side"] == ("BUY" if dirn > 0 else "SELL")
                         and q["why"].startswith("TARGET") and q["exit_ts"] <= op) if mil else 0
            if dd != dirn:
                call["entry_action"] = "NOT_WITH_LEG" if dd else "NO_DETECTOR_LEG"
            elif cut is not None and op < cut:
                call["entry_action"] = "VETOED_BEFORE_05_PARIS"
            elif cfg and claims >= cfg["milcap"]:                                  # v1.03: 2 claims on this MIL -> wait for the next MIL
                call["entry_action"] = f"MIL_CAP_{cfg['milcap']}_CLAIMS"
            elif rider is not None:
                call["entry_action"] = "SKIPPED_HOLDING"
            else:
                fill = px + dirn * HALF
                r = ride(bars, op, dirn, fill, d0, **({"target": cfg["target"], "decay": cfg["decay"]} if cfg else {}))
                rider = {"dir": dirn, "fill": fill, "op": op, **r}
                rec["presses"].append({"decision_ts": call["ts"], "side": "BUY" if dirn > 0 else "SELL", "decision_px": px,
                                       "fill": round(fill, 2), "exit_ts": r["exit_ts"],
                                       "exit_at": dt.datetime.fromtimestamp(r["exit_ts"], UTC).isoformat(),
                                       "exit_px": round(r["exit_px"], 2), "why": r["why"], "mae_pt": r["mae"], "pnl_usd": r["pnl"],
                                       "held_min": round((r["exit_ts"] - op) / 60, 1), "reason": call["reason"],
                                       "mil_pivot": mil[0] if mil else None})
                call["entry_action"] = "PRESS_" + ("BUY" if dirn > 0 else "SELL")
        elif pos is not None and act == "EXIT":
            done.append(S._close(pos, px, op, "CLAUDE_EXIT"))
            pos = None
        rec["calls"].append(call)
    if rider is not None:
        realised += rider["pnl"]
    rec["lock"] = lock
    rec["sim_done"] = done
    rec["net_usd"] = round(sum(p["pnl_usd"] for p in rec["presses"]), 2)
    rec["errors"] = sum(1 for c in rec["calls"] if c.get("error"))
    os.makedirs(OUT, exist_ok=True)
    tmp = path + ".tmp"
    json.dump(rec, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, path)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", required=True, help="label or label=rules_path (repeat)")
    ap.add_argument("--days", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--stop-at", default=os.environ.get("E112_STOP_AT", "20:45"), help="UTC HH:MM after which no new day is started")
    a = ap.parse_args()
    assert a.workers <= 3, "memory: the box is 7.5GB and the live desk runs on it"
    assert L.detector_sha() == SHA, "frozen detector changed"
    assert not os.environ.get("ANTHROPIC_MODEL"), "the live service sets no model override; neither does this"
    arms = {}
    for spec in a.arm:
        lab, _, p = spec.partition("=")
        arms[lab] = open(p).read().strip() if p else ""
    days = sorted(a.days.split(","))
    os.makedirs(OUT, exist_ok=True)
    jobs = [(lab, d) for d in days for lab in arms]          # day-interleaved so a partial run is always paired
    t0 = time.time()
    print(f"E112 replay: arms {[(k, hashlib.sha256(v.encode()).hexdigest()[:12]) for k, v in arms.items()]}, {len(days)} days, "
          f"billing {'api' if S._api_env().get('ANTHROPIC_API_KEY') else 'subscription'}", flush=True)
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        sh, sm = map(int, a.stop_at.split(":"))

        def guarded(lab, d):
            n = dt.datetime.now(UTC)
            if _abort["why"]:
                raise Abort("run aborted: " + _abort["why"])
            if not ALLOW_LIVE["on"] and ((n.hour, n.minute) >= (sh, sm) or n.hour * 60 + n.minute < 13 * 60 + 35):   # A4: only 13:35Z..stop-at
                raise Abort(f"not started: past {a.stop_at}Z, inside the live desk's hours")
            while _avail_mb() < 1500:
                time.sleep(30)
            return run_day(lab, arms[lab], d)
        futs = {ex.submit(guarded, lab, d): (lab, d) for lab, d in jobs}
        for f in cf.as_completed(futs):
            lab, d = futs[f]
            try:
                r = f.result()
                print(f"  {lab} {d}: " + (r["skipped"] if r.get("skipped") else
                      f"calls {len(r['calls'])} err {r['errors']} presses {len(r['presses'])} net ${r['net_usd']:+,.0f} lock {bool(r['lock'])}")
                      + f"  ({(time.time()-t0)/60:.0f} min)", flush=True)
            except Exception as e:
                print(f"  {lab} {d}: FAILED {type(e).__name__}: {e}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
