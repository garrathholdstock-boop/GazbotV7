#!/usr/bin/env python3
"""TUNNEL v3 — the levels come from the TAPE, not from a width we chose.

★★★ 2026-09-04, operator: *"why do you have to set a range. why cant we build something that is
live, dynamic and is reading the range and the tape going back and forth and recognises we are in a
tunnel. surely we can build those smarts."*

He is right and both previous attempts deserved it:
  v1  a 2-state HMM on per-minute true range — a VOLATILITY state. Refuted by his own labels: two of
      his tunnels overlap in time at different price levels and one is 113 points wide. 2/17 matched.
  v2  price containment inside k x ATR — better object (5/17, median IoU 0.10 -> 0.37) but the WIDTH
      was still imposed by us, so it fragmented his 673-minute structure into thirteen boxes.

v3 imposes no width. It finds where price actually KEEPS TURNING AROUND:

  · a swing HIGH is a bar whose high is the highest of the k bars either side of it. ⚠ CONFIRMED
    ONLY k BARS LATER — that lag is the honest cost of knowing a pivot happened, and pretending
    otherwise is the look-ahead that makes a backtest lie.
  · swing highs that land within `tol` of each other are one CEILING; swing lows likewise a FLOOR.
    The tape drew those levels, so the break needs no invented buffer.
  · we are IN A TUNNEL when both a ceiling and a floor are established (>= `touches` pivots each),
    price is rotating between them, and the EFFICIENCY RATIO is low — |net| small against the path
    actually travelled. That ratio is the arithmetic of "going back and forth".
  · the tunnel is LIVE: every new pivot can widen a level or extend the structure, and it ends the
    moment price closes beyond a level.

★ MULTI-SCALE BY CONSTRUCTION, which the single-width detectors could never be. His boxes measure a
  median 3.8x ATR but 08-13 is 16.8x — that is not one rule with noise, it is two scales. Running k
  small and k large in parallel produces both without either being privileged.
"""
from __future__ import annotations

import os

MAX_ER = float(os.environ.get("TV3_MAX_ER", "0.35"))     # |net| / path — low means rotating
TOUCHES = int(os.environ.get("TV3_TOUCHES", "2"))        # pivots needed to call a level
TOL_ATR = float(os.environ.get("TV3_TOL_ATR", "0.60"))   # pivots this close are the same level
MIN_MIN = int(os.environ.get("TV3_MIN_MIN", "25"))


def atr_at(trs, i, n=14):
    w = trs[max(0, i - n + 1):i + 1]
    return max(sum(w) / max(1, len(w)), 1e-9)


def pivots(bars, k):
    """Causal swing highs/lows. Each is stamped with the bar it could first be KNOWN at (i + k)."""
    hi, lo = [], []
    for i in range(k, len(bars) - k):
        w = bars[i - k:i + k + 1]
        if bars[i]["hi"] >= max(b["hi"] for b in w):
            hi.append((i, i + k, bars[i]["hi"]))
        if bars[i]["lo"] <= min(b["lo"] for b in w):
            lo.append((i, i + k, bars[i]["lo"]))
    return hi, lo


def _cluster(pv, tol):
    """Group pivots whose prices sit within `tol`. Returns (level, [indices]) per group."""
    out = []
    for i, known, px in pv:
        placed = False
        for g in out:
            if abs(px - g["level"]) <= tol:
                g["pts"].append((i, known, px))
                g["level"] = sum(p[2] for p in g["pts"]) / len(g["pts"])
                placed = True
                break
        if not placed:
            out.append({"level": px, "pts": [(i, known, px)]})
    return out


def er(bars, a, b):
    """Efficiency ratio over [a,b]: |net| / path. Low = the tape is going back and forth."""
    path = sum(abs(bars[i]["close"] - bars[i - 1]["close"]) for i in range(a + 1, b + 1))
    return abs(bars[b]["close"] - bars[a]["close"]) / path if path > 0 else 1.0


