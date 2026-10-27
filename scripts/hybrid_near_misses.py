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
            e["n"] += 1; e["last_i"] = rows.index(x); e["end"] = x["t"]
        else:
            eps.append({"cls": x["out"]["cls"], "mil": x["mil"], "start": x["t"], "end": x["t"], "n": 1, "last_i": rows.index(x), "first": x})
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
           "episodes": [{k: v for k, v in e.items() if k != "last_i"} for e in eps], "rows": rows}
    return rep


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
    tg = sorted(rep["by_tag"].items(), key=lambda kv: -sum(kv[1].values()))
    L_.append("Wait reasons (missed-fast / dodged): " + " · ".join(f"{t} {v['QUICK']}/{v['LATE'] + v['LOSS']}" for t, v in tg))
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
    msg = text(rep)
    open(f"{OUT}/{key}.txt", "w").write(msg + "\n")
    print(msg)
    if not a.no_send:
        H.page(msg[:3900])
    return 0


if __name__ == "__main__":
    sys.exit(main())
