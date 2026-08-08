#!/usr/bin/env python3
"""CL-VERIFY runner — verify unscored live signals, then print the scoreboard.

Gates nothing. Writes only to shadow.db's cl_verdicts table. Safe to run any time; it picks up
where it left off. See docs/CL_VERIFICATION_SHADOW_SCOPE.md.

  PYTHONPATH=src ./.venv/bin/python scripts/cl_verify_run.py --since 2026-07-27 [--limit 20]
  PYTHONPATH=src ./.venv/bin/python scripts/cl_verify_run.py --score-only
"""
from __future__ import annotations
import argparse, sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.cl_verify import GB, build_context, open_db, record, score, unverified  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-27")
    ap.add_argument("--limit", type=int, default=0, help="0 = all outstanding")
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="build contexts, do not call the model")
    a = ap.parse_args()

    con = open_db()
    if not a.score_only:
        todo = unverified(f"{GB}/data/gazbot7.db", con, a.since)
        if a.limit:
            todo = todo[:a.limit]
        print(f"{len(todo)} signals to verify\n")
        for i, s in enumerate(todo, 1):
            ctx = build_context(f"{GB}/data/capture.db", f"{GB}/data/gazbot7.db", s)
            if not ctx:
                print(f"  [{i}/{len(todo)}] {s.gate:<20} SKIP — insufficient bar history")
                continue
            if a.dry_run:
                print(f"  [{i}/{len(todo)}] {s.gate:<20} ctx ok  "
                      f"ATR {ctx['regime']['atr_pt']} ER {ctx['regime']['er30']} "
                      f"tradeability {ctx['regime']['tradeability_0_10']}")
                continue
            from gazbot7.cl_verify import verify
            res, ms = verify(ctx)
            record(con, s, ctx, res, ms)
            print(f"  [{i}/{len(todo)}] {s.gate:<20} {res['verdict']:<10} "
                  f"conf {res['confidence']:>3}  {ms:>5}ms  live ${s.live_pnl:+7.2f}  "
                  f"{res['primary_factor'][:40]}")

    sc = score(con)
    print("\n" + "=" * 78)
    for v in ("PASS", "VETO", "no_verdict"):
        d = sc[v]
        print(f"  {v:<12} n={d['n']:<5} total ${d['total']:>9,.2f}   ${d['per_signal']:>7.2f}/signal")
    print("-" * 78)
    print(f"  separation: ${sc['separation_per_signal']}/signal")
    print(f"  {sc['verdict']}")
    if sc["primary_factors"]:
        print(f"  veto factors: {sc['primary_factors']}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
