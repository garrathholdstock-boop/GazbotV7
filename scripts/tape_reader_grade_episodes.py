#!/usr/bin/env python3
"""GRADE THE TAPE READER PER EPISODE, NOT PER CALL.

★★★ Operator: *"if you just snapshot the days tape and look at it from a distance you can see it has
turned. cant you do that? send out a call to claude to review it and make a call? these arent
microsecond moves they take longer we have time."*

He was right, and `gazbot7-tape-reader` has been doing exactly that every two minutes since
2026-09-12 — **3,853 calls on live positions, none of which had ever been graded.** The shipped
`tape_reader_grade.py` reported all of them as UNGRADEABLE, so an instrument built to answer this
question had three weeks of answers nobody scored.

⚠⚠⚠ WHY PER EPISODE AND NOT PER CALL — THIS IS THE WHOLE POINT OF THIS SCRIPT.
The reader fires every 2 minutes on the SAME position. A first pass per call gave HOLD +5.9pt of
further P&L against exit calls' +1.5pt over 2h, n=3,853 — which reads like a strong result and is
not one. Those 3,853 calls are **69 distinct episodes**: ~31 calls per HOLD episode, ~14 per CLAIM.
Treating them as independent inflates n about 50-fold, and this desk has already measured that
per-observation statistics on correlated tape are inflated roughly tenfold
([[per-observation-t-on-book-data-is-inflated-tenfold]] — a real 0.72x effect whose t=-12.45 did
not replicate). So:

  · ONE ROW PER EPISODE. An episode is a contiguous run of calls on one position; a gap of more
    than EPISODE_GAP_MIN starts a new one.
  · the episode's verdict is taken at its FIRST call of each type, because that is the moment a
    decision would actually have been acted on. The 30 repeats afterwards are the same decision
    restated, not 30 decisions.
  · uncertainty is a DAY-CLUSTERED bootstrap, resampling whole SESSIONS. Minutes inside a session
    are not independent draws and neither are episodes within a day.

WHAT IS BEING TESTED. A HOLD is right when the position went on to GAIN; a CLAIM or CUT is right
when it went on to LOSE. So HOLD's further-P&L should sit ABOVE the exit calls'. The GAP is the
reader's skill and it needs no assumption about the ladder, no fee model, and no entry rule.

⚠ P&L is signed by the POSITION'S OWN DIRECTION, taken from `facts.position.direction`. A call is
about the position in front of it, so an unsigned price move says nothing about whether the call
was right.
⚠ READ-ONLY. Reads the reader's log and capture.db; writes one report. No order path.
"""

from __future__ import annotations

import argparse
import bisect
import collections
import datetime as dt
import json
import random
import sqlite3
import statistics as st

GB = "/home/alphabot/gazbot7"
LOG = f"{GB}/data/tape_reader_log.jsonl"
CAPTURE = f"{GB}/data/capture.db"

EPISODE_GAP_MIN = 15      # a gap this long means a different position / a different decision
HORIZONS = (30, 60, 120)
BOOT = 2000


def load_calls():
    """Every decision made while holding, with the position's side. Plus the failure census."""
    calls, errors = [], collections.Counter()
    for ln in open(LOG):
        try:
            r = json.loads(ln)
        except Exception:
            errors["unparseable log line"] += 1
            continue
        d = r.get("decision")
        if not isinstance(d, dict):
            continue
        if d.get("error"):
            errors[str(d["error"]).split(":")[0][:40]] += 1
            continue
        if not (d.get("decision") and r.get("holding")):
            continue
        f = r.get("facts") or {}
        p = f.get("position") or {}
        if p.get("direction") not in (1, -1) or p.get("closed") or not f.get("price"):
            continue
        calls.append({"ts": dt.datetime.fromisoformat(r["ts"]),
                      "px": float(f["price"]), "dir": int(p["direction"]),
                      "call": d["decision"], "conf": d.get("confidence"),
                      "atr": f.get("atr")})
    calls.sort(key=lambda x: x["ts"])
    return calls, errors


def episodes(calls):
    """Contiguous runs of calls on one position. Returns [[call, ...], ...]."""
    out, cur = [], []
    for c in calls:
        if cur and ((c["ts"] - cur[-1]["ts"]).total_seconds() > EPISODE_GAP_MIN * 60
                    or c["dir"] != cur[-1]["dir"]):
            out.append(cur)
            cur = []
        cur.append(c)
    if cur:
        out.append(cur)
    return out


