#!/usr/bin/env python3
"""GRIND_LONG full rehab — tick-honest, regime-segmented, on this week's capture.db (+ V5 archive).

Live grind_long pipeline reproduced faithfully:
  entry  : gate_grind(slope_min=0.4, fast_slope=True) LONG   (vwap_slope_fast>=0.4, 0.3<=ext_atr<=4.0)
  floors : ER(30-bar 1m)>=0.35   AND   ATR>=24pt        (deciders.ER_FLOOR / ATR_FLOOR, live)
  exit   : SCALEOUT (live slate) — Lot A scalp 2.5R (1-ATR stop) + Lot B lock-chandelier
           (start_k=3.5, lock_r=6.0, lock_k=0.5, 1-ATR native stop).  60-min max-hold cap.
  cost   : $2/pt, $1.50/RT per lot.  Entry = first tick after the 1-min signal bar closes.

Regime segmentation (operator 2026-07-31 backtest discipline): key on ATR level + ER + range-break
AND time-of-day (overnight/pre-open vs US session post-13:30 UTC). Score each config on its HOME
segments; never a blanket cross-tape number.

  PYTHONPATH=src:scripts .venv/bin/python scripts/rehab_grind_long.py
"""
from __future__ import annotations

import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import (  # noqa: E402
    Bar,
    Position,
    compute_features,
    efficiency_ratio,
    exit_chandelier_lock,
    exit_scalp,
    gate_grind,
)

VPP, FEE = 2.0, 1.5
CAP_MIN = 60
FEAT_WIN = 60      # live MinuteBars maxlen (60 completed 1m bars → compute_features / ER-30)


