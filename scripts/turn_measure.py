#!/usr/bin/env python3
"""RE-MEASURE THE TURN RULE ON THE LAKE — rate and reliability, per variant.

★★★ Phase 0 of docs/SCOPE_RECURSIVE_TRADING_LOOP.md. `turn_watch` ships a claim —
**15xATR retrace, 77% of the time the old direction does not return within 2h, 3.6 fires/day** —
and its own canary (`test_it_fires_at_roughly_the_rate_it_CLAIMS_on_real_tape`) now reads a
**median 12 fires/session**. One of the rule and the claim is wrong. This settles which.

⚠⚠ THE INSTRUMENT'S FOUNDING NUMBERS HAVE BEEN WRONG ONCE BEFORE. Its first cut shipped
"7xATR, 70%, 2.3/day" measured on a study that tracked retraces WITHOUT EVER FLIPPING DIRECTION —
a rarer event than the detector implements. So this harness replays the rule EXACTLY AS SHIPPED by
importing `turn_watch` itself rather than re-deriving it: [[call-the-real-detector-dont-re-derive-it]],
where a hand-rolled copy once fabricated +$819.

WHAT IS MEASURED, per variant:
  fires/session        — the claim is 3.6
  reliability          — of fires, the share where the OLD direction did not come back within 2h
  giveback             — points surrendered from the extreme before the call

VARIANTS (the threshold is the only thing that differs):
  ratio       threshold = M x atr14(now)              <- AS SHIPPED
  floor       threshold = max(M x atr14(now), FLOOR)  <- an absolute point floor
  leg_atr     threshold = M x atr14 AS AT THE LEG'S EXTREME   <- cannot shrink mid-leg
  leg_max     threshold = M x max(atr14) over the leg so far  <- strictest

⚠ `leg_atr` and `leg_max` exist because the live failures are ATR-REGIME failures: three false
fires at atr 5.4-9.3 and one 384pt late at atr 24.9. A RATIO threshold shrinks toward whatever
giveback is already sitting there whenever volatility collapses, so the detector can fire on
stillness. Anchoring the threshold to the leg removes that mechanism rather than papering over it.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics as st
import sys

SPEC = importlib.util.spec_from_file_location("tw", "/home/alphabot/gazbot7/scripts/turn_watch.py")
TW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TW)                      # the REAL detector, not a copy

RESUME_MIN = 120          # "did the old direction come back within 2h" — the claim's own window
WARM = 30                 # bars needed before the rule may speak, as in replay()


def lake_sessions(limit: int | None, min_bars: int = 300):
    """1-minute bars per UTC session-day from the unified lake. Returns [(day, [(ts,h,l,c)])]."""
    sys.path.insert(0, "/home/alphabot/gazbot7/src")
    from gazbot7.lake import connect
    con = connect()
    q = """
        SELECT CAST(bar_ts / 86400 AS INT) AS d,
               CAST(bar_ts / 60 AS INT) * 60 AS m,
               MAX(high) h, MIN(low) l,
               ARG_MAX(close, bar_ts) c
        FROM bars WHERE symbol = 'MNQ'
        GROUP BY d, m ORDER BY d, m
    """
    cur = {}
    for d, m, h, l, c in con.execute(q).fetchall():
        cur.setdefault(d, []).append((int(m), float(h), float(l), float(c)))
    out = [(d, b) for d, b in sorted(cur.items()) if len(b) >= min_bars]
    return out[-limit:] if limit else out


def run_session(bars, mult: float, mode: str, floor_pt: float):
    """Replay one session. Returns (fires, [(idx, old_dir, give, atr_used)])."""
    cl = [b[3] for b in bars]
    if len(cl) < WARM:
        return 0, []
    dirn = 1 if cl[10] > cl[0] else -1
    ext, ext_i = cl[10], 10
    atr_at_ext = TW.atr14(bars[:11]) or 0.0
    atr_leg_max = atr_at_ext
    fires = []
    for i in range(11, len(cl)):
        atr_now = TW.atr14(bars[max(0, i - 40):i + 1])
        if atr_now <= 0:
            continue
        if mode == "ratio":
            thr = mult * atr_now
        elif mode == "floor":
            thr = max(mult * atr_now, floor_pt)
        elif mode == "leg_atr":
            thr = mult * (atr_at_ext or atr_now)
        elif mode == "leg_max":
            thr = mult * (atr_leg_max or atr_now)
        else:
            raise ValueError(mode)
        atr_leg_max = max(atr_leg_max, atr_now)
        if dirn * (cl[i] - ext) > 0:
            ext, ext_i = cl[i], i
            atr_at_ext = atr_now
            atr_leg_max = atr_now          # a new extreme restarts the leg's ATR memory
        elif dirn * (ext - cl[i]) >= thr:
            fires.append((i, dirn, dirn * (ext - cl[i]), atr_now))
            dirn = -dirn
            ext, ext_i = cl[i], i
            atr_at_ext = atr_now
            atr_leg_max = atr_now
    return len(fires), fires


def reliability(bars, fires):
    """Of the fires, the share where the OLD direction did NOT regain the extreme within 2h.

    ⚠ THIS IS THE CLAIM'S OWN DEFINITION and it is a weak one: "did not come back" is not "the new
    direction ran". A coin that never retraces would score 100%. Reported because it is what the
    shipped number means, NOT because it is evidence of an edge.
    """
    cl = [b[3] for b in bars]
    held = 0
    for i, old_dir, _give, _atr in fires:
        ref = cl[i]
        window = cl[i + 1:i + 1 + RESUME_MIN]
        if not window:
            continue
        # the old direction "came back" if price travels further that way than it already had
        back = max((old_dir * (p - ref) for p in window), default=0.0)
        if back < 0.5 * abs(_give):
            held += 1
    return held / len(fires) if fires else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=120)
    ap.add_argument("--mult", type=float, default=TW.RETRACE_ATR)
    ap.add_argument("--floor", type=float, default=150.0)
    ap.add_argument("--modes", default="ratio,floor,leg_atr,leg_max")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--continuous", action="store_true",
                    help="never reset direction/extreme at a session boundary — as the SERVICE runs")
    a = ap.parse_args()

    sess = lake_sessions(a.sessions)
    print(f"lake sessions loaded: {len(sess)}  (>=300 one-minute bars each)")
    print(f"rule as shipped: {a.mult}xATR  ·  claim: 3.6 fires/day, 77% reliability")
    print()
    results = {}
    for mode in a.modes.split(","):
        rates, rels, gives = [], [], []
        if a.continuous:
            flat = [b for _d, bars in sess for b in bars]
            n_all, f_all = run_session(flat, a.mult, mode, a.floor)
            rates = [n_all / len(sess)] * len(sess)
            if f_all:
                r = reliability(flat, f_all)
                if r is not None:
                    rels.append(r)
                gives += [g for _i, _d2, g, _at in f_all]
            print(f"  [continuous] {mode:9} {n_all} fires over {len(sess)} sessions "
                  f"= {n_all/len(sess):.2f}/session")
            med = n_all / len(sess); mean = med
            rel = sum(rels)/len(rels) if rels else None
            results[mode] = {"fires_per_session": round(med, 2), "fires_total": n_all,
                             "reliability": round(rel, 3) if rel else None,
                             "median_giveback_pt": round(st.median(gives), 1) if gives else None}
            continue
        for _d, bars in sess:
            n, f = run_session(bars, a.mult, mode, a.floor)
            rates.append(n)
            if f:
                r = reliability(bars, f)
                if r is not None:
                    rels.append(r)
                gives += [g for _i, _d2, g, _at in f]
        med = st.median(rates) if rates else 0
        mean = sum(rates) / len(rates) if rates else 0
        rel = sum(rels) / len(rels) if rels else None
        results[mode] = {"median_fires": med, "mean_fires": round(mean, 2),
                         "reliability": round(rel, 3) if rel else None,
                         "median_giveback_pt": round(st.median(gives), 1) if gives else None,
                         "sessions": len(rates)}
        print(f"  {mode:9} median {med:>5.1f} fires/session   mean {mean:>5.2f}   "
              f"reliability {('%.0f%%' % (100*rel)) if rel else '  n/a':>5}   "
              f"median giveback {results[mode]['median_giveback_pt']}pt")
    print()
    if a.json:
        print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
