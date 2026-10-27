#!/usr/bin/env python
"""HYBRID NEAR MISSES - nightly (operator 2026-10-27: "it would need to buy on a sharp break where it can bank quickly ... Can you measure
each night the near misses?"). Read-only, zero Claude tokens.

For every live 5-min decision of the session where the desk was FLAT and an entry could have been traded (after the veto, a detector MIL
in force), price what an entry IN THE MIL'S DIRECTION at that decision would have done on the real 1-min tape, exactly like a press:
fill = last closed bar +/- half spread, target +37.5 (trade-through 0.25), no stop, flat at 20:40Z. Then sort Claude's WAITs (and ENTERs the
votes blocked) into:
    QUICK  - hit the target within 60 min                     -> a NEAR MISS (what the operator wants caught)
    SLOW   - hit later but before the US open (13:30Z)
    LATE   - hit only after 13:30Z (rode the US session)       -> a DODGE in spirit: it would have sat offside into the US
    LOSS   - never hit by 20:40Z                               -> a DODGE
Both sides are reported: a rule that catches the misses also lets in the dodges. Consecutive calls of one class are one EPISODE.

    PYTHONPATH=src .venv/bin/python scripts/hybrid_near_misses.py [--day YYYY-MM-DD] [--no-send]
Writes reports/hybrid_near_misses/<day>.json and .txt; sends the summary (non-critical) unless --no-send.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
import hybrid_robot as H  # noqa: E402
import leg_robot as L  # noqa: E402
import mil_labels as ML  # noqa: E402

UTC = dt.timezone.utc
OUT = f"{GB}/reports/hybrid_near_misses"
TARGET, THRU, ADV = 37.5, 0.25, H.S.HALF_SPREAD_PT
QUICK_MIN = 60
BUCKETS = f"{OUT}/buckets.json"   # per session, per wait-reason bucket: stretches missed (fast winners) vs dodged (losers / rode the US)
ROLL = 5                          # sessions in the rolling read
LOOSEN_DAYS, LOOSEN_NET, LOOSEN_RATIO = 3, 500, 2.0   # a bucket is a LOOSEN CANDIDATE when all three hold over the rolling sessions
FLAT = (20, 40)
WIN_USD = H.QTY * H.PV * TARGET - H.QTY * 1.5
TAGS = [("time-left", r"minutes? (remain|left|to the US|before the US)|US open|US session|rides? the US"),
        ("no-progress", r"no net progress|stalled|stalling|sideways|chop|range|going nowhere|not (clearly )?driving|isn't driving|not driving"),
        ("repeat", r"repeat"),
        ("bounce/counter", r"bounce|counter-leg|pullback|pulled back"),
        ("impulse/no-pause", r"impulsive|flush|no pause|no sign of (the leg )?stalling|spike"),
        ("young-leg", r"only \d+ minutes old|young|just (turned|started)|fresh leg"),
        ("veto/not-tradable", r"can't be traded|cannot be traded")]


def tags(reason: str) -> list:
    return [t for t, rx in TAGS if re.search(rx, reason or "", re.I)] or ["other"]


def decisions(key: str) -> list:
    out = []
    for ln in open(H.LOG_FILE):
        if '"DECISION"' not in ln:
            continue
        r = json.loads(ln)
        if r.get("dry") or r.get("event") != "DECISION":
            continue
        op = dt.datetime.fromisoformat(r["decision_ts"])
        if L.session_day(op).isoformat() == key:
            out.append(r)
    return out


def positions(key: str) -> list:
    """(open_ts, close_ts, side) of every real rider position of the session - flagged rows included: a flagged trade still held the rider."""
    d0 = dt.datetime.fromisoformat(key + "T00:00:00+00:00")
    with sqlite3.connect(f"file:{H.LEDGER}?mode=ro", uri=True, timeout=5) as c:
        rows = c.execute("SELECT opened_at, max(closed_at), side FROM trades WHERE gate='day_rider' AND opened_at>=? AND opened_at<? GROUP BY opened_at",
                         ((d0 - dt.timedelta(hours=2)).isoformat(), (d0 + dt.timedelta(hours=22)).isoformat())).fetchall()
    return [(dt.datetime.fromisoformat(a).timestamp(), dt.datetime.fromisoformat(b).timestamp() if b else 9e18, s) for a, b, s in rows]


def outcome(bars: list, op: int, dirn: int, d0: int) -> dict | None:
    """an entry at decision op in direction dirn, priced like the rider: target +37.5, no stop, flat 20:40Z"""
    prior = [b for b in bars if b[0] + 60 <= op]
    if not prior:
        return None
    fill = prior[-1][3] + dirn * ADV
    flat = d0 + FLAT[0] * 3600 + FLAT[1] * 60
    mae, last = 0.0, prior[-1]
    for t, hi, lo, cl in (b for b in bars if op <= b[0] < flat):
        fav = (hi - fill) if dirn > 0 else (fill - lo)
        if fav >= TARGET + THRU:
            mins = (t + 60 - op) / 60
            return {"fill": round(fill, 2), "hit": True, "mins": round(mins), "mae": round(mae, 1), "pnl": round(WIN_USD),
                    "cls": "QUICK" if mins <= QUICK_MIN else ("SLOW" if t + 60 <= d0 + 13 * 3600 + 1800 else "LATE")}
        mae = max(mae, (fill - lo) if dirn > 0 else (hi - fill))
        last = (t, hi, lo, cl)
    pnl = H.QTY * H.PV * dirn * (last[3] - fill) - H.QTY * 1.5
    return {"fill": round(fill, 2), "hit": False, "mins": None, "mae": round(mae, 1), "pnl": round(pnl), "cls": "LOSS"}


def every_chance(key: str, bars: list, series: list, d0: int) -> dict:
    """DETECTOR-ONLY baseline - NO Claude judgment at all: the desk if every tradable call had been an ENTER: one position at a time, re-enter when flat, +$1,000 lock (realised).
    Misses and dodges cannot be summed - taking one changes which others were possible; this path can."""
    busy, tot, path = 0, 0.0, []
    for r in decisions(key):
        op = int(dt.datetime.fromisoformat(r["decision_ts"]).timestamp())
        cut = L.veto_cutoff(op)
        if op < busy or (cut is not None and op < cut) or r.get("error") or tot >= H.LOCK_USD:
            continue
        dirn = H.det_dir(L.confirmed_turns([b for b in series if b[0] + 60 <= op - L.SETTLE_S]), op - 60)
        o = outcome(bars, op, dirn, d0) if dirn else None
        if not o:
            continue
        tot += o["pnl"]
        path.append({"t": r["decision_ts"][11:16], "side": "LONG" if dirn > 0 else "SHORT", "cls": o["cls"], "mins": o["mins"], "pnl": o["pnl"]})
        busy = op + o["mins"] * 60 if o["hit"] else 10 ** 12
    return {"pnl": round(tot), "trades": path, "locked": tot >= H.LOCK_USD}


def actual_pnl(key: str) -> float:
    d0 = dt.datetime.fromisoformat(key + "T00:00:00+00:00")
    with sqlite3.connect(f"file:{H.LEDGER}?mode=ro", uri=True, timeout=5) as c:
        return float(c.execute("SELECT COALESCE(SUM(pnl_usd),0) FROM trades WHERE gate='day_rider' AND opened_at>=? AND opened_at<? "
                               "AND COALESCE(data_quality,'') NOT LIKE 'BADFILL%' AND COALESCE(data_quality,'') NOT LIKE 'EXCLUDE%'",
                               ((d0 - dt.timedelta(hours=2)).isoformat(), (d0 + dt.timedelta(hours=22)).isoformat())).fetchone()[0])


def run(key: str) -> dict:
    d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
    bars = ML.minute_bars(key)
    series = L.series_for(dt.date.fromisoformat(key))
    pos = positions(key)
    rows = []
    for r in decisions(key):
        op = int(dt.datetime.fromisoformat(r["decision_ts"]).timestamp())
        cut = L.veto_cutoff(op)
        held = any(a <= op < b for a, b, _ in pos)
        dirn = H.det_dir(L.confirmed_turns([b for b in series if b[0] + 60 <= op - L.SETTLE_S]), op - 60)
        row = {"t": r["decision_ts"][11:16], "px": r["px"], "action": r["action"], "entry_action": r.get("entry_action"),
               "reason": r.get("reason", ""), "brief": (r.get("brief") or {}).get("version"), "mil": dirn,
               "votes": f"{r['votes']['agree']}/{r['votes']['n']}" if r.get("votes") else None}
        pressed = str(r.get("entry_action") or "").startswith("PRESS_")
        sh = r.get("preveto_shadow")
        if sh and not held and dirn and str(sh.get("action", "")).startswith("ENTER"):     # E125: what the no-veto prompt would have entered
            row["shadow"] = {"action": sh["action"], "votes": (sh.get("votes") or {}).get("agree"), "would_press": sh.get("would_press"),
                             "reason": sh.get("reason", ""), "out": outcome(bars, op, dirn, d0) if sh.get("would_press") else None}
        if held or (cut is not None and op < cut) or not dirn or r.get("error"):
            row["tradable"] = False
        else:
            row["tradable"] = True
            row["kind"] = "TAKEN" if pressed else ("BLOCKED" if r["action"].startswith("ENTER") else "WAIT")
            row["out"] = outcome(bars, op, dirn, d0)
            row["tags"] = tags(row["reason"])
        rows.append(row)
    tr = [x for x in rows if x["tradable"] and x.get("out")]
    eps = []
    for x in tr:
        if x["kind"] == "TAKEN":
            continue
        e = eps[-1] if eps else None
        if e and e["cls"] == x["out"]["cls"] and e["mil"] == x["mil"] and e["last_i"] == rows.index(x) - 1:
            e["n"] += 1; e["last_i"] = rows.index(x); e["end"] = x["t"]; e["tags"] = sorted(set(e["tags"]) | set(x["tags"]))
        else:
            eps.append({"cls": x["out"]["cls"], "mil": x["mil"], "start": x["t"], "end": x["t"], "n": 1, "last_i": rows.index(x), "first": x,
                        "tags": list(x["tags"])})
    by_tag = {}
    for x in tr:
        if x["kind"] == "TAKEN":
            continue
        for t in x["tags"]:
            d = by_tag.setdefault(t, {"QUICK": 0, "SLOW": 0, "LATE": 0, "LOSS": 0})
            d[x["out"]["cls"]] += 1
    cnt = lambda c: sum(1 for x in tr if x["kind"] != "TAKEN" and x["out"]["cls"] == c)
    complete = bool(bars) and bars[-1][0] + 60 >= d0 + FLAT[0] * 3600 + FLAT[1] * 60
    rep = {"day": key, "generated_at": dt.datetime.now(UTC).isoformat(), "decisions": len(rows), "tradable": len(tr), "complete": complete,
           "taken": [{"t": x["t"], "side": "LONG" if x["mil"] > 0 else "SHORT", "votes": x["votes"], **x["out"]} for x in tr if x["kind"] == "TAKEN"],
           "counts": {c: cnt(c) for c in ("QUICK", "SLOW", "LATE", "LOSS")}, "by_tag": by_tag,
           "episodes": [{k: v for k, v in e.items() if k != "last_i"} for e in eps], "rows": rows,
           "every_chance": every_chance(key, bars, series, d0), "actual_pnl": round(actual_pnl(key))}
    return rep


def bucket_day(rep: dict) -> dict:
    """one session's buckets: a stretch counts once in every bucket its calls gave as a reason"""
    out = {}
    for e in rep["episodes"]:
        o = e["first"]["out"]
        for t in e["tags"]:
            b = out.setdefault(t, {"miss": 0, "miss_usd": 0, "dodge": 0, "dodge_usd": 0, "slow": 0})
            if e["cls"] == "QUICK":
                b["miss"] += 1; b["miss_usd"] += o["pnl"]
            elif e["cls"] in ("LATE", "LOSS"):
                b["dodge"] += 1; b["dodge_usd"] += o["pnl"] if e["cls"] == "LOSS" else 0
            else:
                b["slow"] += 1
    return out


