#!/usr/bin/env python3
"""MGC FADER — does gold revert from extension, and does the CLOCK matter?

Operator, 2026-08-05: "try and find a fader gate. do web research on the best way to trade mgc. mgc
has juicy smooth runs. i dont want to give up. but if this shows nothing ill leave it alone."

★ WHY THIS IS NOT A RE-RUN OF THE FIVE NULLS. Every earlier MGC study needed a DIRECTION PREDICTOR
and none existed (census ~2pp over the best constant; delay-confirm negative in all 24 cells; router
filter placebo-null; book select and book veto both null). A FADER does not need one — the extension
itself picks the side. Fade an up-extension short, a down-extension long. That is a mechanism the
tape has never been asked about.

★ AND IT ADDS THE ONE UNTRIED INFORMATION SOURCE: THE CLOCK. Not from a sweep, from research.
  - arXiv 2605.04004 (Mesfin 2026) falsified 14 OHLCV momentum families on MNQ over 947 days on cost
    alone — but its two POSITIVE CONTROLS were both session-anchored: "London Session Signal B"
    (T=5.15, N=289) and "RTH Confluence" (T=5.83, N=538). Structure came from TIME, not price shape.
  - Gold's documented anchor is the London PM fix, 10:00 ET, where institutional order flow
    concentrates; the London/NY overlap (08:00-12:00 ET) is the liquid window.
  ⚠ The web ALSO returned "gold Hurst = 0.41, all Ornstein-Uhlenbeck configs failed on MGC". That was
  a search-engine synthesis, NOT in the paper (which is MNQ-only and never mentions Hurst). It is not
  used here. Hurst is COMPUTED BELOW ON OUR OWN TAPE instead — memory [[verify-desk-facts-never-guess]].

★ TAPE: the 250ms book mid, 15 CONTINUOUS days including 07-18..08-03 where MGC ticks/bars do not
exist. More gold tape than any earlier study, and no seam to straddle.

★ MULTIPLE COMPARISONS ARE THE REAL RISK HERE. Slicing 24 hours guarantees some hour looks good. Every
time-of-day claim is therefore placebo-tested against the SAME slice size drawn at random hours, and
the hour cells are reported in full so nothing is quietly dropped.

  PYTHONPATH=src .venv/bin/python scripts/mgc_fader.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.lake import connect  # noqa: E402

VPP = 10.0
SESSION_START_UTC = 22        # Paris midnight, the desk's session boundary


def frame(con):
    return con.execute("""
        WITH s AS (SELECT ts_ms, (bid1p+ask1p)/2.0 AS mid FROM depth
                   WHERE bid1p IS NOT NULL AND ask1p IS NOT NULL AND ask1p > bid1p)
        SELECT CAST(ts_ms/60000 AS BIGINT)*60 AS m, max(mid) hi, min(mid) lo,
               arg_max(mid, ts_ms) cl, arg_min(mid, ts_ms) op, count(*) n
        FROM s GROUP BY 1 HAVING count(*) >= 20 ORDER BY 1""").fetchall()


def hurst(series, lags=range(2, 60)):
    """Hurst via the aggregated-variance / rescaled-lag method: sd of k-lag differences scales as k^H.
    H<0.5 mean-reverting, 0.5 random walk, >0.5 trending. Computed on OUR tape, not quoted."""
    xs, ys = [], []
    for k in lags:
        d = [series[i + k] - series[i] for i in range(len(series) - k)]
        if len(d) < 30:
            continue
        s = statistics.pstdev(d)
        if s <= 0:
            continue
        xs.append(math.log(k))
        ys.append(math.log(s))
    if len(xs) < 5:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = sum((a - mx) ** 2 for a in xs)
    return num / den if den else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee", type=float, default=1.50)
    z = ap.parse_args()
    con = connect(symbol="MGC")
    rows = frame(con)
    m = [r[0] for r in rows]
    hi = [float(r[1]) for r in rows]
    lo = [float(r[2]) for r in rows]
    cl = [float(r[3]) for r in rows]
    days = sorted({dt.datetime.fromtimestamp(x, dt.UTC).date() for x in m})
    print(f"MGC {len(rows):,} minutes, {len(days)} days ({days[0]}..{days[-1]}), price = book mid\n")

    # ── 1. is gold actually mean-reverting on OUR tape? ──
    print("1. HURST ON OUR OWN TAPE (H<0.5 mean-reverting, 0.5 random walk, >0.5 trending)")
    h_all = hurst(cl)
    print(f"   minute mid, lags 2-60min:  H = {h_all:.3f}" if h_all else "   n/a")
    for lo_l, hi_l, lab in ((2, 15, "2-15 min"), (15, 60, "15-60 min"), (60, 240, "60-240 min")):
        h = hurst(cl, range(lo_l, hi_l))
        if h:
            tag = "mean-reverting" if h < 0.47 else ("trending" if h > 0.53 else "random walk")
            print(f"   lags {lab:<10} H = {h:.3f}   {tag}")
    print("   ★ H near 0.5 means there is no exploitable memory in EITHER direction — it does not")
    print("     favour a fader any more than it favoured the momentum gates.\n")

    # ── 2. the fader's core premise, tested directly ──
    # ★ ANCHOR = a ROLLING mean, not the cumulative session mean. The first run used the session
    # cumulative mean and got mean |extension| of 5-16 ATR — because a cumulative mean LAGS badly in a
    # trending session, so price sits "extended" almost permanently and `ext>=2` selected nothing. A
    # fader measures against recent fair value. (No volume in the book feed, so this is a price mean,
    # not a true VWAP — stated, not hidden.)
    ANCHOR_N = 30
    anchor, ext, atr = [], [], []
    for i, t in enumerate(m):
        a0 = max(0, i - ANCHOR_N)
        anchor.append(sum(cl[a0:i + 1]) / (i - a0 + 1))
        w0 = max(1, i - 60)
        trs = [max(hi[j] - lo[j], abs(hi[j] - cl[j - 1]), abs(lo[j] - cl[j - 1]))
               for j in range(w0, i + 1)]
        a = sum(trs) / len(trs) if trs else 0.0
        atr.append(a)
        ext.append((cl[i] - anchor[i]) / a if a > 0 else 0.0)

    print("2. THE FADER PREMISE: after an extension, does price REVERT or CONTINUE?")
    print(f"{'extension':<18}{'n':>7}{'reverted':>10}{'continued':>11}{'edge vs 50':>12}")
    LOOK = 40
    for lo_e, hi_e in ((1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 99.0)):
        rev = con_ = 0
        for i in range(60, len(rows) - LOOK):
            if m[i + LOOK] - m[i] > LOOK * 60 * 1.5 or atr[i] <= 0:
                continue
            e = ext[i]
            if not (lo_e <= abs(e) < hi_e):
                continue
            sgn = -1 if e > 0 else 1                   # fade: extended up -> short
            c0 = cl[i]
            fav = (max(hi[i+1:i+1+LOOK]) - c0) if sgn > 0 else (c0 - min(lo[i+1:i+1+LOOK]))
            adv = (c0 - min(lo[i+1:i+1+LOOK])) if sgn > 0 else (max(hi[i+1:i+1+LOOK]) - c0)
            rev += fav >= adv
            con_ += fav < adv
        n = rev + con_
        if n:
            print(f"{lo_e:>4.0f}-{hi_e:<13.0f}{n:>7}{100*rev/n:>9.1f}%{100*con_/n:>10.1f}%"
                  f"{100*rev/n-50:>+11.1f}")
    print("   ★ >50% reverted = the fade is the right side. This is the ONE question the earlier")
    print("     studies never asked, because they all needed a direction predictor and a fader does not.\n")

    # ── 3. the clock: the untried source, motivated by the research not by a sweep ──
    print("3. BY HOUR (UTC) — 14:00 UTC = 10:00 ET = the London PM fix")
    print(f"{'hour':<7}{'n':>7}{'reverted':>10}{'mean |ext|':>12}{'mean ATR':>10}")
    byh = defaultdict(lambda: [0, 0, [], []])
    for i in range(60, len(rows) - LOOK):
        if m[i + LOOK] - m[i] > LOOK * 60 * 1.5 or atr[i] <= 0 or abs(ext[i]) < 2.0:
            continue
        h = dt.datetime.fromtimestamp(m[i], dt.UTC).hour
        sgn = -1 if ext[i] > 0 else 1
        c0 = cl[i]
        fav = (max(hi[i+1:i+1+LOOK]) - c0) if sgn > 0 else (c0 - min(lo[i+1:i+1+LOOK]))
        adv = (c0 - min(lo[i+1:i+1+LOOK])) if sgn > 0 else (max(hi[i+1:i+1+LOOK]) - c0)
        b = byh[h]
        b[0] += fav >= adv
        b[1] += 1
        b[2].append(abs(ext[i]))
        b[3].append(atr[i])
    for h in sorted(byh):
        r, n, e, a = byh[h]
        if n < 20:
            continue
        star = "  <-- London PM fix" if h == 14 else ("  <-- LDN/NY overlap" if 12 <= h <= 16 else "")
        print(f"{h:>4}:00{n:>7}{100*r/n:>9.1f}%{statistics.mean(e):>12.2f}"
              f"{statistics.mean(a):>10.2f}{star}")

    # ── 4. the gate: 2-lot, A = fixed-R scalp, B = revert-to-anchor ──
    print("\n4. FADER GATE P&L — A = fixed-R scalp, B = target the session anchor")
    print("   (B targets the MEAN, not a chandelier: a fader's thesis is reversion, and memory")
    print("    [[mgc-momentum-greenfield-null]] measured chandeliers at -$6.13/trade on gold)")
    print(f"{'config':<34}{'n':>5}{'total':>9}{'win':>7}{'green':>9}{'strip-1':>9}{'strip-day':>10}")

    def gate(ext_min, k_stop, a_r, hours=None, fade=True):
        tr, busy = [], 0
        for i in range(60, len(rows) - LOOK):
            if m[i] < busy or atr[i] <= 0 or m[i + LOOK] - m[i] > LOOK * 60 * 1.5:
                continue
            if abs(ext[i]) < ext_min:
                continue
            h = dt.datetime.fromtimestamp(m[i], dt.UTC).hour
            if hours and h not in hours:
                continue
            sgn = (-1 if ext[i] > 0 else 1) * (1 if fade else -1)
            entry = cl[i]
            r = k_stop * atr[i]
            stop = entry - sgn * r
            tgt_a = entry + sgn * a_r * r
            tgt_b = anchor[i]                      # revert to the mean
            ea = eb = None
            for j in range(i + 1, min(i + 1 + LOOK, len(rows))):
                x_hi, x_lo = hi[j], lo[j]
                if ea is None:
                    if (sgn > 0 and x_lo <= stop) or (sgn < 0 and x_hi >= stop):
                        ea = stop
                    elif (sgn > 0 and x_hi >= tgt_a) or (sgn < 0 and x_lo <= tgt_a):
                        ea = tgt_a
                if eb is None:
                    if (sgn > 0 and x_lo <= stop) or (sgn < 0 and x_hi >= stop):
                        eb = stop
                    elif (sgn > 0 and x_hi >= tgt_b) or (sgn < 0 and x_lo <= tgt_b):
                        eb = tgt_b
                if ea is not None and eb is not None:
                    break
            last = cl[min(i + LOOK, len(rows) - 1)]
            ea = last if ea is None else ea
            eb = last if eb is None else eb
            tr.append((m[i], sgn * (ea - entry) * VPP - z.fee, sgn * (eb - entry) * VPP - z.fee))
            busy = m[i] + LOOK * 60
        return tr

    def show(tr, lab):
        if len(tr) < 5:
            print(f"{lab:<34}{len(tr):>5}   too few")
            return None
        tot = sum(a + b for _, a, b in tr)
        bd = defaultdict(float)
        for t0, a, b in tr:
            bd[dt.datetime.fromtimestamp(t0, dt.UTC).date().isoformat()] += a + b
        g = sum(1 for v in bd.values() if v > 0)
        w = sum(1 for _, a, b in tr if a + b > 0)
        print(f"{lab:<34}{len(tr):>5}{tot:>9.0f}{100*w/len(tr):>6.0f}%{g:>4}/{len(bd):<4}"
              f"{tot-max(a+b for _,a,b in tr):>9.0f}{tot-max(bd.values()):>10.0f}")
        return tot

    for e in (2.0, 3.0):
        for k in (1.0, 1.5):
            show(gate(e, k, 1.0), f"fade ext>={e} stop{k} A=1.0R")
    print()
    # ★ THE CONTINUE CONTROL MUST BE LOT-A ONLY. Lot B targets the ANCHOR, which for a continuation
    # trade sits BEHIND the entry — it books an instant loss on every trade and reported -$64,298 in
    # the first run. That is a broken control, not evidence. Lot A is symmetric (fixed R either way)
    # so fade-vs-continue is a fair comparison on it.
    def show_a(tr, lab):
        if len(tr) < 5:
            print(f"{lab:<34}{len(tr):>5}   too few")
            return
        tot = sum(a for _, a, _ in tr)
        bd = defaultdict(float)
        for t0, a, _ in tr:
            bd[dt.datetime.fromtimestamp(t0, dt.UTC).date().isoformat()] += a
        g = sum(1 for v in bd.values() if v > 0)
        w = sum(1 for _, a, _ in tr if a > 0)
        print(f"{lab:<34}{len(tr):>5}{tot:>9.0f}{100*w/len(tr):>6.0f}%{g:>4}/{len(bd):<4}"
              f"{tot-max(a for _,a,_ in tr):>9.0f}{tot-max(bd.values()):>10.0f}")
    print("LOT A ONLY (symmetric) — fade vs continue, the fair comparison:")
    show_a(gate(2.0, 1.0, 1.0), "  A-only: FADE the extension")
    show_a(gate(2.0, 1.0, 1.0, fade=False), "  A-only: CONTINUE the extension")
    for lab, hrs in (("LDN/NY overlap 12-16 UTC", {12, 13, 14, 15, 16}),
                     ("London PM fix hour 14 UTC", {14}),
                     ("Asia 00-06 UTC", {0, 1, 2, 3, 4, 5})):
        show(gate(2.0, 1.0, 1.0, hours=hrs), f"fade ext>=2, {lab}")

    # placebo for the hour claim: same number of trades, random hours
    full = gate(2.0, 1.0, 1.0)
    sel = gate(2.0, 1.0, 1.0, hours={12, 13, 14, 15, 16})
    if len(sel) >= 5 and len(full) > len(sel):
        rnd = random.Random(20260805)
        tots = [sum(a + b for _, a, b in rnd.sample(full, len(sel))) for _ in range(3000)]
        real = sum(a + b for _, a, b in sel)
        mu, sd = statistics.mean(tots), statistics.pstdev(tots)
        pct = 100.0 * sum(1 for x in tots if x >= real) / len(tots)
        print(f"\nplacebo for the session claim: random {len(sel)}-of-{len(full)} -> mean ${mu:.0f} "
              f"(sd ${sd:.0f}); real ${real:.0f} = {(real-mu)/sd if sd else 0:+.2f} sd, "
              f"beaten by {pct:.0f}% of random draws")
    # ★ every hour placebo-tested, not just the two the research nominated — otherwise a good-looking
    # hour elsewhere stays invisible and the reader cannot see how many cells were really examined.
    print("\nEVERY HOUR, PLACEBO-TESTED (same trade count drawn from random hours, 2000 draws)")
    print(f"{'hour':<7}{'n':>5}{'total':>9}{'placebo mean':>14}{'sd':>7}{'beaten by':>11}")
    rnd2 = random.Random(4242)
    for h in range(24):
        sel_h = [t for t in full if dt.datetime.fromtimestamp(t[0], dt.UTC).hour == h]
        if len(sel_h) < 8:
            continue
        real_h = sum(a + b for _, a, b in sel_h)
        ts_ = [sum(a + b for _, a, b in rnd2.sample(full, len(sel_h))) for _ in range(2000)]
        mu_, sd_ = statistics.mean(ts_), statistics.pstdev(ts_)
        pc = 100.0 * sum(1 for x in ts_ if x >= real_h) / len(ts_)
        print(f"{h:>4}:00{len(sel_h):>5}{real_h:>9.0f}{mu_:>14.0f}{sd_:>7.0f}{pc:>10.0f}%")

    print("\n★ 24 hour-cells exist; some WILL look good. Only a session result far into the placebo")
    print("  tail means anything, and it must also be a session with a REASON (the fix, the overlap).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