def detect(bars, k=10, *, touches=TOUCHES, tol_atr=TOL_ATR, max_er=MAX_ER, min_min=MIN_MIN):
    """ONE FORWARD PASS. State is carried bar to bar, so this is the same computation a live reader
    would do — no rescanning, nothing that needs the future.

    ⚠ The first version re-clustered every candidate span and was O(n^2); it timed out on a single
    session. Speed matters here beyond convenience: a detector that cannot run in one pass over a
    session is not a detector that can run on the tape.
    """
    from importlib.util import module_from_spec, spec_from_file_location
    _s = spec_from_file_location("tw", "/home/alphabot/gazbot7/scripts/tunnel_watch.py")
    tw = module_from_spec(_s); _s.loader.exec_module(tw)
    trs = tw.true_range(bars)
    ph, pl = pivots(bars, k)
    hi_at, lo_at = {}, {}
    for i, known, px in ph:
        hi_at.setdefault(known, []).append((i, px))
    for i, known, px in pl:
        lo_at.setdefault(known, []).append((i, px))

    out = []
    rec_h: list = []          # recent confirmed swing highs (i, px)
    rec_l: list = []
    cur = None
    # ⚠ Without this the pivots that BUILT a tunnel are still in memory the moment it breaks, so the
    # next bar rebuilds the same structure and the detector emits thousands of overlapping copies
    # (2,709 across five sessions on the first run). A structure is over when it breaks.
    last_end = -1
    for j in range(len(bars)):
        for i, px in hi_at.get(j, []):
            rec_h.append((i, px))
        for i, px in lo_at.get(j, []):
            rec_l.append((i, px))
        # only the recent past defines a live level
        rec_h = [p for p in rec_h if j - p[0] <= 400]
        rec_l = [p for p in rec_l if j - p[0] <= 400]
        tol = tol_atr * atr_at(trs, j)

        if cur is not None:
            c = bars[j]["close"]
            if c > cur["hi"] or c < cur["lo"]:
                cur["i1"] = j - 1
                cur["t1"] = bars[j - 1]["m"]
                cur["mins"] = cur["i1"] - cur["i0"] + 1
                cur["width"] = cur["hi"] - cur["lo"]
                cur["er"] = round(er(bars, cur["i0"], cur["i1"]), 3)
                if cur["mins"] >= min_min and cur["er"] <= max_er:
                    cur["break"] = {"i": j, "t": bars[j]["m"], "px": c,
                                    "side": "UP" if c > cur["hi"] else "DOWN"}
                    out.append(cur)
                last_end = cur["i1"]
                rec_h = [q for q in rec_h if q[0] > last_end]
                rec_l = [q for q in rec_l if q[0] > last_end]
                cur = None
            else:                      # still inside: let new pivots refine the levels
                for i, px in rec_h:
                    if i >= cur["i0"] and abs(px - cur["hi"]) <= tol:
                        cur["hi"] = max(cur["hi"], px)
                for i, px in rec_l:
                    if i >= cur["i0"] and abs(px - cur["lo"]) <= tol:
                        cur["lo"] = min(cur["lo"], px)
                continue

        # not in a tunnel: has the tape drawn a ceiling AND a floor?
        if len(rec_h) < touches or len(rec_l) < touches:
            continue
        ch = max(_cluster([(i, j, px) for i, px in rec_h], tol), key=lambda g: len(g["pts"]))
        cf = max(_cluster([(i, j, px) for i, px in rec_l], tol), key=lambda g: len(g["pts"]))
        if len(ch["pts"]) < touches or len(cf["pts"]) < touches:
            continue
        hi = max(p[2] for p in ch["pts"]); lo = min(p[2] for p in cf["pts"])
        i0 = min(min(p[0] for p in ch["pts"]), min(p[0] for p in cf["pts"]))
        if hi <= lo or i0 <= last_end or er(bars, i0, j) > max_er:
            continue
        cur = {"i0": i0, "t0": bars[i0]["m"], "hi": hi, "lo": lo,
               "touch_hi": len(ch["pts"]), "touch_lo": len(cf["pts"]), "scale": k}
    return out


def detect_multiscale(bars, ks=(5, 15, 40), **kw):
    """Run several pivot scales at once — his tunnels span 1.5x to 16.8x ATR and one scale cannot
    produce both. Each tunnel carries the scale that found it."""
    all_ = []
    for k in ks:
        for t in detect(bars, k, **kw):
            t["scale"] = k
            all_.append(t)
    return sorted(all_, key=lambda z: (z["t0"], z["scale"]))
