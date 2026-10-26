#!/usr/bin/env python3
"""THE HYBRID'S NIGHTLY REVIEW (E92): is GazBot V8 Robo v1.02 WORKING, what did it do, and what is worth tuning on Saturday.

Operator, 2026-10-14: *"nightly review, analysis and tuning of both detector and Claude only if need be. Perhaps the analysis is
collected for weekend tuning? Only critical things that are clearly broken or not working are fixed nightly?"*  This is that policy:

  1. HEALTH     — FAULT / WARN / INFO lines. Only a FAULT pages (critical); everything else is carried by the 06:05 Paris
                  `overnight_allclear`, because a process cannot report its own absence and 20:50Z is inside quiet hours.
  2. ANALYSIS   — per-day JSON + text under reports/hybrid_nightly/: call/latency stats, the entry funnel, every Claude ENTER
                  candidate with a counterfactual, every real press with its MFE/MAE, per-lot rung lag and a target-grid replay,
                  the detector's legs. Collected, never acted on.
  3. WEEKLY PACK — week_<ISO>.json/.txt: pooled per ARM (v1.02 and v1.02-EXT are NEVER pooled) plus a RANKED SHORTLIST for
                  Saturday. A shortlist, not a verdict: every item says its n, and nothing here changes a rule.

⚠⚠⚠ READ-ONLY AND NO AUTHORITY. It reads the robot's log/state/day records, capture.db (bars), the trade ledger and the rider's
state — all opened read-only — and writes ONLY inside reports/hybrid_nightly/ (tmp + os.replace). It imports no broker library,
names no request or switch file, restarts nothing, repairs nothing, and never edits the brief or the detector. Both stay FROZEN;
retuning is Saturday work, one rule per iteration, gated by bible.gate (L1/L2/L4). tests/test_hybrid_nightly.py asserts that
against the AST.

⚠ THE LEDGER IS THE TRUTH FOR WHAT WAS TRADED. hybrid_robot's PRESS_RESULT reads the rider state BEFORE the rider saves it (the 16:25
press logged the previous entry's price and "already traded"), so it is never used here. Presses are attributed to ledger rows by
matching the request timestamp to `opened_at` in [req, req+180s].
⚠ Counterfactuals use the 5s tape at +-5s resolution and IDEAL fills (the paper engine fabricates a 0.1% adverse fill on lots 2-4,
which flatters the real book). They compare arms with each other; they are not a forecast of P&L.

  PYTHONPATH=src .venv/bin/python scripts/hybrid_nightly.py [--day YYYY-MM-DD] [--quiet] [--json] [--week-only]
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import os
import sqlite3
import statistics
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import hybrid_robot as H  # noqa: E402  constants, det_dir, the arm's own definitions — imported, not copied
import leg_robot as L  # noqa: E402
import sim_week_recursive as S  # noqa: E402

UTC = dt.timezone.utc
SCHEMA = 1
OUT_DIR = f"{GB}/reports/hybrid_nightly"
USD_PT = 2.0                      # MNQ
FEE_LOT = 1.5                     # per lot, round trip
LOTS = H.QTY
CHAMPION_PT = 37.5                # the shipped ladder: all four lots out at +37.5pt
GRID_PT = (12.5, 25.0, 37.5, 50.0, 62.5, 75.0, 100.0)
HARD_FLAT_MIN = 20 * 60 + 40
REVIEW_FLAT_MIN = 20 * 60 + 45    # a "not flat" fault is only meaningful once the 20:40Z flat has had 5 minutes
#: The fast ladder (E91) went live at the mtime of day_rider.py. Rung lag measured before it describes the OLD 60s ladder.
FAST_LADDER_LIVE_FROM = dt.datetime(2026, 10, 14, 15, 52, 23, tzinfo=UTC)
LADDER_STALL_S = 300              # a rung crossed this long ago and still not sold, after the fast ladder: broken, not slow
RUNG_LAG_WARN_S = 20
COVERAGE_FAULT_FRAC = 0.10
LOST_FAULT_FRAC = 0.30
COVERAGE_FAULT_RUN = 6            # six consecutive unexplained missed slots = 30 minutes of no robot
ERROR_WARN_RATE = 0.03
LATENCY_WARN_P95_S = 60.0
MIN_N_PROMISING = 10              # entries before a counterfactual is called PROMISING rather than UNDERPOWERED
ENTER = ("ENTER_LONG", "ENTER_SHORT")


# ── environment (every path injectable, so tests never touch the live desk) ─────────────────────────────────────────────
class Env:
    def __init__(self, gb: str = GB, out: str | None = None, series_fn=None, **over):
        self.gb = gb
        self.out = out or f"{gb}/reports/hybrid_nightly"
        self.log = f"{gb}/data/hybrid_robot.jsonl"
        self.state = f"{gb}/data/hybrid_robot_state.json"
        self.switch = f"{gb}/data/hybrid_robot.env"
        self.leg_switch = f"{gb}/data/leg_robot.env"
        self.daydir = f"{gb}/reports/hybrid_robot"
        self.ledger = f"{gb}/data/gazbot7.db"
        self.capture = f"{gb}/data/capture.db"
        self.rider_state = f"{gb}/data/day_rider_state.json"
        self.series_fn = series_fn or L.series_for
        self.ticks_fn = over.pop('ticks_fn', None) or journal_ticks
        for k, v in over.items():
            setattr(self, k, v)


def jload(path: str):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def parse_ts(s) -> dt.datetime | None:
    try:
        d = dt.datetime.fromisoformat(str(s))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except Exception:
        return None


def iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, UTC).isoformat()


def d0_of(key: str) -> int:
    return int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())


def version_of(key: str) -> str:
    """The robot version a session ran: v1.03 (+MIL cap) from MILCAP_FROM, v1.02 before it. Labelled by DATE, so a version bump never relabels history."""
    return H.VERSION if key >= H.MILCAP_FROM else H.PREV_VERSION


def arm_of(key: str) -> str:
    v = version_of(key)
    if key == H.EXT_KEY:
        return f"v{v}-EXT"
    if key >= H.MILCAP_FROM:
        return f"v{v}+LOCK+MILCAP"
    return f"v{v}+LOCK" if key >= H.LOCK_FROM else f"v{v}"


def pctile(xs: list, p: float):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))], 1)


# ── the robot's own logs ────────────────────────────────────────────────────────────────────────────────────────────────
def read_log(env: Env, key: str) -> dict:
    """DECISION/ERROR/REFUSED/DAY_WRITTEN records belonging to the session `key`. Malformed lines are COUNTED, not skipped quietly."""
    out = {"decisions": [], "errors": [], "refused": [], "day_written": [], "lock": None, "lock_errors": [], "bad_lines": 0, "readable": True}
    try:
        fh = open(env.log)
    except Exception:
        out["readable"] = False
        return out
    with fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                out["bad_lines"] += 1
                continue
            ev = r.get("event")
            if ev == "DECISION":
                if r.get("dry") or not str(r.get("decision_ts", "")).startswith(key):
                    continue
                out["decisions"].append(r)
            elif str(r.get("at", "")).startswith(key):
                if ev == "ERROR":
                    out["errors"].append(r)
                elif ev == "REFUSED_LEG_ROBOT_ON":
                    out["refused"].append(r)
                elif ev == "DAY_WRITTEN":
                    out["day_written"].append(r)
                elif ev == "DAY_LOCK" and out["lock"] is None:
                    out["lock"] = r
                elif ev == "LOCK_CHECK_ERROR":
                    out["lock_errors"].append(r)
    out["decisions"].sort(key=lambda r: r["decision_ts"])
    return out


# ── the service journal: the one place LATE_TICK / FEED_STALE / NO_BARS are recorded ────────────────────────────────────
JOURNAL_UNIT = "gazbot7-hybrid-robot.service"


def journal_ticks(env, key: str):
    """Every tick the robot printed for session `key`, parsed from the unit's journal; None if the journal cannot be read.

    Fixed argv, no shell, read-only (`journalctl` is the only subprocess this module runs).
    """
    d0 = d0_of(key)
    since = dt.datetime.fromtimestamp(d0 - 3600, UTC).strftime("%Y-%m-%d %H:%M:%S")
    until = dt.datetime.fromtimestamp(d0 + 22 * 3600 + 3600, UTC).strftime("%Y-%m-%d %H:%M:%S")
    try:
        cp = subprocess.run(["journalctl", "-u", JOURNAL_UNIT, "--since", since, "--until", until, "-o", "cat", "--no-pager", "--utc"],
                            capture_output=True, text=True, timeout=60, check=False)
    except Exception:
        return None
    if cp.returncode != 0:
        return None
    out = []
    for ln in cp.stdout.splitlines():
        if not ln.startswith('{"at"'):
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("session") == key and r.get("status"):
            t = parse_ts(r["at"])
            if t:
                out.append({"ts": t.timestamp(), "status": r["status"], "late_s": r.get("late_s"), "fault": r.get("fault")})
    return sorted(out, key=lambda x: x["ts"])


# ── the tape ────────────────────────────────────────────────────────────────────────────────────────────────────────────
class Tape:
    """5s MNQ bars as parallel arrays; bar_ts is the bar START."""

    def __init__(self, rows):
        rows = sorted(rows)
        self.ts = [r[0] for r in rows]
        self.hi = [float(r[1]) for r in rows]
        self.lo = [float(r[2]) for r in rows]
        self.cl = [float(r[3]) for r in rows]

    def __len__(self):
        return len(self.ts)

    def last_before(self, t: float):
        """index of the last bar with ts <= t, or -1"""
        return bisect.bisect_right(self.ts, t) - 1


def load_tape(env: Env, t0: int, t1: int) -> Tape:
    con = sqlite3.connect(f"file:{env.capture}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT bar_ts, high, low, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
                           "AND bar_ts >= ? AND bar_ts <= ? ORDER BY bar_ts", (t0, t1)).fetchall()
    finally:
        con.close()
    return Tape(rows)


def feed_stale_at(tape: Tape, op: int) -> bool:
    """Would hybrid_robot's own FEED_STALE test have fired on the tick for slot `op`? (tick ~ op+20s; stale if newest bar's end is >180s old.)"""
    i = tape.last_before(op + 20)
    if i < 0:
        return True
    return (op + 20) - (tape.ts[i] + 5) > H.FEED_STALE_S


def path_stats(tape: Tape, side: int, entry: float, t0: float, t_end: float, grid=GRID_PT) -> dict:
    """What an entry at `entry` (side +1/-1) from t0 would have done on the tape until t_end, with NO stop (the desk's rule).

    mfe/mae are in points; `cross` is the START of the first 5s bar that reached each target (+-5s); `grid_usd` is the 4-lot net of an
    all-lots-at-T ladder (reached: T pts each; else flat at the last print), IDEAL fills, $2/pt, $1.5/lot fee.
    """
    i0 = bisect.bisect_left(tape.ts, int(t0))
    i1 = bisect.bisect_right(tape.ts, int(t_end))
    res = {"n_bars": max(0, i1 - i0), "mfe_pt": 0.0, "mfe_ts": None, "mae_pt": 0.0, "mae_ts": None, "last_px": None,
           "cross": {}, "grid_usd": {}}
    if i1 <= i0:
        return res
    pend = list(grid)
    for i in range(i0, i1):
        fav = (tape.hi[i] - entry) if side > 0 else (entry - tape.lo[i])
        adv = (entry - tape.lo[i]) if side > 0 else (tape.hi[i] - entry)
        if fav > res["mfe_pt"]:
            res["mfe_pt"], res["mfe_ts"] = round(fav, 2), tape.ts[i]
        if adv > res["mae_pt"]:
            res["mae_pt"], res["mae_ts"] = round(adv, 2), tape.ts[i]
        if pend:
            for T in list(pend):
                if fav >= T:
                    res["cross"][str(T)] = tape.ts[i]
                    pend.remove(T)
    res["last_px"] = tape.cl[i1 - 1]
    for T in grid:
        if str(T) in res["cross"]:
            pts = T
        else:
            pts = side * (res["last_px"] - entry)
        res["grid_usd"][str(T)] = round(LOTS * (pts * USD_PT - FEE_LOT), 2)
    return res


# ── the ledger (the truth for what was traded) ──────────────────────────────────────────────────────────────────────────
def load_ledger(env: Env, key: str) -> list:
    lo = dt.datetime.fromtimestamp(d0_of(key) - 2 * 3600, UTC).isoformat()
    hi = dt.datetime.fromtimestamp(d0_of(key) + 22 * 3600, UTC).isoformat()
    con = sqlite3.connect(f"file:{env.ledger}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT id, side, qty, entry_price, exit_price, opened_at, closed_at, pnl_usd, fees_usd, exit_reason, "
                           "data_quality, entry_source FROM trades WHERE gate='day_rider' AND opened_at >= ? AND opened_at < ? "
                           "ORDER BY opened_at, id", (lo, hi)).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def group_entries(rows: list) -> list:
    """Lots opened in the same instant are ONE entry (four lots share opened_at and entry_price)."""
    g: dict = {}
    for r in rows:
        g.setdefault(r["opened_at"], []).append(r)
    return [{"opened_at": k, "lots": v} for k, v in sorted(g.items())]


def counted(r: dict) -> bool:
    dq = r.get("data_quality") or ""
    return not (dq.startswith("EXCLUDE") or dq.startswith("BADFILL"))


# ── expected slots and the gap classifier ───────────────────────────────────────────────────────────────────────────────
def expected_slots(key: str, now_ts: int) -> list:
    d0 = d0_of(key)
    day = dt.date.fromisoformat(key)
    if day.weekday() >= 5:
        return []
    win_end = H.EXT_END_MIN if key == H.EXT_KEY else S.WIN_END_MIN
    start_after = int(H.START_AFTER.timestamp())
    stop_after = int(H.STOP_AFTER.timestamp())
    out = []
    for op in range(d0 + S.WIN_START_MIN * 60, d0 + win_end * 60, H.STEP_S):
        if op < start_after or op >= stop_after:
            continue
        if op + 120 > now_ts:          # its tick has not (fully) happened yet
            continue
        out.append(op)
    return out


def on_grid(key: str, op: int) -> bool:
    """A decision slot that exists on this session's grid (so a decision not yet 'due' by our clock is not an extra)."""
    d0 = d0_of(key)
    win_end = H.EXT_END_MIN if key == H.EXT_KEY else S.WIN_END_MIN
    return d0 + S.WIN_START_MIN * 60 <= op < d0 + win_end * 60 and (op - d0) % H.STEP_S == 0


def classify_coverage(env: Env, key: str, slots: list, log: dict, tape: Tape, switch_on: bool, ticks=None) -> dict:
    decided = {int(parse_ts(r["decision_ts"]).timestamp()) for r in log["decisions"] if parse_ts(r["decision_ts"])}
    refused_ts = [parse_ts(r["at"]) for r in log["refused"]]
    err_ts = [parse_ts(r["at"]) for r in log["errors"]]
    missed, feed, refused, crashed, unexplained, late, other, locked = [], [], [], [], [], [], [], []
    lock_ts = parse_ts((log.get("lock") or {}).get("decision_ts"))
    by_status: dict = {}
    for op in slots:
        if op in decided:
            continue
        missed.append(op)
        near = lambda xs: any(x and abs(x.timestamp() - (op + 20)) <= 120 for x in xs)  # noqa: E731
        tk = [t for t in (ticks or []) if op <= t["ts"] < op + H.STEP_S]
        st_ = {t["status"] for t in tk}
        if "DAY_LOCKED" in st_ or (lock_ts and op >= lock_ts.timestamp()):     # v1.02+LOCK: decided not to decide — an explained, healthy slot
            locked.append(op)
        elif st_ & {"LATE_TICK"}:
            late.append(op)
            by_status["LATE_TICK"] = by_status.get("LATE_TICK", 0) + 1
        elif st_ & {"FEED_STALE", "NO_BARS"}:
            feed.append(op)
            by_status["FEED_STALE/NO_BARS"] = by_status.get("FEED_STALE/NO_BARS", 0) + 1
        elif st_ & {"PREFLIGHT_FAILED", "LEG_ROBOT_ON_CONFLICT"}:
            other.append(op)
            for x in st_ & {"PREFLIGHT_FAILED", "LEG_ROBOT_ON_CONFLICT"}:
                by_status[x] = by_status.get(x, 0) + 1
        elif near(refused_ts):
            refused.append(op)
        elif feed_stale_at(tape, op):
            feed.append(op)
        elif near(err_ts):
            crashed.append(op)
        else:
            unexplained.append(op)
    runs, cur = [], []
    for op in unexplained:
        if cur and op - cur[-1] == H.STEP_S:
            cur.append(op)
        else:
            if cur:
                runs.append(cur)
            cur = [op]
    if cur:
        runs.append(cur)
    return {"expected": len(slots), "decided": len([o for o in slots if o in decided]), "missed": len(missed),
            "journal_ok": ticks is not None, "locked": len(locked), "late_tick": len(late), "refused_or_preflight": len(other), "by_status": by_status,
            "no_tick_at_all": (len([o for o in unexplained if not any(o <= t['ts'] < o + H.STEP_S for t in ticks)]) if ticks is not None else None),
            "feed_explained": len(feed), "refused": len(refused), "crash_logged": len(crashed), "unexplained": len(unexplained),
            "longest_unexplained_run": max((len(r) for r in runs), default=0),
            "unexplained_runs": [{"from": iso(r[0]), "to": iso(r[-1]), "slots": len(r)} for r in runs][:12],
            "extra_decisions": len([o for o in decided if o not in set(slots) and not on_grid(key, o)]), "switch_on_at_review": switch_on}


# ── detector view ───────────────────────────────────────────────────────────────────────────────────────────────────────
def detector_view(env: Env, key: str, t_end: int) -> dict:
    day = dt.date.fromisoformat(key)
    try:
        series = [b for b in env.series_fn(day) if b[0] + 60 <= t_end]
        turns = L.confirmed_turns(series) if len(series) >= 200 else []
    except Exception as e:  # noqa: BLE001  the review must survive a detector-side read problem and say so
        return {"ok": False, "error": repr(e), "turns": [], "legs": []}
    s0 = d0_of(key) - 2 * 3600
    legs = []
    for i, (pts, ppx, nd, cts, cpx) in enumerate(turns):
        if cts < s0:
            continue
        end_ts, end_px = (turns[i + 1][0], turns[i + 1][1]) if i + 1 < len(turns) else (series[-1][0], series[-1][3])
        legs.append({"dir": nd, "pivot_ts": iso(pts), "pivot_px": ppx, "confirm_ts": iso(cts), "confirm_px": cpx,
                     "confirm_lag_min": round((cts - pts) / 60, 1), "confirm_giveback_pt": round(nd * (cpx - ppx), 1),
                     "end_ts": iso(end_ts), "size_pt": round(nd * (end_px - ppx), 1), "open": i + 1 >= len(turns)})
    return {"ok": True, "n_bars": len(series), "turns": turns, "legs": legs}


# ── per-candidate and per-press analysis ────────────────────────────────────────────────────────────────────────────────
def analyse_candidates(decisions: list, tape: Tape, t_flat: int, turns: list) -> list:
    out = []
    mismatches = 0
    for r in decisions:
        if r.get("action") not in ENTER or "entry_action" not in r:
            continue
        op = int(parse_ts(r["decision_ts"]).timestamp())
        dirn = 1 if r["action"] == "ENTER_LONG" else -1
        entry = float(r["px"]) + dirn * S.HALF_SPREAD_PT
        ps = path_stats(tape, dirn, entry, op, t_flat)
        replay = H.det_dir(turns, op - 60) if turns else None
        agree = (replay == r.get("detector_dir")) if replay is not None else None
        if agree is False:
            mismatches += 1
        ea = r["entry_action"]
        cat = ("PRESSED" if ea.startswith("PRESS_") else "SKIPPED_HOLDING" if ea == "SKIPPED_HOLDING" else
               "SKIPPED_OTHER" if ea.startswith("SKIPPED_") else ea)
        out.append({"decision_ts": r["decision_ts"], "side": r.get("candidate"), "dir": dirn, "px": r["px"], "conf": r.get("conf"),
                    "entry_action": ea, "category": cat, "detector_dir": r.get("detector_dir"), "detector_replay_dir": replay,
                    "detector_agrees": agree, "request": r.get("request"), "latency_s": r.get("latency_s"), "reason": r.get("reason"),
                    "cf_mfe_pt": ps["mfe_pt"], "cf_mae_pt": ps["mae_pt"],
                    "cf_reached_champion": str(CHAMPION_PT) in ps["cross"],
                    "cf_minutes_to_champion": (round((ps["cross"][str(CHAMPION_PT)] - op) / 60, 1) if str(CHAMPION_PT) in ps["cross"] else None),
                    "cf_grid_usd": ps["grid_usd"]})
    return out


def parse_request(req: str):
    try:
        iso_s, side, qty, tg = req.split("|")
        return parse_ts(iso_s), side, int(qty), [float(x) / USD_PT for x in tg.split(",")]
    except Exception:
        return None, None, None, []


def analyse_presses(decisions: list, groups: list, tape: Tape, t_flat: int, flat_complete: bool) -> tuple:
    """Attribute each PRESS to a ledger entry; compute its path, fill gap and per-lot rung lag. Returns (presses, unattributed groups)."""
    used, presses = set(), []
    for r in decisions:
        ea = r.get("entry_action") or ""
        if not (ea.startswith("PRESS_") and r.get("request")):
            continue
        rts, side, _qty, tgts = parse_request(r["request"])
        grp = None
        if rts:
            for g in groups:
                ot = parse_ts(g["opened_at"])
                if ot and g["opened_at"] not in used and 0 <= (ot - rts).total_seconds() <= 180:
                    grp = g
                    used.add(g["opened_at"])
                    break
        p = {"decision_ts": r["decision_ts"], "request": r["request"], "side": side, "conf": r.get("conf"), "reason": r.get("reason"),
             "targets_pt": tgts, "filled": grp is not None, "lots": [], "ledger_net_usd": None, "entered_at": None}
        if grp:
            lots = grp["lots"]
            ot = parse_ts(grp["opened_at"])
            dirn = 1 if lots[0]["side"] == "LONG" else -1
            entry = float(lots[0]["entry_price"])
            ps = path_stats(tape, dirn, entry, ot.timestamp(), t_flat)
            closed = sorted([x for x in lots if x["closed_at"]], key=lambda x: x["closed_at"])
            n_lots = int(round(sum(float(x["qty"] or 1) for x in lots)))
            n_closed = int(round(sum(float(x["qty"] or 1) for x in closed)))
            post_deploy = ot >= FAST_LADDER_LIVE_FROM
            lot_rows = []
            cum = 0
            for x in closed:
                j = cum
                cum += int(round(float(x["qty"] or 1)))
                T = tgts[min(j, len(tgts) - 1)] if tgts else CHAMPION_PT
                cross = None
                for i in range(bisect.bisect_left(tape.ts, int(ot.timestamp())), len(tape)):
                    if (dirn > 0 and tape.hi[i] - entry >= T) or (dirn < 0 and entry - tape.lo[i] >= T):
                        cross = tape.ts[i]
                        break
                ct = parse_ts(x["closed_at"]).timestamp()
                target_exit = str(x.get("exit_reason") or "").startswith("TARGET")
                lot_rows.append({"id": x["id"], "qty": x["qty"], "exit_reason": x["exit_reason"], "exit_price": x["exit_price"], "pnl_usd": x["pnl_usd"],
                                 "closed_at": x["closed_at"], "target_pt": T,
                                 "cross_ts": iso(cross) if cross else None,
                                 "lag_s": (round(ct - cross, 1) if cross else None),
                                 "slip_pt_vs_target": (round(dirn * (float(x["exit_price"]) - entry) - T, 2) if target_exit and x["exit_price"] is not None else None),
                                 "target_exit": target_exit})
            net = round(sum(x["pnl_usd"] for x in lots if x["closed_at"] and counted(x)), 2)
            g37 = ps["grid_usd"].get(str(CHAMPION_PT))
            manual = [str(x["exit_reason"]) for x in closed if str(x["exit_reason"]).startswith(("MANUAL", "OPERATOR"))]
            p.update({"entered_at": grp["opened_at"], "entry": entry, "dir": dirn, "n_lots": n_lots, "n_closed": n_closed,
                      "manual_exit": bool(manual),
                      "lots": lot_rows, "ledger_net_usd": net, "post_fast_ladder": post_deploy,
                      "flagged_lots": sum(1 for x in lots if not counted(x)),
                      "mfe_pt": ps["mfe_pt"], "mae_pt": ps["mae_pt"], "mfe_ts": iso(ps["mfe_ts"]) if ps["mfe_ts"] else None,
                      "mae_ts": iso(ps["mae_ts"]) if ps["mae_ts"] else None,
                      "extra_after_target_pt": round(max(0.0, ps["mfe_pt"] - CHAMPION_PT), 2),
                      "grid_usd": ps["grid_usd"], "provisional": not flat_complete,
                      "vs_ideal_37_usd": (round(net - g37, 2) if (g37 is not None and n_closed == n_lots) else None),
                      "exit_reasons": sorted({str(x["exit_reason"]) for x in closed})})
        presses.append(p)
    unattrib = [g for g in groups if g["opened_at"] not in used]
    return presses, unattrib


# ── health ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def health_checks(env: Env, key: str, now: dt.datetime, log: dict, cov: dict, cands: list, presses: list, unattrib: list,
                  dayrec, switch_on: bool, sess_open: bool, det: dict, groups: list) -> list:
    H_: list = []

    def add(sev, code, msg):
        H_.append({"sev": sev, "code": code, "msg": msg})

    day = dt.date.fromisoformat(key)
    now_ts = int(now.timestamp())
    live = now.date().isoformat() == key and now_ts < d0_of(key) + 22 * 3600
    if day.weekday() >= 5:
        add("INFO", "NO_SESSION", f"{key} is a weekend — the hybrid does not run; weekly pack refreshed only.")
        return H_
    if L.detector_sha() != H.DETECTOR_SHA:
        add("FAULT", "DETECTOR_SHA", "the frozen detector's source hash changed — the robot REFUSES to run (PREFLIGHT_FAILED); no entries until it is reverted.")
    if not log["readable"]:
        if cov["expected"] > 0:
            add("FAULT", "LOG_UNREADABLE", f"{env.log} cannot be read but {cov['expected']} decisions were due.")
        return H_
    if log["bad_lines"]:
        add("WARN", "LOG_CORRUPT_LINES", f"{log['bad_lines']} unparseable line(s) in hybrid_robot.jsonl.")
    if not switch_on and cov["expected"] > 0:
        add("WARN", "SWITCH_OFF", "data/hybrid_robot.env says hybrid_robot=off at review time — if you stopped it on purpose, ignore the coverage lines.")
    if cov["expected"] == 0:
        add("INFO", "NO_SLOTS_DUE", f"no decision slots were due on {key} (before start, after stop, or the session has not opened).")
    else:
        if switch_on:
            fr = cov["unexplained"] / cov["expected"]
            if cov["expected"] >= 12 and fr > COVERAGE_FAULT_FRAC or cov["longest_unexplained_run"] >= COVERAGE_FAULT_RUN:
                add("FAULT", "COVERAGE", f"{cov['unexplained']}/{cov['expected']} decision slots missing with NO cause on record "
                    f"(longest gap {cov['longest_unexplained_run']} slots = {cov['longest_unexplained_run'] * 5} min) — the robot was not running.")
            elif cov["unexplained"]:
                add("WARN", "COVERAGE", f"{cov['unexplained']}/{cov['expected']} slots missing with no cause on record.")
        lost = sum(cov.get(k) or 0 for k in ("crash_logged", "feed_explained", "late_tick", "no_tick_at_all"))
        if switch_on and cov["expected"] >= 12 and lost / cov["expected"] > LOST_FAULT_FRAC:
            add("FAULT", "LOST_SLOTS", f"{lost}/{cov['expected']} decision slots lost to explained causes (crash {cov['crash_logged']}, stale tape {cov['feed_explained']}, "
                f"late tick {cov['late_tick']}, timer silent {cov['no_tick_at_all']}) — each slot has an excuse but the robot made almost no decisions.")
        if log.get("lock"):
            lk = log["lock"]
            add("INFO", "DAY_LOCK", f"v1.02+LOCK engaged: the day touched +${lk.get('limit', 0):,.0f} at {str(lk.get('touched_at'))[11:16]}Z "
                f"(equity then {lk.get('equity_now'):+,.0f}, peak {lk.get('peak'):+,.0f}); {cov.get('locked', 0)} later slot(s) made no call and no entry by design.")
        if log.get("lock_errors"):
            add("WARN", "LOCK_CHECK_ERROR", f"{len(log['lock_errors'])} tick(s) could not read the day's P&L, so the lock was NOT protecting them "
                f"(last: {str(log['lock_errors'][-1].get('error'))[:120]}).")
        if cov["refused_or_preflight"]:
            add("FAULT", "ROBOT_REFUSED", f"{cov['refused_or_preflight']} slot(s) lost to {cov['by_status']} — the robot refused to run (a failed preflight or leg_robot left ON). No entries were possible.")
        if cov["late_tick"]:
            add("WARN" if cov["late_tick"] >= 3 else "INFO", "LATE_TICKS", f"{cov['late_tick']} slot(s) skipped as LATE_TICK (the tick started >{H.MAX_LATE_S}s after the slot — box load or a timer change).")
        if cov["no_tick_at_all"]:
            add("WARN", "TIMER_DID_NOT_FIRE", f"{cov['no_tick_at_all']} slot(s) have no journal record at all — the timer did not start the service.")
        if cov["feed_explained"]:
            add("INFO", "FEED_GAPS", f"{cov['feed_explained']} slot(s) skipped for a stale tape (hybrid_robot declines to decide on a dead feed).")
        if cov["crash_logged"]:
            add("WARN", "CRASHES", f"{cov['crash_logged']} slot(s) lost to a logged ERROR.")
        if cov["extra_decisions"]:
            add("WARN", "EXTRA_DECISIONS", f"{cov['extra_decisions']} decision(s) outside the expected slot grid.")
    if log["errors"]:
        add("WARN", "ROBOT_ERRORS", f"{len(log['errors'])} ERROR event(s) in the log, last: {str(log['errors'][-1].get('error'))[:160]}")
    stamps = [r["decision_ts"] for r in log["decisions"]]
    if len(stamps) != len(set(stamps)):
        add("WARN", "DOUBLE_DECISION", "the same slot was decided more than once (state lost mid-day?).")
    # Claude call health
    calls = [r for r in log["decisions"]]
    errs = [r for r in calls if r.get("error")]
    if calls:
        rate = len(errs) / len(calls)
        if rate > H.POISON_RATE:
            add("FAULT", "POISONED_DAY", f"{len(errs)}/{len(calls)} Claude calls errored ({rate:.0%} > {H.POISON_RATE:.0%}) — the day is POISONED and unscorable; check `claude` login.")
        elif rate > ERROR_WARN_RATE:
            add("WARN", "CALL_ERRORS", f"{len(errs)}/{len(calls)} Claude calls errored ({rate:.1%}).")
        lat = [r["latency_s"] for r in calls if isinstance(r.get("latency_s"), (int, float))]
        if lat and pctile(lat, 0.95) > LATENCY_WARN_P95_S:
            add("WARN", "LATENCY", f"Claude call latency p95 {pctile(lat, 0.95)}s (max {max(lat)}s) — entries older than {H.PRESS_MAX_AGE_S}s are dropped as STALE.")
    stale = [c for c in cands if c["entry_action"] == "STALE_NOT_ENTERED"]
    if stale:
        add("WARN", "STALE_ENTRIES", f"{len(stale)} entry(ies) were with the leg and after the veto but took >{H.PRESS_MAX_AGE_S}s to decide, so were NOT entered.")
    # day record
    win_end = H.EXT_END_MIN if key == H.EXT_KEY else S.WIN_END_MIN
    window_over = now_ts >= d0_of(key) + (win_end + 15) * 60
    if window_over and calls:
        if not dayrec:
            add("FAULT", "DAY_RECORD_MISSING", f"reports/hybrid_robot/{key}.json was never written although {len(calls)} decisions were logged — the 13:30/19:55 close-out tick did not run.")
        else:
            if dayrec.get("poisoned"):
                add("FAULT", "POISONED_RECORD", "the day record is stamped poisoned.")
            if dayrec.get("calls") != len([r for r in calls]):
                add("WARN", "RECORD_CALLS_MISMATCH", f"day record says {dayrec.get('calls')} calls, log has {len(calls)} decisions.")
            if dayrec.get("partial_from"):
                add("INFO", "PARTIAL_DAY", f"the robot only started deciding at {dayrec['partial_from']} (partial day).")
            if dayrec.get("version") != version_of(key):
                add("WARN", "VERSION_MISMATCH", f"day record version {dayrec.get('version')} != the version this session should have run ({version_of(key)}).")
    # brief frozen
    cur_sha = S.hashlib.sha256(S.brief_for(H.LINE).encode()).hexdigest()[:16]
    if dayrec and dayrec.get("brief_sha") and dayrec.get("version") == version_of(key) and dayrec["brief_sha"] != cur_sha:
        add("FAULT", "BRIEF_DRIFT", f"the brief changed under v{H.VERSION}: day record {dayrec['brief_sha']} vs source {cur_sha}. A new brief is a NEW ARM and a version bump, never an in-place edit.")
    # press rules
    for c in cands:
        if c["category"] != "PRESSED":
            continue
        why = []
        if c["detector_dir"] != c["dir"]:
            why.append("not with the detector's leg")
        cut = L.veto_cutoff(int(parse_ts(c["decision_ts"]).timestamp()))
        if cut and int(parse_ts(c["decision_ts"]).timestamp()) < cut:
            why.append("before the 05:00 Paris veto")
        rts = parse_request(c.get("request") or "")[0]
        if rts and (rts - parse_ts(c["decision_ts"])).total_seconds() > H.PRESS_MAX_AGE_S:
            why.append("older than PRESS_MAX_AGE_S")
        if why:
            add("FAULT", "PRESS_RULE_BREACH", f"press at {c['decision_ts']} broke the entry rules: {', '.join(why)}.")
        if c["detector_agrees"] is False:
            add("WARN", "DETECTOR_REPLAY_MISMATCH", f"the detector direction logged at {c['decision_ts']} ({c['detector_dir']}) differs from an offline replay ({c['detector_replay_dir']}).")
    flat_due = (not live) or (now_ts >= d0_of(key) + REVIEW_FLAT_MIN * 60)
    rider = jload(env.rider_state) or {}
    for p in presses:
        if not p["filled"]:
            if flat_due and not (live and (rider.get("entered") and not rider.get("closed"))):
                add("FAULT", "PRESS_NOT_ENTERED", f"the press at {p['request'].split('|')[0]} left NO ledger rows and the rider is flat — the entry never happened.")
            continue
        if flat_due and p["n_lots"] != H.QTY:
            add("FAULT", "PRESS_LOT_COUNT", f"the press at {p['entered_at']} opened {p['n_lots']} lot(s), not {H.QTY} — a partial or doubled entry.")
        if p.get("manual_exit"):
            add("INFO", "OPERATOR_EXIT", f"entry {p['entered_at'][11:19]}Z was closed by the OPERATOR's hands ({', '.join(p['exit_reasons'])}) — its P&L is the operator's exit, not the ladder's; keep it out of any ladder comparison.")
        if p.get("flagged_lots"):
            add("WARN", "FLAGGED_LOTS", f"{p['flagged_lots']} lot(s) of the {p['entered_at']} entry carry EXCLUDE/BADFILL and are not counted.")
        if p.get("post_fast_ladder"):
            for lot in p["lots"]:
                if lot["cross_ts"] and lot["lag_s"] is not None:
                    if lot["lag_s"] > LADDER_STALL_S:
                        add("FAULT", "LADDER_STALLED", f"entry {p['entered_at']}: a +{lot['target_pt']}pt rung crossed {lot['lag_s']:.0f}s before the lot closed ({lot['exit_reason']}) — the fast ladder is not selling.")
                    elif lot["lag_s"] > RUNG_LAG_WARN_S and lot["target_exit"]:
                        add("WARN", "RUNG_LAG", f"entry {p['entered_at']}: a rung sold {lot['lag_s']:.0f}s after the tape crossed it (fast ladder expected a few seconds).")
    if unattrib:
        add("INFO", "UNATTRIBUTED_ENTRIES", f"{len(unattrib)} rider entr{'y' if len(unattrib) == 1 else 'ies'} not made by the hybrid (his own hands or another robot) — excluded from the hybrid's numbers.")
    # never hold overnight — only meaningful when this IS the evening of the session
    if live and now_ts >= d0_of(key) + REVIEW_FLAT_MIN * 60:
        # lots_open is NOT a flatness signal: a MANUAL_CLAIM that passes qty leaves lots_open=4 with closed=True (the rider and the
        # robot's own gate both treat that as flat). IBKR's net is the truth; entered-and-not-closed is the rider's own claim.
        lots_open = float(rider.get("lots_open") or 0)
        venue_net = float(rider.get("venue_net") or 0)
        if (rider.get("entered") and not rider.get("closed")) or abs(venue_net) > 0.01:
            add("FAULT", "NOT_FLAT", f"rider shows entered={rider.get('entered')} closed={rider.get('closed')} lots_open={lots_open} venue_net={venue_net} at {now.strftime('%H:%MZ')} — past the 20:40Z hard flat. NEVER HOLD OVERNIGHT.")
    return H_


