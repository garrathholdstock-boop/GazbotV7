#!/usr/bin/env python
"""GAZBOT V8 ROBO v1.02 — THE NO-PRESS SHADOWS (E104): what would the entries the robot is NOT allowed to take have done?

Declared in reports/recursive_loop/E104_change.txt BEFORE any number. Two own arms, never pooled with each other or with the live arm:
  v1.02-LOCKSHADOW  after the live robot's +$1,000 day lock (it stops calling Claude), the same 5-min call goes on and the would-be entry is LOGGED.
  v1.02-PM-shadow   13:30Z-19:55Z (the live window ends 13:30Z), same call, same filters, would-be entries LOGGED.
`--grade` scores every would-be entry on the 5s tape: IDEAL fill at the decision price, 4 lots all out at +37.5pt, no stop, ride to the 20:40Z flat, $6 fee.

⚠⚠⚠ READ-ONLY. It writes exactly three things, all its own: data/hybrid_shadow.jsonl, data/hybrid_shadow_state.json, reports/hybrid_shadow/*.
It reads the live robot's state and the rider state (never writes them), capture.db and the ledger (mode=ro). It has no broker call, no request file,
no switch file and no Telegram. tests/test_hybrid_shadow.py asserts that against the AST (the docstring deliberately names what it must never touch).
Reuses, imports not copies: hybrid_robot (bars, det_dir, preflight, session), leg_robot (detector, veto, rider gate), sim_week_recursive (brief, page, parser,
fill model), hybrid_nightly (path_stats = the counterfactual convention).
"""
from __future__ import annotations

import argparse
import collections
import copy
import datetime as dt
import json
import os
import re
import sys
import time

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import hybrid_nightly as N  # noqa: E402
import hybrid_robot as H  # noqa: E402
import leg_robot as L  # noqa: E402
import sim_week_recursive as S  # noqa: E402

UTC = dt.timezone.utc
VERSION = "1.02"
ROBOT = "GazBot V8 Robo shadow"
ARMS = {"LOCK": "v1.02-LOCKSHADOW", "PM": "v1.02-PM-shadow"}
AM_START_MIN, AM_END_MIN = S.WIN_START_MIN, S.WIN_END_MIN          # 02:00Z-13:30Z, the live window
PM_START_MIN, PM_END_MIN = S.WIN_END_MIN, 19 * 60 + 55             # last decision 19:50Z, sim book closed 19:55Z
HARD_FLAT_MIN = N.HARD_FLAT_MIN                                    # 20:40Z, the rider's own flat
TARGET_PT = N.CHAMPION_PT                                          # +37.5pt, all four lots
GRID = (TARGET_PT,)
FREE_S = 30                                                        # re-entry free at exit + 30s (the proxy.py convention)
STEP_S = S.STEP_MIN * 60
MAX_LATE_S = 150                                                   # the timer fires at :50; a tick later than this after its boundary is a different decision
PRESS_MAX_AGE_S = H.PRESS_MAX_AGE_S
FEED_STALE_S = H.FEED_STALE_S
POISON_RATE = H.POISON_RATE
MIN_N_PROMISING = N.MIN_N_PROMISING
MIN_N_FIT = 30
ENTER = ("ENTER_LONG", "ENTER_SHORT")
RECONCILE_SIM = H.RECONCILE_SIM

SWITCH = f"{GB}/data/hybrid_shadow.env"
STATE_FILE = f"{GB}/data/hybrid_shadow_state.json"
LOG_FILE = f"{GB}/data/hybrid_shadow.jsonl"
OUT_DIR = f"{GB}/reports/hybrid_shadow"
CAPTURE = f"{GB}/data/capture.db"


def new_arm() -> dict:
    return {"pos": None, "done": [], "calls": 0, "errors": 0, "streak": 0, "decisions": 0, "last_op": 0, "open_wb": None,
            "reconciled": [], "started": False, "start_op": None, "partial_from": None, "entries": []}