def tape():
    c = sqlite3.connect(f"file:{CAPTURE}?mode=ro", uri=True)
    bars = c.execute("SELECT bar_ts, high, low, close FROM bars "
                     "WHERE symbol='MNQ' AND timeframe='5s' ORDER BY bar_ts").fetchall()
    return bars, [b[0] for b in bars]


def forward(bars, ts_list, epoch, mins):
    i = bisect.bisect_left(ts_list, epoch)
    j = bisect.bisect_left(ts_list, epoch + mins * 60)
    if i >= len(bars) or j <= i:
        return None
    seg = bars[i:j]
    return max(b[1] for b in seg), min(b[2] for b in seg), seg[-1][3]


def boot_ci(by_day: dict, stat=st.median, reps: int = BOOT, seed: int = 20261003):
    """Day-clustered bootstrap: resample whole SESSIONS, not observations."""
    days = list(by_day)
    if len(days) < 3:
        return None, None
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        pick = [rng.choice(days) for _ in days]
        pool = [x for d in pick for x in by_day[d]]
        if pool:
            vals.append(stat(pool))
    if not vals:
        return None, None
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    calls, errors = load_calls()
    eps = episodes(calls)
    bars, ts_list = tape()

    print(f"calls on a live position : {len(calls):,}")
    print(f"EPISODES                 : {len(eps)}   "
          f"(a >{EPISODE_GAP_MIN}min gap or a side change starts a new one)")
    print(f"calls per episode        : median {st.median(len(e) for e in eps):.0f}, "
          f"max {max(len(e) for e in eps)}")
    print()
    print("FAILURE CENSUS — a quarter of this instrument's calls produced nothing for three weeks:")
    for k, n in errors.most_common(6):
        print(f"  {n:>5}  {k}")
    print("  ⚠ 934 of these were `raw.find('{')` to `raw.rfind('}')` spanning TWO braced things.")
    print("    Fixed 2026-10-03 with a brace-balanced first-object extractor.")
    print()

    # ── one row per episode per call-type, taken at the FIRST such call ──────────────────────────
    rows = []
    for ep_i, ep in enumerate(eps):
        seen = set()
        day = ep[0]["ts"].date().isoformat()
        for c in ep:
            if c["call"] in seen:
                continue                     # the same decision restated, not a new one
            seen.add(c["call"])
            epoch = int(c["ts"].timestamp())
            rec = {"ep": ep_i, "day": day, "call": c["call"], "conf": c["conf"]}
            ok = False
            for h in HORIZONS:
                w = forward(bars, ts_list, epoch, h)
                if not w:
                    continue
                hi, lo, close = w
                rec[f"pnl{h}"] = c["dir"] * (close - c["px"])
                ok = True
            if ok:
                rows.append(rec)

    print(f"=== GRADED: {len(rows)} episode-decisions across {len(set(r['day'] for r in rows))} "
          f"sessions ===")
    print("    a HOLD is right if the position GAINED; a CLAIM/CUT is right if it LOST.")
    print()
    results = {}
    for h in HORIZONS:
        key = f"pnl{h}"
        print(f"  --- {h} minutes after the decision ---")
        print(f"  {'call':7} {'episodes':>9} {'median further P&L':>19} {'day-clustered 95% CI':>24}")
        med = {}
        for call in ("HOLD", "CUT", "CLAIM"):
            v = [r for r in rows if r["call"] == call and key in r]
            if len(v) < 5:
                print(f"  {call:7} {len(v):>9}   too few episodes to grade")
                continue
            by_day = collections.defaultdict(list)
            for r in v:
                by_day[r["day"]].append(r[key])
            m = st.median(r[key] for r in v)
            lo, hi = boot_ci(by_day)
            med[call] = m
            ci = f"[{lo:+.1f}, {hi:+.1f}]" if lo is not None else "n/a"
            print(f"  {call:7} {len(v):>9} {m:>+18.1f}pt {ci:>24}")
        if "HOLD" in med and ("CLAIM" in med or "CUT" in med):
            ex = [med[k] for k in ("CLAIM", "CUT") if k in med]
            sep = med["HOLD"] - (sum(ex) / len(ex))
            print(f"  → SEPARATION (HOLD minus exit calls): {sep:+.1f}pt")
            results[h] = {"median": med, "separation_pt": round(sep, 2)}
        print()

    print("⚠⚠ HOW TO READ THIS. A separation of a few points per episode on this many episodes is")
    print("   NOT a validated edge — it is a reason to keep grading. The per-CALL version of this")
    print("   same data showed +4.4pt on n=3,853 and that n was fiction: 69 episodes wearing 3,853")
    print("   coats. The honest n is in the 'episodes' column and the CI is day-clustered.")
    if a.json:
        print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
