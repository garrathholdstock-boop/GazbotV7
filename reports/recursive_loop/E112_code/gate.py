"""E112 A5 - SECOND-OPINION GATE, zero-shot check. For every press the LIVE setup (v102) made in Oct+Nov 2025, a separate Claude call
(the risk reviewer) sees the identical page plus the proposed trade and answers TAKE or SKIP. Outcomes are known; the reviewer prompt was
written without looking at any individual entry. Counts: SKIP rate on entries <= -$1,000 vs on the rest. Read-only.

    PYTHONPATH=src .venv/bin/python reports/recursive_loop/E112_code/gate.py [--model MODEL]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay as R  # noqa: E402

S = R.S
GATE = """You are the RISK REVIEWER for an MNQ futures desk. Another trader has just decided to enter the trade described at the end.
The desk's rules for that trade are fixed and you cannot change them: 4 contracts, ALL four exit at +37.5 points from the entry price,
there is NO stop, and anything not at +37.5 is held until it is flattened at 20:40Z (after the full US cash session, which opens 13:30Z).
So a trade that does not reach +37.5 soon can sit hundreds of points offside through the US session; a typical loss of that kind is
$1,500-$4,500, a win is +$294. Your only job: decide whether THIS entry, at THIS moment, is likely to reach +37.5 cleanly, or is the kind
of entry that stalls and is then reversed. You see exactly what the trader saw (the page below). Judge it independently; do not defer to
the trader's reasoning. Answer with ONE JSON object and nothing else:
{"verdict": "TAKE" or "SKIP", "p_reach": <0..1 your probability it reaches +37.5 before 13:30Z>, "reason": "<one sentence>"}"""


def review(day: str, p: dict) -> dict:
    page_bars, _ = S.load_day(day)
    op = int(dt.datetime.fromisoformat(p["decision_ts"]).timestamp())
    upto = [b for b in page_bars if b[0] + 60 <= op]
    page = S.context(upto, op, None, "", [], True, band=False, leg_list=False, mil=False, card=False)
    trade = (f"\n\n=== THE PROPOSED TRADE ===\n{'LONG' if p['side'] == 'BUY' else 'SHORT'} 4 MNQ at about {p['decision_px']:.2f}, "
             f"decided {p['decision_ts'][11:16]}Z. The trader's reason: {p['reason']}")
    d = S.ask(GATE + "\n\n=== THE PAGE THE TRADER SAW ===\n" + page + trade)
    return {"day": day, "ts": p["decision_ts"][11:16], "side": p["side"], "pnl": p["pnl_usd"], "mae": p["mae_pt"],
            "verdict": d.get("verdict"), "p_reach": d.get("p_reach"), "reason": (d.get("reason") or "")[:300], "error": d.get("error")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="ANTHROPIC_MODEL for the reviewer ('' = CLI default, as live)")
    a = ap.parse_args()
    if a.model:
        os.environ["ANTHROPIC_MODEL"] = a.model
    jobs = []
    for f in sorted(glob.glob(f"{R.OUT}/v102_2025-1[01]-*.json")):
        r = json.load(open(f))
        if r.get("skipped") or (r["calls"] and r["errors"] / len(r["calls"]) > 0.10):
            continue
        jobs += [(r["day"], p) for p in r["presses"]]
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        rows = list(ex.map(lambda j: review(j[0], j[1]), jobs))
    bad = [x for x in rows if x["pnl"] <= -1000]; rest = [x for x in rows if x["pnl"] > -1000]
    win = [x for x in rows if x["pnl"] > 0]
    sk = lambda xs: sum(1 for x in xs if x["verdict"] == "SKIP")
    tag = a.model or "cli-default"
    out = [f"E112 A5 SECOND-OPINION GATE (zero-shot, reviewer model {tag}): {len(rows)} v102 presses Oct+Nov 2025, errors {sum(1 for x in rows if x['error'])}",
           f"  entries <= -$1,000: {len(bad):>3}   SKIPPED by the reviewer {sk(bad):>3}  ({sk(bad) / max(len(bad), 1):.0%})",
           f"  all other entries : {len(rest):>3}   SKIPPED by the reviewer {sk(rest):>3}  ({sk(rest) / max(len(rest), 1):.0%})   of which winners skipped {sk(win)}",
           f"  static $ if every SKIP had not traded: {-sum(x['pnl'] for x in rows if x['verdict'] == 'SKIP'):+,.0f}  (positive = the gate saves money)"]
    for x in sorted(rows, key=lambda x: x["pnl"]):
        out.append(f"  {x['day']} {x['ts']} {x['side']:4} {x['pnl']:>+7.0f} MAE {x['mae']:>4.0f}  {str(x['verdict']):5} p={x['p_reach']}  {x['reason'][:150]}")
    open(f"{R.OUT}/gate_{tag}.txt", "w").write("\n".join(out) + "\n")
    json.dump(rows, open(f"{R.OUT}/gate_{tag}.json", "w"), indent=1)
    print("\n".join(out[:4]))


if __name__ == "__main__":
    main()