def verdict_of(health: list) -> str:
    sevs = {h["sev"] for h in health}
    return "FAULT" if "FAULT" in sevs else "WARN" if "WARN" in sevs else "OK"


# ── the day review ──────────────────────────────────────────────────────────────────────────────────────────────────────
def review_day(env: Env, key: str, now: dt.datetime) -> dict:
    now_ts = int(now.timestamp())
    d0 = d0_of(key)
    t_flat = min(d0 + HARD_FLAT_MIN * 60, now_ts)
    flat_complete = now_ts >= d0 + HARD_FLAT_MIN * 60
    switch_on = L.read_switch(env.switch, "hybrid_robot")
    log = read_log(env, key)
    dayrec = jload(f"{env.daydir}/{key}.json")
    slots = expected_slots(key, now_ts)
    try:
        tape = load_tape(env, d0 - 2 * 3600, min(now_ts, d0 + 22 * 3600))
        tape_ok = len(tape) > 0
    except Exception:
        tape, tape_ok = Tape([]), False
    try:
        ticks = env.ticks_fn(env, key)
    except Exception:
        ticks = None
    cov = classify_coverage(env, key, slots, log, tape, switch_on, ticks)
    det = detector_view(env, key, t_flat) if tape_ok else {"ok": False, "error": "no tape", "turns": [], "legs": []}
    try:
        ledger = load_ledger(env, key)
        ledger_ok = True
    except Exception:
        ledger, ledger_ok = [], False
    groups = group_entries(ledger)
    cands = analyse_candidates(log["decisions"], tape, t_flat, det.get("turns") or [])
    presses, unattrib = analyse_presses(log["decisions"], groups, tape, t_flat, flat_complete)
    health = health_checks(env, key, now, log, cov, cands, presses, unattrib, dayrec, switch_on, True, det, groups)
    if not ledger_ok:
        health.append({"sev": "WARN", "code": "LEDGER_UNREADABLE", "msg": "the trade ledger could not be read; presses are not attributed."})
    if not tape_ok and cov["expected"] > 0:
        health.append({"sev": "WARN", "code": "NO_TAPE", "msg": "capture.db had no 5s bars for the session; counterfactuals and feed explanations are empty."})
    dec = log["decisions"]
    acts: dict = {}
    for r in dec:
        acts[r.get("action", "?")] = acts.get(r.get("action", "?"), 0) + 1
    lat = [r["latency_s"] for r in dec if isinstance(r.get("latency_s"), (int, float))]
    conf = [r["conf"] for r in dec if isinstance(r.get("conf"), (int, float))]
    funnel = {"enter_signals": len(cands), "with_leg": sum(1 for c in cands if c["detector_dir"] == c["dir"]),
              "not_with_leg": sum(1 for c in cands if c["entry_action"] in ("NOT_WITH_LEG", "NO_DETECTOR_LEG")),
              "vetoed_before_05_paris": sum(1 for c in cands if c["entry_action"] == "VETOED_BEFORE_05_PARIS"),
              "stale": sum(1 for c in cands if c["entry_action"] == "STALE_NOT_ENTERED"),
              "skipped_rider_busy": sum(1 for c in cands if c["entry_action"] == "SKIPPED_HOLDING"),
              "skipped_other": sum(1 for c in cands if c["category"] == "SKIPPED_OTHER"),
              "pressed": sum(1 for c in cands if c["category"] == "PRESSED"),
              "filled_entries": sum(1 for p in presses if p["filled"])}
    nets = [p["ledger_net_usd"] for p in presses if p["ledger_net_usd"] is not None]
    lots_all = [x for p in presses for x in p["lots"]]
    rep = {"schema": SCHEMA, "generated_at": now.isoformat(), "key": key, "arm": arm_of(key), "version": H.VERSION,
           "verdict": verdict_of(health), "health": health,
           "coverage": cov,
           "calls": {"n": len(dec), "errors": sum(1 for r in dec if r.get("error")), "actions": acts,
                     "conf_mean": round(statistics.mean(conf), 3) if conf else None,
                     "latency_p50": pctile(lat, 0.5), "latency_p95": pctile(lat, 0.95), "latency_max": max(lat) if lat else None,
                     "first": dec[0]["decision_ts"] if dec else None, "last": dec[-1]["decision_ts"] if dec else None},
           "funnel": funnel, "candidates": cands, "presses": presses,
           "unattributed_entries": [{"opened_at": g["opened_at"], "lots": len(g["lots"]), "entry_source": g["lots"][0].get("entry_source"),
                                     "net_usd": round(sum(x["pnl_usd"] for x in g["lots"] if x["closed_at"] and counted(x)), 2)} for g in unattrib],
           "totals": {"ledger_net_usd": round(sum(nets), 2) if nets else 0.0, "presses": len(presses), "filled": len([p for p in presses if p["filled"]]),
                      "lots_closed": int(sum(float(x["qty"] or 1) for x in lots_all)),
                      "lots_by_target": int(sum(float(x["qty"] or 1) for x in lots_all if x["target_exit"])),
                      "lots_other_exit": int(sum(float(x["qty"] or 1) for x in lots_all if not x["target_exit"])),
                      "manual_exit_entries": sum(1 for p in presses if p.get("manual_exit")),
                      "winners": sum(1 for p in presses if (p["ledger_net_usd"] or 0) > 0)},
           "flat_complete": flat_complete,
           "discipline": discipline_row([g for g in groups if any(counted(x) for x in g["lots"])], tape, key, now_ts, flat_complete,
                                        round(sum(nets), 2) if nets else 0.0),
           "claude_sim": ({"net_usd": dayrec.get("claude_sim_net_usd"), "trades": len(dayrec.get("claude_sim_trades") or []),
                           "brief_sha": dayrec.get("brief_sha"), "poisoned": dayrec.get("poisoned")} if dayrec else None),
           "detector": {"ok": det.get("ok"), "error": det.get("error"), "sha_ok": L.detector_sha() == H.DETECTOR_SHA,
                        "n_turns": len(det.get("turns") or []), "legs": det.get("legs") or [],
                        "replay_mismatches": sum(1 for c in cands if c["detector_agrees"] is False)},
           "notes": ["Counterfactuals: 5s tape, +-5s, ideal fills, no stop, flat at 20:40Z. The paper engine's 0.1% adverse fill on lots 2-4 is NOT in them.",
                     "PRESS_RESULT in hybrid_robot.jsonl is unreliable (reads the rider before it saves); the ledger is used instead."]}
    return rep


