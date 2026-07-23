#!/usr/bin/env python3
"""Direction-router backtest — would an auto on/off router have helped TODAY?

The gates' ER condition reads tape CLEANLINESS, not DIRECTION, so a clean DOWN-trend at ER 0.32
sits inside a long-fader's band and it fades the falling knife (today: rgv_long −$361 in one hour).
A router flips the COUNTER-TREND reversion gates off once a trend is PROVEN, back on in chop:

    TREND DOWN (confirmed) → off {rgv_long, capitulation_long}   (long-faders fade the drop)
    TREND UP   (confirmed) → off {rgv_short, thrust_short, exhaustion_short}  (short-faders fade the rise)
    CHOP / NEUTRAL          → ALL on   (both faders earn in chop)

HYSTERESIS is the whole game (today the tape flipped up→chop inside an hour, and rgv_long was green
the very hour after it looked like an /off): a raw per-mark signal only becomes the EFFECTIVE state
after HOLD consecutive marks agree, and only reverts after HOLD marks disagree. Runs every STEP min.

Backtest: build the regime timeline from capture, then for each of today's REALISED trades decide
ALLOW (gate on under the router at entry) vs BLOCK (gate off) and sum. Blocked-trades P&L = the
router's effect (negative blocked = it removed losers = it helped). ⚠ today's trades are already
partly HAND-gated (operator's manual /off's), so this is an illustrative lower bound, not a clean
counterfactual — a blocked-and-negative bucket still proves the rule catches the right trades.
DuckDB-vectorised. Read-only.

  PYTHONPATH=src python scripts/direction_router_backtest.py
"""
from __future__ import annotations

import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import pnl  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"

# ── router knobs (tunable — these are the "how proven is proven" dials) ──
ER_TREND = 0.25    # ER must clear this for a mark to read as a trend (above the 0.18 bucket line)
NET_MIN = 40.0     # AND net move over the window must be >= this many points (a real directional leg)
WINDOW = 30        # trailing 1-min bars for ER/net (matches the gate's 30-min ER)
STEP = 15          # minutes between router scans
HOLD = 2           # consecutive agreeing marks to flip a state (hysteresis, both directions)

DOWN_OFF = {"rgv_long", "capitulation_long"}
UP_OFF = {"rgv_short", "thrust_short", "exhaustion_short"}


def er_net(closes):
    c = closes[-WINDOW:]
    if len(c) < 6:
        return 0.0, 0.0
    path = sum(abs(c[i] - c[i - 1]) for i in range(1, len(c))) or 1.0
    net = c[-1] - c[0]
    return abs(net) / path, net


def _blocked(gate, st):
    return (st == "TREND_DOWN" and gate in DOWN_OFF) or (st == "TREND_UP" and gate in UP_OFF)


def run_day(con, t0, t1, verbose=False):
    """Backtest one Paris day [t0, t1). Returns a result dict; prints the regime timeline if verbose."""
    bars = con.execute(f"""
        SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) c
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
          AND bar_ts >= {t0 - WINDOW*60} AND bar_ts < {t1} GROUP BY 1 ORDER BY 1""").fetchall()
    trades = con.execute(f"""
        SELECT gate, pnl_usd, epoch(opened_at::TIMESTAMPTZ) te
        FROM g.trades WHERE symbol='MNQ'
          AND epoch(opened_at::TIMESTAMPTZ) >= {t0} AND epoch(opened_at::TIMESTAMPTZ) < {t1}
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY te""").fetchall()
    date = dt.datetime.fromtimestamp(t0 + 43200, dt.UTC).strftime("%m-%d")  # +12h → the Paris calendar day
    if not bars or not trades:
        return {"date": date, "n": len(trades), "base": sum(t[1] for t in trades),
                "router": sum(t[1] for t in trades), "delta": 0.0, "blk": [], "flips": 0, "marks": []}
    mins = [b[0] for b in bars]
    closes = [b[1] for b in bars]
    marks, state, raw_run, last_raw = [], "CHOP", 0, "CHOP"
    t = max(mins[0] - (mins[0] % (STEP * 60)) + STEP * 60, int(t0))
    while t <= mins[-1]:
        er, net = er_net([closes[i] for i in range(len(mins)) if mins[i] <= t])
        raw = "TREND_UP" if (er >= ER_TREND and net >= NET_MIN) else \
              "TREND_DOWN" if (er >= ER_TREND and net <= -NET_MIN) else "CHOP"
        raw_run = raw_run + 1 if raw == last_raw else 1
        last_raw = raw
        if raw_run >= HOLD and raw != state:
            state = raw
        marks.append((t, state, round(er, 2), round(net, 0)))
        t += STEP * 60

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
    blk = [x for x in trades if _blocked(x[0], regime_at(x[2]))]
    router = base - sum(x[1] for x in blk)
    from collections import defaultdict
    bd = defaultdict(lambda: [0, 0.0])
    for gate, p, te in blk:
        bd[(gate, regime_at(te))][0] += 1
        bd[(gate, regime_at(te))][1] += p
    return {"date": date, "n": len(trades), "base": base, "router": router, "delta": router - base,
            "blk": sorted(bd.items(), key=lambda x: x[1][1]), "flips": flips, "marks": marks}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    days = ap.parse_args().days
    t_today = pnl.paris_day_start_utc(dt.datetime.now(dt.UTC))
    today0 = dt.datetime.fromisoformat(t_today).timestamp() if isinstance(t_today, str) else t_today.timestamp()
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")

    print(f"DIRECTION-ROUTER BACKTEST — last {days} day(s)")
    print(f"knobs: ER_TREND>={ER_TREND} & |net|>={NET_MIN}pt over {WINDOW}min · scan {STEP}min · hysteresis {HOLD} marks\n")
    results = []
    for k in range(days - 1, -1, -1):     # oldest → newest
        t0 = today0 - k * 86400
        results.append(run_day(con, t0, t0 + 86400, verbose=(days == 1)))
    con.close()

    print(f"{'DATE':>6} {'trades':>7} {'baseline':>9} {'router':>8} {'delta':>7} {'flips':>6}  blocked")
    tb = tr = 0.0
    for r in results:
        tb += r["base"]
        tr += r["router"]
        blk = " · ".join(f"{g} {s.split('_')[-1][:2]} ${pl:+.0f}" for (g, s), (n, pl) in r["blk"]) or "—"
        print(f"{r['date']:>6} {r['n']:>7} ${r['base']:>+8.0f} ${r['router']:>+7.0f} ${r['delta']:>+6.0f} {r['flips']:>6}  {blk}")
    print(f"{'TOTAL':>6} {sum(r['n'] for r in results):>7} ${tb:>+8.0f} ${tr:>+7.0f} ${tr-tb:>+6.0f}")
    print(f"\n→ over {days} day(s): baseline ${tb:+.0f} → router ${tr:+.0f}  (DELTA ${tr-tb:+.0f})")
    print("(delta>0 = router helped that day; watch for days where flips are high but delta≈0/negative —\n"
          "that's whipsaw churn. ⚠ realised trades already partly hand-gated → illustrative, not clean A/B.)")


if __name__ == "__main__":
    main()
