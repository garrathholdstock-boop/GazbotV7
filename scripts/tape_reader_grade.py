#!/usr/bin/env python3
"""GRADE THE TAPE READER — the harness the 119 claim calibrations never had.

Every logged decision is scored against what the tape ACTUALLY did next, in the position's own
direction, in dollars. Same verdict vocabulary as the router bad-call ledger (GOOD / BAD / CHURN /
NEUTRAL), because that file is the proof this desk can grade a judgement call: 290 of them, with
dollar attribution, over six weeks.

★ THE COUNTERFACTUAL IS THE POINT, AND IT RUNS BOTH WAYS.
    CLAIM is GOOD when banking beat holding — i.e. the position was WORSE later.
    HOLD  is GOOD when holding beat banking — i.e. the position was BETTER later.
  A reader that is right about direction but always says HOLD scores no better than the ladder,
  and that is the correct outcome: the ladder is the incumbent and it has to be BEATEN, not matched.

⚠ IT GRADES ONLY WHAT IT CAN PRICE. A decision with no forward tape (the last one of a session,
  or one logged while the venue was shut) is UNGRADEABLE and is reported as such, never as NEUTRAL.
  "Nothing to grade" and "graded zero" are different facts and this desk has confused them before.
"""
from __future__ import annotations

import argparse, json, sqlite3
import datetime as dt

GB = "/home/alphabot/gazbot7"
LOG = f"{GB}/data/tape_reader_log.jsonl"
VPP = 2.0          # MNQ $/point
FLAT_S = 20 * 3600 + 40 * 60


def forward(symbol: str, t0: int, side: int, entry_px: float):
    """The position's P&L path in dollars after t0, to the 20:40Z flat."""
    con = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
    day0 = (t0 // 86400) * 86400
    rows = con.execute(
        "select bar_ts, high, low, close from bars where symbol=? and timeframe='5s' "
        "and bar_ts > ? and bar_ts <= ? order by bar_ts",
        (symbol, t0, day0 + FLAT_S)).fetchall()
    if not rows:
        return None
    best = max(side * (float(h if side > 0 else l) - entry_px) for _, h, l, _ in rows)
    end = side * (float(rows[-1][3]) - entry_px)
    return {"best_usd": best * VPP, "end_usd": end * VPP, "bars": len(rows)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=LOG)
    a = ap.parse_args()
    try:
        recs = [json.loads(l) for l in open(a.log) if l.strip()]
    except FileNotFoundError:
        print("no log yet — the reader has not run"); return 0

    judged = [r for r in recs if r.get("decision") and "error" not in r["decision"]]
    errs = [r for r in recs if r.get("decision", {}).get("error")]
    skip = [r for r in recs if r.get("skipped")]
    print(f"{len(recs)} log lines · {len(judged)} decisions · {len(errs)} failures · "
          f"{len(skip)} idle-skips")
    if errs:
        print(f"  ⚠ FAILURES ARE NOT NOTHING — {len(errs)} calls produced no decision:")
        for e in errs[-3:]:
            print(f"     {e['ts'][11:19]} {e['decision'].get('error','')[:80]}")
    if not judged:
        print("\nnothing gradeable yet."); return 0

    rows, ungradeable = [], 0
    for r in judged:
        f, d = r["facts"], r["decision"]
        pos = f.get("position") or {}
        side = 1 if str(pos.get("side", "")).upper().startswith("L") else (
            -1 if str(pos.get("side", "")).upper().startswith("S") else 0)
        entry = pos.get("entry_price") or pos.get("entry")
        t0 = int(dt.datetime.fromisoformat(f["ts"]).timestamp())
        if not side or not entry:
            ungradeable += 1
            continue
        fw = forward(f.get("symbol", "MNQ"), t0, side, float(entry))
        if fw is None:
            ungradeable += 1
            continue
        now_usd = side * (f["price"] - float(entry)) * VPP
        dec = d["decision"]
        if dec in ("CLAIM", "CUT"):
            delta = now_usd - fw["end_usd"]          # banking beat holding by this much
        elif dec == "HOLD":
            delta = fw["end_usd"] - now_usd          # holding beat banking by this much
        else:
            delta = 0.0
        rows.append({"ts": f["ts"][11:19], "dec": dec, "conf": d.get("confidence"),
                     "now": now_usd, "end": fw["end_usd"], "best": fw["best_usd"],
                     "delta": delta,
                     "verdict": "GOOD" if delta > 5 else ("BAD" if delta < -5 else "NEUTRAL")})

    print(f"\n{'time':>9}{'decision':>10}{'conf':>6}{'P&L now':>10}{'at flat':>10}"
          f"{'peak':>10}{'the call':>10}{'verdict':>9}")
    for x in rows[-25:]:
        print(f"{x['ts']:>9}{x['dec']:>10}{x['conf'] or 0:>6.2f}{x['now']:>10.0f}"
              f"{x['end']:>10.0f}{x['best']:>10.0f}{x['delta']:>+10.0f}{x['verdict']:>9}")
    if rows:
        g = sum(1 for x in rows if x["verdict"] == "GOOD")
        b = sum(1 for x in rows if x["verdict"] == "BAD")
        tot = sum(x["delta"] for x in rows)
        print(f"\n  GOOD {g} · BAD {b} · NEUTRAL {len(rows)-g-b} · "
              f"the reader's calls are worth {tot:+,.0f} USD against the incumbent")
    if ungradeable:
        print(f"  {ungradeable} decision(s) UNGRADEABLE (no forward tape, or no position detail) "
              f"— reported, not scored as zero")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
