#!/usr/bin/env python3
"""ROUTER ARCHITECTURE A/B — is the 15-min polling router the best plumbing, or is a per-tick
in-code / in-tournament guard more elegant AND better on the money?

The alternatives all compute the SAME regime signal (ER + net over the trailing WINDOW). What
differs is WHEN it is sampled:
  ROUTER-NOW  : shipped — STEP=15 min grid + HOLD=2 sticky hysteresis (a poll + switch-file)
  POLL-5      : same router, finer 5-min grid
  POLL-1      : same router, 1-min grid (polling as fast as bars arrive)
  CONTINUOUS  : per-tick — regime read at the EXACT entry epoch, no grid, no hysteresis
                (== the in-code per-gate guard / in-tournament gate: alt a / c)
  EVENT-HYST  : per-tick but the raw state must have held HOLD consecutive minutes to count
                (== the event-driven confirmed-flip: alt b)

Each blocks a realised managed-fader trade iff its gate is in desired_off(regime@entry). Router net
= base - sum(blocked pnl). Also splits the delta into LAG-CAUGHT (losers the shipped poll let through
that a per-tick guard would have blocked) and OVER-BENCH (winners the shipped poll benched that a
per-tick guard would have kept).

  PYTHONPATH=src .venv/bin/python scripts/router_architecture_ab.py
"""
from __future__ import annotations
import datetime as dt, sys
from collections import defaultdict
import duckdb
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr

DB = "/home/alphabot/gazbot7/data/gazbot7.db"
WEEK_START = "2026-07-20"   # Paris Monday


def raw_state(er, net):
    if er >= dr.ER_TREND and net >= dr.NET_MIN:
        return "TREND_UP"
    if er >= dr.ER_TREND and net <= -dr.NET_MIN:
        return "TREND_DOWN"
    return "CHOP"


def load_day(con, t0, t1):
    bars = con.execute(f"""
        SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
          AND bar_ts >= {t0 - dr.WINDOW*60} AND bar_ts < {t1} GROUP BY 1 ORDER BY 1""").fetchall()
    mins = [b[0] for b in bars]
    closes = [b[1] for b in bars]
    return mins, closes


def poll_regime_at(mins, closes, t0, t1, te, step, hold):
    old_step, old_hold = dr.STEP, dr.HOLD
    dr.STEP, dr.HOLD = step, hold
    try:
        marks = dr.replay_marks(mins, closes, int(t0), int(t1))
    finally:
        dr.STEP, dr.HOLD = old_step, old_hold
    st = "CHOP"
    for mt, s, _e, _n in marks:
        if mt <= te:
            st = s
        else:
            break
    return st


def continuous_regime_at(mins, closes, te, hyst=0):
    """Instantaneous raw state at the entry epoch. hyst>0 → the raw state must be identical for the
    last `hyst` minute-marks (event-confirmed) else CHOP-fallback to prior confirmed state."""
    idx = [i for i in range(len(mins)) if mins[i] <= te]
    if len(idx) < 6:
        return "CHOP"
    if not hyst:
        er, net = dr.er_net([closes[i] for i in idx])
        return raw_state(er, net)
    # event-confirmed: walk minute-by-minute, flip only when `hyst` consecutive raw marks agree
    state = "CHOP"
    recent = []
    for j in range(6, len(idx) + 1):
        sub = [closes[i] for i in idx[:j]]
        er, net = dr.er_net(sub)
        recent.append(raw_state(er, net))
        if len(recent) > hyst:
            recent.pop(0)
        if len(recent) == hyst and len(set(recent)) == 1 and recent[0] != state:
            state = recent[0]
    return state


