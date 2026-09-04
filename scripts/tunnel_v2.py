#!/usr/bin/env python3
"""TUNNEL DETECTOR v2 — the three faults the operator's own labels exposed on 2026-09-04.

He labelled 17 tunnels and 18 breaks across 5 sessions. Scoring the SHIPPED detector against them
found three distinct bugs, not one:

★ 1. IT IS STRUCTURALLY NEAR-BLIND IN US HOURS. `tunnel_watch`'s quiet mean is a FIXED 5.14pt
     (exp(MU[0])), but median per-minute true range is 7.25pt in Asia and 11.75pt in the US session
     — 2.29x that constant. Only 24.3% of US minutes can ever be scored quiet, against 58.3% of Asia
     minutes, so 88% of detected tunnels are overnight. On 2026-08-10 he marked three tunnels
     between 11:30 and 14:29 where the shipped model found NOTHING between 10:57 and 18:07.
     ⚠ THIS FLAW WAS ALREADY FOUND AND FIXED FOR GOLD and never back-ported: the MGC study concluded
     the live-worthy feature is range against a CAUSAL TRAILING MEDIAN, not a fixed threshold.
     FIX: normalise log(TR) by a causal trailing median before the filter. The window is deliberately
     LONG (6h default): it must track the REGIME (Asia vs US) without adapting away the very
     compression we are trying to find — a short window would raise the bar during a quiet stretch
     and erase the tunnel.

★ 2. IT FRAGMENTS ONE STRUCTURE INTO MANY, THEN TRADES THE FRAGMENTS. Volatility flickers inside a
     consolidation even while price holds its range, so his single 673-minute tunnel on 08-13 became
     FIVE of the detector's. Each fragment got its own narrow boundary, and price leaving a fragment
     — while still deep inside the real range — registered as a break. That is where the two bad
     counter-trend shorts came from (+31pt best; the other went -54.8pt against).
     FIX: merge adjacent quiet runs whose PRICE RANGES overlap. A consolidation is one structure.

★ 3. THE BUFFER ENTERS LATE AND WORSE. His breaks sit at +0.00pt from his own ceiling; the shipped
     rule needs a close beyond ceiling + 10% of width — 11 points of give-up on his 113pt tunnel.
     FIX: buffer defaults to 0 and is a knob, not a constant.

⚠⚠ THE HONEST LIMIT OF THIS FILE. It is shaped by 17 hand labels on 5 sessions. That is enough to
   diagnose a STRUCTURAL fault (fault 1 is arithmetic, not a sample artefact) and nowhere near enough
   to tune parameters on. Defaults here are round numbers chosen for being principled, NOT optimised
   against his labels — the match rate is reported so it can be judged, and the real validation is
   him looking at the re-rendered pages and a fresh measurement afterwards.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import math
import os

GB = "/home/alphabot/gazbot7"
_s = importlib.util.spec_from_file_location("tw", f"{GB}/scripts/tunnel_watch.py")
tw = importlib.util.module_from_spec(_s)
_s.loader.exec_module(tw)                      # MU/SD/A, true_range, filter_states — never refitted

TRAIL_MIN = int(os.environ.get("TV2_TRAIL_MIN", "360"))    # regime window, hours not minutes
MERGE_GAP_MIN = int(os.environ.get("TV2_MERGE_GAP", "90"))
MERGE_OVERLAP = float(os.environ.get("TV2_MERGE_OVERLAP", "0.30"))
MIN_MIN = int(os.environ.get("TV2_MIN_MIN", "25"))
BUF_PCT = float(os.environ.get("TV2_BUF_PCT", "0.0"))      # his breaks are AT the edge


def normalised_tr(trs, trail_min: int = TRAIL_MIN):
    """log(TR) re-centred by a CAUSAL trailing median, so 'quiet' means quiet FOR THIS REGIME.

    Returns the feature already on the scale the shipped MU/SD were fitted on, so the model's own
    parameters keep their meaning and nothing is refitted.
    ⚠ CAUSAL: the window is strictly the trailing `trail_min` minutes up to and including now. Using
    a centred or full-sample median would be the look-ahead that makes a backtest lie.
    """
    ref = math.exp(tw.MU[0])                    # the scale the model calls 'quiet'
    out, win = [], []
    import bisect
    sortedwin: list[float] = []
    for i, t in enumerate(trs):
        v = max(float(t), 1e-6)
        win.append(v)
        bisect.insort(sortedwin, v)
        if len(win) > trail_min:
            old = win.pop(0)
            k = bisect.bisect_left(sortedwin, old)
            sortedwin.pop(k)
        med = sortedwin[len(sortedwin) // 2]
        # ★ warm-up: until the window has real regime information, fall back to the raw feature
        # rather than normalising by a median built from a handful of minutes.
        if len(win) < 30 or med <= 0:
            out.append(math.log(v))
        else:
            out.append(math.log(v) - math.log(med) + math.log(ref * 1.55))
    return out


def _filter_from_feature(feat):
    """The shipped forward filter, but fed the normalised feature.

    `tw.filter_states` takes raw TR and logs it internally, so exponentiate back to hand it a value
    whose log is our feature — one definition of the model, no second implementation of the maths.
    """
    return tw.filter_states([math.exp(f) for f in feat])


def quiet_runs(post, floor=1):
    runs, cur = [], None
    for i, p in enumerate(post):
        if p >= 0.5 and cur is None:
            cur = i
        elif p < 0.5 and cur is not None:
            if i - cur >= floor:
                runs.append((cur, i - 1))
            cur = None
    if cur is not None:
        runs.append((cur, len(post) - 1))
    return runs


def merge_containment(tuns, gap_min=MERGE_GAP_MIN, overlap=MERGE_OVERLAP):
    """Join adjacent runs that share a price range — a consolidation is ONE structure."""
    out = []
    for t in sorted(tuns, key=lambda z: z["t0"]):
        if out:
            p = out[-1]
            inter = max(0.0, min(p["hi"], t["hi"]) - max(p["lo"], t["lo"]))
            small = min(p["hi"] - p["lo"], t["hi"] - t["lo"])
            if (t["t0"] - p["t1"]) <= gap_min * 60 and small > 0 and inter / small >= overlap:
                p["t1"] = max(p["t1"], t["t1"])
                p["hi"] = max(p["hi"], t["hi"]); p["lo"] = min(p["lo"], t["lo"])
                p["i1"] = t["i1"]
                continue
        out.append(dict(t))
    return out


K_ATR = float(os.environ.get("TV2_K_ATR", "4.0"))
BOX_MIN = int(os.environ.get("TV2_BOX_MIN", "30"))


def detect_boxes(bars, *, k_atr=K_ATR, min_min=BOX_MIN, buf_pct=BUF_PCT):
    """PRICE CONTAINMENT, not a volatility state — maximal windows where price stays inside k x ATR.

    ★★★ 2026-09-04. The operator's 17 hand labels killed the volatility framing outright. Two of his
    tunnels on 08-11 OVERLAP IN TIME at different price levels, and his 08-13 box is 113 POINTS wide
    across 11 hours. Neither is a quiet-volatility run; both are ranges price keeps returning to.
    Scored against his labels: shipped HMM 2/17 at IoU>=0.5 (median IoU 0.10), the regime-normalised
    HMM 2/17 (0.06), containment 5/17 (0.37). Different object, not a better threshold.

    ⚠⚠ k_atr=4 and 30 minutes were picked from an 18-cell sweep against SEVENTEEN labels. That is a
    search wide enough to fit noise and is NOT a validated setting — it is a starting point to be
    judged by eye on sessions he has not labelled, then re-measured. Do not quote 5/17 as a result.

    ⚠ ATR is trailing-only (the 14 minutes up to and including now), so the box that forms is one a
    live reader could have formed. A box sized with the window's own full-period ATR would be a
    look-ahead.
    """
    trs = tw.true_range(bars)
    out, i, n = [], 0, len(bars)
    while i < n:
        w = trs[max(0, i - 14):i + 1]
        W = k_atr * max(sum(w) / max(1, len(w)), 1.0)
        hi, lo, j = bars[i]["hi"], bars[i]["lo"], i
        while j + 1 < n:
            h2, l2 = max(hi, bars[j + 1]["hi"]), min(lo, bars[j + 1]["lo"])
            if h2 - l2 > W:
                break
            hi, lo, j = h2, l2, j + 1
        if j - i + 1 >= min_min:
            m = {"i0": i, "i1": j, "t0": bars[i]["m"], "t1": bars[j]["m"],
                 "hi": hi, "lo": lo, "mins": j - i + 1, "width": hi - lo, "break": None}
            buf = buf_pct * (hi - lo)
            for q in range(j + 1, min(n, j + 1 + 480)):
                c = bars[q]["close"]
                if c > hi + buf:
                    m["break"] = {"i": q, "t": bars[q]["m"], "px": c, "side": "UP"}; break
                if c < lo - buf:
                    m["break"] = {"i": q, "t": bars[q]["m"], "px": c, "side": "DOWN"}; break
            out.append(m)
            i = j + 1
        else:
            i += 1
    return out


def detect(bars, *, trail_min=TRAIL_MIN, min_min=MIN_MIN, buf_pct=BUF_PCT,
           gap_min=MERGE_GAP_MIN, overlap=MERGE_OVERLAP):
    """The regime-normalised HMM route. KEPT, but no longer the default — see detect_boxes."""
    trs = tw.true_range(bars)
    post = _filter_from_feature(normalised_tr(trs, trail_min))
    raw = []
    for a, b in quiet_runs(post):
        seg = bars[a:b + 1]
        raw.append({"i0": a, "i1": b, "t0": bars[a]["m"], "t1": bars[b]["m"],
                    "hi": max(s["hi"] for s in seg), "lo": min(s["lo"] for s in seg)})
    merged = [m for m in merge_containment(raw, gap_min, overlap)
              if (m["t1"] - m["t0"]) / 60 + 1 >= min_min]
    for m in merged:
        m["mins"] = int((m["t1"] - m["t0"]) / 60) + 1
        buf = buf_pct * (m["hi"] - m["lo"])
        m["break"] = None
        for j in range(m["i1"] + 1, min(len(bars), m["i1"] + 1 + 480)):
            c = bars[j]["close"]
            if c > m["hi"] + buf:
                m["break"] = {"i": j, "t": bars[j]["m"], "px": c, "side": "UP"}; break
            if c < m["lo"] - buf:
                m["break"] = {"i": j, "t": bars[j]["m"], "px": c, "side": "DOWN"}; break
    return merged, post
