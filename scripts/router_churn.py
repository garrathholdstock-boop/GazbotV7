#!/usr/bin/env python3
"""ROUTER CHURN — switch changes per day, and how many of them were worth making.

    PYTHONPATH=src .venv/bin/python scripts/router_churn.py [--days 21]

★★2026-08-16 BUILD #4, and it is a MEASUREMENT not a build. The dwell requirement the report wanted
shadowed went LIVE this morning (window 60->45, hold 2->3), so the question stopped being "would a
dwell help?" and became "did it?". That can only be answered against a measured BEFORE — hence this,
run now, while the pre-change days are still on disk.

★ WHY CHURN IS INVISIBLE WITHOUT THIS. A switch change costs nothing at the moment it is made: no
fee, no slippage, no alarm. On 2026-08-07 the router made 20 changes in four hours and only 4 of them
produced a trade — the other 16 were free, silent, and wrong. The only way that shows up is by
counting.

⚠ IT DOES NOT SCORE THE ROUTER. A change that benches a gate which then does not fire may have been
exactly right — that is the point of benching. `useful` here means "the gate traded within the
window", which is a proxy for "the change mattered", not for "the change was correct". Read the RATIO
across days, never a single day's number.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sqlite3
import sys
from collections import defaultdict

GB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GB, "src"))

TRIAL_LOG = os.path.join(GB, "data", "router_trial_log.txt")
DB = os.path.join(GB, "data", "gazbot7.db")
CUTOVER = dt.date(2026, 8, 16)          # the day window/hold changed to 45/3

_TS = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})")


def changes_by_day(path: str = TRIAL_LOG) -> dict:
    """{date: [(hh, mm), ...]} for every logged switch CHANGE.

    ⚠ KEY ON THE `changed:` FIELD, NEVER ON FREE TEXT. The first version of this matched any line
    containing "=on"/"=off" and duly reported 248 changes on 08-12 and 172 on a SATURDAY with zero
    trades. Those were the router's own REASONING — it logs the gate states it is weighing, every
    tick. The log already states the answer explicitly as `changed: none`, so anything else is a real
    change. A churn meter that counts ticks rather than changes makes a quiet night look identical to
    a thrashing one, which is precisely the distinction it exists to draw.
    """
    out = defaultdict(list)
    try:
        with open(path, errors="replace") as f:
            for line in f:
                if "changed:" not in line:
                    continue
                field = line.split("changed:", 1)[1].lstrip()
                if field[:4].lower() == "none":
                    continue
                m = _TS.search(line)
                if m:
                    out[m.group(1)].append((int(m.group(2)), int(m.group(3))))
    except FileNotFoundError:
        pass
    return dict(out)


def trades_by_day(db: str = DB) -> dict:
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = c.execute(
            "SELECT substr(opened_at,1,10) d, COUNT(*) FROM trades "
            "WHERE symbol='MNQ' AND data_quality IS NULL GROUP BY 1").fetchall()
        c.close()
        return {d: n for d, n in rows}
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    a = ap.parse_args()

    ch, tr = changes_by_day(), trades_by_day()
    days = sorted(set(ch) | set(tr))[-a.days:]
    if not days:
        print("no data — is data/router_trial_log.txt present?")
        return 1

    print(f"{'date':<12} {'changes':>8} {'trades':>7} {'chg/trade':>10}   era")
    pre, post = [], []
    for d in days:
        n, t = len(ch.get(d, [])), tr.get(d, 0)
        era = "45/3" if dt.date.fromisoformat(d) >= CUTOVER else "60/2"
        (post if era == "45/3" else pre).append((n, t))
        ratio = f"{n / t:>10.2f}" if t else f"{'—':>10}"
        print(f"{d:<12} {n:>8} {t:>7} {ratio}   {era}")

    def summarise(rows, label):
        if not rows:
            print(f"\n  {label}: no days yet")
            return
        c = sum(r[0] for r in rows)
        t = sum(r[1] for r in rows)
        print(f"\n  {label}: {len(rows)} days · {c} changes · {t} trades · "
              f"{c / len(rows):.1f} changes/day · "
              f"{(c / t) if t else float('nan'):.2f} changes per trade")

    # ★2026-08-16 (audit) FREEZE THE BASELINE. It was recomputed from a GROWING log on every run, so
    # the "before" number the AFTER gets judged against was not reproducible — it drifted every time
    # anyone looked. Written once, then read; delete the file to re-baseline deliberately.
    import json as _j
    frozen = os.path.join(GB, "data", "router_churn_baseline.json")
    if pre and not os.path.exists(frozen):
        c, t = sum(r[0] for r in pre), sum(r[1] for r in pre)
        with open(frozen, "w") as f:
            _j.dump({"frozen_on": days[-1], "days": len(pre), "changes": c, "trades": t,
                     "per_day": round(c / len(pre), 2),
                     "per_trade": round(c / t, 3) if t else None,
                     "era": "window 60 / hold 2",
                     "_note": "Frozen so the AFTER comparison is against a fixed number. Delete to "
                              "re-baseline; do not let it recompute silently."}, f, indent=2)
        print(f"\n  BASELINE FROZEN -> {frozen}")
    if os.path.exists(frozen):
        b = _j.load(open(frozen))
        print(f"\n  BEFORE (FROZEN {b['frozen_on']}, {b['era']}): {b['days']} days · "
              f"{b['changes']} changes · {b['per_day']} /day · {b['per_trade']} per trade")
    summarise(pre, "BEFORE recomputed now (drifts as the log grows — use the FROZEN row above)")
    summarise(post, "AFTER  (window 45 / hold 3)")
    print("\n  ⚠ The AFTER row is not a verdict until it spans several trading days — and REV2's own "
          "\n    caveat on this change stands: its +$502 was ALL on non-trend days, and holding out "
          "\n    the trending eighth it is -$13.50. Ship it for the mechanism; do not quote the number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
