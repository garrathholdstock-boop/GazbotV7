"""UNTRADEABLE-DAY METER — the evidence for a stay-out call, computed live.

Three measurable tells, validated on 07-29/30 (green) vs 07-31 (untradeable −$569):
  1. ROUNDTRIP  = |day net move| / day range. Tradeable days GO somewhere (0.57/0.80);
     an untradeable day ends where it started (07-31 = 0.00 — 646pt range, net -1pt).
     This is THE discriminator (avg-ATR / clean-trend-% / shadow-net did NOT separate).
  2. WHIPSAW    = # significant (>=1.5 ATR) direction reversals in the day's path.
     A trend day has few; a roundtrip day whipsaws repeatedly.
  3. GATE-STOPS = fraction of recent live trades that exited STOP, across mechanisms.

Each → a 0-100 meter (higher = more untradeable); blended into a STAY-OUT score + verdict.
Single source of truth for the durable router AND the /v7/router dashboard panel. READ-ONLY.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone

UTC = timezone.utc


def _conn(p):
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _failed_breakouts(highs, lows, atr, look=12):
    """Count FALSE breakouts: a fresh session extreme (new high/low, by >=0.5 ATR over the prior
    extreme) that then reverses >= 1 ATR within `look` bars. A trend day EXTENDS its extremes
    (few fails); a roundtrip day breaks then comes back (many fails)."""
    n = len(highs)
    if n < 4 or atr <= 0:
        return 0
    fb = 0
    sh, sl = highs[0], lows[0]
    for i in range(1, n):
        if highs[i] > sh + 0.5 * atr:                      # new session high
            sh = highs[i]
            fwd = lows[i + 1:i + 1 + look]
            if fwd and min(fwd) <= highs[i] - atr:         # gave back >= 1 ATR
                fb += 1
        if lows[i] < sl - 0.5 * atr:                       # new session low
            sl = lows[i]
            fwd = highs[i + 1:i + 1 + look]
            if fwd and max(fwd) >= lows[i] + atr:
                fb += 1
    return fb


def compute(cap_path, store_path, day_start_ep, now_ep=None):
    """Return the untradeability read for the Paris day starting at day_start_ep (unix sec).
    Every part is guarded; a bad read degrades to neutral, never raises."""
    now_ep = now_ep or int(datetime.now(UTC).timestamp())
    out = {
        "roundtrip": None, "giveback": None, "net_pt": 0.0, "range_pt": 0.0, "atr": None,
        "failed_breakouts": 0, "stop_rate": None, "stop_n": 0, "stop_gates": 0,
        "meters": {"chop": 50, "giveback": 50, "stops": 50},
        "score": 50, "verdict": "—", "detail": "",
    }
    # ── tape: roundtrip + whipsaw ────────────────────────────────────────────
    atr = None
    try:
        c = _conn(cap_path)
        rows = c.execute(
            "SELECT bar_ts, high, low, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
            "AND bar_ts>=? AND bar_ts<=? ORDER BY bar_ts", (day_start_ep, now_ep)).fetchall()
        c.close()
        mins = {}
        for r in rows:
            mins[r["bar_ts"] // 60] = (r["high"], r["low"], r["close"])
        keys = sorted(mins)
        closes = [mins[k][2] for k in keys]
        highs = [mins[k][0] for k in keys]
        lows = [mins[k][1] for k in keys]
        if len(closes) >= 6:
            op = closes[0]
            net = closes[-1] - op
            rng = max(highs) - min(lows)
            out["net_pt"] = round(net, 1); out["range_pt"] = round(rng, 1)
            if rng >= 30:                      # need a real range for roundtrip to mean anything
                out["roundtrip"] = round(abs(net) / rng, 2)
                big = max(max(highs) - op, op - min(lows), 1.0)   # biggest excursion from the open
                out["giveback"] = round(max(0.0, min(1.0, 1 - abs(net) / big)), 2)
            # ATR (14-min true range)
            trs = []
            for i in range(1, len(closes)):
                trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
            if trs:
                atr = sum(trs[-14:]) / min(14, len(trs))
                out["atr"] = round(atr, 1)
            if atr and atr > 0:
                out["failed_breakouts"] = _failed_breakouts(highs, lows, atr)
    except Exception:
        pass
    # ── live gates: stop-rate across mechanisms (recent trades today) ─────────
    try:
        ds_iso = datetime.fromtimestamp(day_start_ep, UTC).strftime("%Y-%m-%dT%H:%M:%S")
        ne_iso = datetime.fromtimestamp(now_ep, UTC).strftime("%Y-%m-%dT%H:%M:%S")
        c = _conn(store_path)
        tr = c.execute(
            "SELECT gate, exit_reason FROM trades WHERE opened_at>=? AND opened_at<=? ORDER BY id DESC LIMIT 15",
            (ds_iso, ne_iso)).fetchall()
        c.close()
        if tr:
            stops = [t for t in tr if (t["exit_reason"] or "").upper() == "STOP"]
            out["stop_n"] = len(tr)
            out["stop_rate"] = round(len(stops) / len(tr), 2)
            out["stop_gates"] = len({(t["gate"] or "").replace("_A", "").replace("_B", "") for t in stops})
    except Exception:
        pass

    # ── meters (0-100, higher = more untradeable) ────────────────────────────
    # ROUNDTRIP (|net|/range) + GIVE-BACK (excursion handed back) are the proven discriminators
    # (validated 07-29/30 green vs 07-31 untradeable); STOP-RATE is supporting real-time context.
    rt = out["roundtrip"]
    gb = out["giveback"]
    chop = 50 if rt is None else round(max(0, min(1, 1 - rt)) * 100)
    give = 50 if gb is None else round(gb * 100)
    # ★2026-08-05 STOP-RATE NEEDS A REAL SAMPLE OR IT MUST NOT VOTE.
    # The old floor was stop_n >= 3, which let 4 trades set 20% of the score — on 08-05 it read 50
    # off n=4, a coin-flip carrying real weight. Worse, an absent reading defaulted to 50 and STILL
    # voted, so "I don't know" was scored identically to "half the trades stopped". Below MIN_STOP_N
    # the meter is now EXCLUDED and roundtrip/give-back are reweighted to 50/50 — the two the module's
    # own validation calls the discriminators. n is surfaced so the dashboard can show what it rests on.
    # Revert: stops = 50 if (...stop_n < 3) else ...; score = 0.40*chop + 0.40*give + 0.20*stops.
    MIN_STOP_N = 10
    have_stops = out["stop_rate"] is not None and out["stop_n"] >= MIN_STOP_N
    stops = round(out["stop_rate"] * 100) if have_stops else None
    out["meters"] = {"chop": chop, "giveback": give, "stops": stops}
    out["stops_counted"] = have_stops
    out["stops_min_n"] = MIN_STOP_N
    if have_stops:
        score = round(0.40 * chop + 0.40 * give + 0.20 * stops)
    else:
        score = round(0.50 * chop + 0.50 * give)
    out["score"] = score
    out["verdict"] = "STAY-OUT" if score >= 65 else ("CAUTION" if score >= 45 else "TRADEABLE")

    # ★2026-08-05 (operator: "show me the thresholds where we will jump back in. so i know what to
    # expect") — a score with no stated exit condition is a mood, not a signal. Solve the blend for
    # each input holding the others fixed, so the panel can say exactly what has to move and by how
    # much. Where a single input cannot get there alone, SAY SO rather than printing an out-of-range
    # number that looks achievable.
    #   score = wc*(1-rt)*100 + wg*gb*100  (+ ws*stop_rate*100 when the stop meter has a real sample)
    wc = wg = (0.40 if have_stops else 0.50)
    ws = 0.20 if have_stops else 0.0
    fixed = (ws * stops) if have_stops else 0.0
    tgt = []
    for name, thr in (("CAUTION", 65), ("TRADEABLE", 45)):
        need = {}
        # round-trip needed, holding give-back fixed
        rt_need = 1.0 - ((thr - wg * give - fixed) / (wc * 100.0))
        need["roundtrip"] = round(rt_need, 3) if 0.0 <= rt_need <= 1.0 else None
        # give-back needed, holding round-trip fixed
        gb_need = (thr - wc * chop - fixed) / (wg * 100.0)
        need["giveback"] = round(gb_need, 3) if 0.0 <= gb_need <= 1.0 else None
        need["reachable_alone"] = any(v is not None for v in (need["roundtrip"], need["giveback"]))
        tgt.append({"verdict": name, "score": thr, **need})
    out["thresholds"] = tgt
    out["now"] = {"roundtrip": rt, "giveback": gb}
    rtxt = "n/a" if rt is None else f"{rt:.2f}"
    gtxt = "n/a" if gb is None else f"{int(gb*100)}%"
    sr = "n/a" if out["stop_rate"] is None else f"{int(out['stop_rate']*100)}%"
    out["detail"] = (f"range {out['range_pt']:.0f}pt, net {out['net_pt']:+.0f}pt (roundtrip {rtxt}); "
                     f"gave back {gtxt} of the day's move; {sr} of last {out['stop_n']} trades stopped")
    return out
