#!/usr/bin/env python3
"""Explain abs_veto_55s — the trades it TOOK today, the thrusts it VETOED, and why the veto helps.

abs_veto_55s = the base thrust gate + a 55s delayed-entry absorption veto (skip a thrust that gets
absorbed in the first 55s). The un-vetoed base is thrust_loose (fires the same thrust immediately).
So a thrust_loose entry at time T that has an abs_veto_55s entry ~55s later = the veto PASSED it; a
thrust_loose entry with NO abs_veto counterpart ~55s later = the veto KILLED it. That difference set
is what the veto dropped — and its tick-repriced P&L tells us if the veto shed losers or clipped
winners. Read-only, DuckDB over shadow.db. ⚠ proxy: the two sims aren't a perfect 1:1 signal map.

  PYTHONPATH=src python scripts/abs_veto_explain.py [--since 2026-07-24]
"""
from __future__ import annotations

import argparse

import duckdb

SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
TOL = 90   # abs_veto passed-trades share the thrust_loose entry stamp (±this, same side) → matched


def pull(con, strat, t0):
    return con.execute(f"""
        SELECT t.entry_ts, t.side, t.entry_price, t.exit_reason, r.real_pnl
        FROM s.shadow_trades t JOIN s.shadow_real r ON r.trade_id=t.id
        WHERE t.strategy='{strat}' AND t.entry_ts>=epoch(TIMESTAMP '{t0} 00:00:00') ORDER BY t.entry_ts""").fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-24")
    a = ap.parse_args()
    con = duckdb.connect()
    con.execute(f"ATTACH '{SHADOW}' AS s (TYPE sqlite, READ_ONLY)")
    av = pull(con, "abs_veto_55s", a.since)
    tl = pull(con, "thrust_loose", a.since)
    con.close()
    import datetime as dt

    def hm(ts):
        return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%H:%M:%S")

    # the veto is a subset of thrust_loose: a thrust_loose entry that abs_veto ALSO took (same
    # stamp ±TOL, same side) = PASSED the veto; one abs_veto never took = VETOED (killed).
    used = set()
    passed, vetoed = [], []
    for ts, side, px, ex, pnl in tl:
        m = next((j for j, (at, aside) in enumerate((r[0], r[1]) for r in av)
                  if j not in used and aside == side and abs(at - ts) <= TOL), None)
        if m is not None:
            used.add(m)
            passed.append((ts, side, px, ex, pnl))
        else:
            vetoed.append((ts, side, px, ex, pnl))

    print(f"═══ abs_veto_55s — {a.since} ═══\n")
    print(f"TOOK {len(av)} trades · net ${sum(r[4] for r in av):+.0f} · win {sum(1 for r in av if r[4]>0)}/{len(av)}")
    print(f"un-vetoed thrust_loose: {len(tl)} trades · net ${sum(r[4] for r in tl):+.0f} · win {sum(1 for r in tl if r[4]>0)}/{len(tl)}\n")

    print("── THE TRADES IT TOOK (passed the veto) ──")
    print(f"{'entry':>10} {'side':>5} {'$pnl':>7}  exit")
    for ts, side, px, ex, pnl in av:
        print(f"{hm(ts):>10} {side:>5} {pnl:>+7.0f}  {ex}")

    print("\n── THE THRUSTS IT VETOED (skipped) — what they went on to do ──")
    vw = [v for v in vetoed if v[4] > 0]
    vl = [v for v in vetoed if v[4] <= 0]
    print(f"vetoed {len(vetoed)} · would have been: {len(vl)} LOSERS (${sum(v[4] for v in vl):+.0f}) + "
          f"{len(vw)} winners (${sum(v[4] for v in vw):+.0f}) · net avoided ${sum(v[4] for v in vetoed):+.0f}")
    print(f"{'entry':>10} {'side':>5} {'$pnl':>7}  {'outcome':>8}  exit")
    for ts, side, px, ex, pnl in sorted(vetoed, key=lambda v: v[4])[:10]:
        tag = "LOSER" if pnl <= 0 else "winner"
        print(f"{hm(ts):>10} {side:>5} {pnl:>+7.0f}  {tag:>8}  {ex}")

    print("\n── THE POINT ──")
    print(f"  veto shed {len(vl)} losers worth ${-sum(v[4] for v in vl):+.0f} of bleed and gave up "
          f"{len(vw)} winners worth ${sum(v[4] for v in vw):+.0f} — a "
          f"{(len(vl)/max(1,len(vw))):.1f}:1 loser:winner cull.")
    print("  same thrusts, same exits — the veto's whole edge is HIT-RATE: it drops the fakeouts that get absorbed.")


if __name__ == "__main__":
    main()