# ── text rendering ──────────────────────────────────────────────────────────────────────────────────────────────────────
def render_day(rep: dict) -> str:
    c, f, t = rep["calls"], rep["funnel"], rep["totals"]
    L_ = [f"HYBRID ROBOT v{rep['version']} — NIGHTLY REVIEW {rep['key']}  [{rep['arm']}]  VERDICT: {rep['verdict']}",
          f"generated {rep['generated_at']}", ""]
    for h in rep["health"]:
        L_.append(f"  [{h['sev']:5}] {h['code']}: {h['msg']}")
    if not rep["health"]:
        L_.append("  (no findings)")
    cov = rep["coverage"]
    L_ += ["", f"COVERAGE  {cov['decided']}/{cov['expected']} slots decided · missed {cov['missed']} (feed {cov['feed_explained']}, logged-crash {cov['crash_logged']}, "
           f"refused {cov['refused']}, unexplained {cov['unexplained']})",
           f"CALLS     n={c['n']} errors={c['errors']} actions={c['actions']} conf̄={c['conf_mean']} latency p50/p95/max={c['latency_p50']}/{c['latency_p95']}/{c['latency_max']}s",
           f"FUNNEL    ENTER signals {f['enter_signals']} → with the leg {f['with_leg']} (against/none {f['not_with_leg']}) · vetoed<05:00Paris {f['vetoed_before_05_paris']} · "
           f"stale {f['stale']} · rider busy {f['skipped_rider_busy']} · other skips {f['skipped_other']} → PRESSED {f['pressed']} → filled {f['filled_entries']}",
           f"LEDGER    net ${t['ledger_net_usd']:+.2f} over {t['filled']} entr{'y' if t['filled'] == 1 else 'ies'} · lots {t['lots_closed']} closed "
           f"({t['lots_by_target']} by target, {t['lots_other_exit']} other) · winners {t['winners']}"]
    if rep.get("claude_sim"):
        cs = rep["claude_sim"]
        L_.append(f"CLAUDE SIM book (own exits, not the real ladder): ${cs['net_usd']} over {cs['trades']} trade(s)")
    for p in rep["presses"]:
        if not p["filled"]:
            L_.append(f"  PRESS {p['request']}  → NOT FILLED (no ledger rows)")
            continue
        L_.append(f"  ENTRY {p['entered_at'][11:19]}Z {p['side']} @ {p['entry']:.2f}  net ${p['ledger_net_usd']:+.2f}  MFE {p['mfe_pt']:.1f} / MAE {p['mae_pt']:.1f}pt  "
                  f"+{p['extra_after_target_pt']:.1f}pt beyond the target  vs-ideal-37.5 {p['vs_ideal_37_usd']}  exits {','.join(p['exit_reasons'])}")
        for x in p["lots"]:
            L_.append(f"      lot {x['id']} x{x['qty']:g}: {x['exit_reason']:<11} @ {x['exit_price']} pnl {x['pnl_usd']:+.2f}"
                      + (f" slip {x['slip_pt_vs_target']}pt rung-lag {x['lag_s']}s" if x['target_exit'] else ""))
        L_.append("      grid(4-lot ideal $): " + "  ".join(f"{k}:{v:+.0f}" for k, v in p["grid_usd"].items()))
    L_ += ["", "ENTER CANDIDATES (counterfactual = ideal 4-lot ladder @37.5 / flat 20:40Z):"]
    for cd in rep["candidates"]:
        L_.append(f"  {cd['decision_ts'][11:16]}Z {str(cd['side']):4} {cd['entry_action']:<26} conf {cd['conf']}  MFE {cd['cf_mfe_pt']:.0f}/MAE {cd['cf_mae_pt']:.0f}  "
                  f"cf37 ${cd['cf_grid_usd'].get(str(CHAMPION_PT), 0):+.0f}  {'reached' if cd['cf_reached_champion'] else 'NOT reached'}")
    d = rep["detector"]
    L_ += ["", f"DETECTOR  sha_ok={d['sha_ok']} turns={d['n_turns']} replay-mismatches={d['replay_mismatches']}"]
    for g in d["legs"]:
        L_.append(f"  leg {'UP  ' if g['dir'] > 0 else 'DOWN'} pivot {g['pivot_ts'][11:16]}Z @{g['pivot_px']}  confirmed {g['confirm_ts'][11:16]}Z (+{g['confirm_lag_min']}min, {g['confirm_giveback_pt']}pt in)  size so far {g['size_pt']}pt")
    L_ += ["", *[f"note: {n}" for n in rep["notes"]]]
    return "\n".join(L_) + "\n"


