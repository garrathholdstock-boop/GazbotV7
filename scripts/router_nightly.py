#!/usr/bin/env python3
"""ROUTER NIGHTLY — post-session performance review of the direction-router (operator 2026-07-28).

Answers the three operator questions for one Paris day:
  (1) Was it OPTIMAL / did we BLOCK ADEQUATELY?  — the router benched some gates. Every time a benched
      gate WANTED to open, the tournament logs `SUPPRESSED-OPEN: <gate> <side> would open @<px> t=<epoch>`.
      Reprice each blocked signal tick-honest (scalp-2R / 1-ATR stop) → benched-and-would've-LOST = a GOOD
      block; benched-and-would've-WON = a MISSED trade (the cost of over-benching).
  (2) Did we MISS good trades?  — the sum of blocked would-be WINNERS.
  (3) NET router value = blocked-losses-SAVED − missed-wins.
  + LEAKAGE: realised trades a managed gate took while ON that lost in a regime it maybe should've been
    benched in (a router that let a loser through).

READ-ONLY. Data = the gazbot7-tournament journal (SUPPRESSED-OPEN + DISABLED-change lines) + capture.db
(bars/ticks) + gazbot7.db (realised trades) + the live direction_router regime replay. Writes
data/router_nightly/<date>.json; prints the report. Feeds the Friday week-review (rollup of the nightlies).
⚠ blocked-signal P&L is a tick-honest ESTIMATE under a standard scalp exit (the benched trade never ran).

  PYTHONPATH=src .venv/bin/python scripts/router_nightly.py [--date YYYY-MM-DD]   (default: yesterday Paris)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections import defaultdict

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import Position, exit_scalp  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
OUTDIR = "/home/alphabot/gazbot7/data/router_nightly"
VPP, FEE = 2.0, 1.50
SUPP_RE = re.compile(r"SUPPRESSED-OPEN: (\S+) (\S+) would open @([\d.]+).*? t=(\d+)")
DISA_RE = re.compile(r"DISABLED \(no new entries\): (\[.*\]|none)")
DEDUP_GAP_S = 120   # collapse a benched gate's repeated per-tick SUPPRESSED-OPENs into one signal


def paris_day_bounds(date_str):
    """UTC [start,end) for a Paris calendar day (Paris = UTC+2 in summer)."""
    d = dt.date.fromisoformat(date_str)
    start = dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone(dt.timedelta(hours=2))) - dt.timedelta(hours=2)
    return start, start + dt.timedelta(days=1)


def journal_lines(t0, t1):
    since = t0.strftime("%Y-%m-%d %H:%M:%S")
    until = t1.strftime("%Y-%m-%d %H:%M:%S")
    out = subprocess.run(["journalctl", "-u", "gazbot7-tournament", "--since", since, "--until", until,
                          "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=120)
    return out.stdout.splitlines()


def reprice_scalp(con, side, entry_px, t0):
    """Tick-honest scalp-2R / 1-ATR-stop P&L estimate for a would-be trade at (entry_px, t0)."""
    rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, max(high) hi, min(low) lo FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={t0-1800} AND bar_ts<={t0} GROUP BY 1""").fetchall()
    atr = sum(r[1]-r[2] for r in rows)/len(rows) if len(rows) >= 6 else 0.0
    if atr <= 0:
        return None
    ticks = con.execute(f"""SELECT price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={int(t0*1000)}
        AND ts_ms<={int((t0+90*60)*1000)} ORDER BY ts_ms""").fetchall()
    if len(ticks) < 2:
        return None
    exit_px = ticks[-1][0]
    for (px,) in ticks[1:]:
        r = exit_scalp(Position(side, entry_px, atr, 0.0), px, target_r=2.0, stop_atr_mult=1.0)
        if r:
            exit_px = px
            break
    pts = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
    return pts * VPP - FEE


