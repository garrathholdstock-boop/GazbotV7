#!/usr/bin/env python3
"""MGC GATES SCORED ON THE TAPE THE ROUTER WOULD ACTUALLY LET THEM TRADE.

Operator, 2026-08-05: "you now need to look at the tape where those trades won. and assume our router
would be switching off this gate in non favourable chop. and remove those trades."

Correct criticism of the blanket backtest — the live desk does NOT trade every arm. It has a router
that benches gates on untradeable days, so scoring a gate across all tape tests a policy the desk does
not run. Memory [[backtest-per-regime-segment-not-blanket]]: score each config on its HOME tape.

★ THE TRAP THIS FILE IS BUILT TO AVOID. Reading which trades won and then filtering to the conditions
those trades shared is circular — it would produce a positive result on ANY random set. Two rules:

  1. THE FILTER IS NOT FITTED HERE. It is `gazbot7.untradeable.compute`'s own blend, already live,
     already validated on MNQ (07-29/30 green vs 07-31 untradeable), with its own published
     thresholds: STAY-OUT >= 65, CAUTION >= 45. Nothing about it is tuned to these trades.
  2. IT IS COMPUTED CAUSALLY. roundtrip and give-back use ONLY the bars from the session open to the
     moment of the entry — never the finished day. Using the closed day's roundtrip would be
     look-ahead: it knows how the day ended before deciding to trade it.

★ AND IT IS PLACEBO-CONTROLLED. A filter that removes 40% of trades will look brilliant whenever the
removed 40% happened to lose. So every filtered result is compared against 2,000 random removals of
the SAME COUNT. If the real filter does not sit clearly in the tail of that distribution, it carries
no information and the improvement is arithmetic, not skill.

  PYTHONPATH=src .venv/bin/python scripts/mgc_router_filtered.py
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import Bar, _atr  # noqa: E402
from gazbot7.lake import connect  # noqa: E402
from gazbot7.sizing import efficiency_ratio  # noqa: E402

VPP = 10.0
HOR = 40 * 60
DAY_START_UTC = 22 * 3600      # Paris midnight = 22:00 UTC, the desk's session boundary


def day_start(t):
    """Most recent 22:00 UTC at or before t — the same session boundary the live router uses."""
    d = dt.datetime.fromtimestamp(t, dt.UTC)
    s = d.replace(hour=22, minute=0, second=0, microsecond=0)
    if d.hour < 22:
        s -= dt.timedelta(days=1)
    return int(s.timestamp())


def meter(mins, keys, t0, t):
    """gazbot7.untradeable.compute's blend, on MGC, using ONLY session-open..t. Returns (score, rt, gb).

    Ported rather than imported because compute() reads MNQ out of capture.db by SQL; the arithmetic
    below is line-for-line the same. The one deliberate change is the range floor: the live version
    hardcodes `rng >= 30` points, which is ~1.5x MNQ's 14-min ATR but ~12x gold's — on MGC it would
    never bind. It is expressed ATR-relative so it means the same THING on a different instrument.
    """
    i0 = bisect.bisect_left(keys, t0 // 60)
    i1 = bisect.bisect_right(keys, t // 60)
    seg = keys[i0:i1]
    if len(seg) < 6:
        return None, None, None
    highs = [mins[k][0] for k in seg]
    lows = [mins[k][1] for k in seg]
    closes = [mins[k][2] for k in seg]
    op, net = closes[0], closes[-1] - closes[0]
    rng = max(highs) - min(lows)
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
           for i in range(1, len(closes))]
    atr = sum(trs[-14:]) / min(14, len(trs)) if trs else 0.0
    if atr <= 0 or rng < 2.0 * atr:
        return None, None, None
    rt = abs(net) / rng
    big = max(max(highs) - op, op - min(lows), 1e-9)
    gb = max(0.0, min(1.0, 1 - abs(net) / big))
    chop = max(0, min(1, 1 - rt)) * 100
    give = gb * 100
    return round(0.50 * chop + 0.50 * give), round(rt, 2), round(gb, 2)


def build(bars, ts, px, mins, keys, *, mode, D=30, C=0.0, atr_f=2.6, er_f=0.22,
          k_stop=1.0, a_r=1.0, k_ch=3.5, fee=1.5):
    """Every arm the gate would fire, each tagged with the router meter AT ENTRY."""
    A = []
    for i in range(60, len(bars) - 45):
        w = bars[max(0, i - 60):i + 1]
        a = _atr(w)
        if a > 0 and a >= atr_f and efficiency_ratio(w, 30) >= er_f:
            A.append((bars[i].ts, a))
    out, busy = [], 0
    for t0, atr in A:
        if t0 < busy:
            continue
        i0 = bisect.bisect_right(ts, t0) - 1
        i_d = bisect.bisect_right(ts, t0 + D) - 1
        if i0 < 0 or i_d < 0:
            continue
        p0, pd = px[i0], px[i_d]
        mv = pd - p0
        if mode == "confirm":
            if abs(mv) < C * atr or mv == 0:
                continue
            side = "LONG" if mv > 0 else "SHORT"
        elif mode == "long":
            side = "LONG"
        else:
            side = "SHORT"
        sgn = 1 if side == "LONG" else -1
        entry = pd
        r = k_stop * atr
        stop, tgt = entry - sgn * r, entry + sgn * a_r * r
        best, ea, eb = entry, None, None
        j = bisect.bisect_right(ts, t0 + HOR)
        for p in px[i_d:j]:
            if sgn * (p - entry) > sgn * (best - entry):
                best = p
            trail = best - sgn * k_ch * atr
            if ea is None:
                if sgn * (p - stop) <= 0:
                    ea = stop
                elif sgn * (p - tgt) >= 0:
                    ea = tgt
            if eb is None:
                if sgn * (p - stop) <= 0:
                    eb = stop
                elif sgn * (best - entry) > k_ch * atr and sgn * (p - trail) <= 0:
                    eb = trail
            if ea is not None and eb is not None:
                break
        last = px[j - 1] if j > i_d else entry
        ea = last if ea is None else ea
        eb = last if eb is None else eb
        sc, rt, gb = meter(mins, keys, day_start(t0), t0)
        out.append({"ts": t0, "side": side, "pnl": sgn * (ea - entry) * VPP - fee
                    + sgn * (eb - entry) * VPP - fee, "score": sc, "rt": rt, "gb": gb,
                    "day": dt.datetime.fromtimestamp(t0, dt.UTC).date().isoformat()})
        busy = t0 + HOR
    return out


def stats(tr):
    if not tr:
        return None
    tot = sum(t["pnl"] for t in tr)
    byday = defaultdict(float)
    for t in tr:
        byday[t["day"]] += t["pnl"]
    green = sum(1 for v in byday.values() if v > 0)
    best_day = max(byday.values()) if byday else 0
    return {"n": len(tr), "tot": tot, "green": green, "days": len(byday),
            "win": 100 * sum(1 for t in tr if t["pnl"] > 0) / len(tr),
            "strip1": tot - max(t["pnl"] for t in tr), "stripday": tot - best_day}


def line(lab, s):
    if not s:
        print(f"{lab:<32}  no trades")
        return
    print(f"{lab:<32}{s['n']:>5}{s['tot']:>9.0f}{s['win']:>6.0f}%"
          f"{s['green']:>4}/{s['days']:<3}{s['strip1']:>9.0f}{s['stripday']:>10.0f}")


def placebo(tr, keep_n, real_tot, draws=2000):
    """Remove the same NUMBER of trades at random. Where does the real filter sit?"""
    rnd = random.Random(20260805)
    tots = []
    for _ in range(draws):
        tots.append(sum(t["pnl"] for t in rnd.sample(tr, keep_n)))
    better = sum(1 for x in tots if x >= real_tot)
    return statistics.mean(tots), statistics.pstdev(tots), 100.0 * better / draws


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee", type=float, default=1.50)
    z = ap.parse_args()
    con = connect(symbol="MGC")
    rows = con.execute("""SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
        arg_max(close,bar_ts) c FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    bars = [Bar(ts=int(m), open=float(c), high=float(h), low=float(lo), close=float(c), volume=0.0)
            for m, h, lo, c in rows]
    mins = {int(m) // 60: (float(h), float(lo), float(c)) for m, h, lo, c in rows}
    keys = sorted(mins)
    tk = con.execute("SELECT ts_ms, price FROM ticks ORDER BY ts_ms").fetchall()
    ts = [int(t) // 1000 for t, _ in tk]
    px = [float(p) for _, p in tk]

    CFG = [("ALWAYS LONG", dict(mode="long")),
           ("ALWAYS SHORT", dict(mode="short")),
           ("confirm 30s C=0", dict(mode="confirm", D=30, C=0.0)),
           ("confirm 30s C=0.25", dict(mode="confirm", D=30, C=0.25))]

    print("PART 1 — WHAT DOES THE TAPE LOOK LIKE WHERE THESE TRADES WIN?")
    print("(router meter at ENTRY, computed session-open..entry only — no look-ahead)\n")
    tr = build(bars, ts, px, mins, keys, fee=z.fee, **CFG[0][1])
    have = [t for t in tr if t["score"] is not None]
    wins = [t for t in have if t["pnl"] > 0]
    loss = [t for t in have if t["pnl"] <= 0]
    print(f"{'':<10}{'n':>5}{'meter':>8}{'roundtrip':>11}{'give-back':>11}{'avg P&L':>10}")
    for nm, g in (("WINNERS", wins), ("LOSERS", loss)):
        if g:
            print(f"{nm:<10}{len(g):>5}"
                  f"{statistics.mean(t['score'] for t in g):>8.1f}"
                  f"{statistics.mean(t['rt'] for t in g):>11.2f}"
                  f"{statistics.mean(t['gb'] for t in g):>11.2f}"
                  f"{statistics.mean(t['pnl'] for t in g):>10.0f}")
    print(f"({len(tr)-len(have)} of {len(tr)} trades had no usable meter read — excluded above)")
    print("★ If WINNERS and LOSERS show the same meter, the router cannot separate them and")
    print("  removing 'chop' trades is removing trades at random.\n")

    print("PART 2 — GATES RESCORED WITH THE ROUTER BENCHING THEM")
    print(f"{'config':<32}{'n':>5}{'total':>9}{'win':>7}{'green':>8}{'strip-1':>9}{'strip-day':>10}")
    for name, kw in CFG:
        tr = build(bars, ts, px, mins, keys, fee=z.fee, **kw)
        have = [t for t in tr if t["score"] is not None]
        line(f"{name}  ALL TAPE", stats(tr))
        for thr, lab in ((65, "bench STAY-OUT>=65"), (45, "bench CAUTION>=45")):
            kept = [t for t in have if t["score"] < thr]
            s = stats(kept)
            line(f"  {lab}", s)
            if s and len(kept) < len(have) and len(kept) >= 5:
                mu, sd, pct = placebo(have, len(kept), s["tot"])
                z_ = (s["tot"] - mu) / sd if sd else 0.0
                print(f"      placebo: random {len(kept)}-of-{len(have)} -> mean ${mu:.0f} "
                      f"(sd ${sd:.0f});  real ${s['tot']:.0f} = {z_:+.2f} sd, "
                      f"beaten by {pct:.0f}% of random draws")
        print()
    print("★ 'beaten by X% of random draws' is the whole verdict. Below ~5% the router is genuinely")
    print("  selecting; near 50% it is removing trades at random and the P&L lift is arithmetic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
