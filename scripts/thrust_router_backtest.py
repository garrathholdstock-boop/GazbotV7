#!/usr/bin/env python3
"""Regime-conditioned thrust ROUTER backtest — veto in chop, un-vetoed in trend.

abs_veto_55s IS thrust (un-vetoed) + the 55s absorption veto, so a router that turns the veto ON in
chop and OFF in trend is faithfully reconstructed from the two shadow variants:

    router(tau) = {abs_veto_55s trades with entry-ER < tau}  UNION  {un-vetoed trades with entry-ER >= tau}

We reconstruct each shadow trade's entry-ER (30-min, 1-min closes — the gate's basis) from capture.db,
restrict to the window both variants cover, and sweep tau. Compares the router to each standalone, and
shows WHERE each variant's money sits by regime (the thesis: veto earns in low-ER, un-vetoed in high-ER).
Tick-repriced real_pnl only. DuckDB-vectorized. Read-only.

  PYTHONPATH=src python scripts/thrust_router_backtest.py
"""
from __future__ import annotations

import duckdb

SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
VETO = "abs_veto_55s"
NOVETO = ("thrust_loose", "thrust_aligned")   # test each as the high-ER (trend) leg


def load():
    con = duckdb.connect()
    con.execute(f"ATTACH '{SHADOW}' AS s (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute("""
        CREATE TABLE feat AS
        WITH m1 AS (
            SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c
            FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1),
        st AS (SELECT m, c, abs(c-lag(c) OVER w) step FROM m1 WINDOW w AS (ORDER BY m))
        SELECT m, abs(c-first_value(c) OVER w30)/NULLIF(SUM(step) OVER w30,0) er
        FROM st WINDOW w30 AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")
    strats = ",".join(f"'{x}'" for x in (VETO, *NOVETO))
    rows = con.execute(f"""
        WITH tr AS (
          SELECT t.strategy, t.entry_ts, r.real_pnl
          FROM s.shadow_trades t JOIN s.shadow_real r ON r.trade_id=t.id
          WHERE t.strategy IN ({strats}) )
        SELECT tr.strategy, tr.entry_ts, tr.real_pnl, f.er
        FROM tr ASOF LEFT JOIN feat f ON f.m <= tr.entry_ts
        ORDER BY tr.entry_ts""").fetchall()
    con.close()
    return [{"strat": s, "ts": t, "pnl": p, "er": e} for s, t, p, e in rows]


def agg(rows):
    n = len(rows)
    net = sum(r["pnl"] for r in rows)
    w = sum(1 for r in rows if r["pnl"] > 0)
    return n, net, (100 * w / n if n else 0)


def line(label, rows):
    n, net, wp = agg(rows)
    print(f"  {label:34} n={n:4}  net=${net:>7.0f}  win={wp:>3.0f}%")


def main():
    rows = load()
    # common window: from the first ts where the veto variant exists (fair head-to-head)
    v_min = min((r["ts"] for r in rows if r["strat"] == VETO), default=0)
    rows = [r for r in rows if r["ts"] >= v_min and r["er"] is not None]
    veto = [r for r in rows if r["strat"] == VETO]

    print(f"THRUST ROUTER BACKTEST — common window from ts={v_min}; {len(rows)} thrust-family trades\n")
    print("=== STANDALONE (whole window) ===")
    line(VETO, veto)
    for nv in NOVETO:
        line(nv, [r for r in rows if r["strat"] == nv])

    print("\n=== WHERE THE MONEY SITS by regime (thesis check, split at ER 0.18 trend line) ===")
    for strat in (VETO, *NOVETO):
        s = [r for r in rows if r["strat"] == strat]
        lo = [r for r in s if r["er"] < 0.18]
        hi = [r for r in s if r["er"] >= 0.18]
        _, nlo, wlo = agg(lo)
        _, nhi, whi = agg(hi)
        print(f"  {strat:16}  chop(ER<0.18): n={len(lo):3} net=${nlo:>6.0f} ({wlo:.0f}%)   "
              f"trend(ER>=0.18): n={len(hi):3} net=${nhi:>6.0f} ({whi:.0f}%)")

    print("\n=== ROUTER SWEEP  router(tau) = veto if ER<tau else un-vetoed ===")
    for nv in NOVETO:
        nvr = [r for r in rows if r["strat"] == nv]
        print(f"\n  high-ER leg = {nv}   (standalone {nv}: ${agg(nvr)[1]:.0f} · standalone {VETO}: ${agg(veto)[1]:.0f})")
        print(f"  {'tau':>5} {'routerNet':>10} {'nTrades':>8} {'win%':>5}   vs-best-standalone")
        best = None
        for tau in [round(0.06 + 0.02 * i, 2) for i in range(11)]:   # 0.06 .. 0.26
            routed = [r for r in veto if r["er"] < tau] + [r for r in nvr if r["er"] >= tau]
            n, net, wp = agg(routed)
            base = max(agg(veto)[1], agg(nvr)[1])
            flag = f"+${net-base:>5.0f}" if net > base else f"{net-base:>6.0f}"
            print(f"  {tau:>5} ${net:>9.0f} {n:>8} {wp:>5.0f}   {flag}")
            if best is None or net > best[1]:
                best = (tau, net, n, wp)
        print(f"  → best tau={best[0]}: ${best[1]:.0f} on {best[2]}tr ({best[3]:.0f}% win)")


if __name__ == "__main__":
    main()
