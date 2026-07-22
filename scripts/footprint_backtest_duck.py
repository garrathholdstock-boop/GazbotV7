#!/usr/bin/env python3
"""Footprint gates on the V5 tick+L2 tape — VECTORIZED with DuckDB, now with the ER gate.

Native-fast: copy the two V5 sqlite tables into DuckDB ONCE (the only full scan), then everything
— 5s bucketing, rolling footprint windows, the 30-min efficiency-ratio, the L2 ASOF-join, AND the
tick-path exits (an in-engine range-join, not 730 sequential lookups) — runs native-columnar.

Gates: capitulation_long (fade a sell-flush, LONG) · exhaustion_short (fade heavy buying into an
ask wall, SHORT). For each gate we report NATURAL (no ER floor) vs ER>=0.18 (only trade trend) vs
ER<0.18 (only trade chop) — the same 0.18 efficiency floor the Features backtest uses, applied here
to the footprint trades. Exit: fixed 8pt stop / 12pt target / 120s on the real ticks.
CAVEAT: 5s-bucketed footprint · fixed exit (live capitulation uses ATR 2R) · one regime · a LEAD.

  PYTHONPATH=src python scripts/footprint_backtest_duck.py
"""

from __future__ import annotations

import datetime as dt

import duckdb
import pandas as pd

TICKS = "/home/alphabot/alphabot2/data/ticks.db"
DEPTH = "/home/alphabot/alphabot2/data/depth.db"
STOP_PT, TARGET_PT, HOLD_MS = 8.0, 12.0, 120_000
VPP, FEE = 2.0, 1.5
ER_GATE = 0.18
CLIMAX_MIN, DOM_MIN = 3.0, 0.7          # gate_capitulation
NET_MIN, MOVE_MAX, WALL = 400.0, 2.0, 1.5   # exhaustion_signal


