"""News-Window Range Breakout (Donchian) greenfield gate — FULL filter battery.

Report flagged this as the ONE positive grave (a "detector"): best config
A = L24/B5/STOP40/TRAIL20/ARM20, reported n=27 / net +$570 / win 85% / 0 losing days.

Spec (per task):
  Active ONLY when 13 <= hour_UTC < 15 (the US news window).
  On each 1-min bar close t:
    hiL/loL = highest high / lowest low of the prior L 1-min bars (excl. current).
    LONG  when close[t] > hiL + B ;  SHORT when close[t] < loL - B.   (L=24, B=5)
  Entry = first tick after the signal bar close. Exit = TRAIL:
    hard stop STOP=40pt; once profit >= ARM=20pt, chandelier-trail TRAIL=20pt from peak.
    Time-cap 15 min, single position, 15-min cooldown.
  Tick-honest replay (stop checked BEFORE trail within a tick = conservative).
  Cost $5/RT, MNQ $2/pt.

Reuses the data-loading + tick-honest-exit machinery from trap_reclaim_sweep.py / afc_er_sweep.py.
READ-ONLY on capture.db. Does NOT touch live services or trading DBs.

  .venv/bin/python scripts/grave_donchian.py
"""
from __future__ import annotations
import datetime as _dt
import duckdb
import numpy as np
import pandas as pd

CAP = "/home/alphabot/gazbot7/data/capture.db"
SINCE, UNTIL = "2026-07-19 22:00:00", "2026-07-24 21:00:00"
# config A
L, B, STOP, ARM, TRAIL = 24, 5.0, 40.0, 20.0, 20.0
CAP_S, COOL = 900, 900           # 15-min time-cap, 15-min cooldown
NEWS_LO, NEWS_HI = 13, 15        # hour_UTC window [13,15)
FEE, VPP = 5.0, 2.0


def load(con):
    lo = int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0])
    hi = int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])
    # raw tick path (tick-honest entry/exit)
    tk = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
        AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts, tpx = tk.ts_ms.values.astype(np.int64), tk.price.values.astype(float)
    # 1-min OHLC (aggregate 5s bars). start L*60+2400s early for rolling-window + ER/ATR history.
    bdf = con.execute(f"""WITH b AS (SELECT (bar_ts-bar_ts%60) m, max(high) h, min(low) l,
        arg_max(close,bar_ts) cl FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
        AND bar_ts>={lo-4200} AND bar_ts<{hi} GROUP BY 1) SELECT m,h,l,cl FROM b ORDER BY m""").df()
    # raw 5s bars (report built the Donchian on these)
    b5 = con.execute(f"""SELECT (bar_ts-bar_ts%5) t, high h, low l, close cl FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={lo-4200} AND bar_ts<{hi} ORDER BY t""").df()
    return lo, hi, tts, tpx, bdf, b5


def build_indicators(bdf):
    mins = bdf.m.values.astype(np.int64)
    cls, hh, ll = bdf.cl.values.astype(float), bdf.h.values.astype(float), bdf.l.values.astype(float)
    idx = {int(m): i for i, m in enumerate(mins)}
    tr = np.zeros(len(mins))
    for i in range(1, len(mins)):
        tr[i] = max(hh[i] - ll[i], abs(hh[i] - cls[i - 1]), abs(ll[i] - cls[i - 1]))
    return mins, cls, hh, ll, tr, idx


