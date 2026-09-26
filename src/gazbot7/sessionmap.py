"""SESSION MAP — the whole trading day, segmented into TUNNELS and RUNS, continuously.

★2026-09-02. The operator, after being given the 8h/DAY chart toggles: *"i can see the story and
the tunnels. then if im sitting in a tunnel i watch it and when i think its broken out i buy or
sell. why cant the desk have that view. always look at the whole day."*

He is right that the desk did not have it. Every detector built before this read a TRAILING WINDOW —
30 or 60 minutes — which cannot hold a tunnel that formed at 09:28 and is still holding at 12:00.
He does not watch a rolling window; he watches the SESSION, and he holds a tunnel in his head as an
object with a floor, a ceiling and an age. This module gives the desk that same object.

WHAT THIS IS AND IS NOT
───────────────────────
This is a VIEW, not a signal. It answers "where are we and what are the levels", never "what next".
The break of a tunnel edge has been measured four separate ways on 240 sessions and carries no
directional edge (P(continuation) 0.44-0.51 against a 0.50 control) and, causally, no magnitude edge
either (1.02x a matched control, where an earlier acausal measurement wrongly claimed 1.75x). Its
value is that the operator and the desk finally look at the SAME OBJECT — which is worth building
because the absence of one has been expensive: every wrong turn in the 09-02 research came from
measuring something that was not what he was watching.

★ CAUSAL BY CONSTRUCTION. Forward filtering only, from the session open. What the map shows for
  10:15 is what was knowable at 10:15 — it never re-labels the past once the future arrives. A
  Viterbi/smoothed map would look tidier and would be a lie: it put the "break" a median 3 minutes
  after the model had already decided, with hindsight, that the compression was over, and only 36%
  of those breaks existed in real time. That artefact produced a z=4-6 "finding" that was entirely
  manufactured. Do not swap the forward pass for a smoothed one to make the chart prettier.

★ ONE DEFINITION. The HMM parameters live HERE and nowhere else; `scripts/tunnel_watch.py` imports
  them. Two copies of a model is two models the moment one is edited.
"""
from __future__ import annotations

import math
import os
import sqlite3
import time
from datetime import datetime, timedelta, UTC

# ── the fitted model (offline, 11 months, 322,300 bars / 240 sessions) ────────
# Gaussian emissions on log(true range in points). Index 0 is QUIET.
QUIET, ACTIVE = 0, 1
MU = (1.636534, 2.682335)
SD = (0.509254, 0.523180)
A = ((0.991211, 0.008789),
     (0.008722, 0.991278))
# quiet mean TR 5.14pt · active 14.62pt · P(stay) 0.9912 / 0.9913

# A quiet stretch shorter than this is not a tunnel, it is a pause inside a move. A gap of active
# minutes shorter than MERGE_GAP does not end a tunnel — price poking out and coming straight back
# is what 91% of "breaks" do, and the operator would not redraw his box for it.
MIN_TUNNEL_MIN = 20
MERGE_GAP_MIN = 4
# how close price must come to an edge to count as TESTING it (in ATR)
TOUCH_ATR = 0.35


def session_start(now: datetime | None = None) -> datetime:
    """The CME session opens 22:00Z. Returns the open of the session `now` falls in."""
    now = now or datetime.now(UTC)
    s = now.replace(hour=22, minute=0, second=0, microsecond=0)
    if now < s:
        s -= timedelta(days=1)
    return s