def load_state(key: str) -> dict:
    try:
        st = json.load(open(STATE_FILE), object_hook=H._dec)
    except Exception:
        st = {}
    if st.get("key") != key:        # a new session never inherits a simulated position
        st = {"key": key, "arms": {"LOCK": new_arm(), "PM": new_arm()}, "stale_n": 0, "alarmed": False}
    return st


def save_state(st: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1, default=H._enc)
    os.replace(tmp, STATE_FILE)


def log(rec: dict) -> None:
    rec = {"robot": ROBOT, "version": VERSION, **rec}
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def atomic_write(name: str, text: str) -> str:
    """The ONLY report write path, and it cannot write outside OUT_DIR. tmp + os.replace."""
    path = os.path.join(OUT_DIR, name)
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(OUT_DIR):
        raise ValueError(f"refusing to write outside {OUT_DIR}: {name}")
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


def tape_env():
    return N.Env(capture=CAPTURE, out=OUT_DIR)


def iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, UTC).isoformat()


def pm_text(op: int, text: str) -> str:
    """The E90/E96 rewrite for the afternoon arm: the page says the window ends 19:55Z and counts minutes-left from there."""
    m = dt.datetime.fromtimestamp(op, UTC)
    left = PM_END_MIN - (m.hour * 60 + m.minute)
    text = re.sub(r"⏱ -?\d+ minutes left in the window", f"⏱ {left} minutes left in the window", text)
    return text.replace("13:30Z", f"{PM_END_MIN // 60:02d}:{PM_END_MIN % 60:02d}Z")


def would_be_state(a: dict, op: int) -> dict | None:
    """The shadow's OWN would-be position: still riding until its +37.5pt print + FREE_S. Returns the open record or None. Mutates nothing."""
    wb = a.get("open_wb")
    if not wb:
        return None
    tape = N.load_tape(tape_env(), int(wb["op"]), op)
    res = N.path_stats(tape, wb["dir"], wb["entry"], wb["op"], op - 5, grid=GRID)
    c = res["cross"].get(str(TARGET_PT))
    if c is not None and c + FREE_S <= op:
        return None
    return wb


def arm_active(arm: str, st_live: dict | None, op: int):
    """(ok, status). LOCK exists only on a session the live robot locked, from the first boundary it skipped."""
    if arm == "PM":
        return True, None
    if not H.lock_enabled():
        return False, "LOCK_DISABLED"
    lk = (st_live or {}).get("lock")
    if not lk:
        return False, "NO_LOCK"
    lop = int(N.parse_ts(lk["decision_ts"]).timestamp())
    if op < lop:
        return False, "BEFORE_LOCK"
    return True, None