def main():
    ap = argparse.ArgumentParser()
    # default = the just-completed Paris day (Paris now − 3h, so a ~22:50 UTC cron reviews the day that
    # rolled at 22:00 UTC; a daytime manual run reviews today-so-far).
    ap.add_argument("--date", default=(dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
                                       - dt.timedelta(hours=3)).strftime("%Y-%m-%d"))
    date = ap.parse_args().date
    t0, t1 = paris_day_bounds(date)
    lines = journal_lines(t0, t1)

    # (a) blocked signals, deduped per gate
    raw = defaultdict(list)   # gate -> [(side, px, epoch)]
    for ln in lines:
        m = SUPP_RE.search(ln)
        if m:
            raw[m.group(1)].append((m.group(2), float(m.group(3)), int(m.group(4)) // 1000))  # t is ms → s
    blocked = defaultdict(list)
    for gate, evs in raw.items():
        evs.sort(key=lambda e: e[2])
        last = -1e9
        for side, px, ep in evs:
            if ep - last >= DEDUP_GAP_S:
                blocked[gate].append((side, px, ep))
                last = ep

    # (b) regime timeline (router replay)
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    ds = t0.timestamp()
    rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1""").fetchall()
    marks = dr.replay_marks([r[0] for r in rows], [r[1] for r in rows], int(ds), int(ds+86400)) if len(rows) > dr.WINDOW else []
    regime_time = defaultdict(int)
    for _mt, s, _e, _n in marks:
        regime_time[s] += 1

    # (c) reprice the blocked signals
    per_gate = {}
    for gate, sigs in blocked.items():
        won = lost = 0
        won_pnl = lost_pnl = 0.0
        for side, px, ep in sigs:
            p = reprice_scalp(con, side, px, ep)
            if p is None:
                continue
            if p >= 0:
                won += 1
                won_pnl += p
            else:
                lost += 1
                lost_pnl += p
        per_gate[gate] = dict(n=len(sigs), won=won, won_pnl=won_pnl, lost=lost, lost_pnl=lost_pnl,
                              net_blocked=won_pnl+lost_pnl)

    con.close()

    # ── report ──
    tot_marks = sum(regime_time.values()) or 1
    print(f"ROUTER NIGHTLY — {date} (Paris)   ·   regime: "
          + "  ".join(f"{k} {100*v//tot_marks}%" for k, v in sorted(regime_time.items())))
    print("router knobs: ER>=%.2f |net|>=%.0f · DOWN_OFF=%s UP_OFF=%s CHOP_OFF=%s\n"
          % (dr.ER_TREND, dr.NET_MIN, sorted(dr.DOWN_OFF), sorted(dr.UP_OFF), sorted(dr.CHOP_OFF)))
    print("BLOCKED SIGNALS (each = a benched gate that wanted to open; repriced tick-honest scalp-2R):")
    print(f"  {'gate':16} {'blocked':>7} {'would-WIN $':>12} {'would-LOSE $':>13} {'net blocked':>12}  verdict")
    saved = missed = 0.0
    for gate in sorted(per_gate, key=lambda g: per_gate[g]["net_blocked"]):
        b = per_gate[gate]
        saved += -b["lost_pnl"]     # losses we avoided
        missed += b["won_pnl"]      # wins we gave up
        v = "GOOD block" if b["net_blocked"] < 0 else "over-bench (missed wins)" if b["net_blocked"] > 0 else "-"
        print(f"  {gate:16} {b['n']:>7} {b['won_pnl']:>+12.0f} {b['lost_pnl']:>+13.0f} {b['net_blocked']:>+12.0f}  {v}")
    router_value = saved - missed
    print(f"\n  → blocked-losses SAVED ${saved:+.0f}  ·  wins MISSED ${missed:+.0f}  ·  NET ROUTER VALUE ${router_value:+.0f}")
    print("  (net<0 blocked = the block helped; net>0 = we benched winners. NET VALUE>0 = router earned its keep.)")

    # (d) leakage — realised managed-gate losers by regime@entry
    con2 = duckdb.connect()
    con2.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    tr = con2.execute(f"""SELECT gate, side, pnl_usd, epoch(opened_at::TIMESTAMPTZ) te FROM g.trades
        WHERE symbol='MNQ' AND epoch(opened_at::TIMESTAMPTZ)>={ds} AND epoch(opened_at::TIMESTAMPTZ)<{ds+86400}
        AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE')""").fetchall()
    con2.close()

    def reg_at(te):
        st = "CHOP"
        for mt, s, _e, _n in marks:
            if mt <= te:
                st = s
            else:
                break
        return st
    leak = [(g, p, reg_at(te)) for g, side, p, te in tr if g in dr.MANAGED and p < 0]
    print(f"\nLEAKAGE — managed-gate LOSERS that fired while ON: {len(leak)} trades, "
          f"${sum(p for _g, p, _r in leak):+.0f}")
    for g, p, r in sorted(leak, key=lambda x: x[1])[:6]:
        print(f"    {g:16} ${p:+7.1f}  regime@entry={r}")

    out = dict(date=date, regime_pct={k: round(100*v/tot_marks, 1) for k, v in regime_time.items()},
               blocked=per_gate, saved=round(saved), missed=round(missed), router_value=round(router_value),
               leakage_n=len(leak), leakage_pnl=round(sum(p for _g, p, _r in leak)))
    import os
    os.makedirs(OUTDIR, exist_ok=True)
    with open(f"{OUTDIR}/{date}.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUTDIR}/{date}.json")


if __name__ == "__main__":
    main()