def update_buckets(rep: dict) -> dict:
    """store this session (complete days only) and return the rolling read over the last ROLL sessions"""
    try:
        allb = json.load(open(BUCKETS))
    except Exception:
        allb = {}
    desk_brief = any(str(x.get("brief") or "").startswith("D") for x in rep["rows"])    # only Desk Brief sessions tune the Desk Brief
    if rep["complete"] and desk_brief:
        allb[rep["day"]] = {"brief": sorted({x["brief"] for x in rep["rows"] if x.get("brief")}), "buckets": bucket_day(rep)}
        json.dump(allb, open(BUCKETS, "w"), indent=1, sort_keys=True)
    days = sorted(allb)[-ROLL:]
    roll = {}
    for d in days:
        for t, b in allb[d]["buckets"].items():
            R = roll.setdefault(t, {"miss": 0, "miss_usd": 0, "dodge": 0, "dodge_usd": 0, "slow": 0, "days": 0})
            for k in ("miss", "miss_usd", "dodge", "dodge_usd", "slow"):
                R[k] += b[k]
            R["days"] += 1 if b["miss"] else 0
    for t, R in roll.items():
        R["net"] = R["miss_usd"] + R["dodge_usd"]
        R["status"] = ("LOOSEN CANDIDATE" if R["days"] >= LOOSEN_DAYS and R["net"] >= LOOSEN_NET and R["miss"] >= LOOSEN_RATIO * max(R["dodge"], 1)
                       else "KEEP (caution pays)" if R["net"] < 0 else "WATCH")
    return {"sessions": days, "buckets": roll}