def step(now: dt.datetime, dry: bool = False, fake: str | None = None, clock=lambda: dt.datetime.now(UTC)) -> dict:
    now_ts = int(now.timestamp())
    key = H.session_key(now)
    d0 = N.d0_of(key)
    mod = (now_ts - d0) // 60
    out = {"at": now.isoformat(), "session": key, "window_min": mod, "status": None}
    st = load_state(key)

    def done(status, **kw):
        out["status"] = status
        out.update(kw)
        if not dry and status not in ("SWITCH_OFF", "WEEKEND", "OUTSIDE_WINDOW", "ARM_OFF"):
            st["heartbeat"] = now.isoformat()
            st["last_status"] = status
            save_state(st)
        return out

    if not L.read_switch(SWITCH, "hybrid_shadow"):
        return done("SWITCH_OFF")
    if now.weekday() >= 5:
        return done("WEEKEND")
    if AM_START_MIN <= mod < AM_END_MIN:
        arm = "LOCK"
    elif PM_START_MIN <= mod < PM_END_MIN:
        arm = "PM"
    else:
        return done("OUTSIDE_WINDOW")
    out["arm"] = ARMS[arm]
    if not L.read_switch(SWITCH, "shadow_lock" if arm == "LOCK" else "shadow_pm"):
        return done("ARM_OFF")
    fault = H.preflight()
    if fault:
        if not dry and not st["alarmed"]:
            st["alarmed"] = True
            log({"at": now.isoformat(), "event": "PREFLIGHT_FAILED", "arm": arm, "fault": fault})
        return done("PREFLIGHT_FAILED", fault=fault)

    op = now_ts - (now_ts - d0) % STEP_S
    if now_ts - op > MAX_LATE_S:
        return done("LATE_TICK", late_s=now_ts - op)
    a = st["arms"][arm]
    live = H.load_state(key) if arm == "LOCK" else None
    ok, why = arm_active(arm, live, op)
    if not ok:
        return done(why)
    if op <= a["last_op"]:
        return done("ALREADY_DECIDED", op=op)

    allbars = H.live_bars(key, now_ts)
    if not allbars:
        return done("NO_BARS")
    feed_age = now_ts - (allbars[-1][0] + 5)
    if feed_age > FEED_STALE_S:
        st["stale_n"] = st.get("stale_n", 0) + 1
        return done("FEED_STALE", feed_age_s=feed_age)
    st["stale_n"] = 0
    upto = [b for b in allbars if b[0] + 60 <= op]
    if len(upto) < 60:
        return done("NO_BARS", bars=len(upto))
    S._assert_causal(upto, op)
    px = upto[-1][3]

    if not a["started"]:
        a["started"] = True
        a["start_op"] = op
        if arm == "LOCK":                     # the live Claude would have carried his sim book and trade list through the lock
            a["pos"] = copy.deepcopy(live.get("pos"))
            a["done"] = copy.deepcopy(live.get("done") or [])
            a["start_op"] = int(N.parse_ts(live["lock"]["decision_ts"]).timestamp())
        elif op > d0 + PM_START_MIN * 60 + STEP_S:
            a["partial_from"] = iso(op)
        if not dry:
            log({"at": now.isoformat(), "event": "ARM_START", "arm": arm, "arm_label": ARMS[arm], "start_op": iso(a["start_op"]),
                 "first_op": iso(op), "partial_from": a["partial_from"], "inherited_pos": bool(a["pos"]), "lock": (live or {}).get("lock") if arm == "LOCK" else None})

    cnow = now if dry else clock()
    real_gate = L.rider_gate(cnow)
    own = would_be_state(a, op)
    if not own:
        a["open_wb"] = None
    reconciled = None
    if RECONCILE_SIM and a["pos"] and real_gate is None and not own:
        gone = a["pos"]
        reconciled = {"decision_ts": iso(op), "side": "BUY" if gone["dir"] > 0 else "SELL", "sim_entry": gone["entry"], "px": px, "real": "FLAT"}
        a["pos"] = None
        a["reconciled"].append(reconciled)
        if not dry:
            log({"at": now.isoformat(), "event": "SIM_RECONCILED", "arm": arm, **reconciled})

    pos = a["pos"]
    if pos:
        pos["peak"] = max(pos["peak"], pos["dir"] * (px - pos["entry"]))
        seg = [b[3] for b in upto if pos["last_ts"] < b[0] <= op]
        if seg:
            pos["peak_1m"] = max(pos["peak_1m"], max(pos["dir"] * (c - pos["entry"]) for c in seg))
        pos["last_ts"] = op
        pos["peak"] = max(pos["peak"], pos["peak_1m"])

    t_call = time.time()
    if fake is not None:
        d = {"action": fake, "reason": "FAKE (dry run)", "confidence": None}
    else:
        prompt = (S.brief_for(H.LINE) + "\n\n=== THE TAPE ===\n"
                  + S.context(upto, op, pos, "", a["done"], True, band=False, leg_list=False, mil=False, card=False))
        d = S.ask(pm_text(op, prompt) if arm == "PM" else prompt)
    latency = round(time.time() - t_call, 1)
    act = d.get("action", "WAIT")
    if fake is None:
        a["calls"] += 1
        if d.get("error"):
            a["errors"] += 1
            a["streak"] += 1
        else:
            a["streak"] = 0
    a["decisions"] += 1
    a["last_op"] = op
    rec = {"at": now.isoformat(), "event": "DECISION", "arm": arm, "arm_label": ARMS[arm], "decision_ts": iso(op), "px": px, "action": act,
           "conf": d.get("confidence"), "reason": (d.get("reason") or "")[:300], "error": d.get("error"), "sim_holding": bool(pos),
           "latency_s": latency, "real_gate": real_gate, "shadow_open": bool(own), "dry": dry}
    if reconciled:
        rec["sim_reconciled"] = True
    out["decision"] = rec

    if pos is None and act in ENTER:
        dirn = 1 if act == "ENTER_LONG" else -1
        a["pos"] = {"dir": dirn, "entry": px + dirn * S.HALF_SPREAD_PT, "peak": 0.0, "peak_1m": 0.0, "last_ts": op,
                    "opened": dt.datetime.fromtimestamp(op, UTC), "reason": (d.get("reason") or "")[:200]}
        side = "BUY" if dirn > 0 else "SELL"
        series = [b for b in L.series_for(L.session_day(now)) if b[0] + 60 <= now_ts - L.SETTLE_S]
        dd = H.det_dir(L.confirmed_turns(series), op - 60) if len(series) >= 200 else 0
        cut = L.veto_cutoff(op)
        rec["candidate"] = side
        rec["detector_dir"] = dd
        rec["veto_cutoff"] = iso(cut) if cut else None
        if dd != dirn:
            rec["entry_action"] = "NOT_WITH_LEG" if dd else "NO_DETECTOR_LEG"
        elif cut is not None and op < cut:
            rec["entry_action"] = "VETOED_BEFORE_05_PARIS"
        elif cnow.timestamp() - op > PRESS_MAX_AGE_S:
            rec["entry_action"] = "STALE_NOT_ENTERED"
        elif real_gate:
            rec["entry_action"] = "SKIPPED_" + real_gate
        elif own:
            rec["entry_action"] = "SKIPPED_SHADOW_HOLDING"
        else:
            rec["entry_action"] = "WOULD_PRESS_" + side
            rec["entry_px"] = px
            rec["entry_dir"] = dirn
            a["open_wb"] = {"op": op, "dir": dirn, "entry": px}
            a["entries"].append({"decision_ts": iso(op), "side": side, "px": px})
    elif a["pos"] and act == "EXIT":
        a["done"].append(S._close(a["pos"], px, op, "CLAUDE_EXIT"))
        a["pos"] = None

    if dry:
        return done("DRY_DECISION", entry_action=rec.get("entry_action"))
    log(rec)
    return done("WOULD_PRESS" if rec.get("entry_action", "").startswith("WOULD_PRESS") else "OK")