def main():
    from gazbot7 import pnl
    con = duckdb.connect()
    con.execute(f"ATTACH '{dr.CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    t_today = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(t_today).timestamp() if isinstance(t_today, str) else t_today.timestamp()
    wk0 = dt.datetime.fromisoformat(WEEK_START).replace(tzinfo=dt.UTC).timestamp()
    days = [(wk0 + k*86400, wk0 + (k+1)*86400) for k in range(int(round((today0 - wk0)/86400)) + 1)]

    trades = []  # (gate, pnl, te, day_t0, day_t1)
    for t0, t1 in days:
        rows = con.execute(f"""
            SELECT gate, pnl_usd, epoch(opened_at::TIMESTAMPTZ) te FROM g.trades
            WHERE symbol='MNQ' AND gate IN ({','.join("'%s'"%g for g in dr.MANAGED)})
              AND epoch(opened_at::TIMESTAMPTZ) >= {t0} AND epoch(opened_at::TIMESTAMPTZ) < {t1}
              AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE')""").fetchall()
        for gate, p, te in rows:
            trades.append((gate, p, te, t0, t1))

    daycache = {t0: load_day(con, t0, t1) for t0, t1 in days}

    schemes = ["ROUTER-NOW", "POLL-5", "POLL-1", "CONTINUOUS", "EVENT-HYST"]
    block = {s: [] for s in schemes}   # list of (gate,pnl) blocked
    base = sum(p for _, p, _, _, _ in trades)

    for gate, p, te, t0, t1 in trades:
        mins, closes = daycache[t0]
        reg = {}
        reg["ROUTER-NOW"] = poll_regime_at(mins, closes, t0, t1, te, 15, 2)
        reg["POLL-5"] = poll_regime_at(mins, closes, t0, t1, te, 5, 2)
        reg["POLL-1"] = poll_regime_at(mins, closes, t0, t1, te, 1, 2)
        reg["CONTINUOUS"] = continuous_regime_at(mins, closes, te, hyst=0)
        reg["EVENT-HYST"] = continuous_regime_at(mins, closes, te, hyst=2)
        for s in schemes:
            if gate in dr.desired_off(reg[s]):
                block[s].append((gate, p, te))

    print(f"MANAGED-FADER TRADES {WEEK_START}..now : n={len(trades)}  base=${base:+.0f}")
    print(f"knobs: ER>={dr.ER_TREND} & |net|>={dr.NET_MIN}pt/{dr.WINDOW}min\n")
    print(f"{'SCHEME':>12} {'blocked_n':>9} {'blocked$':>9} {'router_net':>10} {'Δ_vs_base':>9}")
    res = {}
    for s in schemes:
        bn = len(block[s]); bp = sum(x[1] for x in block[s]); net = base - bp
        res[s] = (bn, bp, net)
        print(f"{s:>12} {bn:>9} ${bp:>+8.0f} ${net:>+9.0f} ${net-base:>+8.0f}")

    # Lag vs over-bench decomposition: CONTINUOUS (per-tick truth) vs ROUTER-NOW (shipped poll)
    now_set = {(g, te) for g, p, te in block["ROUTER-NOW"]}
    cont_set = {(g, te) for g, p, te in block["CONTINUOUS"]}
    lag = [(g, p, te) for g, p, te in trades_flat(trades) if (g, te) in cont_set and (g, te) not in now_set]
    over = [(g, p, te) for g, p, te in trades_flat(trades) if (g, te) in now_set and (g, te) not in cont_set]
    print("\nLAG-CAUGHT (per-tick blocks, shipped poll missed) — the reaction-lag cost:")
    print(f"  n={len(lag)}  pnl=${sum(x[1] for x in lag):+.0f}  (negative = losers the 15-min lag let through)")
    print("OVER-BENCH (shipped poll blocked, per-tick kept) — the whipsaw/stale-hold cost:")
    print(f"  n={len(over)}  pnl=${sum(x[1] for x in over):+.0f}  (positive = winners the sticky poll benched)")

    # per-gate x scheme blocked pnl
    print("\nBLOCKED $ by gate (negative = removed losers = good):")
    for s in schemes:
        d = defaultdict(lambda: [0, 0.0])
        for g, p, te in block[s]:
            d[g][0] += 1; d[g][1] += p
        cells = "  ".join(f"{g}:{v[0]}/${v[1]:+.0f}" for g, v in sorted(d.items()))
        print(f"  {s:>12}: {cells}")


def trades_flat(trades):
    return [(g, p, te) for g, p, te, _, _ in trades]


if __name__ == "__main__":
    main()
