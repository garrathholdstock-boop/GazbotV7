#!/usr/bin/env python3
"""Absorption-CONFIRM sweep on the live rgv_long / rgv_short faders (45/50/55/60s).

The mirror of the abs_veto momentum filter: a reversion fader WANTS the move it is fading to be
exhausting. So instead of vetoing, it CONFIRMS — delay the entry N seconds and only take the fade if
the faded move is being ABSORBED in that window (heavy aggressor flow the WRONG way for the fade that
FAILS to move price). rgv_long fades a down-stretch → confirm = net SELLING but price did NOT fall
(selling absorbed → safe to go long). rgv_short fades an up-stretch → confirm = net BUYING but price
did NOT rise. The bet: this drops the falling-knife catches (price kept going) and keeps the real turns.

Backtests it as a SELECTOR on the live trades (gazbot7.db) using capture.db ticks — for each N, does
the confirmed subset beat the full book? ⚠ first-pass: it filters the trades that happened at their
recorded entry/P&L; a real delayed entry would shift the fill by N seconds (noted, not modelled).

  PYTHONPATH=src python scripts/absorption_confirm_sweep.py [--floor 30]
"""
from __future__ import annotations

import argparse

import duckdb

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=float, default=30.0, help="min net-aggressor size to call it absorption")
    ap.add_argument("--ns", default="45,50,55,60", help="comma-separated confirm delays in seconds")
    ap.add_argument("--gates", default="rgv_long,rgv_short", help="comma-separated fade gates to test")
    a = ap.parse_args()
    NS = [int(x) for x in a.ns.split(",")]
    GATES = a.gates.split(",")
    BAND = {"rgv_long": (0.10, 0.40), "rgv_short": (0.30, 0.40)}   # LIVE ER band (only rgv used one; cap/exh use CEIL)
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    # reconstruct the 30-min ER at each entry (the live gate's basis) so we can apply the live band uniformly
    con.execute("""
        CREATE TABLE feat AS
        WITH m1 AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c
                    FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1),
        st AS (SELECT m, c, abs(c-lag(c) OVER w) step FROM m1 WINDOW w AS (ORDER BY m))
        SELECT m, abs(c-first_value(c) OVER w30)/NULLIF(SUM(step) OVER w30,0) er
        FROM st WINDOW w30 AS (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)""")
    gph = ",".join(f"'{x}'" for x in GATES)
    raw = con.execute(f"""
        WITH tr AS (SELECT gate, side, epoch(opened_at::TIMESTAMPTZ) te, pnl_usd, entry_price, qty,
                           strftime(opened_at::TIMESTAMPTZ, '%m-%d') d
                    FROM g.trades WHERE symbol='MNQ' AND gate IN ({gph})
                      AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE'))
        SELECT tr.gate, tr.side, tr.te, tr.pnl_usd, tr.entry_price, tr.qty, tr.d, f.er
        FROM tr ASOF LEFT JOIN feat f ON f.m <= tr.te ORDER BY tr.te""").fetchall()
    # apply the live ER band ONLY to gates that have one (rgv); cap/exh use a CEIL, not a band → no filter
    n_all = len(raw)
    trades = [t for t in raw if (t[0] not in BAND) or (t[7] is not None and BAND[t[0]][0] <= t[7] <= BAND[t[0]][1])]
    n_erdrop = n_all - len(trades)
    trades = [t[:7] for t in trades if con.execute(
        f"SELECT COUNT(*) FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={t[2]*1000} AND ts_ms<{(t[2]+60)*1000}").fetchone()[0] >= 5]
    print(f"[filters] gates={GATES}; ER band applied only where one exists ({n_erdrop} dropped); no ATR floor.")

    def window(te, n):
        return con.execute(f"""
            SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END),0),
                   arg_min(price, ts_ms), arg_max(price, ts_ms), COUNT(*)
            FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={te*1000} AND ts_ms<{(te+n)*1000}""").fetchone()

    days = sorted({t[6] for t in trades})
    gstr = ", ".join(GATES)
    print(f"ABSORPTION-CONFIRM SWEEP — {gstr} LIVE trades (floor={a.floor})")
    print(f"{len(trades)} trades with real tick coverage, {days[0]}–{days[-1]}. "
          f"Entry repriced at the real tick at T+N (delayed fill); exit unchanged. Confirm = faded move ABSORBED.\n")
    base = sum(t[3] for t in trades)
    bw = sum(1 for t in trades if t[3] > 0)
    print(f"BASE (all, no confirm): {len(trades)}tr · net ${base:+.0f} · win {bw}/{len(trades)} ({100*bw/len(trades):.0f}%)\n")
    print(f"{'N(s)':>5} {'confirmed':>10} {'conf net':>9} {'conf win%':>10} {'conf $/tr':>10}   {'skipped':>8} {'skip net':>9}   verdict")
    for n in NS:
        conf, skip = [], []
        for gate, side, te, pnl, entry, qty, _d in trades:
            flow, p_first, p_last, nt = window(te, n)
            if nt < 5:
                skip.append(pnl)   # no tape in the window → can't confirm → skip
                continue
            dp = p_last - p_first
            long = side in ("LONG", "BUY")
            ok = (flow <= -a.floor and dp >= 0) if long else (flow >= a.floor and dp <= 0)
            if not ok:
                skip.append(pnl)
                continue
            mult = 2.0 * (qty or 1)                       # reprice the entry at the T+N tick (real fill)
            adj = pnl - (p_last - entry) * mult if long else pnl + (p_last - entry) * mult
            conf.append(adj)
        cn = sum(conf) or 0.0
        cw = sum(1 for p in conf if p > 0)
        sptr = cn / len(conf) if conf else 0
        base_tr = base / len(trades)
        v = "HELPS" if (conf and sptr > base_tr and cn > 0) else "no lift"
        print(f"{n:>5} {len(conf):>10} ${cn:>+8.0f} {100*cw/len(conf) if conf else 0:>9.0f}% ${sptr:>+9.1f}   "
              f"{len(skip):>8} ${sum(skip):>+8.0f}   {v}")
    print(f"\n(base $/tr = ${base/len(trades):+.1f}. HELPS = confirmed subset beats base on $/tr AND is net-green.\n"
          " skip net negative = the confirm is correctly dropping losers.)")
    con.close()


if __name__ == "__main__":
    main()
