#!/usr/bin/env python3
"""grind + thrust with NO ER/ATR floor, only the 55s absorption VETO — what would they have done?

The live grind_long/thrust_short carry an ER floor (0.20) + ATR floor (20/16). This asks: strip both
floors and instead give the momentum gates the abs_veto (skip a move that gets ABSORBED = a fakeout).
Since the LIVE trades already passed the floors, the "no floor" base is the RAW shadow momentum
variants (grind_fast = raw grind, thrust_loose = raw thrust — no ER/ATR floor, no veto). We apply the
VETO ourselves (momentum polarity: LONG vetoed if heavy BUYING failed to lift price; SHORT if heavy
SELLING failed to drop it), repricing the delayed entry at the real tick at T+N.

  step 1: base (raw, no filter) vs +55s veto.
  step 2: the ER-floor sweep ON TOP of the veto (reconstruct ER at entry, sweep the floor).

Tick-repriced shadow real_pnl. capture.db ticks/bars + shadow.db. DuckDB. ⚠ shadow 1-lot, thin week.

  PYTHONPATH=src python scripts/momentum_veto_sweep.py [--ns 55] [--variants grind_fast,thrust_loose]
"""
from __future__ import annotations

import argparse

import duckdb

CAP = "/home/alphabot/gazbot7/data/capture.db"
SH = "/home/alphabot/gazbot7/data/shadow.db"
SINCE = "2026-07-20"
FLOOR = 30.0


def stat(pnls):
    n = len(pnls)
    net = sum(pnls)
    return n, net, (net / n if n else 0), (100 * sum(1 for p in pnls if p > 0) / n if n else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns", type=int, default=55)
    ap.add_argument("--variants", default="grind_fast,thrust_loose")
    a = ap.parse_args()
    n = a.ns
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")
    con.execute("""
        CREATE TABLE feat AS
        WITH m1 AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c
                    FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1),
        st AS (SELECT m, c, abs(c-lag(c) OVER w) step FROM m1 WINDOW w AS (ORDER BY m))
        SELECT m, abs(c-first_value(c) OVER w30)/NULLIF(SUM(step) OVER w30,0) er
        FROM st WINDOW w30 AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")

    def load(variant):
        rows = con.execute(f"""
            WITH t AS (SELECT entry_ts, side, entry_price, id FROM s.shadow_trades
                       WHERE strategy='{variant}' AND entry_ts>=epoch(TIMESTAMP '{SINCE} 00:00:00'))
            SELECT t.entry_ts, t.side, t.entry_price, r.real_pnl, f.er
            FROM t JOIN s.shadow_real r ON r.trade_id=t.id ASOF LEFT JOIN feat f ON f.m<=t.entry_ts
            ORDER BY t.entry_ts""").fetchall()
        out = []
        for te, side, entry, pnl, er in rows:
            flow, p0, p1, nt = con.execute(f"""
                SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END),0),
                       arg_min(price,ts_ms), arg_max(price,ts_ms), COUNT(*)
                FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={te*1000} AND ts_ms<{(te+n)*1000}""").fetchone()
            long = side in ("LONG", "BUY")
            if nt < 5:
                kept, adj = False, pnl   # no tape → can't judge → (treat as vetoed: don't enter)
            else:
                dp = p1 - p0
                absorbed = (flow >= FLOOR and dp <= 0) if long else (flow <= -FLOOR and dp >= 0)
                kept = not absorbed
                adj = (pnl - (p1 - entry) * 2 if long else pnl + (p1 - entry) * 2) if kept else pnl
            out.append({"pnl": pnl, "er": er, "kept": kept, "adj": adj})
        return out

    variants = a.variants.split(",")
    print(f"MOMENTUM 55s-VETO — raw shadow momentum (no ER/ATR floor), since {SINCE}, {n}s veto, floor {FLOOR}\n")
    data = {}
    for v in variants:
        d = load(v)
        data[v] = d
        bn, bnet, bev, bw = stat([x["pnl"] for x in d])
        kn, knet, kev, kw = stat([x["adj"] for x in d if x["kept"]])
        vetoed = [x["pnl"] for x in d if not x["kept"]]
        print(f"── {v} ──")
        print(f"   BASE (raw, no filter): {bn}tr · net ${bnet:+.0f} · ${bev:+.1f}/tr · {bw:.0f}%w")
        print(f"   + {n}s VETO:            {kn}tr · net ${knet:+.0f} · ${kev:+.1f}/tr · {kw:.0f}%w"
              f"   (vetoed {len(vetoed)} worth ${sum(vetoed):+.0f})")

    print(f"\n── STEP 2: ER-FLOOR sweep ON TOP of the {n}s veto (keep only kept-trades with ER>=floor) ──")
    print(f"   {'variant':<14}{'ER floor':>9}{'trades':>8}{'net$':>8}{'$/tr':>8}{'win%':>6}")
    for v in variants:
        d = data[v]
        for erf in [0.0, 0.10, 0.15, 0.20, 0.25, 0.30]:
            keep = [x["adj"] for x in d if x["kept"] and x["er"] is not None and x["er"] >= erf]
            kn, knet, kev, kw = stat(keep)
            print(f"   {v:<14}{('none' if erf==0 else f'>={erf:.2f}'):>9}{kn:>8}${knet:>+7.0f}${kev:>+7.1f}{kw:>5.0f}%")
    con.close()
    print("\n(veto = skip a move whose own aggressors got ABSORBED = fakeout. ⚠ shadow 1-lot, ~1wk — a LEAD.\n"
          " compare to the LIVE floored gates: grind_long/thrust_short in gazbot7.db.)")


if __name__ == "__main__":
    main()
