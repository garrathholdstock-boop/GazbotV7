#!/usr/bin/env python3
"""GIVE-BACK GRID — the raw numbers behind "should the Rs tighten on quiet tape?".

Operator challenge (2026-08-01): "I absolutely don't believe wide is what we need. I have watched it.
How on earth is that going to capture small green that goes red?"

He is right that a wide exit CANNOT bank small green that goes red — by construction. So an aggregate
"wide wins" result and his observation can only both be true if the round-trippers are a minority and
tightening to catch them costs more on everything else. This script does not summarise; it prints the
decomposition so the tradeoff is visible:

    ROUND-TRIPPERS  = trades that went >= RT_GREEN_R green and still finished <= 0.
                      These are the trades he is talking about. A tight clip should win here.
    THE REST        = everything else. A tight clip caps these.
    NET             = what the whole book does at each setting.

Every candidate exit is replayed against the SAME entries on 250ms ticks with the real 1-ATR stop, so
the comparison is like-for-like. Fee $1.50/round trip (venue truth). Exits fill at the exact level with
no slippage, so every number is a CEILING — the desk's standing finding is live losses run 1.1-3.1x
modelled, and a tight clip takes MORE round trips, so it pays that tax more often. Stated, not hidden.

  PYTHONPATH=src ./.venv/bin/python scripts/giveback_grid.py [--window quiet|us|all] [--gate G]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, "/home/alphabot/gazbot7/src")
import duckdb  # noqa: E402

GB = "/home/alphabot/gazbot7"
STORE, CAP = f"{GB}/data/gazbot7.db", f"{GB}/data/capture.db"
VPP, FEE_RT, ATR_N = 2.0, 1.50, 14
MAX_HOLD_S = 120 * 60
RT_GREEN_R = 1.0        # "went green" = reached this many R favourable

# candidate Lot-A exits: fixed R multiples, and fixed DOLLAR clips (the operator's mental model)
R_GRID = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5]
D_GRID = [10, 15, 20, 30, 40, 50]


def q_atr(con, t_s: int) -> float | None:
    rows = con.execute(f"""
        SELECT CAST(bar_ts/60 AS BIGINT) m, MAX(high) h, MIN(low) l, ARG_MAX(close, bar_ts) c
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
          AND bar_ts < {t_s} AND bar_ts >= {t_s - 3600}
        GROUP BY 1 ORDER BY 1 DESC LIMIT {ATR_N + 1}""").fetchall()
    if len(rows) < ATR_N + 1:
        return None
    rows = rows[::-1]
    trs = [max(rows[i][1] - rows[i][2], abs(rows[i][1] - rows[i - 1][3]), abs(rows[i][2] - rows[i - 1][3]))
           for i in range(1, len(rows))]
    return sum(trs) / len(trs) if trs else None


def race(path, side, entry, target_pt, stop_pt):
    """First of (target, stop) along the real tick path. Returns net $ for 1 lot."""
    for _, px in path:
        fav = (px - entry) if side == "LONG" else (entry - px)
        if fav >= target_pt:
            return target_pt * VPP - FEE_RT
        if -fav >= stop_pt:
            return -stop_pt * VPP - FEE_RT
    last = path[-1][1]
    fav = (last - entry) if side == "LONG" else (entry - last)
    return fav * VPP - FEE_RT


def wide_chandelier(path, side, entry, atr, start_k=3.5, lock_r=6.0, lock_k=0.5):
    """The loaded BIG-RUN Lot-B rule: hold a start_k*ATR trail until peak>=lock_r, then lock to lock_k."""
    peak = 0.0
    stop_pt = start_k * atr
    for _, px in path:
        fav = (px - entry) if side == "LONG" else (entry - px)
        peak = max(peak, fav)
        k = lock_k if (atr > 0 and peak / atr >= lock_r) else start_k
        stop_pt = max(0.0, peak - k * atr) if peak > 0 else 0.0
        if peak > 0 and fav <= stop_pt and peak >= k * atr:
            return fav * VPP - FEE_RT
        if -fav >= 1.0 * atr:
            return -1.0 * atr * VPP - FEE_RT
    last = path[-1][1]
    fav = (last - entry) if side == "LONG" else (entry - last)
    return fav * VPP - FEE_RT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=["quiet", "us", "all"], default="quiet")
    ap.add_argument("--gate", default=None)
    a = ap.parse_args()

    sq = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    sq.row_factory = sqlite3.Row
    rows = list(sq.execute("SELECT * FROM trades WHERE closed_at IS NOT NULL ORDER BY opened_at"))
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (READ_ONLY)")

    def in_win(iso):
        t = datetime.fromisoformat(iso)
        mins = t.hour * 60 + t.minute
        quiet = (t.hour >= 22) or (mins < 810)      # 22:00 -> 13:30 UTC
        return quiet if a.window == "quiet" else (not quiet) if a.window == "us" else True

    trades = []
    for t in rows:
        if not in_win(t["opened_at"]):
            continue
        if a.gate and not t["gate"].startswith(a.gate):
            continue
        t0 = int(datetime.fromisoformat(t["opened_at"]).timestamp())
        atr = q_atr(con, t0)
        if not atr or atr <= 0:
            continue
        path = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms >= {t0 * 1000} AND ts_ms <= {(t0 + MAX_HOLD_S) * 1000}
            ORDER BY ts_ms""").fetchall()
        if len(path) < 10:
            continue
        entry, side = float(t["entry_price"]), t["side"]
        # ★ MFE for CLASSIFICATION must be measured over the ACTUAL holding period only.
        # Using the full 120-min forward path counts peaks that happened after the desk was already
        # out, which is not "we were green and gave it back" — it is "the trade would have worked
        # later". That error inflated the round-tripper count from ~19% to ~60% in the first cut.
        # The counterfactual exits below legitimately use the full forward path, because under a
        # different rule the desk WOULD still have been holding.
        t1_ms = int(datetime.fromisoformat(t["closed_at"]).timestamp() * 1000)
        held = [(ts, px) for ts, px in path if ts <= t1_ms] or path[:1]
        mfe_held = max(((px - entry) if side == "LONG" else (entry - px)) for _, px in held)
        mfe_fwd = max(((px - entry) if side == "LONG" else (entry - px)) for _, px in path)
        trades.append(dict(gate=t["gate"], side=side, entry=entry, atr=atr, path=path,
                           mfe_pt=mfe_held, mfe_fwd_pt=mfe_fwd, actual=float(t["pnl_usd"])))

    if not trades:
        print("no trades with tick coverage in this window")
        return 1

    rt = [x for x in trades if x["mfe_pt"] >= RT_GREEN_R * x["atr"] and x["actual"] <= 0]
    rest = [x for x in trades if x not in rt]

    print(f"\nGIVE-BACK GRID — window={a.window}  gate={a.gate or 'ALL'}  "
          f"n={len(trades)} tick-covered live trades")
    print(f"  ROUND-TRIPPERS (reached >={RT_GREEN_R}R green, finished <=0): {len(rt)} "
          f"({100*len(rt)/len(trades):.1f}%)   THE REST: {len(rest)}")
    print(f"  currently handed back by the round-trippers: "
          f"${sum(x['mfe_pt']*VPP for x in rt):,.0f} of peak, actually banked "
          f"${sum(x['actual'] for x in rt):,.0f}")
    print(f"\n  Fee ${FEE_RT}/RT. Exact-level fills = a CEILING. Actual-loaded book net: "
          f"${sum(x['actual'] for x in trades):,.0f}\n")

    hdr = (f"{'exit rule':<22}{'ROUND-TRIPPERS':>26}{'THE REST':>24}{'WHOLE BOOK':>26}")
    print(hdr)
    print(f"{'':<22}{'net$':>10}{'$/tr':>8}{'win%':>8}{'net$':>10}{'$/tr':>7}{'win%':>7}"
          f"{'net$':>11}{'$/tr':>8}{'win%':>7}")
    print("-" * len(hdr))

    def line(label, fn):
        def agg(group):
            if not group:
                return 0.0, 0.0, 0.0
            v = [fn(x) for x in group]
            return sum(v), sum(v) / len(v), 100 * sum(1 for z in v if z > 0) / len(v)
        a1, b1, c1 = agg(rt)
        a2, b2, c2 = agg(rest)
        a3, b3, c3 = agg(trades)
        print(f"{label:<22}{a1:>10.0f}{b1:>8.1f}{c1:>8.0f}{a2:>10.0f}{b2:>7.1f}{c2:>7.0f}"
              f"{a3:>11.0f}{b3:>8.1f}{c3:>7.0f}")

    for r in R_GRID:
        line(f"Lot A fixed {r}R", lambda x, r=r: race(x["path"], x["side"], x["entry"],
                                                      r * x["atr"], 1.0 * x["atr"]))
    print("-" * len(hdr))
    for d in D_GRID:
        line(f"fixed ${d} clip", lambda x, d=d: race(x["path"], x["side"], x["entry"],
                                                     d / VPP, 1.0 * x["atr"]))
    print("-" * len(hdr))
    line("WIDE lock-chandelier", lambda x: wide_chandelier(x["path"], x["side"], x["entry"], x["atr"]))
    line("ACTUAL (as traded)", lambda x: x["actual"])
    print("-" * len(hdr))
    print(f"\n  median entry ATR = {sorted(x['atr'] for x in trades)[len(trades)//2]:.1f} pt "
          f"→ 1R ≈ ${sorted(x['atr'] for x in trades)[len(trades)//2]*VPP:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
