"""E112 in-sample check for a candidate rule R (declared in E112_change.txt TUNING): re-ask Claude WITH R at every Phase A slot
where v102 PRESSED, on the identical page (same closed bars, flat sim book, the same earlier sim trades), and count how many BAD vs good
presses R would have declined. Labelled in-sample. Read-only.

    .venv/bin/python reports/recursive_loop/E112_code/vetocheck.py --rules R.txt --days 2025-10-01,... [--arm v102]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay as R  # noqa: E402  (patches ML.minute_bars; same S / L / H)

S = R.S


def bad(p: dict) -> bool:
    return p["pnl_usd"] <= -1000 or p["mae_pt"] >= 150


def check(day: str, arm: str, rules: str) -> list:
    rec = json.load(open(f"{R.OUT}/{arm}_{day}.json"))
    if rec.get("skipped"):
        return []
    page_bars, _ = S.load_day(day)
    out = []
    for p in rec["presses"]:
        op = int(dt.datetime.fromisoformat(p["decision_ts"]).timestamp())
        upto = [b for b in page_bars if b[0] + 60 <= op]
        done = [t for t in rec["sim_done"] if t["closed"] < p["decision_ts"]]
        d = S.ask(S.brief_for("v2") + "\n\n=== THE TAPE ===\n"
                  + S.context(upto, op, None, rules, done, True, band=False, leg_list=False, mil=False, card=False))
        want = "ENTER_LONG" if p["side"] == "BUY" else "ENTER_SHORT"
        out.append({**{k: p[k] for k in ("decision_ts", "side", "pnl_usd", "mae_pt", "why")}, "day": day, "bad": bad(p),
                    "with_R": d.get("action"), "kept": d.get("action") == want, "reason_R": (d.get("reason") or "")[:300],
                    "error": d.get("error")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", required=True)
    ap.add_argument("--days", required=True)
    ap.add_argument("--arm", default="v102")
    a = ap.parse_args()
    rules = open(a.rules).read().strip()
    days = sorted(a.days.split(","))
    rows = []
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        for r in ex.map(lambda d: check(d, a.arm, rules), days):
            rows += r
    b = [x for x in rows if x["bad"]]; g = [x for x in rows if not x["bad"]]
    print(f"IN-SAMPLE (Phase A presses re-asked with R, sha {R.hashlib.sha256(rules.encode()).hexdigest()[:12]}): {len(rows)} presses, errors {sum(1 for x in rows if x['error'])}")
    print(f"  BAD  (net <= -$1,000 or MAE >= 150pt): {len(b):>3}  declined by R {sum(1 for x in b if not x['kept']):>3}")
    print(f"  good                                 : {len(g):>3}  declined by R {sum(1 for x in g if not x['kept']):>3}"
          f"   (winners declined {sum(1 for x in g if not x['kept'] and x['pnl_usd'] > 0)})")
    print(f"  $ of declined presses: {sum(x['pnl_usd'] for x in rows if not x['kept']):+,.0f}")
    for x in rows:
        print(f"  {x['day']} {x['decision_ts'][11:16]} {x['side']:4} {'BAD ' if x['bad'] else 'good'} {x['pnl_usd']:>+7.0f} MAE {x['mae_pt']:>5.0f}  R -> {x['with_R']:12} {x['reason_R'][:140]}")
    json.dump(rows, open(f"{R.OUT}/vetocheck_{os.path.basename(a.rules)}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