def text(rep: dict) -> str:
    c = rep["counts"]
    side = lambda m: "LONG" if m > 0 else "SHORT"
    L_ = [f"🔎 NEAR MISSES {rep['day']} — flat & tradable calls {rep['tradable']} (of {rep['decisions']})"
          + ("" if rep["complete"] else "  ⚠ PARTIAL: the tape stops before 20:40Z, 'never hit' is not final")]
    for t in rep["taken"]:
        L_.append(f"Taken {t['t']} {t['side']} (votes {t['votes'] or '-'}): " + (f"+37.5 in {t['mins']}m" if t["hit"] else f"no hit, ${t['pnl']:+,}"))
    L_.append(f"Not taken: {c['QUICK']} would have banked within {QUICK_MIN}m · {c['SLOW']} by 13:30Z · {c['LATE']} only in the US session · {c['LOSS']} never")
    miss = [e for e in rep["episodes"] if e["cls"] == "QUICK"]
    dodge = [e for e in rep["episodes"] if e["cls"] in ("LATE", "LOSS")]
    if miss:
        L_.append("MISSED (would have banked fast):")
        for e in miss[:6]:
            f = e["first"]; o = f["out"]
            L_.append(f"• {e['start']}-{e['end']} {side(e['mil'])} @{f['px']:.0f} ({e['n']} calls{', votes ' + f['votes'] if f['votes'] else ''}): +37.5 in {o['mins']}m, "
                      f"worst {o['mae']:.0f}pt against — \"{f['reason'][:110]}\" [{', '.join(f['tags'])}]")
    if dodge:
        L_.append("DODGED (would have ridden into the US or lost):")
        for e in dodge[:4]:
            f = e["first"]; o = f["out"]
            res = f"hit only after {o['mins']}m" if o["hit"] else f"never hit, ${o['pnl']:+,} at 20:40Z"
            L_.append(f"• {e['start']}-{e['end']} {side(e['mil'])} @{f['px']:.0f} ({e['n']} calls): {res}, worst {o['mae']:.0f}pt — [{', '.join(f['tags'])}]")
    ec = rep["every_chance"]
    L_.append(f"Desk P&L ${rep['actual_pnl']:+,} vs DETECTOR-ONLY (no Claude: every flat tradable call entered) ${ec['pnl']:+,} ({len(ec['trades'])} trades"
              f"{', locked' if ec['locked'] else ''}: " + ", ".join(f"{t['t']} {t['side'][0]} {t['pnl']:+}" for t in ec["trades"][:6]) + ")"
              f" -> Claude {'beat' if rep['actual_pnl'] >= ec['pnl'] else 'trailed'} it by ${abs(rep['actual_pnl'] - ec['pnl']):,}"
              " [baseline only: detector-only averages about -$22/day over a year, E121]")
    shd = [x for x in rep["rows"] if x.get("shadow")]
    if shd:
        passed = [x for x in shd if x["shadow"]["would_press"] and x["shadow"]["out"]]
        first = passed[0] if passed else None
        L_.append(f"PRE-VETO SHADOW (no-veto prompt, log only): {len(shd)} ENTER(s), {len(passed)} passed the vote"
                  + (f"; first would-be trade {first['t']} {first['shadow']['action'][6:]} @{first['px']:.0f} ({first['shadow']['votes']}/5): "
                     + (f"+37.5 in {first['shadow']['out']['mins']}m, worst {first['shadow']['out']['mae']:.0f}pt" if first["shadow"]["out"]["hit"]
                        else f"never hit, ${first['shadow']['out']['pnl']:+,}") if first else ""))
        for x in passed[1:4]:
            o = x["shadow"]["out"]
            L_.append(f"  · {x['t']} {x['shadow']['action'][6:]} ({x['shadow']['votes']}/5): " + (f"+37.5 in {o['mins']}m" if o["hit"] else f"never hit, ${o['pnl']:+,}"))
    rb = rep.get("rolling")
    if rb and rb["buckets"]:
        L_.append(f"BUCKETS, last {len(rb['sessions'])} session(s) ({rb['sessions'][0]}..{rb['sessions'][-1]}) - stretches: missed fast / dodged, net $ if this caution were loosened (rode-the-US counted $0):")
        for t, R in sorted(rb["buckets"].items(), key=lambda kv: -kv[1]["net"]):
            L_.append(f"• {t}: {R['miss']} missed (+${R['miss_usd']:,}) / {R['dodge']} dodged (${R['dodge_usd']:,}) -> net ${R['net']:+,}, missed on {R['days']} day(s) - {R['status']}")
    return "\n".join(L_)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="session YYYY-MM-DD (default: today's session)")
    ap.add_argument("--no-send", action="store_true")
    a = ap.parse_args()
    key = a.day or L.session_day(dt.datetime.now(UTC)).isoformat()
    if not any(True for _ in decisions(key)):
        print(f"{key}: no live decisions - nothing to report")
        return 0
    rep = run(key)
    os.makedirs(OUT, exist_ok=True)
    json.dump(rep, open(f"{OUT}/{key}.json", "w"), indent=1, default=str)
    rep["rolling"] = update_buckets(rep)
    msg = text(rep)
    open(f"{OUT}/{key}.txt", "w").write(msg + "\n")
    print(msg)
    if not a.no_send:
        H.page(msg[:3900])
    return 0


if __name__ == "__main__":
    sys.exit(main())