def er_atr_net30(idx, cls, tr, ts_ms):
    """30-bar Kaufman ER + 14-bar ATR + signed 30-min move (trend dir) at the minute of ts_ms."""
    m = int((ts_ms // 1000) - ((ts_ms // 1000) % 60))
    i = idx.get(m)
    if i is None or i < 30:
        return None, None, None
    seg = cls[i - 30:i + 1]
    tot = np.abs(np.diff(seg)).sum()
    er = abs(seg[-1] - seg[0]) / tot if tot > 0 else 0.0
    atr = float(tr[i - 13:i + 1].mean()) if i >= 14 else None
    net30 = float(seg[-1] - seg[0])
    return er, atr, net30


def replay(tts, tpx, ei, d, stop, arm, trail, cap_s):
    """Tick-honest chandelier-trail replay. Stop checked BEFORE trail within a tick (conservative)."""
    entry_px, entry_ts = tpx[ei], int(tts[ei])
    peak, armed = 0.0, False
    j = ei + 1
    while j < len(tts):
        px, t = tpx[j], int(tts[j])
        fav = (px - entry_px) * d
        if -fav >= stop:                                  # hard stop -> fill at stop level
            return (-stop) * VPP - FEE, "stop", t
        if fav > peak:
            peak = fav
        if not armed and peak >= arm:
            armed = True
        if armed and (peak - fav) >= trail:               # chandelier trail from peak
            return fav * VPP - FEE, "trail", t
        if t - entry_ts >= cap_s * 1000:
            return fav * VPP - FEE, "time", t
        j += 1
    return (tpx[-1] - entry_px) * d * VPP - FEE, "time", int(tts[-1])


def build_trades(tts, tpx, mins, cls, hh, ll, tr, idx, Lb, Bb,
                 stop=STOP, arm=ARM, trail=TRAIL, cap_s=CAP_S, cool=COOL):
    """Generate Donchian-breakout trades in the news window for (L=Lb, B=Bb)."""
    trades = []
    busy_until_ms = -1
    for i in range(len(mins)):
        m = int(mins[i])
        hourutc = (m % 86400) // 3600
        if not (NEWS_LO <= hourutc < NEWS_HI):
            continue
        if i < Lb:
            continue
        entry_ms = (m + 60) * 1000                        # first tick after bar close
        if entry_ms <= busy_until_ms:
            continue
        hiL = hh[i - Lb:i].max()                           # prior L bars, excl current
        loL = ll[i - Lb:i].min()
        cl = cls[i]
        d = 0.0
        if cl > hiL + Bb:
            d = 1.0
        elif cl < loL - Bb:
            d = -1.0
        if d == 0.0:
            continue
        ei = int(np.searchsorted(tts, entry_ms, "left"))
        if ei >= len(tts):
            break
        pnl, reason, exit_ts = replay(tts, tpx, ei, d, stop, arm, trail, cap_s)
        er, atr, net30 = er_atr_net30(idx, cls, tr, int(tts[ei]))
        trades.append({"d": d, "pnl": pnl, "reason": reason, "ts": int(tts[ei]),
                       "exit_ts": exit_ts, "er": er, "atr": atr, "net30": net30})
        busy_until_ms = exit_ts + cool * 1000              # single position + cooldown from exit
    return trades


def build_trades_5s(tts, tpx, b5, idx, cls, tr, Lb, Bb, side=None,
                    stop=STOP, arm=ARM, trail=TRAIL, cap_s=CAP_S, cool=COOL):
    """Report-faithful variant: Donchian breakout on 5s bars (L=Lb 5s-bars lookback).
    Evaluated at each 5s bar close in the news window. ER/ATR/net30 still from 1-min series.
    side=None both; side=+1 long-only standalone gate; side=-1 short-only standalone gate."""
    bt = b5.t.values.astype(np.int64)
    bh, bl, bc = b5.h.values.astype(float), b5.l.values.astype(float), b5.cl.values.astype(float)
    trades = []
    busy_until_ms = -1
    for i in range(Lb, len(bt)):
        t0 = int(bt[i])
        hourutc = (t0 % 86400) // 3600
        if not (NEWS_LO <= hourutc < NEWS_HI):
            continue
        entry_ms = (t0 + 5) * 1000                          # first tick after 5s bar close
        if entry_ms <= busy_until_ms:
            continue
        hiL = bh[i - Lb:i].max()
        loL = bl[i - Lb:i].min()
        cl = bc[i]
        d = 0.0
        if cl > hiL + Bb:
            d = 1.0
        elif cl < loL - Bb:
            d = -1.0
        if d == 0.0:
            continue
        if side is not None and d != side:                  # standalone single-side gate
            continue
        ei = int(np.searchsorted(tts, entry_ms, "left"))
        if ei >= len(tts):
            break
        pnl, reason, exit_ts = replay(tts, tpx, ei, d, stop, arm, trail, cap_s)
        er, atr, net30 = er_atr_net30(idx, cls, tr, int(tts[ei]))
        trades.append({"d": d, "pnl": pnl, "reason": reason, "ts": int(tts[ei]),
                       "exit_ts": exit_ts, "er": er, "atr": atr, "net30": net30})
        busy_until_ms = exit_ts + cool * 1000
    return trades


def st(rows):
    n = len(rows)
    net = sum(r["pnl"] for r in rows)
    w = 100 * sum(1 for r in rows if r["pnl"] > 0) / n if n else 0
    return n, net, w


def run_battery(header, trades, builder):
    """builder(L,B) -> trade list, used for the hold-at-n sweep."""
    print("\n" + "=" * 78)
    print(header)
    print("=" * 78)

    # ── 1. RAW + validation ──
    n, net, w = st(trades)
    rc = {}
    for t in trades:
        rc[t["reason"]] = rc.get(t["reason"], 0) + 1
    days = sorted({_dt.datetime.fromtimestamp(t["ts"] / 1000, _dt.UTC).strftime("%m-%d") for t in trades})
    daypnl = {d: 0.0 for d in days}
    for t in trades:
        daypnl[_dt.datetime.fromtimestamp(t["ts"] / 1000, _dt.UTC).strftime("%m-%d")] += t["pnl"]
    losedays = sum(1 for d in daypnl if daypnl[d] < 0)
    print(f"1. RAW: {n}tr · net ${net:+.0f} · ${net/n if n else 0:+.1f}/tr · {w:.0f}%w · "
          f"exits {rc} · losing days {losedays}/{len(days)}")
    print(f"   per-day: " + "  ".join(f"{d} ${daypnl[d]:+.0f}" for d in days))
    print(f"   VALIDATION vs report (27tr / +$570 / 85%w / 0 losing days): "
          f"{'MATCH' if abs(n-27)<=3 and net>0 and w>=75 else 'DIVERGES'}")

    # ── 2. LONG vs SHORT split ──
    Lg = [t for t in trades if t["d"] > 0]
    Sg = [t for t in trades if t["d"] < 0]
    print("\n2. LONG vs SHORT split (the directional-edge test):")
    for lbl, g in [("LONG", Lg), ("SHORT", Sg)]:
        gn, gnet, gw = st(g)
        print(f"     {lbl:>6}: {gn}tr · ${gnet:+.0f} · ${gnet/gn if gn else 0:+.1f}/tr · {gw:.0f}%w")

    # ── 3. ER bands ──
    have_er = [t for t in trades if t["er"] is not None]
    print(f"\n3. ER bands ({len(have_er)}/{n} have ER):   {'band':>10}{'tr':>5}{'net$':>9}{'$/tr':>8}{'win%':>6}")
    for a, b in [(0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, 9)]:
        g = [t for t in have_er if a <= t["er"] < b]
        if not g:
            continue
        gn, gnet, gw = st(g)
        print(f"   {f'{a:.1f}-{b:.1f}' if b < 9 else f'{a:.1f}+':>21}{gn:>5}${gnet:>+8.0f}${gnet/gn:>+7.1f}{gw:>5.0f}%")

    # ── 4. ATR bands ──
    have_atr = [t for t in trades if t["atr"] is not None]
    print(f"\n4. ATR bands ({len(have_atr)}/{n} have ATR):  {'band(pt)':>10}{'tr':>5}{'net$':>9}{'$/tr':>8}{'win%':>6}")
    for a, b in [(0, 12), (12, 16), (16, 20), (20, 25), (25, 999)]:
        g = [t for t in have_atr if a <= t["atr"] < b]
        if not g:
            continue
        gn, gnet, gw = st(g)
        print(f"   {f'{a}-{b}' if b < 999 else f'{a}+':>21}{gn:>5}${gnet:>+8.0f}${gnet/gn:>+7.1f}{gw:>5.0f}%")

    # ── 5. Strip-best fluke test ──
    print("\n5. Strip-best (fluke test) — net after removing the best K trades:")
    srt = sorted(t["pnl"] for t in trades)
    for k in [0, 1, 2, 3, 5]:
        kept = srt[:len(srt) - k] if k else srt
        s = sum(kept)
        print(f"     strip best {k}: {len(kept)}tr · ${s:+.0f}" + ("  <- GONE" if s <= 0 else ""))

    # ── 6. Beta-vs-edge: side × concurrent 30-min trend direction ──
    core = [t for t in trades if t["net30"] is not None]
    print("\n6. Beta-vs-edge (side × concurrent 30-min trend dir; net30 sign):")

    def q(rows):
        n = len(rows)
        return f"{n}tr ${sum(r['pnl'] for r in rows):+.0f} {100*sum(1 for r in rows if r['pnl']>0)/n if n else 0:.0f}%w"

    for side, dv in [("LONG ", 1.0), ("SHORT", -1.0)]:
        g = [t for t in core if t["d"] == dv]
        up = [t for t in g if t["net30"] > 0]
        dn = [t for t in g if t["net30"] <= 0]
        print(f"     {side}: WITH-up-trend {q(up):>22}  |  in-down-trend {q(dn):>22}")
    print("     (real edge = winning side wins in BOTH trend dirs; beta = wins only with the trend)")

    # ── 7. Hold-at-n: loosen the trigger, does the edge HOLD as n grows? ──
    print("\n7. Hold-at-n (loosen trigger to grow n; does win%/edge HOLD or decay to coin-flip?):")
    print(f"     {'config':>16}{'tr':>5}{'net$':>9}{'$/tr':>8}{'win%':>6}")
    for Lb, Bb, tag in [(24, 5, "A base L24/B5"), (24, 2, "L24/B2"), (24, 0, "L24/B0"),
                        (12, 5, "L12/B5"), (12, 2, "L12/B2"), (12, 0, "L12/B0")]:
        tt = builder(Lb, Bb)
        gn, gnet, gw = st(tt)
        print(f"   {tag:>18}{gn:>5}${gnet:>+8.0f}${gnet/gn if gn else 0:>+7.1f}{gw:>5.0f}%")


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo, hi, tts, tpx, bdf, b5 = load(con)
    con.close()
    mins, cls, hh, ll, tr, idx = build_indicators(bdf)

    print("NEWS-WINDOW RANGE BREAKOUT (Donchian) — grave re-dig + full filter battery")
    print(f"window {SINCE} -> {UNTIL} UTC · news gate 13:00<=hUTC<15:00 · config A "
          f"L{L}/B{int(B)}/STOP{int(STOP)}/TRAIL{int(TRAIL)}/ARM{int(ARM)} · $5/RT $2/pt")
    print("report target: 27tr / +$570 / 85%w / 0 losing days")

    # Interpretation 1 (task literal): Donchian on 1-MIN bars, L=24 1-min bars.
    b1 = lambda Lb, Bb: build_trades(tts, tpx, mins, cls, hh, ll, tr, idx, Lb, Bb)
    run_battery("INTERPRETATION 1 — Donchian on 1-MIN bars (L=24 => 24-min lookback)  [task-literal]",
                b1(L, B), b1)

    # Interpretation 2 (report-faithful): Donchian on 5s bars, L=24 5s-bars (=2-min lookback).
    b2 = lambda Lb, Bb: build_trades_5s(tts, tpx, b5, idx, cls, tr, Lb, Bb)
    run_battery("INTERPRETATION 2 — Donchian on 5s bars (L=24 => 2-min lookback)  [report-faithful]",
                b2(L, B), b2)

    # ── Report's two smoking-gun kills, reproduced faithfully on interpretation 2 ──
    print("\n" + "-" * 78)
    print("REPORT KILL-TESTS (interpretation 2, config A):")
    print("-" * 78)
    print("  a) SIDE-ISOLATION (each side re-run as its OWN standalone gate, not a partition):")
    for lbl, sd in [("long-only ", 1.0), ("short-only", -1.0)]:
        g = build_trades_5s(tts, tpx, b5, idx, cls, tr, L, B, side=sd)
        gn, gnet, gw = st(g)
        print(f"       {lbl}: {gn}tr · ${gnet:+.0f} · ${gnet/gn if gn else 0:+.1f}/tr · {gw:.0f}%w")
    print("     (report claimed long-only -$32 / short-only +$36 = both independently flat)")
    print("\n  b) BUFFER RAZOR at fixed L24/STOP40/TRAIL20/ARM20 (curve-fit tell):")
    print(f"       {'B':>4}{'tr':>5}{'net$':>9}{'$/tr':>8}{'win%':>6}")
    for Bb in [0, 2, 3, 5, 7, 10]:
        g = build_trades_5s(tts, tpx, b5, idx, cls, tr, L, float(Bb))
        gn, gnet, gw = st(g)
        print(f"       {Bb:>4}{gn:>5}${gnet:>+8.0f}${gnet/gn if gn else 0:>+7.1f}{gw:>5.0f}%")
    print("     (report: B0 +$22 · B2 -$25 · B3 -$278 · B5 +$570 · B7 +$305 · B10 -$181 = knife-edge spike)")

    print("\n(1 week, in-sample, tick-honest at $5/RT. Verdict in the report text.)")


if __name__ == "__main__":
    main()