def load_session(capture_path: str, symbol: str = "MNQ", now: datetime | None = None) -> list[dict]:
    """1-minute bars for the CURRENT session, aggregated from the live 5s capture. READ-ONLY.

    ★ `bar_ts - (bar_ts % 60)` — integer modulo. Float division by 60 is a silent no-op that once
      read 5s bars as "1m" for hours.
    ★ The close is the REAL last print of the minute, not a midpoint: the model was fitted on true
      range off the close, and computing the feature differently here would run the model on
      something it was not fitted on.
    """
    start = int(session_start(now).timestamp())
    uri = f"file:{capture_path}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as c:
        rows = c.execute(
            """select bar_ts - (bar_ts % 60) as m, bar_ts, high, low, "close", volume
               from bars where symbol = ? and bar_ts >= ? order by bar_ts""",
            (symbol, start),
        ).fetchall()
    agg: dict[int, dict] = {}
    for m, bts, hi, lo, cl, vol in rows:
        b = agg.get(m)
        if b is None:
            agg[m] = {"m": int(m), "hi": float(hi), "lo": float(lo),
                      "close": float(cl), "_last": bts, "vol": float(vol or 0)}
        else:
            b["hi"] = max(b["hi"], float(hi))
            b["lo"] = min(b["lo"], float(lo))
            b["vol"] += float(vol or 0)
            if bts >= b["_last"]:
                b["_last"] = bts
                b["close"] = float(cl)
    bars = [agg[k] for k in sorted(agg)]
    # drop the minute still forming, so a partial bar never moves a level
    return bars[:-1] if len(bars) > 1 else bars


def true_range(bars: list[dict]) -> list[float]:
    out, prev = [], None
    for b in bars:
        tr = b["hi"] - b["lo"]
        if prev is not None:
            tr = max(tr, abs(b["hi"] - prev), abs(b["lo"] - prev))
        out.append(max(tr, 1e-6))
        prev = b["close"]
    return out


def _emit(logtr: float, k: int) -> float:
    z = (logtr - MU[k]) / SD[k]
    return math.exp(-0.5 * z * z) / (SD[k] * math.sqrt(2 * math.pi)) + 1e-300


def filter_quiet(trs: list[float]) -> list[float]:
    """P(QUIET at t | data up to t). FORWARD ONLY — see the module docstring on why."""
    if not trs:
        return []
    xs = [math.log(max(float(t), 1e-9)) for t in trs]
    a = [0.5 * _emit(xs[0], 0), 0.5 * _emit(xs[0], 1)]
    s = sum(a) or 1e-300
    a = [v / s for v in a]
    post = [a[QUIET]]
    for x in xs[1:]:
        nxt = [(a[0] * A[0][k] + a[1] * A[1][k]) * _emit(x, k) for k in (0, 1)]
        s = sum(nxt) or 1e-300
        a = [v / s for v in nxt]
        post.append(a[QUIET])
    return post


def segment(bars: list[dict], post: list[float]) -> list[dict]:
    """Contiguous QUIET runs -> tunnels; everything between them -> runs.

    Short active gaps are BRIDGED (MERGE_GAP_MIN): price poking out of a range and coming straight
    back is what most "breaks" do, and a human would not redraw the box for it. Bridging costs a few
    minutes of lag on confirming the tunnel really ended, which is honest — the operator's own read
    has the same lag.
    """
    if not bars:
        return []
    q = [p >= 0.5 for p in post]
    # bridge short active gaps between quiet stretches
    i = 0
    while i < len(q):
        if q[i]:
            j = i
            while j + 1 < len(q) and q[j + 1]:
                j += 1
            k = j + 1
            gap = 0
            while k < len(q) and not q[k] and gap < MERGE_GAP_MIN:
                k += 1
                gap += 1
            if k < len(q) and q[k] and gap > 0:
                for t in range(j + 1, k):
                    q[t] = True
                i = j
                continue
            i = j + 1
        else:
            i += 1

    segs, i = [], 0
    while i < len(q):
        j = i
        while j + 1 < len(q) and q[j + 1] == q[i]:
            j += 1
        seg = bars[i:j + 1]
        kind = "tunnel" if q[i] else "run"
        if kind == "tunnel" and (j - i + 1) < MIN_TUNNEL_MIN:
            kind = "run"                     # too short to be a tunnel; it is part of the move
        top = max(x["hi"] for x in seg)
        bot = min(x["lo"] for x in seg)
        net = seg[-1]["close"] - seg[0]["close"]
        segs.append({
            "kind": kind, "i0": i, "i1": j,
            "t0": seg[0]["m"], "t1": seg[-1]["m"], "minutes": j - i + 1,
            "ceiling": round(top, 2), "floor": round(bot, 2),
            "width": round(top - bot, 2), "net": round(net, 2),
            "roundtrip": round(abs(net) / (top - bot), 3) if top > bot else 0.0,
            "vol_per_min": round(sum(x["vol"] for x in seg) / max(1, j - i + 1)),
        })
    # merge consecutive same-kind segments created by the demotion above
    out: list[dict] = []
    for s in segs:
        if out and out[-1]["kind"] == s["kind"]:
            p = out[-1]
            p["i1"], p["t1"] = s["i1"], s["t1"]
            p["minutes"] += s["minutes"]
            p["ceiling"] = max(p["ceiling"], s["ceiling"])
            p["floor"] = min(p["floor"], s["floor"])
            p["width"] = round(p["ceiling"] - p["floor"], 2)
            p["vol_per_min"] = round((p["vol_per_min"] + s["vol_per_min"]) / 2)
        else:
            out.append(dict(s))
    for s in out:
        seg = bars[s["i0"]:s["i1"] + 1]
        s["net"] = round(seg[-1]["close"] - seg[0]["close"], 2)
        s["roundtrip"] = round(abs(s["net"]) / s["width"], 3) if s["width"] > 0 else 0.0
    return out