# ── grading ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def read_log(path: str, key: str) -> dict:
    out = {"decisions": {"LOCK": {}, "PM": {}}, "starts": {}, "bad_lines": 0}
    try:
        f = open(path)
    except FileNotFoundError:
        return out
    with f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                out["bad_lines"] += 1
                continue
            if r.get("event") == "DECISION" and not r.get("dry") and r.get("arm") in ARMS and str(r.get("decision_ts", "")).startswith(key):
                out["decisions"][r["arm"]][r["decision_ts"]] = r              # de-duplicated by (arm, decision_ts)
            elif r.get("event") == "ARM_START" and r.get("arm") in ARMS and str(r.get("first_op", "")).startswith(key):
                out["starts"].setdefault(r["arm"], r)
    return out


def live_lock(key: str) -> dict | None:
    """The live robot's DAY_LOCK record for the session, read from its own log (never written here)."""
    try:
        f = open(H.LOG_FILE)
    except FileNotFoundError:
        return None
    with f:
        for ln in f:
            if '"DAY_LOCK"' not in ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("event") == "DAY_LOCK" and str(r.get("at", "")).startswith(key):
                return r
    return None


def grade_entry(tape, r: dict, t_end: int) -> dict:
    side, px = int(r["entry_dir"]), float(r["entry_px"])
    op = int(N.parse_ts(r["decision_ts"]).timestamp())
    full = N.path_stats(tape, side, px, op, t_end, grid=GRID)
    c = full["cross"].get(str(TARGET_PT))
    hit = c is not None
    upto = N.path_stats(tape, side, px, op, c, grid=GRID) if hit else full
    exit_ts = c if hit else (tape.ts[tape.last_before(t_end)] if len(tape) else op)
    return {"decision_ts": r["decision_ts"], "side": "BUY" if side > 0 else "SELL", "px": px, "hit": hit,
            "net_usd": full["grid_usd"][str(TARGET_PT)], "exit_ts": iso(exit_ts) if exit_ts else None,
            "hold_min": round((exit_ts - op) / 60, 1) if exit_ts else None, "mae_pt": upto["mae_pt"], "mfe_pt": upto["mfe_pt"],
            "n_bars": full["n_bars"], "reason": (r.get("reason") or "")[:160]}


