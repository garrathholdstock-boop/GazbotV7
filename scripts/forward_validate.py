#!/usr/bin/env python3
"""Forward-validation harness for the two-gate complementary stack (2026-07-18).

Freezes tonight's candidate gates + damage-control and measures them HONESTLY:
  - GRIND  = gate_grind(slope_min .4, fast_slope) · vol-adaptive chandelier · peak-trail day-latch
  - RGV    = gate_reversal_grab(LONG, ext 2.0, fast) · 2R exit (1-ATR stop) · flat day-latch

Two validations:
  1. WALK-FORWARD (the honest OOS): for each test day, the latch param is re-tuned on the
     PRIOR days only, then applied to the unseen day. No test day informs its own param.
  2. FROZEN: the params chosen tonight (grind peak-trail -300, rgv flat -400), applied as-is.

Run on the 25-day tune set (default) to see if the APPROACH generalises; then re-run on
NEW captured days (post 2026-07-17) as they accumulate — that's the real forward test.

  PYTHONPATH=src python scripts/forward_validate.py                    # alphabot2 1m tune set
  PYTHONPATH=src python scripts/forward_validate.py --db data/capture.db --tf 5s --from 2026-07-18
"""
import argparse
import sqlite3
import statistics as st

from gazbot7.deciders import (Bar, compute_features, gate_grind, gate_reversal_grab,
                              chandelier_start_k, exit_chandelier, exit_scalp, Position)

FROZEN_GRIND_GB = 300.0    # grind peak-trail give-back ($) — locked 2026-07-18
FROZEN_RGV_DD = 400.0      # rgv flat day-drawdown ($) — locked 2026-07-18
GRIND_GB_GRID = [200, 250, 300, 350, 400]
RGV_DD_GRID = [300, 350, 400, 450, 500]


