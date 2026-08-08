#!/usr/bin/env python3
"""Companion to router_architecture_ab.py — two extra research angles:
  (1) STEP x HOLD grid: does ANY polling granularity / hysteresis beat the shipped (15min, hold2)?
  (2) NET-ONLY in-code guard: the literal 'no long-fade when net is down' veto (alt a), no ER gate,
      per-tick at the exact entry epoch — the simplest possible in-code directional guard.
"""
from __future__ import annotations
import datetime as dt, sys
import duckdb
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr
from gazbot7 import pnl

DB = "/home/alphabot/gazbot7/data/gazbot7.db"
WEEK_START = "2026-07-20"


def load_day(con, t0, t1):
    bars = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= {t0-dr.WINDOW*60} AND bar_ts < {t1}
        GROUP BY 1 ORDER BY 1""").fetchall()
    return [b[0] for b in bars], [b[1] for b in bars]


def poll_regime_at(mins, closes, t0, t1, te, step, hold):
    o1, o2 = dr.STEP, dr.HOLD
    dr.STEP, dr.HOLD = step, hold
    try:
        marks = dr.replay_marks(mins, closes, int(t0), int(t1))
    finally:
        dr.STEP, dr.HOLD = o1, o2
    st = "CHOP"
    for mt, s, _e, _n in marks:
        if mt <= te: st = s
        else: break
    return st


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{dr.CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    t_today = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(t_today).timestamp() if isinstance(t_today, str) else t_today.timestamp()
    wk0 = dt.datetime.fromisoformat(WEEK_START).replace(tzinfo=dt.UTC).timestamp()
    days = [(wk0+k*86400, wk0+(k+1)*86400) for k in range(int(round((today0-wk0)/86400))+1)]
    daycache = {t0: load_day(con, t0, t1) for t0, t1 in days}
    trades = []
    for t0, t1 in days:
        rows = con.execute(f"""SELECT gate, pnl_usd, epoch(opened_at::TIMESTAMPTZ) te FROM g.trades
            WHERE symbol='MNQ' AND gate IN ({','.join("'%s'"%g for g in dr.MANAGED)})
              AND epoch(opened_at::TIMESTAMPTZ)>={t0} AND epoch(opened_at::TIMESTAMPTZ)<{t1}
              AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE')""").fetchall()
        for gate, p, te in rows:
            trades.append((gate, p, te, t0))
    base = sum(t[1] for t in trades)

    print(f"base=${base:+.0f} over n={len(trades)} managed-fader trades\n")
    print("(1) POLLING STEP x HOLD grid — router_net (higher=better; shipped=STEP15/HOLD2):")
    print(f"{'STEP\\HOLD':>9} " + " ".join(f"{h:>7}" for h in (1,2,3)))
    for step in (1,5,10,15,30):
        cells = []
        for hold in (1,2,3):
            blk = 0.0
            for gate, p, te, t0 in trades:
                mins, closes = daycache[t0]
                reg = poll_regime_at(mins, closes, t0, t0+86400, te, step, hold)
                if gate in dr.desired_off(reg):
                    blk += p
            cells.append(base - blk)
        star = " <-- shipped" if step==15 else ""
        print(f"{step:>9} " + " ".join(f"${c:>+6.0f}" for c in cells) + star)

    print("\n(2) NET-ONLY in-code guard (alt a) — veto per-tick on sign of net only, sweep |net| floor:")
    print(f"{'net_floor':>9} {'blocked_n':>9} {'blocked$':>9} {'router_net':>10}")
    for floor in (20, 30, 40, 50, 60):
        bn = 0; bp = 0.0
        for gate, p, te, t0 in trades:
            mins, closes = daycache[t0]
            idx = [i for i in range(len(mins)) if mins[i] <= te]
            if len(idx) < 6:
                continue
            _er, net = dr.er_net([closes[i] for i in idx])
            down = net <= -floor; up = net >= floor
            veto = (gate in dr.DOWN_OFF and down) or (gate in dr.UP_OFF and up)
            if veto:
                bn += 1; bp += p
        print(f"{floor:>9} {bn:>9} ${bp:>+8.0f} ${base-bp:>+9.0f}")


if __name__ == "__main__":
    main()
