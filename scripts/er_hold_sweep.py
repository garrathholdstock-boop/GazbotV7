#!/usr/bin/env python3
"""Backtest the ER-hold-for-N-bars spike fix, and sweep the minimum N.

The spike-entry blind spot: a gate fires on the LIVE/forming price when ER momentarily crosses its
floor, but the completed 1-min bar walks it back (violent-chop whipsaw). Fix: require the
COMPLETED-bar ER to satisfy the gate's rule for N consecutive 1-min bars before the gate may fire.

This replays every GATED-era trade: for N in 1..MAXN, a trade is HELD only if the closed entry bar
AND the N-1 bars before it were all in-rule; otherwise the hold-filter would have BLOCKED it. We
want the BLOCKED set to be net-negative (we're removing losers, especially the ~$714 spike bucket)
while sacrificing as little winner P&L as possible. DuckDB-vectorized (the rule); read-only.

  PYTHONPATH=src:scripts python scripts/er_hold_sweep.py [--days 7] [--maxn 5]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import filter_check as fc  # noqa: E402
from gazbot7 import pnl  # noqa: E402

GATED = set(list(fc.ER_FLOOR) + list(fc.ER_CEIL) + list(fc.ER_BAND))
MAXN = 5


def held_series(t0, maxn):
    """Per gated trade: (gate, pnl, was_spike, [er@entry, er@-1, ... er@-(maxn-1)])."""
    con = duckdb.connect()
    con.execute(f"ATTACH '{fc.DB}' AS g (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{fc.CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lag_cols = ", ".join(f"lag(er,{k}) OVER (ORDER BY m) er_l{k}" for k in range(1, maxn))
    con.execute(f"""
        CREATE TABLE feat AS
        WITH m1 AS (
            SELECT (bar_ts-bar_ts%60) m, max(high) h, min(low) l, arg_max(close,bar_ts) c
            FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1),
        st AS (SELECT m, c, abs(c - lag(c) OVER w) step FROM m1 WINDOW w AS (ORDER BY m)),
        e AS (
            SELECT m, abs(c - first_value(c) OVER w30) / NULLIF(SUM(step) OVER w30,0) er
            FROM st WINDOW w30 AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW))
        SELECT m, er, {lag_cols} FROM e""")
    ph = ",".join(f"'{x}'" for x in fc._CLEANUP)
    gph = ",".join(f"'{x}'" for x in GATED)
    sel = ", ".join([f"f.er_l{k}" for k in range(1, maxn)])
    rows = con.execute(f"""
        WITH tr AS (
            SELECT gate, pnl_usd, exit_reason, epoch(opened_at::TIMESTAMPTZ) te
            FROM g.trades WHERE symbol='MNQ' AND gate IN ({gph})
              AND exit_reason NOT IN ({ph}) AND epoch(opened_at::TIMESTAMPTZ) >= {t0})
        SELECT tr.gate, tr.pnl_usd, f.er, {sel}
        FROM tr ASOF LEFT JOIN feat f ON f.m <= tr.te
        ORDER BY tr.te""").fetchall()
    con.close()
    out = []
    for r in rows:
        gate, p, er = r[0], r[1], r[2]
        lags = list(r[3:])
        series = [er] + lags
        was_spike = fc.classify(gate, p, er, None)["below_rule"] and p < 0
        out.append((gate, p, was_spike, series))
    return out


def held(gate, series, n):
    """True iff ER satisfied the gate's rule for all N closed bars up to entry."""
    for er in series[:n]:
        if er is None or not fc.er_flags(gate, er)[0]:
            return False
    return True


def run(days, maxn):
    _t0 = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(_t0).timestamp() if isinstance(_t0, str) else _t0.timestamp()
    trades = held_series(today0 - (days - 1) * 86400, maxn)
    base = sum(p for _, p, _, _ in trades)
    spike_loss = sum(p for _, p, sp, _ in trades if sp)
    nsp = sum(1 for _, _, sp, _ in trades if sp)
    print(f"ER-HOLD-N SWEEP — {len(trades)} gated trades, base net ${base:+.0f} "
          f"| spike-entry losers: {nsp} = ${spike_loss:+.0f}\n")
    print(f"{'N':>2} {'blocked':>7} {'blk$':>7} {'spikeBlk':>8} {'spike$rec':>9} "
          f"{'winSac':>6} {'winSac$':>8} {'kept':>5} {'kept$':>7} {'deskΔ':>7} {'newNet':>7}")
    for n in range(1, maxn + 1):
        blk = [(g, p, sp) for (g, p, sp, s) in trades if not held(g, s, n)]
        kept = [(g, p) for (g, p, sp, s) in trades if held(g, s, n)]
        blk_pnl = sum(p for _, p, _ in blk)
        spike_blk = [(g, p) for g, p, sp in blk if sp]
        win_sac = [(g, p) for g, p, _ in blk if p > 0]
        kept_pnl = sum(p for _, p in kept)
        desk_delta = -blk_pnl   # removing blocked trades' P&L from the desk
        print(f"{n:>2} {len(blk):>7} ${blk_pnl:>+6.0f} {len(spike_blk):>8} "
              f"${sum(p for _,p in spike_blk):>+8.0f} {len(win_sac):>6} ${sum(p for _,p in win_sac):>+7.0f} "
              f"{len(kept):>5} ${kept_pnl:>+6.0f} ${desk_delta:>+6.0f} ${kept_pnl:>+6.0f}")
    print("\nblocked = trades the hold-filter removes · deskΔ = P&L change (positive = filter helped) · "
          "newNet = net of the KEPT trades.\nWant: spike$rec recovered with the fewest winSac$ sacrificed — "
          "the N where deskΔ peaks before winner-sacrifice eats it.")
    # per-gate at each N: winners sacrificed (the cost)
    print("\nwinners sacrificed per gate, by N:")
    for n in range(1, maxn + 1):
        sac = {}
        for g, p, sp, s in trades:
            if p > 0 and not held(g, s, n):
                sac[g] = sac.get(g, 0) + p
        if sac:
            print(f"  N={n}: " + " · ".join(f"{g} ${v:+.0f}" for g, v in sorted(sac.items(), key=lambda x: x[1])))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--maxn", type=int, default=MAXN)
    a = ap.parse_args()
    run(a.days, a.maxn)