def _load_days(db, tf, dfrom, dto):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    col = "bar_ts" if tf != "5s" else "bar_ts"
    q = (f"SELECT DISTINCT date({col},'unixepoch') d FROM {'bar_history' if tf!='5s' else 'bars'} "
         f"WHERE symbol='MNQ' AND timeframe=? ")
    if dfrom: q += f"AND date({col},'unixepoch')>='{dfrom}' "
    if dto: q += f"AND date({col},'unixepoch')<='{dto}' "
    q += "ORDER BY 1"
    days = [r["d"] for r in c.execute(q, (tf,))]
    out = []
    for day in days:
        tbl = "bar_history" if tf != "5s" else "bars"
        rows = c.execute(f"SELECT bar_ts,open,high,low,close,volume FROM {tbl} "
                         f"WHERE symbol='MNQ' AND timeframe=? AND date(bar_ts,'unixepoch')=? ORDER BY bar_ts",
                         (tf, day)).fetchall()
        if tf == "5s":  # aggregate 5s → 1m to match the decided timeframe
            agg = {}
            for r in rows:
                m = (r["bar_ts"] // 60) * 60
                b = agg.get(m)
                if b is None:
                    agg[m] = [m, r["open"], r["high"], r["low"], r["close"], r["volume"] or 0]
                else:
                    b[2] = max(b[2], r["high"]); b[3] = min(b[3], r["low"]); b[4] = r["close"]; b[5] += r["volume"] or 0
            bars = [Bar(*v) for v in agg.values()]
        else:
            bars = [Bar(r["bar_ts"], r["open"], r["high"], r["low"], r["close"], r["volume"] or 0) for r in rows]
        if len(bars) >= 600:
            out.append((day, bars))
    c.close()
    return out


def _load_days_lake(dfrom, dto):
    """Same shape as _load_days, but over the FULL history via gazbot7.lake.

    ★★★2026-08-18. _load_days reads ONE sqlite file. Pointed at capture.db — which is PRUNED to a
    few trading days — a walk-forward "from 2026-06-01" silently validates on whatever the hot tier
    holds and reports as though it covered the range. The whole point of a walk-forward is the
    breadth of the out-of-sample period, so a silently-truncated one is worse than none: it looks
    like evidence. Same defect just fixed in run_census.py.

    Aggregates 5s -> 1m in SQL, which is also ~40x faster than the python fold it replaces.
    ⚠ CAST(bar_ts/60 AS INT)*60, never bar_ts/60*60: DuckDB `/` is FLOAT and that is a silent no-op
    which once read 5s bars as "1m" for hours.
    """
    from gazbot7.lake import connect as lake_connect
    con = lake_connect(symbol="MNQ")
    where = ["symbol='MNQ'", "timeframe='5s'"]
    if dfrom:
        where.append(f"CAST(to_timestamp(bar_ts) AS DATE) >= DATE '{dfrom}'")
    if dto:
        where.append(f"CAST(to_timestamp(bar_ts) AS DATE) <= DATE '{dto}'")
    rows = con.execute(f"""
        SELECT CAST(to_timestamp(bar_ts) AS DATE) d, CAST(bar_ts/60 AS INT)*60 t,
               arg_min(open, bar_ts) o, MAX(high) h, MIN(low) l,
               arg_max(close, bar_ts) c, SUM(COALESCE(volume,0)) v
        FROM bars WHERE {' AND '.join(where)}
        GROUP BY d, t ORDER BY d, t""").fetchall()
    con.close()
    byday = {}
    for d, t, o, h, low, c, v in rows:
        byday.setdefault(str(d), []).append(Bar(int(t), float(o), float(h), float(low),
                                               float(c), float(v or 0)))
    out = [(d, b) for d, b in sorted(byday.items()) if len(b) >= 600]
    print(f"[lake] {len(out)} usable days, {sum(len(b) for _, b in out):,} 1-min bars"
          + (f", {out[0][0]} .. {out[-1][0]}" if out else ""))
    return out


def _grind_trades(bars):
    out = []; op = None
    for i in range(len(bars)):
        w = bars[max(0, i - 59):i + 1]
        if len(w) < 6: continue
        f = compute_features(w); px = f.price
        if op:
            fav = (px - op['e']) if op['s'] == 'LONG' else (op['e'] - px); op['peak'] = max(op['peak'], fav)
            pos = Position(op['s'], op['e'], op['atr'], op['peak'])
            if exit_chandelier(pos, px, start_k=op['k'], min_k=0.5, tighten=0.75) or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0):
                g = (px - op['e']) if op['s'] == 'LONG' else (op['e'] - px); out.append(g * 2 - 1.5); op = None
        if op is None:
            e = gate_grind(f, tape_net=0.0, slope_min=0.4, fast_slope=True)
            if e: op = {'s': e.side, 'e': px, 'atr': f.atr, 'peak': 0.0, 'k': chandelier_start_k(f.atr)}
    return out


def _rgv_trades(bars):
    out = []; op = None
    for i in range(len(bars)):
        w = bars[max(0, i - 59):i + 1]
        if len(w) < 6: continue
        f = compute_features(w); px = f.price
        if op:
            pos = Position(op['s'], op['e'], op['atr'], 0.0)
            if exit_scalp(pos, px, target_r=2.0, stop_atr_mult=1.0):
                g = (px - op['e']) if op['s'] == 'LONG' else (op['e'] - px); out.append(g * 2 - 1.5); op = None
        if op is None:
            e = gate_reversal_grab(f, side="LONG", ext_min=2.0, turn_atr=0.15, fast_slope=True,
                                   fast_turn=True, atr_min=13.0, tape_net=0.0, in_rth=True)
            if e: op = {'s': e.side, 'e': px, 'atr': f.atr}
    return out


def _peak_trail(pnls, gb):
    tot = peak = 0.0; done = False
    for p in pnls:
        if done: continue
        tot += p; peak = max(peak, tot)
        if peak - tot >= gb: done = True
    return tot


