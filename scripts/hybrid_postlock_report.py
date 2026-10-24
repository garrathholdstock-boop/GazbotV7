#!/usr/bin/env python
"""GAZBOT V8 ROBO v1.02 — THE NIGHTLY "LIVE TO THE LOCK, THEN SIMULATE AFTER" REPORT (E108).

Declared in reports/recursive_loop/E108_change.txt BEFORE any run. Operator, 2026-10-24: simulate what happens if the desk does not stop at the +$1,000 lock,
every night at close, report in the morning, and a weekly pack including everything. The desk is untouched.

ZERO Claude tokens. The simulate-after is NOT re-run here: the forward E104 shadows (v1.02-LOCKSHADOW after the lock, v1.02-PM-shadow 13:30-19:55Z) already
are that simulation, collected at the live cadence. This COMBINES, per session, three things that already exist on disk:
  LIVE to the lock  (hybrid_nightly's ledger-attributed presses before the first DAY_LOCK; no lock -> the whole live window)
  + LOCKSHADOW      (would-be entries after the lock)   + PM-shadow (afternoon).
Beside it: LIVE AS IT RAN. Counts first, dollars second, n labelled per arm, arms listed separately. Sim = ideal fills, live = paper fills (stated in the output).

  hybrid_postlock_report.py [--day YYYY-MM-DD]     write the session report + week pack
  hybrid_postlock_report.py --morning              the 06:10 Paris Telegram (non-critical; critical only if last night's report is missing)

⚠⚠⚠ READ-ONLY. Writes only reports/hybrid_postlock/*. Reads JSON/JSONL reports and the robot's log; opens no database, has no broker call, no request or switch
file. The only side effect outside its folder is the morning notify(). tests/test_hybrid_postlock_report.py asserts that against the AST.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

GB = "/home/alphabot/gazbot7"
UTC = dt.timezone.utc
OUT_DIR = f"{GB}/reports/hybrid_postlock"
NIGHTLY_DIR = f"{GB}/reports/hybrid_nightly"
SHADOW_DIR = f"{GB}/reports/hybrid_shadow"
LOSERS_LATEST = f"{GB}/reports/hybrid_losers/LATEST.txt"
ROBOT_LOG = f"{GB}/data/hybrid_robot.jsonl"
LIVE_WINDOW_END = "13:30"          # the live robot's last decision window closes here
FINISHED_AFTER_MIN = 20 * 60 + 45  # a session is finished (flat 20:40Z + grace) after this UTC minute
MIN_N_PROMISING, MIN_N_FIT = 10, 30
ARMS = (("LOCK", "v1.02-LOCKSHADOW"), ("PM", "v1.02-PM-shadow"))


def _read(path: str):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def default_day(now: dt.datetime) -> str:
    d = now.date()
    return (d if now.hour * 60 + now.minute >= FINISHED_AFTER_MIN else d - dt.timedelta(days=1)).isoformat()


def prev_weekday(today: dt.date) -> dt.date:
    d = today - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def tag(n: int) -> str:
    return "NO DATA" if n == 0 else "UNDERPOWERED (n<10)" if n < MIN_N_PROMISING else "n<30: NO FITTING, NO DECISION" if n < MIN_N_FIT else "n>=30"


def lock_events(day: str, log_path: str = ROBOT_LOG) -> list:
    out = []
    try:
        f = open(log_path)
    except FileNotFoundError:
        return out
    with f:
        for ln in f:
            if '"DAY_LOCK"' not in ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("event") == "DAY_LOCK" and str(r.get("at", "")).startswith(day):
                out.append({"decision_ts": r.get("decision_ts"), "touched_at": r.get("touched_at"), "peak": r.get("peak"), "equity_now": r.get("equity_now")})
    return sorted(out, key=lambda r: str(r["decision_ts"]))


def _hm(ts: str) -> str:
    return str(ts)[11:16]


def live_side(nightly: dict | None, locks: list) -> dict:
    presses = [p for p in (nightly or {}).get("presses", []) if p.get("filled")]
    cut = locks[0]["decision_ts"] if locks else None
    rows = [{"t": _hm(p["decision_ts"]), "decision_ts": p["decision_ts"], "side": p.get("side"), "usd": round(float(p.get("ledger_net_usd") or 0.0), 2)} for p in presses]
    rows.sort(key=lambda r: r["decision_ts"])
    pre = [r for r in rows if cut is None or r["decision_ts"] < cut]
    leak = [r for r in rows if cut is not None and r["decision_ts"] >= cut]
    return {"cut": cut and _hm(cut), "cut_label": f"first DAY_LOCK {_hm(cut)}Z" if cut else f"no lock; live window ends {LIVE_WINDOW_END}Z",
            "to_cut": {"entries": len(pre), "usd": round(sum(r["usd"] for r in pre), 2), "list": pre},
            "as_ran": {"entries": len(rows), "usd": round(sum(r["usd"] for r in rows), 2)},
            "after_lock_live_presses": leak}


def arm_side(shadow: dict | None, arm: str) -> dict:
    a = ((shadow or {}).get("arms") or {}).get(arm)
    if not a:
        return {"status": "NO_DATA", "n": 0, "hits": 0, "misses": 0, "usd": 0.0, "list": [], "coverage": "0/0 slots", "poisoned": False}
    ents = a.get("entries") or []
    return {"status": a.get("status", "NO_DATA"), "n": len(ents), "hits": sum(1 for e in ents if e.get("hit")), "misses": sum(1 for e in ents if not e.get("hit")),
            "usd": round(sum(float(e.get("net_usd") or 0) for e in ents), 2),
            "list": [{"t": _hm(e["decision_ts"]), "side": e.get("side"), "hit": bool(e.get("hit")), "usd": round(float(e.get("net_usd") or 0), 2), "mae_pt": e.get("mae_pt")} for e in ents],
            "coverage": f"{a.get('slots_made', 0)}/{a.get('slots_expected', 0)} slots", "poisoned": bool(a.get("poisoned")), "calls": a.get("calls"), "errors": a.get("errors")}


def build_day(day: str, nightly: dict | None, shadow: dict | None, locks: list, generated_at: str) -> dict:
    d = dt.date.fromisoformat(day)
    live = live_side(nightly, locks)
    arms = {k: arm_side(shadow, k) for k, _ in ARMS}
    flags = []
    if d.weekday() >= 5:
        flags.append("NO_SESSION")
    if nightly is None and d.weekday() < 5:
        flags.append("NIGHTLY_MISSING")
    if live["after_lock_live_presses"]:
        flags.append(f"LOCK_LEAK x{len(live['after_lock_live_presses'])}")
    if len(locks) > 1:
        flags.append(f"LOCK_RELATCH x{len(locks)}")
    if locks and arms["LOCK"]["status"] == "NO_DATA" and shadow is not None:
        flags.append("SHADOW_MISSING_LOCK_ARM")
    for k, a in arms.items():
        if a["poisoned"]:
            flags.append(f"POISONED_{k}")
    if shadow and shadow.get("partial_tape"):
        flags.append("PARTIAL_TAPE")
    if shadow is None and d.weekday() < 5:
        flags.append("SHADOW_RECORD_MISSING")
    sim_poisoned = any(a["poisoned"] for a in arms.values())
    sim_usd = sum(a["usd"] for a in arms.values() if not a["poisoned"])
    sim_n = sum(a["n"] for a in arms.values() if not a["poisoned"])
    comb = {"entries": live["to_cut"]["entries"] + sim_n, "usd": round(live["to_cut"]["usd"] + sim_usd, 2), "sim_entries": sim_n, "sim_usd": round(sim_usd, 2),
            "delta_vs_live_as_ran": round(live["to_cut"]["usd"] + sim_usd - live["as_ran"]["usd"], 2), "sim_arms_scored": not sim_poisoned}
    return {"schema": 1, "generated_at": generated_at, "day": day, "weekday": d.strftime("%a"), "locks": locks, "live": live, "arms": arms, "combined": comb, "flags": flags}


def render_day(r: dict) -> str:
    if "NO_SESSION" in r["flags"]:
        return f"E108 {r['day']} ({r['weekday']}): no session (weekend).\n"
    lv, c = r["live"], r["combined"]
    L = [f"E108 POST-LOCK REPORT {r['day']} ({r['weekday']}) - counts first, then dollars. Live = paper fills; sim arms = IDEAL fills, 4 lots all out at +37.5pt, no stop, 20:40Z flat, $6 fee.",
         "Arms are listed separately and never pooled into a decision; COMBINED is a narrative line. Nothing here is a decision below 30 would-be entries per arm.", ""]
    L.append(f"LIVE   to cut [{lv['cut_label']}]: {lv['to_cut']['entries']} entries  ${lv['to_cut']['usd']:,.0f}   | live AS IT RAN: {lv['as_ran']['entries']} entries  ${lv['as_ran']['usd']:,.0f}")
    for k, name in ARMS:
        a = r["arms"][k]
        L.append(f"SIM    {name:18s} [{tag(a['n'])}] {a['n']} entries ({a['hits']} hit / {a['misses']} miss)  ${a['usd']:,.0f}   status {a['status']}, coverage {a['coverage']}"
                 + ("   POISONED - NOT SCORED" if a["poisoned"] else ""))
        if a["list"]:
            L.append("         " + "; ".join(f"{e['t']}Z {e['side']} {'HIT' if e['hit'] else 'MISS'} ${e['usd']:,.0f} (MAE {e['mae_pt']}pt)" for e in a["list"]))
    if "SHADOW_RECORD_MISSING" in r["flags"]:
        L.append(f"COMBINED: sim arms unavailable for this day (no shadow record); live to cut ${lv['to_cut']['usd']:,.0f} vs live as it ran ${lv['as_ran']['usd']:,.0f}")
    else:
      L.append(f"COMBINED (live to cut + sims): {c['entries']} entries  ${c['usd']:,.0f}    vs live as it ran ${lv['as_ran']['usd']:,.0f}   => lock {'cost' if c['delta_vs_live_as_ran'] > 0 else 'saved'} ${abs(c['delta_vs_live_as_ran']):,.0f}"
             if r["locks"] else
             f"COMBINED (no lock today: live window + PM sim): {c['entries']} entries  ${c['usd']:,.0f}    vs live as it ran ${lv['as_ran']['usd']:,.0f}   => PM sim adds ${c['delta_vs_live_as_ran']:,.0f}")
    if lv["to_cut"]["list"]:
        L.append("LIVE entries to cut: " + "; ".join(f"{e['t']}Z {e['side']} ${e['usd']:,.0f}" for e in lv["to_cut"]["list"]))
    if lv["after_lock_live_presses"]:
        L.append("!! LOCK_LEAK - live presses AFTER the lock (the lock should have stopped these): " + "; ".join(f"{e['t']}Z {e['side']} ${e['usd']:,.0f}" for e in lv["after_lock_live_presses"]))
    L.append("FLAGS: " + (", ".join(r["flags"]) or "none"))
    L.append("CAVEAT: n is days x arm shown above; a one-day sim is a story, not a result. Sims start flat at their window and do not inherit a live open position.")
    return "\n".join(L) + "\n"


def iso_week(day: str) -> str:
    y, w, _ = dt.date.fromisoformat(day).isocalendar()
    return f"{y}-W{w:02d}"


def week_days(day: str, out_dir: str = OUT_DIR) -> list:
    wk = iso_week(day)
    res = []
    try:
        names = sorted(n for n in os.listdir(out_dir) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", n))
    except FileNotFoundError:
        names = []
    for n in names:
        r = _read(os.path.join(out_dir, n))
        if r and iso_week(r["day"]) == wk and r["day"] <= day and "NO_SESSION" not in r["flags"]:
            res.append(r)
    return res


def _head(path: str, n: int) -> list:
    try:
        return open(path).read().splitlines()[:n]
    except Exception:
        return []


def render_week(day: str, days: list) -> str:
    L = [f"E108 WEEKLY PACK {iso_week(day)} (through {day}) - everything in one place. Counts first, then dollars; arms never pooled into a decision.", ""]
    L.append(f"{'day':11s} {'lock':>6s} | LIVE to cut {'ent':>3s} {'$':>7s} | LOCKSHADOW {'n':>2s} {'$':>7s} | PM-shadow {'n':>2s} {'$':>7s} | COMBINED {'ent':>3s} {'$':>8s} | live as ran {'$':>7s} | flags")
    tl = tc = tr = 0.0
    n_lock = n_pm = n_leak = 0
    for r in days:
        lv, c, a_l, a_p = r["live"], r["combined"], r["arms"]["LOCK"], r["arms"]["PM"]
        L.append(f"{r['day']:11s} {(lv['cut'] or '-'):>6s} | {'':11s}{lv['to_cut']['entries']:>3d} {lv['to_cut']['usd']:>7,.0f} | {'':10s}{a_l['n']:>2d} {a_l['usd']:>7,.0f} | {'':9s}{a_p['n']:>2d} {a_p['usd']:>7,.0f} | {'':8s}{c['entries']:>3d} {c['usd']:>8,.0f} | {'':11s}{lv['as_ran']['usd']:>7,.0f} | {','.join(r['flags']) or '-'}")
        tl += lv["to_cut"]["usd"]; tc += c["usd"]; tr += lv["as_ran"]["usd"]
        n_lock += a_l["n"]; n_pm += a_p["n"]; n_leak += len(lv["after_lock_live_presses"])
    L.append(f"{'WEEK':11s} {'':6s} | live to cut ${tl:,.0f} | LOCKSHADOW n={n_lock} [{tag(n_lock)}] | PM-shadow n={n_pm} [{tag(n_pm)}] | COMBINED ${tc:,.0f} | live as ran ${tr:,.0f}")
    L.append(f"days {len(days)}; live presses after a lock: {n_leak}")
    L.append("")
    L.append("--- SHADOW ARMS (cumulative, reports/hybrid_shadow/SUMMARY.txt) ---")
    L += _head(os.path.join(SHADOW_DIR, "SUMMARY.txt"), 40) or ["(missing)"]
    L.append("")
    L.append("--- NIGHTLY WEEK SHORTLIST (reports/hybrid_nightly/LATEST_WEEK.txt, head) ---")
    L += _head(os.path.join(NIGHTLY_DIR, "LATEST_WEEK.txt"), 30) or ["(missing)"]
    L.append("")
    L.append("--- SATURDAY LOSERS STUDY (reports/hybrid_losers/LATEST.txt, head) ---")
    L += _head(LOSERS_LATEST, 30) or ["(not produced yet - the Saturday losers timer writes it)"]
    return "\n".join(L) + "\n"


def atomic_write(name: str, text: str, out_dir: str = OUT_DIR) -> str:
    path = os.path.join(out_dir, name)
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(out_dir):
        raise ValueError(f"refusing to write outside {out_dir}: {name}")
    os.makedirs(out_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


def run(day: str, now: dt.datetime, out_dir: str = OUT_DIR) -> dict:
    nightly = _read(os.path.join(NIGHTLY_DIR, f"{day}.json"))
    shadow = _read(os.path.join(SHADOW_DIR, f"{day}.json"))
    r = build_day(day, nightly, shadow, lock_events(day), now.isoformat())
    js, tx = json.dumps(r, indent=1, default=str), render_day(r)
    atomic_write(f"{day}.json", js, out_dir)
    atomic_write(f"{day}.txt", tx, out_dir)
    if now.date().isoformat() == day or default_day(now) == day:
        if "NO_SESSION" not in r["flags"]:
            atomic_write("latest.json", js, out_dir)
    wk = week_days(day, out_dir)
    atomic_write(f"week_{iso_week(day)}.json", json.dumps(wk, indent=1, default=str), out_dir)
    wtx = render_week(day, wk)
    atomic_write(f"week_{iso_week(day)}.txt", wtx, out_dir)
    atomic_write("LATEST_WEEK.txt", wtx, out_dir)
    return r


def morning_text(r: dict, today: dt.date, week_txt: str | None) -> str:
    lv, c = r["live"], r["combined"]
    a_l, a_p = r["arms"]["LOCK"], r["arms"]["PM"]
    lines = [f"Post-lock sim {r['day']} ({r['weekday']}): LIVE to {('lock ' + lv['cut'] + 'Z') if lv['cut'] else 'window end'} {lv['to_cut']['entries']} ent ${lv['to_cut']['usd']:,.0f}"
             f" | after-lock sim {a_l['n']} ent ${a_l['usd']:,.0f} | PM sim {a_p['n']} ent ${a_p['usd']:,.0f}"
             f" | COMBINED {c['entries']} ent ${c['usd']:,.0f} vs live as ran ${lv['as_ran']['usd']:,.0f}.",
             f"n: lock-arm {a_l['n']} [{tag(a_l['n'])}], PM {a_p['n']} [{tag(a_p['n'])}]. Sim = ideal fills."]
    if r["flags"]:
        lines.append("FLAGS: " + ", ".join(r["flags"]))
    if today.weekday() == 5 and week_txt:
        wk = [ln for ln in week_txt.splitlines() if ln.startswith("WEEK") or ln.startswith("days ")]
        lines.append("WEEK: " + " ".join(wk))
        lines.append("Full pack: reports/hybrid_postlock/LATEST_WEEK.txt; losers study: reports/hybrid_losers/LATEST.txt")
    return "\n".join(lines)


def morning(now: dt.datetime, out_dir: str = OUT_DIR, send=None) -> int:
    today = now.date()
    if today.weekday() in (6, 0):          # Sunday/Monday: nothing new to report (Saturday carried the week)
        return 0
    if send is None:
        sys.path.insert(0, f"{GB}/src")
        from gazbot7.notify import notify as send  # noqa: E402
    want = prev_weekday(today).isoformat()
    r = _read(os.path.join(out_dir, "latest.json"))
    if not r or r.get("day") != want:
        send(f"Post-lock sim report MISSING for {want} (latest on disk: {r and r.get('day')}). hybrid-postlock did not run or failed.", critical=True)
        return 1
    ok = send(morning_text(r, today, _head_text(os.path.join(out_dir, "LATEST_WEEK.txt"))), critical=False)
    return 0 if ok is not False else 0


def _head_text(path: str) -> str | None:
    try:
        return open(path).read()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--morning", action="store_true")
    a = ap.parse_args()
    now = dt.datetime.now(UTC)
    if a.morning:
        return morning(now)
    r = run(a.day or default_day(now), now)
    print(render_day(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