def expected_ops(arm: str, key: str, start_op: int | None) -> list:
    d0 = N.d0_of(key)
    lo, hi = (d0 + PM_START_MIN * 60, d0 + (PM_END_MIN - 5) * 60) if arm == "PM" else (start_op, d0 + (AM_END_MIN - 5) * 60)
    return list(range(lo, hi + 1, STEP_S)) if lo is not None else []


def grade_day(key: str) -> dict:
    d0 = N.d0_of(key)
    t_end = d0 + HARD_FLAT_MIN * 60
    lg = read_log(LOG_FILE, key)
    env = tape_env()
    tape = N.load_tape(env, d0 + AM_START_MIN * 60 - 60, t_end)
    lk = live_lock(key)
    rec = {"day": key, "schema": 1, "tape_bars": len(tape), "tape_through": iso(tape.ts[-1]) if len(tape) else None,
           "partial_tape": bool(len(tape) == 0 or tape.ts[-1] < t_end - 120), "live_lock": lk and {"touched_at": lk.get("touched_at"), "decision_ts": lk.get("decision_ts"), "peak": lk.get("peak")},
           "arms": {}}
    for arm, label in ARMS.items():
        decs = sorted(lg["decisions"][arm].values(), key=lambda r: r["decision_ts"])
        start = lg["starts"].get(arm)
        if arm == "LOCK" and lk:
            start_op = int(N.parse_ts(lk["decision_ts"]).timestamp())
        elif start:
            start_op = int(N.parse_ts(start["start_op"]).timestamp())
        else:
            start_op = None
        exp = expected_ops(arm, key, start_op) if (decs or (arm == "LOCK" and lk) or arm == "PM") else []
        made = {int(N.parse_ts(r["decision_ts"]).timestamp()) for r in decs}
        calls = len(decs)
        errs = sum(1 for r in decs if r.get("error"))
        rate = (errs / calls) if calls else 0.0
        entries = [grade_entry(tape, r, t_end) for r in decs if str(r.get("entry_action", "")).startswith("WOULD_PRESS")]
        skips = collections.Counter(r.get("entry_action") for r in decs if r.get("entry_action") and not r["entry_action"].startswith("WOULD_PRESS"))
        enters = sum(1 for r in decs if r.get("action") in ENTER)
        act = collections.Counter(r.get("action") for r in decs)
        status = "ACTIVE" if decs else ("MISSING_LOCK_ARM" if (arm == "LOCK" and lk) else "NO_DATA")
        rec["arms"][arm] = {
            "label": label, "status": status, "slots_expected": len(exp), "slots_made": len(made & set(exp)), "calls": calls, "errors": errs,
            "error_rate": round(rate, 4), "poisoned": rate > POISON_RATE, "claude_enters": enters, "actions": dict(act),
            "skipped": dict(skips), "entries": entries, "n": len(entries), "hits": sum(1 for e in entries if e["hit"]),
            "misses": sum(1 for e in entries if not e["hit"]), "net_usd": round(sum(e["net_usd"] for e in entries), 2),
            "partial_from": (lg["starts"].get(arm) or {}).get("partial_from"),
            "inherited_pos": (lg["starts"].get(arm) or {}).get("inherited_pos"),
        }
    return rec