def _flat(pnls, dd):
    tot = 0.0; done = False
    for p in pnls:
        if done: continue
        tot += p
        if tot <= -dd: done = True
    return tot


def walk_forward(day_streams, latch_fn, grid, min_train=8):
    """Expanding-window: tune the latch param on days[:i], apply to day i. Returns OOS per-day."""
    oos = []
    for i, (day, pnls) in enumerate(day_streams):
        if i < min_train:
            continue
        train = day_streams[:i]
        best = max(grid, key=lambda g: sum(latch_fn(p, g) for _, p in train))
        oos.append((day, latch_fn(pnls, best), best))
    return oos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/home/alphabot/alphabot2/data/alphabot.db")
    ap.add_argument("--tf", default="1m")
    ap.add_argument("--from", dest="dfrom", default=None)
    ap.add_argument("--to", dest="dto", default=None)
    ap.add_argument("--lake", action="store_true",
                    help="validate over the FULL history (V5 + Parquet + hot), not one sqlite file")
    a = ap.parse_args()

    days = (_load_days_lake(a.dfrom, a.dto) if a.lake
            else _load_days(a.db, a.tf, a.dfrom, a.dto))
    # ⚠ NAME THE SOURCE ACTUALLY READ. This printed "alphabot.db 1m" even under --lake, because
    # it echoed the --db default rather than what was used. A header that misnames its data source
    # is the same class of fault as a health line that reports on something it never checked.
    _src = ("lake (V5 + Parquet + hot)" if a.lake else f"{a.db.split('/')[-1]} {a.tf}")
    _span = f" · {days[0][0]}..{days[-1][0]}" if days else ""
    print(f"forward-validation · {len(days)} days · {_src}{_span}\n")

    grind = [(d, _grind_trades(b)) for d, b in days]
    rgv = [(d, _rgv_trades(b)) for d, b in days]

    # frozen configs
    gf = [(d, _peak_trail(p, FROZEN_GRIND_GB)) for d, p in grind]
    rf = [(d, _flat(p, FROZEN_RGV_DD)) for d, p in rgv]
    print(f"FROZEN (grind peak-trail -{int(FROZEN_GRIND_GB)}, rgv flat -{int(FROZEN_RGV_DD)}):")
    print(f"  grind {round(sum(p for _, p in gf)):>6}   rgv {round(sum(p for _, p in rf)):>6}   "
          f"combined {round(sum(p for _, p in gf) + sum(p for _, p in rf)):>6}")

    # walk-forward OOS
    gw = walk_forward(grind, _peak_trail, GRIND_GB_GRID)
    rw = walk_forward(rgv, _flat, RGV_DD_GRID)
    if gw and rw:
        gwt = sum(p for _, p, _ in gw); rwt = sum(p for _, p, _ in rw)
        tdays = [d for d, _, _ in gw]
        gmap = {d: p for d, p, _ in gw}; rmap = {d: p for d, p, _ in rw}
        comb = [gmap[d] + rmap.get(d, 0) for d in tdays]
        gs = [gmap[d] for d in tdays]; rs = [rmap.get(d, 0) for d in tdays]
        cov = sum((gs[i] - st.mean(gs)) * (rs[i] - st.mean(rs)) for i in range(len(gs))) / len(gs)
        corr = cov / ((st.pstdev(gs) or 1) * (st.pstdev(rs) or 1))
        print(f"\nWALK-FORWARD OOS ({len(tdays)} held-out days, latch re-tuned on prior days only):")
        print(f"  grind {round(gwt):>6}   rgv {round(rwt):>6}   combined {round(sum(comb)):>6}")
        print(f"  combined worst day {round(min(comb)):>6}   green {sum(1 for x in comb if x > 0)}/{len(comb)}   "
              f"grind~rgv corr {corr:+.2f}")
    else:
        print("\n(not enough days for a walk-forward split — need > 8; run on the full tune set or accumulate more)")


if __name__ == "__main__":
    main()