def run():
    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    con.execute(f"ATTACH '{TICKS}' AS tk (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DEPTH}' AS dp (TYPE sqlite, READ_ONLY)")

    # 0) copy the two tables into NATIVE duck once (the only full sqlite scan) — everything after is native
    con.execute("CREATE TABLE tick AS SELECT ts_ms, price, size, aggressor FROM tk.trade_tick WHERE symbol='MNQ'")
    con.execute("CREATE TABLE depth AS SELECT ts_ms, bid1p, bid1s, ask1p, ask1s FROM dp.depth_snap WHERE symbol='MNQ'")
    con.execute("CREATE INDEX ix_tick ON tick(ts_ms)")

    # 1) 5s bins: sell/buy/net vol + open/close price
    con.execute("""
        CREATE TABLE b5 AS
        SELECT (ts_ms/5000)*5000 AS t,
               SUM(CASE WHEN aggressor='sell' THEN size ELSE 0 END) AS sell,
               SUM(CASE WHEN aggressor='buy'  THEN size ELSE 0 END) AS buy,
               SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) AS net,
               arg_min(price, ts_ms) AS o, arg_max(price, ts_ms) AS c
        FROM tick GROUP BY 1""")

    # 1b) 30-min efficiency ratio off the 1-min closes (matches hour_watch / gate_backtest ER)
    con.execute("""
        CREATE TABLE erm AS
        WITH m1 AS (SELECT (t/60000)*60000 AS m, arg_max(c, t) AS mc FROM b5 GROUP BY 1),
             st AS (SELECT m, mc, abs(mc - lag(mc) OVER (ORDER BY m)) AS step FROM m1)
        SELECT m,
               abs(mc - first_value(mc) OVER w) / NULLIF(SUM(step) OVER w, 0) AS er
        FROM st WINDOW w AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")

    # 2) roll the footprint windows: 20s climax + 180s baseline
    con.execute("""
        CREATE TABLE feat AS
        SELECT t, c,
               SUM(sell)          OVER w20  AS cap_sell,
               SUM(buy)           OVER w20  AS cap_buy,
               SUM(net)           OVER w20  AS net_signed,
               (SUM(sell+buy) OVER w180 - SUM(sell+buy) OVER w20) / 8.0 AS cap_base,
               c - first_value(o) OVER w20  AS move
        FROM b5
        WINDOW w20  AS (ORDER BY t RANGE BETWEEN 20000  PRECEDING AND CURRENT ROW),
               w180 AS (ORDER BY t RANGE BETWEEN 180000 PRECEDING AND CURRENT ROW)""")

    # 3) ASOF-join the L2 level-1 + the ER, then the gate logic as boolean columns → fires
    fires = con.execute(f"""
        WITH jd AS (
            SELECT f.*, d.bid1p, d.bid1s, d.ask1p, d.ask1s
            FROM feat f ASOF LEFT JOIN depth d ON d.ts_ms <= f.t
        ),
        j AS (
            SELECT jd.*, e.er
            FROM jd ASOF LEFT JOIN erm e ON e.m <= jd.t
        )
        SELECT t, (bid1p+ask1p)/2.0 AS entry, COALESCE(er, 1.0) AS er,
            (move < 0 AND cap_base > 0 AND (cap_sell+cap_buy) > 0
               AND cap_sell >= {CLIMAX_MIN}*cap_base AND cap_sell >= {DOM_MIN}*(cap_sell+cap_buy)) AS cap_long,
            (net_signed >= {NET_MIN} AND abs(move) <= {MOVE_MAX} AND bid1s>0 AND ask1s>0
               AND ask1s >= {WALL}*bid1s) AS exh_short
        FROM j
        WHERE bid1p IS NOT NULL AND (cap_long OR exh_short)
        ORDER BY t""").df()

    # 4) exits — ONE in-engine range-join over all fires (not a per-fire loop)
    con.register("fires_v", fires[["t", "entry", "cap_long", "exh_short"]])
    con.execute(f"""
        CREATE TABLE fexit AS
        WITH ff AS (
            SELECT t, entry, cap_long AS is_long,
                   CASE WHEN cap_long THEN entry-{STOP_PT}  ELSE entry+{STOP_PT}  END AS stop,
                   CASE WHEN cap_long THEN entry+{TARGET_PT} ELSE entry-{TARGET_PT} END AS tgt
            FROM fires_v
        ),
        hits AS (
            SELECT f.t, f.entry, f.is_long, f.stop, f.tgt, k.ts_ms, k.price,
                   CASE WHEN f.is_long THEN (k.price<=f.stop OR k.price>=f.tgt)
                        ELSE (k.price>=f.stop OR k.price<=f.tgt) END AS is_hit
            FROM ff f JOIN tick k ON k.ts_ms > f.t AND k.ts_ms <= f.t+{HOLD_MS}
        )
        SELECT t,
               any_value(entry) AS entry, any_value(is_long) AS is_long,
               any_value(stop) AS stop, any_value(tgt) AS tgt,
               MIN(ts_ms) FILTER (WHERE is_hit)                        AS hit_ts,
               arg_min(price, CASE WHEN is_hit THEN ts_ms END)         AS hit_px,
               MAX(ts_ms)                                              AS last_ts,
               arg_max(price, ts_ms)                                   AS last_px
        FROM hits GROUP BY t""")
    ex = con.execute("SELECT * FROM fexit").df().set_index("t")

    # resolve each fire's exit price/time + $pnl (tiny pandas pass, <3k rows)
    def resolve(row):
        t = int(row["t"])
        if t not in ex.index:
            return 0.0, t                                # no ticks in window (rare) → scratch
        e = ex.loc[t]
        entry, is_long = e["entry"], bool(e["is_long"])
        if not pd.isna(e["hit_ts"]):                     # a stop/target was hit
            hit_stop = (e["hit_px"] <= e["stop"]) if is_long else (e["hit_px"] >= e["stop"])
            xpx, xms = (e["stop"] if hit_stop else e["tgt"]), int(e["hit_ts"])
        else:                                            # timed out → last price in window
            xpx, xms = e["last_px"], int(e["last_ts"])
        g = ((xpx - entry) if is_long else (entry - xpx)) * VPP - FEE
        return g, xms

    fires[["pnl", "exit_ts"]] = fires.apply(lambda r: resolve(r), axis=1, result_type="expand")

    # 5) sequence one-position-at-a-time within a fire subset, using the cached exits
    def seq(sub):
        total = n = w = 0.0
        nxt = 0
        for r in sub.itertuples():
            if r.t < nxt:
                continue
            total += r.pnl
            n += 1
            w += r.pnl > 0
            nxt = r.exit_ts
        return total, int(n), (round(100 * w / n) if n else 0)

    span = con.execute("SELECT min(t),max(t) FROM feat").fetchone()
    print("footprint gates on the V5 tick+L2 tape (DuckDB-vectorized, native, with the 0.18 ER gate)")
    print(f"(tape {dt.datetime.fromtimestamp(span[0]/1000, dt.UTC).date()} → "
          f"{dt.datetime.fromtimestamp(span[1]/1000, dt.UTC).date()})\n")
    print(f"{'GATE':18} {'scenario':16} {'N':>4} {'win%':>5} {'NET':>9}")
    for tag, col in [("capitulation_long", "cap_long"), ("exhaustion_short", "exh_short")]:
        g = fires[fires[col]]
        for label, sub in [("natural", g),
                           (f"ER>={ER_GATE} (trend)", g[g["er"] >= ER_GATE]),
                           (f"ER<{ER_GATE} (chop)", g[g["er"] < ER_GATE])]:
            total, n, win = seq(sub)
            print(f"{tag:18} {label:16} {n:>4} {win:>4}% ${round(total):>+8.0f}")
    # per-gate ER CEILING scan (both footprint gates are reversion → keep er<=cut) — derive the threshold
    grid = [0.05, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35, 0.40]
    print("\nceiling scan (reversion → keep er<=cut; ★ = P&L-max cut):")
    for tag, col in [("capitulation_long", "cap_long"), ("exhaustion_short", "exh_short")]:
        g = fires[fires[col]]
        cells, best = [], (None, -1e9, 0)
        for c in grid:
            total, n, _ = seq(g[g["er"] <= c])
            cells.append(f"≤{c:.2f}:${round(total):+}({n})")
            if total > best[1]:
                best = (c, total, n)
        print(f"  {tag:18} nat=${round(seq(g)[0]):+} | " + "  ".join(cells) +
              f"  ★≤{best[0]:.2f} ${round(best[1]):+}({best[2]}tr)")

    print("\n⚠ tick fills (honest) · fixed 8/12pt exit (live capitulation uses ATR 2R) · "
          "ER over trailing 30-min 1-min closes · one regime · a LEAD not a verdict.")


if __name__ == "__main__":
    run()