# ── the discipline table: what it FELT like to hold, from the real ledger and the 5s tape ───────────────────────────────
HALF_SPREAD_PT = 0.25             # an open lot is marked as if sold now: half a tick of spread plus the fee
T_MIDDAY_MIN = 13 * 60 + 30       # the robot stops entering here; whatever is open rides
T_EVENING_MIN = 18 * 60


def _lot_state(x: dict, t: float, tape: Tape, i: int):
    """P&L of one ledger lot at time t: realised if it was already sold, else marked at the tape's close as if flattened now. None if not yet opened."""
    ot, ct = parse_ts(x["opened_at"]), parse_ts(x["closed_at"]) if x.get("closed_at") else None
    if ot is None or ot.timestamp() > t:
        return None
    if ct is not None and ct.timestamp() <= t:
        return float(x["pnl_usd"]) if counted(x) else 0.0
    if i < 0:
        return None
    dirn = 1 if x["side"] == "LONG" else -1
    q = float(x["qty"] or 1)
    return q * ((dirn * (tape.cl[i] - float(x["entry_price"])) - HALF_SPREAD_PT) * USD_PT - FEE_LOT)


def _book_at(groups: list, t: float, tape: Tape):
    """(day total, total of the open position or None, open-lot count) at time t. A lot opened after t is invisible, so a mark never uses the future."""
    i = tape.last_before(t)
    tot, pos, n_open = 0.0, None, 0
    for g in groups:
        sub = [_lot_state(x, t, tape, i) for x in g["lots"]]
        if all(v is None for v in sub):
            continue
        gt = sum(v for v in sub if v is not None)
        tot += gt
        opn = sum(1 for x, v in zip(g["lots"], sub) if v is not None and not (x.get("closed_at") and parse_ts(x["closed_at"]).timestamp() <= t))
        if opn:
            pos, n_open = gt, n_open + opn
    return tot, pos, n_open


