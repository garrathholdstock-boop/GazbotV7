#!/usr/bin/env python3
"""rgv faders: find the BEST (ER band × absorption-confirm delay) combo — this week, tick-accurate.

Three things in one pass:
  1. ER LOSS-MAP — per gate, bucket every rgv trade by its entry ER (the 30-min gate basis) so we see
     WHERE in the ER range the losses sit (a fader bleeds in TREND = high ER, earns in CHOP = low ER).
  2. The absorption-CONFIRM at 30/35/40/45s (mirror of the abs_veto momentum filter): only take the
     fade if the faded move ABSORBS in the N-s window; entry repriced at the real tick at T+N.
  3. The GRID — every (ER-band × delay) cell: trades, net $, $/trade, win% — so you can pick the
     max-trades / max-EV / max-per-trade corner. Live rgv has NO ATR floor, so no ATR filter.

capture.db ticks/bars + gazbot7.db trades. DuckDB, read-only. ⚠ thin-n (a week) — a LEAD.

  PYTHONPATH=src python scripts/absorption_confirm_grid.py [--floor 30]
"""
from __future__ import annotations

import argparse

import duckdb

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
DELAYS = [30, 35, 40, 45]
GATES = ("rgv_long", "rgv_short")


def stat(pnls):
    n = len(pnls)
    net = sum(pnls)
    w = sum(1 for p in pnls if p > 0)
    return n, net, (net / n if n else 0), (100 * w / n if n else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=float, default=30.0)
    a = ap.parse_args()
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    con.execute("""
        CREATE TABLE feat AS
        WITH m1 AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c
                    FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1),
        st AS (SELECT m, c, abs(c-lag(c) OVER w) step FROM m1 WINDOW w AS (ORDER BY m))
        SELECT m, abs(c-first_value(c) OVER w30)/NULLIF(SUM(step) OVER w30,0) er
        FROM st WINDOW w30 AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")
    raw = con.execute("""
        WITH tr AS (SELECT gate, side, epoch(opened_at::TIMESTAMPTZ) te, pnl_usd, entry_price, qty
                    FROM g.trades WHERE symbol='MNQ' AND gate IN ('rgv_long','rgv_short')
                      AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE'))
        SELECT tr.gate, tr.side, tr.te, tr.pnl_usd, tr.entry_price, tr.qty, f.er
        FROM tr ASOF LEFT JOIN feat f ON f.m <= tr.te ORDER BY tr.te""").fetchall()

    # precompute the confirm decision + tick-repriced (delayed-entry) pnl for each trade at each delay
    T = []   # (gate, er, raw_pnl, {N: (confirmed, adj_pnl)})
    for gate, side, te, pnl, entry, qty, er in raw:
        cov = con.execute(f"SELECT COUNT(*) FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={te*1000} AND ts_ms<{(te+45)*1000}").fetchone()[0]
        if er is None or cov < 5:
            continue
        long = side in ("LONG", "BUY")
        mult = 2.0 * (qty or 1)
        cf = {}
        for n in DELAYS:
            flow, p0, p1, nt = con.execute(f"""
                SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END),0),
                       arg_min(price,ts_ms), arg_max(price,ts_ms), COUNT(*)
                FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={te*1000} AND ts_ms<{(te+n)*1000}""").fetchone()
            if nt < 5:
                cf[n] = (False, pnl)
                continue
            dp = p1 - p0
            ok = (flow <= -a.floor and dp >= 0) if long else (flow >= a.floor and dp <= 0)
            adj = pnl - (p1 - entry) * mult if long else pnl + (p1 - entry) * mult
            cf[n] = (ok, adj)
        T.append((gate, er, pnl, cf))
    con.close()

    print(f"rgv absorption-confirm GRID — {len(T)} trades w/ tick coverage this week (floor={a.floor})\n")
    # ── 1. ER LOSS-MAP (per gate) ──
    print("1) ER LOSS-MAP — where do the faders bleed? (all trades, no confirm)")
    for gate in GATES:
        gt = [t for t in T if t[0] == gate]
        print(f"  {gate} ({len(gt)}tr):")
        for lo in [0.0, 0.10, 0.20, 0.30, 0.40, 0.50]:
            b = [t[2] for t in gt if lo <= t[1] < lo + 0.10]
            if b:
                n, net, ev, wp = stat(b)
                bar = ('+' if net >= 0 else '-') * min(20, int(abs(net) / 20) + 1)
                print(f"      ER {lo:.2f}-{lo+0.10:.2f}: {n:>2}tr  net ${net:>+5.0f}  ${ev:>+5.1f}/tr  {wp:>3.0f}%w  {bar}")
    # ── 2/3. the GRID: ER band × delay ──
    bands = {"full (no ER)": {"rgv_long": (0.0, 1.0), "rgv_short": (0.0, 1.0)},
             "live band": {"rgv_long": (0.10, 0.40), "rgv_short": (0.30, 0.40)},
             "chop-cap .25": {"rgv_long": (0.10, 0.25), "rgv_short": (0.30, 0.40)},
             "chop-cap .20": {"rgv_long": (0.10, 0.20), "rgv_short": (0.30, 0.40)}}
    print("\n2) GRID — ER band × confirm delay  (cell = trades · net$ · $/tr · win%). ⚠ <8tr = thin/noise")
    cells = []
    for bname, band in bands.items():
        print(f"\n  ── {bname} ──")
        print(f"     {'delay':>7} {'trades':>7} {'net$':>7} {'$/tr':>7} {'win%':>6}")
        inband = [t for t in T if band[t[0]][0] <= t[1] <= band[t[0]][1]]
        for n in [0] + DELAYS:
            if n == 0:
                pnls = [t[2] for t in inband]
            else:
                pnls = [t[3][n][1] for t in inband if t[3][n][0]]
            nt, net, ev, wp = stat(pnls)
            flag = "  ⚠thin" if 0 < nt < 8 else ""
            lbl = "none" if n == 0 else f"{n}s"
            print(f"     {lbl:>7} {nt:>7} ${net:>+6.0f} ${ev:>+6.1f} {wp:>5.0f}%{flag}")
            if nt > 0:
                cells.append((bname, lbl, nt, net, ev, wp))
    # ── best-of ──
    print("\n3) BEST COMBINATIONS (of cells with >=8 trades):")
    solid = [c for c in cells if c[2] >= 8]
    if solid:
        for label, key in (("MAX trades", 2), ("MAX total EV ($)", 3), ("MAX $/trade", 4)):
            b = max(solid, key=lambda c: c[key])
            print(f"   {label:<18}: {b[0]} @ {b[1]} → {b[2]}tr · net ${b[3]:+.0f} · ${b[4]:+.1f}/tr · {b[5]:.0f}%w")
    print("\n(a fader bleeds in TREND=high-ER; capping the upper ER band removes trend-bleed, and the "
          "confirm removes the falling-knife that slips through. best combo = where both agree.)")


if __name__ == "__main__":
    main()