def current_state(bars: list[dict], segs: list[dict], trs: list[float]) -> dict:
    """Where are we RIGHT NOW, and what are the live levels.

    This is the object the operator holds in his head: in a tunnel with a floor and a ceiling, how
    long we have been in it, and how many times each edge has been tested without giving way.
    """
    if not bars or not segs:
        return {"ok": False}
    last = segs[-1]
    px = bars[-1]["close"]
    atr = sum(trs[-14:]) / min(14, len(trs)) if trs else 0.0
    st = {"ok": True, "kind": last["kind"], "price": round(px, 2),
          "atr": round(atr, 2), "minutes": last["minutes"],
          "bars": len(bars), "last_ts": bars[-1]["m"]}
    if last["kind"] == "tunnel":
        seg = bars[last["i0"]:last["i1"] + 1]
        tol = atr * TOUCH_ATR
        st.update({
            "ceiling": last["ceiling"], "floor": last["floor"], "width": last["width"],
            "to_ceiling": round(last["ceiling"] - px, 2),
            "to_floor": round(px - last["floor"], 2),
            "ceiling_tests": sum(1 for b in seg if b["hi"] >= last["ceiling"] - tol),
            "floor_tests": sum(1 for b in seg if b["lo"] <= last["floor"] + tol),
            "vol_per_min": last["vol_per_min"],
        })
    else:
        st.update({"net": last["net"], "roundtrip": last["roundtrip"],
                   "vol_per_min": last["vol_per_min"]})
    return st


def build(capture_path: str, symbol: str = "MNQ", now: datetime | None = None) -> dict:
    """The whole map: every segment of the session so far, plus the live state."""
    bars = load_session(capture_path, symbol, now)
    if len(bars) < 20:
        return {"ok": False, "reason": "not enough session tape yet", "bars": len(bars)}
    trs = true_range(bars)
    post = filter_quiet(trs)
    segs = segment(bars, post)
    stale = time.time() - (bars[-1]["m"] + 60)
    return {
        "ok": True,
        "session_open": int(session_start(now).timestamp()),
        "bars": len(bars),
        "stale_s": round(stale),
        "segments": [{k: v for k, v in s.items() if k not in ("i0", "i1")} for s in segs],
        "tunnels": sum(1 for s in segs if s["kind"] == "tunnel"),
        "runs": sum(1 for s in segs if s["kind"] == "run"),
        "now": current_state(bars, segs, trs),
    }