def discipline_row(groups: list, tape: Tape, key: str, now_ts: int, flat_complete: bool, day_total: float) -> dict:
    """One row of the weekly 'be patient' table, from REAL ledger lots (realised) plus the 5s tape (open marks). Read-only.

    Marks after `now_ts` are None (not yet happened). `pos` is the entry still holding any lot at 13:30Z; its P&L includes lots already sold.
    """
    d0 = d0_of(key)
    t13, t18, t_end = d0 + T_MIDDAY_MIN * 60, d0 + T_EVENING_MIN * 60, d0 + HARD_FLAT_MIN * 60
    row = {"trades": len(groups), "day_total_usd": round(day_total, 2), "total_1330_usd": None, "pos": None, "day_low_usd": None, "complete": flat_complete}
    if not groups or not len(tape):
        row["total_1330_usd"] = 0.0 if t13 <= now_ts else None
        return row
    if t13 <= now_ts:
        row["total_1330_usd"] = round(_book_at(groups, t13, tape)[0], 2)
        for g in groups:
            lots = g["lots"]
            ot = min(parse_ts(x["opened_at"]).timestamp() for x in lots)
            still = [x for x in lots if ot <= t13 and (not x.get("closed_at") or parse_ts(x["closed_at"]).timestamp() > t13)]
            if not still:
                continue
            dirn = 1 if lots[0]["side"] == "LONG" else -1
            last_close = max((parse_ts(x["closed_at"]).timestamp() for x in lots if x.get("closed_at")), default=None) if all(x.get("closed_at") for x in lots) else None
            end = min(last_close if last_close else t_end, now_ts)
            gp = lambda t: (sum(v for v in (_lot_state(x, t, tape, tape.last_before(t)) for x in lots) if v is not None))  # noqa: E731
            low, low_ts = None, None
            for k in range(bisect.bisect_left(tape.ts, int(t13)), bisect.bisect_right(tape.ts, int(end))):
                v = gp(tape.ts[k])
                if low is None or v < low:
                    low, low_ts = v, tape.ts[k]
            final = round(sum(float(x["pnl_usd"]) for x in lots if x.get("closed_at") and counted(x)), 2) if all(x.get("closed_at") for x in lots) else (
                round(gp(min(t_end, now_ts)), 2) if min(t_end, now_ts) >= t13 else None)
            row["pos"] = {"side": lots[0]["side"], "entered_at": min(x["opened_at"] for x in lots), "entry": float(lots[0]["entry_price"]),
                          "lots_open": len(still), "pnl_1330": round(gp(t13), 2), "pnl_1800": round(gp(t18), 2) if t18 <= now_ts else None,
                          "pnl_close": final, "low_after_1330": round(low, 2) if low is not None else None,
                          "low_ts": iso(low_ts) if low_ts else None, "dir": dirn}
            break
    first = min(parse_ts(x["opened_at"]).timestamp() for g in groups for x in g["lots"])
    lo, last = None, min(t_end, now_ts)
    for k in range(bisect.bisect_left(tape.ts, int(first)), bisect.bisect_right(tape.ts, int(last))):
        v = _book_at(groups, tape.ts[k], tape)[0]
        if lo is None or v < lo:
            lo = v
    row["day_low_usd"] = round(min(lo, 0.0), 2) if lo is not None else None
    return row


