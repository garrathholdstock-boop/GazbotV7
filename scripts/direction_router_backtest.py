#!/usr/bin/env python3
"""Direction-router backtest — validate the LIVE router (gazbot7.direction_router) on realised trades.

Imports the router's EXACT logic + tuned constants from the module (no drift): replays each Paris
day's 15-min regime marks from capture, labels each realised trade ALLOW/BLOCK by whether its gate is
in desired_off(regime@entry), and sums. Blocked-trades P&L = the router's effect (negative = removed
losers = it helped). --days N loops per Paris day + a total.

⚠ realised trades are already partly HAND-gated (operator /off's) → illustrative lower bound, not a
clean A/B. To RE-TUNE, edit the constants in src/gazbot7/direction_router.py (moves live + this together).

  PYTHONPATH=src python scripts/direction_router_backtest.py --days 4
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7 import pnl  # noqa: E402

DB = "/home/alphabot/gazbot7/data/gazbot7.db"


def run_day(con, t0, t1, fast_exit=False, verbose=False):
    """Backtest one Paris day [t0, t1). Returns a result dict; prints the regime timeline if verbose."""
    bars = con.execute(f"""
        SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
          AND bar_ts >= {t0 - dr.WINDOW*60} AND bar_ts < {t1} GROUP BY 1 ORDER BY 1""").fetchall()
    trades = con.execute(f"""
        SELECT gate, pnl_usd, epoch(opened_at::TIMESTAMPTZ) te
        FROM g.trades WHERE symbol='MNQ'
          AND epoch(opened_at::TIMESTAMPTZ) >= {t0} AND epoch(opened_at::TIMESTAMPTZ) < {t1}
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY te""").fetchall()
    date = dt.datetime.fromtimestamp(t0 + 43200, dt.UTC).strftime("%m-%d")   # +12h → Paris calendar day
    if not bars or not trades:
        b = sum(t[1] for t in trades)
        return {"date": date, "n": len(trades), "base": b, "router": b, "delta": 0.0, "blk": [], "flips": 0}
    mins = [b[0] for b in bars]
    closes = [b[1] for b in bars]
    marks = dr.replay_marks(mins, closes, int(t0), int(t1), fast_exit=fast_exit)

    def regime_at(te):
        st = "CHOP"
        for mt, s, _e, _n in marks:
            if mt <= te:
                st = s
            else:
                break
        return st

    flips = sum(1 for i in range(1, len(marks)) if marks[i][1] != marks[i - 1][1])
    if verbose:
        print(f"\nREGIME TIMELINE {date} (effective state per scan):")
        prev = None
        for mt, s, er, net in marks:
            hh = dt.datetime.fromtimestamp(mt, dt.UTC).strftime("%H:%M")
            print(f"  {hh}Z  {s:11} (ER {er:.2f}, net {net:+.0f}pt){'  <<< FLIP' if s != prev else ''}")
            prev = s
    base = sum(x[1] for x in trades)
    blk = [x for x in trades if x[0] in dr.desired_off(regime_at(x[2]))]
    router = base - sum(x[1] for x in blk)
    bd = defaultdict(lambda: [0, 0.0])
    for gate, p, te in blk:
        bd[(gate, regime_at(te))][0] += 1
        bd[(gate, regime_at(te))][1] += p
    return {"date": date, "n": len(trades), "base": base, "router": router, "delta": router - base,
            "blk": sorted(bd.items(), key=lambda x: x[1][1]), "flips": flips}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    days = ap.parse_args().days
    t_today = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(t_today).timestamp() if isinstance(t_today, str) else t_today.timestamp()
    con = duckdb.connect()
    con.execute(f"ATTACH '{dr.CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")

    print(f"DIRECTION-ROUTER BACKTEST — last {days} day(s)  ·  SHIPPED (sticky) vs sticky-EXIT FIX (fast_exit)")
    print(f"knobs: ER>={dr.ER_TREND} & |net|>={dr.NET_MIN}pt/{dr.WINDOW}min · scan {dr.STEP}min · hold {dr.HOLD} · "
          f"down-off {sorted(dr.DOWN_OFF)} · up-off {sorted(dr.UP_OFF)}\n")
    windows = [(today0 - k * 86400, today0 - (k - 1) * 86400) for k in range(days - 1, -1, -1)]
    cur = [run_day(con, a, b, fast_exit=False) for a, b in windows]
    fix = [run_day(con, a, b, fast_exit=True) for a, b in windows]
    con.close()

    print(f"{'DATE':>6} {'trades':>7} {'baseline':>9} | {'router_NOW':>10} {'ΔNOW':>6} {'fl':>3} | "
          f"{'router_FIX':>10} {'ΔFIX':>6} {'fl':>3} | {'FIX−NOW':>8}")
    tb = trn = trf = 0.0
    for c, f in zip(cur, fix):
        tb += c["base"]
        trn += c["router"]
        trf += f["router"]
        print(f"{c['date']:>6} {c['n']:>7} ${c['base']:>+8.0f} | ${c['router']:>+9.0f} ${c['delta']:>+5.0f} "
              f"{c['flips']:>3} | ${f['router']:>+9.0f} ${f['delta']:>+5.0f} {f['flips']:>3} | ${f['router']-c['router']:>+7.0f}")
    print(f"{'TOTAL':>6} {sum(c['n'] for c in cur):>7} ${tb:>+8.0f} | ${trn:>+9.0f} ${trn-tb:>+5.0f}     | "
          f"${trf:>+9.0f} ${trf-tb:>+5.0f}     | ${trf-trn:>+7.0f}")
    print(f"\n→ baseline ${tb:+.0f}  ·  SHIPPED (sticky) ${trn:+.0f} (Δ{trn-tb:+.0f})  ·  "
          f"FIX (fast-exit) ${trf:+.0f} (Δ{trf-tb:+.0f})  ·  FIX vs SHIPPED ${trf-trn:+.0f}")
    print("(FIX−NOW>0 = the sticky-exit fix would have earned more; fewer flips is also better. ⚠ realised\n"
          " trades already partly hand-gated → illustrative, not a clean A/B. LIVE still runs SHIPPED until you deploy.)")


if __name__ == "__main__":
    main()