def _tag(n: int) -> str:
    return "NO DATA" if n == 0 else "UNDERPOWERED (n<10)" if n < MIN_N_PROMISING else "n<30: NO FITTING, NO DECISION" if n < MIN_N_FIT else "n>=30"


def summarise(days: list) -> dict:
    """Per arm, never pooled across arms. Poisoned days are named and NOT scored."""
    out = {}
    for arm, label in ARMS.items():
        act = [(d["day"], d["arms"][arm]) for d in days if d["arms"].get(arm, {}).get("status") == "ACTIVE"]
        scored = [(k, x) for k, x in act if not x["poisoned"]]
        ents = [dict(e, day=k) for k, x in scored for e in x["entries"]]
        n = len(ents)
        miss = [e for e in ents if not e["hit"]]
        wins = [e for e in ents if e["hit"]]
        per_day = {k: round(x["net_usd"], 2) for k, x in scored}
        w_avg = (sum(e["net_usd"] for e in wins) / len(wins)) if wins else None
        l_avg = (-sum(e["net_usd"] for e in miss) / len(miss)) if miss else None
        out[arm] = {
            "label": label, "n_days_active": len(act), "n_days_scored": len(scored), "poisoned_days": [k for k, x in act if x["poisoned"]],
            "n_entries": n, "n_hits": len(wins), "n_misses": len(miss), "p_miss": round(len(miss) / n, 4) if n else None, "tag": _tag(n),
            "breakeven_p_miss": round(w_avg / (w_avg + l_avg), 4) if (w_avg and l_avg and l_avg > 0 and len(miss) >= 3) else None,
            "tail_net_usd": sorted((e["net_usd"], e["day"], e["decision_ts"][11:16]) for e in ents)[:5],
            "worst_mae_pt": max((e["mae_pt"] for e in ents), default=None),
            "usd_per_day_4lots": round(sum(per_day.values()) / len(per_day), 2) if per_day else None,
            "days_positive": sum(1 for v in per_day.values() if v > 0), "worst_day_usd": min(per_day.values()) if per_day else None,
            "per_day": per_day,
            "coverage": f"{sum(x['slots_made'] for _, x in act)}/{sum(x['slots_expected'] for _, x in act)} slots",
            "missing_lock_arm_days": [d["day"] for d in days if d["arms"].get(arm, {}).get("status") == "MISSING_LOCK_ARM"],
        }
        if arm == "PM":
            blocks = {"13:30-16:00": (13 * 60 + 30, 16 * 60), "16:00-18:00": (16 * 60, 18 * 60), "18:00-19:55": (18 * 60, 19 * 60 + 55)}
            sp = {}
            for nm, (lo, hi) in blocks.items():
                es = [e for e in ents if lo <= int(e["decision_ts"][11:13]) * 60 + int(e["decision_ts"][14:16]) < hi]
                sp[nm] = {"n": len(es), "misses": sum(1 for e in es if not e["hit"]), "net_usd": round(sum(e["net_usd"] for e in es), 2)}
            out[arm]["by_hour_block"] = sp
    return out