def render_discipline(rows: list) -> list:
    """rows = [(day, row)]; ranked best to worst by the day's final total. Honest about what is a mark and what is booked."""
    def m(v, w=9):
        return f"{'n/a':>{w}}" if v is None else f"{v:>+{w}.0f}"
    out = ["   THE DISCIPLINE TABLE — this week's days, best → worst (normal robot, no early cut; REAL ledger + 5s tape)",
           "   day         day$  @13:30  trades  open at 13:30Z (side, entered, px, lots)     pos@13:30   pos@18:00   pos@20:40  pos-low>13:30   day-low",
           "   " + "-" * 140]
    for day, r in sorted(rows, key=lambda t: -(t[1].get("day_total_usd") or 0.0)):
        p = r.get("pos")
        if p:
            when = (p["entered_at"] or "")[11:16]
            desc = f"{p['side']:<5} {when}Z {p['entry']:.2f} x{p['lots_open']}"
            tail = f"{m(p['pnl_1330'], 11)} {m(p['pnl_1800'], 11)} {m(p['pnl_close'], 11)} {m(p['low_after_1330'], 14)}"
        else:
            desc = "flat"
            tail = f"{'-':>11} {'-':>11} {'-':>11} {'-':>14}"
        flag = "" if r.get("complete") else "  (provisional)"
        out.append(f"   {day}  {m(r['day_total_usd'], 7)} {m(r['total_1330_usd'], 7)}  {r['trades']:>6}  {desc:<45} {tail} {m(r.get('day_low_usd'), 9)}{flag}")
    out += ["   Reading: pos columns are ONE position's total (lots already sold at +37.5 included); marks are 'if flattened now' (half-tick spread + $1.50/lot);",
            "   day-low is the deepest the whole day's book (booked + open) sat at any 5s bar. The point of the table: even the good days sat red first. Do not intervene."]
    return out


