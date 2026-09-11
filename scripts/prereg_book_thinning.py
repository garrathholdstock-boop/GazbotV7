#!/usr/bin/env python3
"""Evaluate the PRE-REGISTERED book-thinning test for one session (or a range).

    PYTHONPATH=src .venv/bin/python scripts/prereg_book_thinning.py --date 2026-09-12
    PYTHONPATH=src .venv/bin/python scripts/prereg_book_thinning.py --range 2026-08-14 2026-09-11 --dry-run

The registration is data/prereg_book_thinning.json and it is the authority. This script
reads its thresholds from that file and MUST NOT hardcode them -- a threshold that lives
in two places is a threshold that can be tuned in one of them.

★★★ EVERY READ IS CAUSAL. The two ways this desk has manufactured edges are (1) pricing a
fill at a level that already passed, and (2) calling drift.read(), which has no upper time
bound and look-aheads when replayed -- on 2026-09-10 it returned DOWN where the causal read
said UP. Both are avoided here by construction: entry is the NEXT bar's open, and drift is
fed a slice that ends at the entry minute.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import duckdb

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
from gazbot7 import drift  # noqa: E402

PREREG = f"{GB}/data/prereg_book_thinning.json"
OPEN_MOD, FLAT_MOD = 13 * 60 + 30, 20 * 60 + 40
VPP, FEE = 2.0, 1.50


def _cfg():
    with open(PREREG) as fh:
        return json.load(fh)


def minute_book(con, day: str):
    """Per-minute book features. Hygiene exactly as registered."""
    return con.execute("""
      select ts_ms//60000*60 as m,
             median(bid1s+bid2s+bid3s+ask1s+ask2s+ask3s) as depth3,
             count(distinct ask1p)                       as ask_vals,
             count(*)                                    as n
      from depth_snap
      where symbol='MNQ' and ask1p>bid1p and bid1p>0
        and cast(to_timestamp(ts_ms/1000) at time zone 'UTC' as date) = ?
      group by 1 having count(*) >= 5
    """, [day]).df()


def minute_bars(con, day: str):
    b = con.execute("""
      select bar_ts as m, open, high, low, "close" from bars
      where symbol='MNQ' and timeframe='1min'
        and cast(to_timestamp(bar_ts) at time zone 'UTC' as date) = ?
      order by bar_ts""", [day]).df()
    if b.empty:
        b = con.execute("""
          select bar_ts//60*60 as m, first(open order by bar_ts) as open,
                 max(high) as high, min(low) as low,
                 last("close" order by bar_ts) as "close"
          from bars where symbol='MNQ' and timeframe='5s'
            and cast(to_timestamp(bar_ts) at time zone 'UTC' as date) = ?
          group by 1 order by 1""", [day]).df()
    return b


def _mod(m):
    t = dt.datetime.fromtimestamp(int(m), dt.UTC)
    return t.hour * 60 + t.minute


def simulate(bars, i_entry, side, ladder, ladder_usd, stop_pt=None):
    """Ladder as RESTING LIMITS + flat at 20:40Z. Returns (pnl_usd, mae_pt, exits)."""
    # ★ THE REGISTRATION SAYS "the OPEN of the next bar" and this is the only place that
    # implements it. Asserted rather than defaulted: a silent fallback to close would be a
    # different rule from the one that was registered.
    if "open" not in bars.columns:
        raise RuntimeError("minute bars carry no 'open' — cannot honour the registered entry rule")
    entry = float(bars.iloc[i_entry]["open"])
    rest = bars.iloc[i_entry:]
    rest = rest[[_mod(m) < FLAT_MOD for m in rest.m]]
    if len(rest) < 2:
        return None
    lots, pnl, done, mae = len(ladder), 0.0, [], 0.0
    for _, row in rest.iloc[1:].iterrows():
        hi, lo = float(row.high), float(row.low)
        adverse = (entry - lo) if side > 0 else (hi - entry)
        mae = max(mae, adverse)
        if stop_pt is not None and adverse >= stop_pt and lots > 0:
            pnl += lots * (-stop_pt * VPP - FEE)
            lots = 0
            done.append("STOP")
            break
        for k, tgt in enumerate(ladder):
            if k in done or lots <= 0:
                continue
            lvl = entry + side * tgt
            hit = (hi >= lvl) if side > 0 else (lo <= lvl)
            if hit:                       # a RESTING limit fills AT its level
                pnl += (tgt * VPP) - FEE
                lots -= 1
                done.append(k)
    if lots > 0:
        last = float(rest.iloc[-1]["close"])
        pnl += lots * (side * (last - entry) * VPP - FEE)
    return dict(entry=entry, pnl_usd=round(pnl, 2), mae_pt=round(mae, 2),
                rungs_filled=len([d for d in done if isinstance(d, int)]))


def run_session(day: str, cfg: dict) -> dict:
    cap = duckdb.connect(f"{GB}/data/capture.db", read_only=True)
    dep = duckdb.connect(f"{GB}/data/depth.db", read_only=True)
    bars = minute_bars(cap, day)
    book = minute_book(dep, day)
    out = {"date": day, "counted": True}

    bars = bars[[OPEN_MOD <= _mod(m) < FLAT_MOD for m in bars.m]].reset_index(drop=True)
    if len(bars) < 60:
        return {**out, "counted": False, "excluded_reason": f"only {len(bars)} session bars"}
    book = book[book.ask_vals > 1]                       # frozen-book minutes out
    if len(book) < cfg["trigger_thinning"]["minimum_baseline_minutes"]:
        return {**out, "counted": False,
                "excluded_reason": f"depth capture thin/down ({len(book)} usable minutes)"}

    th = float(cfg["trigger_thinning"]["threshold"])
    dmap = dict(zip(book.m.astype(int), book.depth3.astype(float)))
    open_ts = int(bars.m.iloc[0])

    fire_thin = fire_drift = None
    ratio_at = {}
    for i in range(len(bars)):
        m = int(bars.m.iloc[i])
        # ── WHEN: depth ratio, both windows ending strictly before this minute ──
        trail = [dmap[x] for x in range(m - 180, m, 60) if x in dmap]
        base = [dmap[x] for x in range(open_ts, m - 900, 60) if x in dmap]
        if len(trail) >= 2 and len(base) >= cfg["trigger_thinning"]["minimum_baseline_minutes"]:
            trail.sort(); base.sort()
            r = (trail[len(trail)//2] / base[len(base)//2]) if base[len(base)//2] else None
            if r is not None:
                ratio_at[m] = round(r, 3)
                if r <= th and fire_thin is None:
                    fire_thin = i
        # ── WHICH WAY: drift over a slice that ENDS HERE ──
        sl = [(int(bars.m.iloc[j]), float(bars.high.iloc[j]), float(bars.low.iloc[j]),
               float(bars["close"].iloc[j])) for j in range(i + 1)]
        d = drift.compute(sl)
        if d.confirmed and d.direction in ("UP", "DOWN") and fire_drift is None:
            fire_drift = (i, 1 if d.direction == "UP" else -1)
        if fire_thin is not None and fire_drift is not None:
            break

    lad = [50.0, 100.0, 200.0, 300.0]
    lusd = [100.0, 200.0, 400.0, 600.0]
    out["thin_fired_at"] = None if fire_thin is None else int(bars.m.iloc[fire_thin])
    out["drift_fired_at"] = None if fire_drift is None else int(bars.m.iloc[fire_drift[0]])
    out["min_depth_ratio"] = min(ratio_at.values()) if ratio_at else None

    # ARM A — drift only (the control / incumbent)
    if fire_drift and fire_drift[0] + 1 < len(bars):
        out["A_drift_only"] = simulate(bars, fire_drift[0] + 1, fire_drift[1], lad, lusd)
    else:
        out["A_drift_only"] = None

    # ARM B — thinning only, direction from drift's CURRENT read
    if fire_thin is not None and fire_thin + 1 < len(bars):
        sl = [(int(bars.m.iloc[j]), float(bars.high.iloc[j]), float(bars.low.iloc[j]),
               float(bars["close"].iloc[j])) for j in range(fire_thin + 1)]
        d = drift.compute(sl)
        s = 1 if d.direction == "UP" else (-1 if d.direction == "DOWN" else 0)
        out["B_thinning_only"] = simulate(bars, fire_thin + 1, s, lad, lusd) if s else None
    else:
        out["B_thinning_only"] = None

    # ARM C — THE HYPOTHESIS: both, entering at whichever condition completes last
    if fire_thin is not None and fire_drift is not None:
        i_c = max(fire_thin, fire_drift[0])
        if i_c + 1 < len(bars):
            out["C_both"] = simulate(bars, i_c + 1, fire_drift[1], lad, lusd)
            out["C_both_stop150_diagnostic"] = simulate(bars, i_c + 1, fire_drift[1],
                                                        lad, lusd, stop_pt=150.0)
    else:
        out["C_both"] = None
        out["C_both_stop150_diagnostic"] = None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--range", nargs=2, metavar=("FROM", "TO"))
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print; never append to the registration")
    a = ap.parse_args()
    cfg = _cfg()

    days = []
    if a.date:
        days = [a.date]
    elif a.range:
        d0 = dt.date.fromisoformat(a.range[0]); d1 = dt.date.fromisoformat(a.range[1])
        while d0 <= d1:
            if d0.weekday() < 5:
                days.append(d0.isoformat())
            d0 += dt.timedelta(days=1)
    else:
        days = [(dt.datetime.now(dt.UTC).date()).isoformat()]

    rows = [run_session(d, cfg) for d in days]
    for r in rows:
        c = r.get("C_both")
        print(f"{r['date']}  thin={str(r.get('min_depth_ratio')):>6}  "
              f"A={(r.get('A_drift_only') or {}).get('pnl_usd')}  "
              f"B={(r.get('B_thinning_only') or {}).get('pnl_usd')}  "
              f"C={(c or {}).get('pnl_usd')}"
              + ("" if r.get("counted") else f"   EXCLUDED: {r.get('excluded_reason')}"))

    if a.dry_run:
        print("\n--dry-run: nothing appended.")
        return 0
    first = cfg["first_eligible_session"]
    keep = [r for r in rows if r["date"] >= first]
    if not keep:
        print(f"\nNothing on or after the first eligible session {first} — nothing appended.")
        return 0
    have = {s["date"] for s in cfg["sessions"]}
    cfg["sessions"].extend([r for r in keep if r["date"] not in have])
    cfg["sessions"].sort(key=lambda s: s["date"])
    n = len([s for s in cfg["sessions"] if s.get("counted")])
    cfg["status"] = (f"ACTIVE — {n}/{cfg['sessions_required']} sessions counted. "
                     f"Verdict is not read before {cfg['sessions_required']}.")
    tmp = PREREG + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, PREREG)
    print(f"\nappended {len(keep)} session(s) — {n}/{cfg['sessions_required']} counted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