def render(summary: dict) -> str:
    L_ = ["E104 NO-PRESS SHADOWS - COUNTS FIRST, THEN DOLLARS. Arms are NEVER pooled. Ideal fills, 4 lots all out at +37.5pt, no stop, 20:40Z flat, $6 fee.",
          "Read-only forward collection: nothing here is a decision. No fitting / tuning / decision below 30 would-be entries per arm.", ""]
    for arm, s in summary.items():
        L_.append(f"== {s['label']} ==   [{s['tag']}]")
        L_.append(f"  entries {s['n_entries']} over {s['n_days_scored']} scored days (active {s['n_days_active']}, poisoned {s['poisoned_days'] or 'none'}); "
                  f"hits {s['n_hits']}, MISSES {s['n_misses']}, P(miss) {('%.1f%%' % (100 * s['p_miss'])) if s['p_miss'] is not None else 'n/a'}"
                  f"; break-even P(miss) {('%.1f%%' % (100 * s['breakeven_p_miss'])) if s['breakeven_p_miss'] else 'n/a (needs >=3 misses)'}")
        L_.append(f"  TAIL worst 5 entries (net $, day, time): {s['tail_net_usd'] or 'none'}; worst MAE {s['worst_mae_pt']}pt")
        L_.append(f"  $/day at 4 lots {s['usd_per_day_4lots']}; days positive {s['days_positive']}/{s['n_days_scored']}; worst day {s['worst_day_usd']}; coverage {s['coverage']}")
        if s.get("by_hour_block"):
            L_.append("  by hour block (entry time): " + "; ".join(f"{k} n={v['n']} miss={v['misses']} ${v['net_usd']}" for k, v in s["by_hour_block"].items()))
        if s["missing_lock_arm_days"]:
            L_.append(f"  !! the live robot LOCKED but this arm made no decision on: {s['missing_lock_arm_days']}")
        L_.append("")
    return "\n".join(L_)


def default_day(now: dt.datetime) -> str:
    d = now.date()
    return (d if now.hour * 60 + now.minute >= HARD_FLAT_MIN + 5 else d - dt.timedelta(days=1)).isoformat()


def grade(key: str) -> dict:
    day = grade_day(key)
    atomic_write(f"{key}.json", json.dumps(day, indent=1, default=str))
    days = []
    try:
        names = sorted(n for n in os.listdir(OUT_DIR) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", n))
    except FileNotFoundError:
        names = []
    for n in names:
        try:
            days.append(json.load(open(os.path.join(OUT_DIR, n))))
        except Exception:
            continue
    summ = summarise(days)
    atomic_write("SUMMARY.json", json.dumps(summ, indent=1, default=str))
    atomic_write("SUMMARY.txt", render(summ))
    return {"day": day, "summary": summ}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="one tick (default)")
    ap.add_argument("--grade", action="store_true", help="score the session's would-be entries on the 5s tape and refresh SUMMARY")
    ap.add_argument("--day", help="session date for --grade (default: the last finished session)")
    ap.add_argument("--dry", action="store_true", help="decide and print; write no log and no state")
    ap.add_argument("--at", help="ISO time (dry runs only)")
    ap.add_argument("--fake", help="dry runs only: replace Claude's answer (WAIT / ENTER_LONG / ENTER_SHORT / EXIT)")
    a = ap.parse_args()
    if (a.at or a.fake) and not a.dry:
        print("--at / --fake require --dry")
        return 2
    now = dt.datetime.fromisoformat(a.at) if a.at else dt.datetime.now(UTC)
    if a.grade:
        try:
            r = grade(a.day or default_day(now))
        except Exception as e:
            print("GRADE ERROR", repr(e))
            return 2
        print(render(r["summary"]))
        return 0
    try:
        r = step(now, dry=a.dry, fake=a.fake)
    except Exception as e:
        if not a.dry:
            log({"at": now.isoformat(), "event": "ERROR", "error": repr(e)})
        print("ERROR", repr(e))
        return 1
    print(json.dumps(r, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