# ── the weekly pack ─────────────────────────────────────────────────────────────────────────────────────────────────────
def iso_week(day: dt.date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def load_day_reports(env: Env) -> list:
    out = []
    try:
        names = sorted(os.listdir(env.out))
    except Exception:
        return out
    for n in names:
        if len(n) == 15 and n.endswith(".json") and n[4] == "-" and n[7] == "-":
            r = jload(f"{env.out}/{n}")
            if r and r.get("schema") == SCHEMA:
                out.append(r)
    return out


NOT_A_DAY = ("NO_SESSION", "NO_SLOTS_DUE", "POISONED_RECORD", "COVERAGE", "LOST_SLOTS", "LOG_UNREADABLE")


def countable(d: dict) -> bool:
    """Law L7: a poisoned day is not a day. A day the robot was not running is not a day of the strategy either."""
    return not any(h["code"] in NOT_A_DAY for h in d.get("health", []))


def arm_stats(days: list) -> dict:
    """Per-arm session table. A day with no entries is a $0 day, not a missing one — consistency (Law 0) needs the zeros."""
    days = [d for d in days if countable(d)]
    nets = [round(d["totals"]["ledger_net_usd"], 2) for d in days]
    n = len(nets)
    if not n:
        return {"days": 0}
    mean = statistics.mean(nets)
    sd = statistics.pstdev(nets) if n > 1 else 0.0
    return {"days": n, "net_usd": round(sum(nets), 2), "mean_usd_day": round(mean, 2), "median_usd_day": round(statistics.median(nets), 2),
            "days_positive": sum(1 for x in nets if x > 0), "worst_day": min(nets), "best_day": max(nets),
            "cv": (round(sd / abs(mean), 2) if mean else None), "entries": sum(d["totals"]["filled"] for d in days),
            "winners": sum(d["totals"]["winners"] for d in days),
            "manual_exit_entries": sum(d["totals"].get("manual_exit_entries", 0) for d in days), "daily": {d["key"]: d["totals"]["ledger_net_usd"] for d in days}}


def pooled_cf(days: list) -> dict:
    """Pooled counterfactuals over the arm: the target grid on REAL entries, and the mean cf@37.5 by candidate category."""
    grid: dict = {}
    n_p = 0
    days = [d for d in days if countable(d)]
    for d in days:
        for p in d["presses"]:
            if p.get("filled") and p.get("grid_usd") and not p.get("provisional"):
                n_p += 1
                for k, v in p["grid_usd"].items():
                    grid[k] = grid.get(k, 0.0) + v
    cats: dict = {}
    for d in days:
        for c in d["candidates"]:
            g = c["cf_grid_usd"].get(str(CHAMPION_PT))
            if g is None:
                continue
            b = cats.setdefault(c["category"], {"n": 0, "sum": 0.0, "reached": 0})
            b["n"] += 1
            b["sum"] += g
            b["reached"] += 1 if c["cf_reached_champion"] else 0
    return {"real_entries": n_p, "grid_total_usd": {k: round(v, 2) for k, v in grid.items()},
            "grid_per_entry_usd": {k: round(v / n_p, 2) for k, v in grid.items()} if n_p else {},
            "by_category": {k: {"n": v["n"], "mean_cf37_usd": round(v["sum"] / v["n"], 2), "reached_pct": round(100 * v["reached"] / v["n"], 0)} for k, v in cats.items()}}


def shortlist(arm: str, stats: dict, cf: dict) -> list:
    """RANKED, never applied. Each item: the change, the point estimate, n, a status, and the law that governs trying it."""
    items = []
    n = cf["real_entries"]
    grid = cf["grid_per_entry_usd"]
    champ = grid.get(str(CHAMPION_PT))
    if champ is not None:
        best_t = max((k for k in grid if k != str(CHAMPION_PT)), key=lambda k: grid[k], default=None)
        if best_t is not None:
            delta = grid[best_t] - champ
            items.append({"rank_key": delta * max(n, 1), "change": f"all-four-lots target {CHAMPION_PT}pt → {best_t}pt",
                          "point_estimate": f"{delta:+.1f} $/entry ideal-fill vs the shipped {CHAMPION_PT}pt (replayed on the {n} real entries)",
                          "n": n, "status": ("PROMISING" if delta > 0 and n >= MIN_N_PROMISING else "UNDERPOWERED" if delta > 0 else "NOT BETTER"),
                          "governance": "ONE rule per iteration (L2); start from the champion verbatim (L1); a challenger must DOMINATE on days-positive, worst day and CV before $/day counts (L4). A target change is a rider-config change, not a brief change."})
    bc = cf["by_category"]
    wl = [bc[k] for k in ("PRESSED", "SKIPPED_HOLDING", "SKIPPED_OTHER") if k in bc]
    nwl = [bc[k] for k in ("NOT_WITH_LEG", "NO_DETECTOR_LEG") if k in bc]
    if wl and nwl:
        a = sum(x["mean_cf37_usd"] * x["n"] for x in wl) / sum(x["n"] for x in wl)
        b = sum(x["mean_cf37_usd"] * x["n"] for x in nwl) / sum(x["n"] for x in nwl)
        nn = sum(x["n"] for x in nwl)
        items.append({"rank_key": (b - a) * nn, "change": "REMOVE the detector-leg filter (take Claude entries against the leg too)",
                      "point_estimate": f"against-the-leg entries average {b:+.1f} $/entry counterfactual vs {a:+.1f} for with-the-leg",
                      "n": nn, "status": ("PROMISING" if b > a and nn >= MIN_N_PROMISING else "UNDERPOWERED" if b > a else "FILTER EARNING ITS KEEP"),
                      "governance": "The detector is FROZEN (sha af0ace53e6dc9faa); this tests whether it should remain a FILTER. Not a detector change."})
    if "VETOED_BEFORE_05_PARIS" in bc:
        v = bc["VETOED_BEFORE_05_PARIS"]
        items.append({"rank_key": 0.0, "change": "05:00 Paris veto earlier/removed — PARKED BY THE OPERATOR 2026-10-14 (data only)",
                      "point_estimate": f"vetoed entries average {v['mean_cf37_usd']:+.1f} $/entry counterfactual (reached the target {v['reached_pct']:.0f}%)",
                      "n": v["n"], "status": "PARKED (operator: leave it for now)", "governance": "Not to be proposed unless the operator reopens it."})
    if "SKIPPED_HOLDING" in bc:
        v = bc["SKIPPED_HOLDING"]
        items.append({"rank_key": 0.0, "change": "stack a second position while the rider is holding (flat-only is the current rule)",
                      "point_estimate": f"entries skipped because the rider was busy average {v['mean_cf37_usd']:+.1f} $/entry counterfactual",
                      "n": v["n"], "status": "DATA ONLY — the rider cannot take a second entry while holding (BUY-while-holding is a known-open bug)", "governance": "Needs a rider change; operator-only."})
    items.sort(key=lambda x: -x["rank_key"])
    for i, it in enumerate(items, 1):
        it["rank"] = i
        it.pop("rank_key", None)
    return items


def build_week(env: Env, day: dt.date, now: dt.datetime) -> dict:
    wk = iso_week(day)
    reps = load_day_reports(env)
    arms: dict = {}
    for a in sorted({r["arm"] for r in reps}):
        mine = [r for r in reps if r["arm"] == a]
        wk_days = [r for r in mine if iso_week(dt.date.fromisoformat(r["key"])) == wk]
        cum_cf = pooled_cf(mine)
        arms[a] = {"this_week": arm_stats(wk_days), "cumulative": arm_stats(mine), "cumulative_cf": cum_cf,
                   "shortlist": shortlist(a, arm_stats(mine), cum_cf),
                   "discipline_this_week": {r["key"]: r.get("discipline") for r in wk_days if countable(r)},
                   "health_this_week": {r["key"]: r["verdict"] for r in wk_days},
                   "calls_this_week": sum(r["calls"]["n"] for r in wk_days),
                   "errors_this_week": sum(r["calls"]["errors"] for r in wk_days)}
    return {"schema": SCHEMA, "generated_at": now.isoformat(), "week": wk, "arms": arms,
            "policy": ["v1.02 and v1.02-EXT are separate arms and are NEVER pooled.",
                       "Nothing here is applied. The brief (BRIEF_V2) and the detector (K=11xATR14) stay frozen; a retune is Saturday-only, one rule per iteration, gated by bible.gate.",
                       "n is the number of REAL entries, not days: below 10 every counterfactual is UNDERPOWERED and a ranking is a story about noise (L10: counts before dollars).",
                       "Counterfactuals are ideal-fill on the 5s tape; the paper engine's 0.1% adverse fill on lots 2-4 flatters the real book and is not in them."]}


def render_week(w: dict) -> str:
    out = [f"HYBRID ROBOT — WEEKLY PACK {w['week']}  (generated {w['generated_at']})", ""]
    for a, v in w["arms"].items():
        for lbl in ("this_week", "cumulative"):
            s = v[lbl]
            if not s.get("days"):
                out.append(f"ARM {a} · {lbl}: no sessions")
                continue
            out.append(f"ARM {a} · {lbl}: {s['days']} session(s), {s['entries']} entr{'y' if s['entries'] == 1 else 'ies'}, net ${s['net_usd']:+.2f}  "
                       f"({s['manual_exit_entries']} closed by the operator's hands) mean ${s['mean_usd_day']:+.2f}/day · median ${s['median_usd_day']:+.2f} · positive {s['days_positive']}/{s['days']} · worst ${s['worst_day']:+.2f} · best ${s['best_day']:+.2f} · CV {s['cv']}")
        cf = v["cumulative_cf"]
        out.append(f"   target grid on {cf['real_entries']} real entr(ies), $/entry ideal: " + "  ".join(f"{k}pt:{x:+.0f}" for k, x in cf["grid_per_entry_usd"].items()))
        out.append("   candidates by category (mean cf@37.5 $/entry, n, reached%): " + " · ".join(f"{k} {x['mean_cf37_usd']:+.0f} n={x['n']} {x['reached_pct']:.0f}%" for k, x in cf["by_category"].items()))
        out.append(f"   health this week: {v['health_this_week']} · Claude calls {v['calls_this_week']} (errors {v['errors_this_week']})")
        dis = [(k, r) for k, r in (v.get("discipline_this_week") or {}).items() if r]
        if dis:
            out += ["", *render_discipline(dis), ""]
        elif v.get("discipline_this_week"):
            out.append("   (discipline table: this week's day reports predate it; re-run `hybrid_nightly.py --day <d> --quiet` to fill it in)")
        out.append("   RANKED SHORTLIST FOR SATURDAY (never applied):")
        for it in v["shortlist"]:
            out.append(f"     {it['rank']}. [{it['status']}] {it['change']} — {it['point_estimate']} (n={it['n']})")
            out.append(f"         {it['governance']}")
        out.append("")
    out += [f"policy: {p}" for p in w["policy"]]
    return "\n".join(out) + "\n"


# ── output and paging ───────────────────────────────────────────────────────────────────────────────────────────────────
def atomic_write(env: Env, name: str, text: str) -> str:
    """The ONLY write path in this module, and it can only write inside env.out. tmp + os.replace, so a root-owned old file is harmless."""
    path = os.path.join(env.out, name)
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(env.out):
        raise ValueError(f"refusing to write outside {env.out}: {name}")
    os.makedirs(env.out, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


def page_faults(env: Env, rep: dict, send=None) -> list:
    """Critical-page each FAULT once per (session, code). Returns the codes paged. A paging failure never fails the review."""
    faults = [h for h in rep["health"] if h["sev"] == "FAULT"]
    if not faults:
        return []
    paged = jload(f"{env.out}/paged.json") or {}
    seen = set(paged.get(rep["key"], []))
    new = [h for h in faults if h["code"] not in seen]
    if not new:
        return []
    msg = (f"HYBRID ROBOT v{rep['version']} [{rep['arm']}] — {len(new)} FAULT(S) in the {rep['key']} review\n"
           + "\n".join(f"• {h['code']}: {h['msg']}" for h in new)
           + "\nNothing was auto-repaired. Detail: reports/hybrid_nightly/" + rep["key"] + ".txt")
    try:
        if send is None:
            from gazbot7.notify import notify
            send = lambda m: notify(m, critical=True)  # noqa: E731
        ok = send(msg)
    except Exception:
        return []
    if ok is False:   # notify() returns False when suppressed or failed (never raises) — do not mark a page that did not go out
        return []
    paged[rep["key"]] = sorted(seen | {h["code"] for h in new})
    keep = sorted(paged)[-30:]
    atomic_write(env, "paged.json", json.dumps({k: paged[k] for k in keep}, indent=1))
    return [h["code"] for h in new]


def default_day(now: dt.datetime) -> str:
    """The most recent session whose window has ended. Before 20:00Z that is yesterday; the EXT window ends 19:55Z."""
    d = now.date()
    if now.hour < 20:
        d -= dt.timedelta(days=1)
    return d.isoformat()


def run(env: Env, key: str, now: dt.datetime, quiet: bool = False, send=None, week_only: bool = False) -> dict:
    rep = None
    if not week_only and dt.date.fromisoformat(key) >= H.START_AFTER.date():   # nothing to review before the hybrid existed
        rep = review_day(env, key, now)
        atomic_write(env, f"{key}.json", json.dumps(rep, indent=1, default=str))
        atomic_write(env, f"{key}.txt", render_day(rep))
    day = dt.date.fromisoformat(key)
    wk = build_week(env, day, now)
    atomic_write(env, f"week_{wk['week']}.json", json.dumps(wk, indent=1, default=str))
    atomic_write(env, f"week_{wk['week']}.txt", render_week(wk))
    atomic_write(env, "LATEST_WEEK.txt", render_week(wk))
    paged: list = []
    if rep is not None:
        latest = {"schema": SCHEMA, "generated_at": now.isoformat(), "key": key, "arm": rep["arm"], "verdict": rep["verdict"],
                  "faults": [h for h in rep["health"] if h["sev"] == "FAULT"], "warns": [h for h in rep["health"] if h["sev"] == "WARN"],
                  "infos": [h["code"] for h in rep["health"] if h["sev"] == "INFO"],
                  "net_usd": rep["totals"]["ledger_net_usd"], "entries": rep["totals"]["filled"], "decided": rep["coverage"]["decided"],
                  "expected": rep["coverage"]["expected"], "week_pack": f"reports/hybrid_nightly/week_{wk['week']}.txt"}
        if key == default_day(now):           # a back-dated manual run must not masquerade as last night's review
            atomic_write(env, "latest.json", json.dumps(latest, indent=1))
        if not quiet:
            paged = page_faults(env, rep, send)
    return {"report": rep, "week": wk, "paged": paged}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="session key YYYY-MM-DD (default: the latest session whose window has ended)")
    ap.add_argument("--quiet", action="store_true", help="analyse and write, never page")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--week-only", action="store_true")
    a = ap.parse_args()
    now = dt.datetime.now(UTC)
    key = a.day or default_day(now)
    try:
        res = run(Env(), key, now, quiet=a.quiet, week_only=a.week_only)
    except Exception as e:  # noqa: BLE001  a crashed review must be loud, not a silent green: exit 2 and no latest.json refresh
        print("HYBRID NIGHTLY CRASHED", repr(e))
        return 2
    rep = res["report"]
    if a.json:
        print(json.dumps(rep, indent=1, default=str))
    elif rep:
        print(render_day(rep))
    print(f"paged: {res['paged']}")
    return 3 if (rep and rep["verdict"] == "FAULT") else 0


if __name__ == "__main__":
    sys.exit(main())
