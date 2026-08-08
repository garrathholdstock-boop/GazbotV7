#!/usr/bin/env python3
"""CL SCOREBOARD — each CL- sim against its LIVE twin, plus the signal journal.

The whole experiment in one screen. See docs/CL_VERIFICATION_SHADOW_SCOPE.md.

  PYTHONPATH=src ./.venv/bin/python scripts/cl_scoreboard.py [--since 2026-08-04]
"""
from __future__ import annotations
import argparse, sqlite3, sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.cl_sims import CL_GATES  # noqa: E402

GB = "/home/alphabot/gazbot7"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-04")
    a = ap.parse_args()
    sh = sqlite3.connect(f"file:{GB}/data/shadow.db?mode=ro", uri=True)
    have = {r[0] for r in sh.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "cl_signals" not in have:
        print("\n  cl_signals / signal_journal not created yet — CL sims have not run.\n"
              "  Enable with GAZBOT7_CL_SIMS=1 on gazbot7-shadow and restart it.\n")
        return 0
    lv = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)

    print(f"\n{'CL sim':<24}{'n':>4}{'CL net':>10}{'$/tr':>8}   |{'live n':>7}{'live net':>10}{'$/tr':>8}   {'verdict':>10}")
    print("-" * 92)
    tot_cl = tot_lv = 0.0
    for sim, gate in CL_GATES.items():
        c = sh.execute("SELECT COUNT(*), COALESCE(SUM(r.real_pnl), SUM(t.ceiling_pnl), 0) "
                       "FROM shadow_trades t LEFT JOIN shadow_real r ON r.trade_id=t.id "
                       "WHERE t.strategy=?", (sim,)).fetchone()
        l = lv.execute("SELECT COUNT(*), COALESCE(SUM(pnl_usd),0) FROM trades "
                       "WHERE gate LIKE ? AND closed_at >= ?", (gate + "%", a.since)).fetchone()
        cn, cp = c[0], c[1] or 0.0
        ln, lp = l[0], l[1] or 0.0
        tot_cl += cp; tot_lv += lp
        v = ""
        if cn >= 5 and ln >= 5:
            v = "CL better" if (cp / cn) > (lp / ln) else "CL worse"
        print(f"{sim:<24}{cn:>4}{cp:>10.2f}{(cp/cn if cn else 0):>8.2f}   |"
              f"{ln:>7}{lp:>10.2f}{(lp/ln if ln else 0):>8.2f}   {v:>10}")
    print("-" * 92)
    print(f"{'TOTAL':<24}{'':>4}{tot_cl:>10.2f}{'':>8}   |{'':>7}{tot_lv:>10.2f}")

    print("\n=== verdicts ===")
    for v, n, lat in sh.execute("SELECT verdict, COUNT(*), AVG(latency_ms) FROM cl_signals "
                                "GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {v or '(none)':<12} n={n:<5} mean latency {lat or 0:.0f}ms")
    nv = sh.execute("SELECT COUNT(*) FROM cl_signals WHERE verdict='no_verdict'").fetchone()[0]
    tt = sh.execute("SELECT COUNT(*) FROM cl_signals").fetchone()[0]
    if tt:
        print(f"  ⚠ no-verdict rate {100*nv/tt:.1f}%  — a HIGH rate makes the CL sims look "
              f"disciplined when they are merely broken")
    print("\n  top veto reasons (if one factor dominates, CODE it — do not ask):")
    for f, n in sh.execute("SELECT primary_factor, COUNT(*) FROM cl_signals WHERE verdict='VETO' "
                           "GROUP BY 1 ORDER BY 2 DESC LIMIT 8"):
        print(f"    {n:>3}x  {(f or '')[:78]}")

    print("\n=== signal journal ===")
    j = sh.execute("SELECT COUNT(*), COUNT(DISTINCT gate) FROM signal_journal").fetchone()
    print(f"  {j[0]} fires logged across {j[1]} gates")
    if j[0]:
        print(f"  {'gate':<22}{'fires':>6}{'med ATR':>9}{'med ER30':>10}{'med 0-10':>10}")
        for g, n, atr, er, td in sh.execute(
                "SELECT gate, COUNT(*), AVG(atr_pt), AVG(er30), AVG(tradeability) "
                "FROM signal_journal GROUP BY 1 ORDER BY 2 DESC"):
            print(f"  {g:<22}{n:>6}{atr or 0:>9.1f}{er or 0:>10.3f}{td or 0:>10.1f}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