# ── bars: aggregate capture 5s → 1m, or read alphabot 1m directly ──
def load_1m_capture(db):
    c = duckdb.connect()
    c.execute(f"ATTACH '{db}' AS s (TYPE sqlite, READ_ONLY)")
    rows = c.execute(
        "SELECT (bar_ts//60)*60 m, arg_min(open,bar_ts) o, max(high) h, min(low) l, "
        "arg_max(close,bar_ts) cl, sum(volume) v FROM s.bars "
        "WHERE symbol='MNQ' AND timeframe='5s' GROUP BY m ORDER BY m").fetchall()
    c.close()
    return [Bar(int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rows]


def load_1m_alpha(db):
    c = duckdb.connect()
    c.execute(f"ATTACH '{db}' AS s (TYPE sqlite, READ_ONLY)")
    rows = c.execute("SELECT bar_ts,open,high,low,close,volume FROM s.bar_history "
                     "WHERE symbol='MNQ' AND timeframe='1m' ORDER BY bar_ts").fetchall()
    c.close()
    return [Bar(int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rows]


def tick_con(db, table, col_ts="ts_ms"):
    con = duckdb.connect()
    con.execute(f"ATTACH '{db}' AS tk (TYPE sqlite, READ_ONLY)")
    con.execute(f"CREATE TABLE tick AS SELECT {col_ts} ts_ms, price FROM tk.{table} WHERE symbol='MNQ'")
    con.execute("CREATE INDEX ix ON tick(ts_ms)")
    span = con.execute("SELECT min(ts_ms),max(ts_ms) FROM tick").fetchone()
    return con, span


# ── exit replay: Lot A scalp target_r + Lot B (mode) — both native 1-ATR stop, first-touch ──
def replay(entry_px, atr, ticks, a_r, b_mode):
    """Return (pnl_A, pnl_B, exit_ms_last) for a LONG. b_mode: 'wide'|'tight'|float R."""
    peak = 0.0
    aP = bP = None
    aMs = bMs = ticks[-1][0]
    stop = atr  # 1-ATR native stop (points)
    for ts, px in ticks:
        fav = px - entry_px
        if fav > peak:
            peak = fav
        pos = Position("LONG", entry_px, atr, peak)
        if aP is None:
            if px <= entry_px - stop:
                aP, aMs = -stop, ts
            elif px >= entry_px + a_r * stop:
                aP, aMs = a_r * stop, ts
        if bP is None:
            if px <= entry_px - stop:
                bP, bMs = -stop, ts
            elif b_mode == "wide":
                if exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5):
                    bP, bMs = fav, ts
            elif b_mode == "tight":
                from gazbot7.deciders import exit_chandelier
                if exit_chandelier(pos, px, start_k=1.5, min_k=0.5, tighten=0.75):
                    bP, bMs = fav, ts
            else:  # fixed R
                if px >= entry_px + float(b_mode) * stop:
                    bP, bMs = float(b_mode) * stop, ts
        if aP is not None and bP is not None:
            break
    last = ticks[-1][1]
    if aP is None:
        aP = last - entry_px
    if bP is None:
        bP = last - entry_px
    return aP * VPP - FEE, bP * VPP - FEE, max(aMs, bMs)


# ── generate grind_long fires with full context ──
def gen_fires(bars, con, tick_lo, tick_hi, er_floor=0.35, atr_floor=24.0, slope_min=0.4,
              ext_hi=4.0, net30_floor=None, us_only=False):
    fires = []
    n = len(bars)
    for i in range(n):
        w = bars[max(0, i - (FEAT_WIN - 1)):i + 1]
        if len(w) < 6:
            continue
        f = compute_features(w)
        e = gate_grind(f, tape_net=0.0, slope_min=slope_min, fast_slope=True, ext_hi=ext_hi)
        if e is None or e.side != "LONG":
            continue
        er = efficiency_ratio(w)
        if er < er_floor or f.atr < atr_floor:
            continue
        if net30_floor is not None and f.net30_pt < net30_floor:
            continue
        if us_only:
            _d = dt.datetime.fromtimestamp(bars[i].ts, dt.UTC)
            if _d.hour * 60 + _d.minute < 13 * 60 + 30:
                continue
        dms = (bars[i].ts + 60) * 1000
        if dms <= tick_lo or dms > tick_hi:
            continue
        # context
        prior = w[:-1][-30:]
        hi30 = max((b.high for b in prior), default=f.price)
        broke = f.price > hi30                         # genuine range-break vs poking resistance
        dist_hi_atr = (hi30 - f.price) / f.atr if f.atr else 0.0   # >0 = below recent high (buying INTO resistance)
        d = dt.datetime.fromtimestamp(bars[i].ts, dt.UTC)
        us = d.hour * 60 + d.minute >= 13 * 60 + 30    # US cash session
        fires.append(dict(ts=bars[i].ts, dms=dms, day=str(d.date()), hour=d.hour, us=us,
                          atr=f.atr, er=er, ext=f.ext_atr, slope=f.vwap_slope_fast,
                          net30=f.net30_pt, price=f.price, broke=broke, dist_hi_atr=dist_hi_atr))
    return fires


def price_fires(fires, con, a_r=2.5, b_mode="wide"):
    """Attach tick-honest pnl (A,B,combined) to each fire; one-position-at-a-time per gate."""
    out = []
    nxt = 0
    for fr in fires:
        if fr["dms"] <= nxt:
            fr = {**fr, "skip": True}
            out.append(fr)
            continue
        ticks = con.execute("SELECT ts_ms,price FROM tick WHERE ts_ms>? AND ts_ms<=? ORDER BY ts_ms",
                            [fr["dms"], fr["dms"] + CAP_MIN * 60000]).fetchall()
        if len(ticks) < 2:
            fr = {**fr, "skip": True}
            out.append(fr)
            continue
        epx = ticks[0][1]
        pa, pb, xms = replay(epx, fr["atr"], ticks[1:], a_r, b_mode)
        nxt = xms
        out.append({**fr, "skip": False, "pa": pa, "pb": pb, "pnl": pa + pb})
    return [f for f in out if not f.get("skip")]


def summ(rows, key="pnl"):
    n = len(rows)
    net = sum(r[key] for r in rows)
    w = sum(1 for r in rows if r[key] > 0)
    return n, round(net), (round(100 * w / n) if n else 0)


# ── regime bucketing (operator discipline: ER + ATR + range-break, + time-of-day) ──
def regime(fr):
    er = fr["er"]
    if er < 0.15:
        r = "dead-chop"
    elif er < 0.30:
        r = "norm-chop"
    elif er < 0.45:
        r = "building"
    else:
        r = "trend"
    return r


def atr_band(a):
    return "lo<16" if a < 16 else ("mid16-24" if a < 24 else "hi>=24")


def table(rows, keyfn, order=None, key="pnl"):
    import collections
    b = collections.defaultdict(list)
    for r in rows:
        b[keyfn(r)].append(r)
    ks = order or sorted(b)
    out = []
    for k in ks:
        if k not in b:
            continue
        n, net, w = summ(b[k], key)
        pt = round(net / n) if n else 0
        out.append(f"    {str(k):12} {n:>4}tr  net ${net:>+6}  {w:>3}%W  ${pt:>+4}/tr")
    return "\n".join(out)


def main():
    import collections
    print("=" * 78)
    print("GRIND_LONG REHAB — tick-honest on capture.db (07-23→07-31 ticks)")
    print("=" * 78)
    bars = load_1m_capture("data/capture.db")
    con, span = tick_con("data/capture.db", "ticks")
    lo, hi = span
    print(f"1m bars={len(bars)}  ticks {dt.datetime.fromtimestamp(lo/1000,dt.UTC)} → "
          f"{dt.datetime.fromtimestamp(hi/1000,dt.UTC)}\n")

    # ---- funnel ----
    raw = gen_fires(bars, con, lo, hi, er_floor=0.0, atr_floor=0.0)
    print("SIGNAL FUNNEL (grind LONG, one-min signal):")
    for nm, ef, af in [("raw", 0.0, 0.0), ("ER>=.35", 0.35, 0.0), ("ATR>=24", 0.0, 24.0),
                       ("LIVE both", 0.35, 24.0)]:
        f = [x for x in raw if x["er"] >= ef and x["atr"] >= af]
        print(f"  {nm:10} signals={len(f)}")

    rawP = price_fires(raw, con)          # realized, one-position-at-a-time, priced on ticks
    print(f"\nRealized (one-at-a-time), NO floors: {summ(rawP)}  A={summ(rawP,'pa')} B={summ(rawP,'pb')}")

    # ---- baseline live config ----
    liveF = [x for x in raw if x["er"] >= 0.35 and x["atr"] >= 24.0]
    liveP = price_fires(liveF, con)
    print(f"LIVE config (ER>=.35 & ATR>=24):     {summ(liveP)}  A={summ(liveP,'pa')} B={summ(liveP,'pb')}")

    # ---- regime segmentation on the RAW realized population ----
    print("\n" + "-" * 78)
    print("RAW population sliced by REGIME (ER-keyed), TIME-OF-DAY, ATR band, DAY:")
    print("-" * 78)
    print("  by ER-regime:")
    print(table(rawP, regime, ["dead-chop", "norm-chop", "building", "trend"]))
    print("  by time-of-day:")
    print(table(rawP, lambda r: "US>=13:30" if r["us"] else "overnight"))
    print("  by ATR band:")
    print(table(rawP, lambda r: atr_band(r["atr"]), ["lo<16", "mid16-24", "hi>=24"]))
    print("  by range-break at entry:")
    print(table(rawP, lambda r: "BROKE-high" if r["broke"] else "into-resist"))
    print("  by DAY:")
    print(table(rawP, lambda r: r["day"]))

    # ---- the WINNERS we must preserve (Lot B tail runs) ----
    bigs = sorted([r for r in rawP if r["pb"] > 80], key=lambda r: -r["pb"])
    print(f"\n  BIG Lot-B tail winners to PRESERVE (pb>80): n={len(bigs)}, "
          f"sum ${round(sum(r['pb'] for r in bigs))}")
    for r in bigs[:12]:
        print(f"    {r['day']} h{r['hour']:>2} ER{r['er']:.2f} ATR{r['atr']:>4.0f} ext{r['ext']:.1f} "
              f"{'BROKE' if r['broke'] else 'resist':>6} slope{r['slope']:.2f}  B=${round(r['pb']):+}")

    # ---- FILTER SEARCH: keep-the-winners test ----
    print("\n" + "-" * 78)
    print("FILTER SEARCH (each scored on RAW realized; must KEEP the big-B winners):")
    print("-" * 78)
    wkeys = {(r["day"], r["ts"]) for r in bigs}

    def score(pred, name):
        keep = [r for r in rawP if pred(r)]
        n, net, w = summ(keep)
        kept_bigs = sum(1 for r in keep if (r["day"], r["ts"]) in wkeys)
        drop_net = round(sum(r["pnl"] for r in rawP if not pred(r)))
        tag = "" if kept_bigs == len(bigs) else f"  <<FAKE? drops {len(bigs)-kept_bigs}/{len(bigs)} winners"
        print(f"  {name:34} n={n:>4} net=${net:>+6} {w:>3}%W  bigs {kept_bigs}/{len(bigs)}  "
              f"(cut pop ${drop_net:+}){tag}")

    score(lambda r: True, "none (raw)")
    for ef in (0.15, 0.20, 0.25, 0.30, 0.35, 0.45):
        score(lambda r, e=ef: r["er"] >= e, f"ER>={ef}")
    for af in (12, 16, 20, 24):
        score(lambda r, a=af: r["atr"] >= a, f"ATR>={af}")
    score(lambda r: r["us"], "US session only (>=13:30 UTC)")
    score(lambda r: r["broke"], "range-BREAK only (px>prior-30hi)")
    score(lambda r: r["ext"] <= 2.0, "ext_atr<=2.0 (not over-extended)")
    score(lambda r: r["ext"] <= 1.5, "ext_atr<=1.5")
    score(lambda r: r["slope"] >= 0.7, "slope_fast>=0.7 (strong)")
    score(lambda r: r["net30"] >= 0, "net30>=0 (not fading a drop)")
    # combos
    score(lambda r: r["us"] and r["er"] >= 0.20, "US & ER>=.20")
    score(lambda r: r["us"] and r["broke"], "US & range-BREAK")
    score(lambda r: r["er"] >= 0.20 and r["broke"], "ER>=.20 & range-BREAK")
    score(lambda r: r["er"] >= 0.20 and r["ext"] <= 2.0, "ER>=.20 & ext<=2.0")
    score(lambda r: r["us"] and r["er"] >= 0.20 and r["ext"] <= 2.5, "US & ER>=.20 & ext<=2.5")

    con.close()
    return rawP, bigs, wkeys


if __name__ == "__main__":
    main()
