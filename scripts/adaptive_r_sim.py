#!/usr/bin/env python3
"""GIVE-BACK STUDY — stage 4: SEQUENTIAL policy simulator for a tape-adaptive R.

Replays the SHIPPED live entry deciders over the unified 250 ms tick tape (16 sessions),
then walks each lot as its OWN slot holding ONE position at a time — exactly the live
dual-slot design, and exactly the accounting REV3 showed swings grind's verdict by $5,076
versus the paired/overlapping method. No overlapping same-signal entries anywhere.

Gates replayed (the four whose ENTRY is pure 1-min features + aggressor flow, so the live
decider can be driven verbatim):
    grind_long        gate_grind(slope_min=.4, fast_slope=True, ext_hi=2.0)      LONG
    abs_veto_long     gate_thrust(thr=1.5, amp_floor=4e-4) + the 55 s absorption VETO
    abs_veto_short    "                                                       "  SHORT
    rgv_short         gate_reversal_grab(**_RGV_SHORT)                          SHORT
capitulation_long / exhaustion_short are NOT here: their entries need the footprint /
L1-book feed, which only exists on the capture half of the tape. They are covered by the
MFE tables (stage 3) on their shadow entries instead, and flagged as such.

Exits: every decision on TICKS. Native 1-ATR stop always armed. 120-min MAX_HOLD.
A position is marked out at the last tick before a >5 min tape gap (session break).
Fee $1.50 per lot round trip. Slippage is a SEPARATE explicit term (--slip ticks).

  PYTHONPATH=src ./.venv/bin/python scripts/adaptive_r_sim.py --stage signals
  PYTHONPATH=src ./.venv/bin/python scripts/adaptive_r_sim.py --stage sweep
"""
from __future__ import annotations

import argparse
import pickle
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import (  # noqa: E402
    VETO_FLOW_MIN,
    VETO_SECS,
    Bar,
    compute_features,
    gate_grind,
    gate_reversal_grab,
    gate_thrust,
)
from gazbot7.sizing import efficiency_ratio  # noqa: E402
from gazbot7.slot_strategy import _RGV_SHORT  # noqa: E402

SCR = "/home/alphabot/gazbot7/scratchpad"
VPP, FEE = 2.0, 1.50
LOOKBACK = 60          # cfg.bar_lookback — 60 one-minute bars into the deciders
MAXHOLD_MS = 120 * 60 * 1000
GAP_MS = 5 * 60 * 1000
TICK = 0.25
QUIET_LO, QUIET_HI = 22 * 3600, 13 * 3600 + 1800


# ══ tape ════════════════════════════════════════════════════════════════════════════
def load_tape():
    con = duckdb.connect()
    t = con.execute(f"SELECT * FROM '{SCR}/mfe_ticks.parquet' ORDER BY ts_ms").df()
    b = con.execute(f"SELECT * FROM '{SCR}/mfe_bars1m.parquet' ORDER BY ts").df()
    ts = t.ts_ms.to_numpy(np.int64)
    return ts, t.price.to_numpy(float), t.signed.to_numpy(float), t.sz.to_numpy(float), b


def session_ends(ts: np.ndarray) -> np.ndarray:
    """ts index of the last tick before each >5 min hole (and the very last tick)."""
    gaps = np.flatnonzero(np.diff(ts) > GAP_MS)
    return np.append(gaps, len(ts) - 1)


# ══ signals ═════════════════════════════════════════════════════════════════════════
def build_signals():
    ts, px, sg, sz, bars = load_tape()
    b = bars.sort_values("ts").reset_index(drop=True)
    bts = b.ts.to_numpy(np.int64)
    barlist = [Bar(int(r.ts), r.o, r.h, r.l, r.c, r.v) for r in b.itertuples()]
    # cumulative signed flow -> O(1) window net-aggressor lookups
    cum = np.concatenate([[0.0], np.cumsum(sg)])

    def flow(a_ms: int, b_ms: int) -> tuple[float, float, int]:
        i = np.searchsorted(ts, a_ms, "left")
        j = np.searchsorted(ts, b_ms, "left")
        if j <= i:
            return 0.0, 0.0, 0
        return float(cum[j] - cum[i]), float(px[j - 1] - px[i]), j - i

    out = []
    n = len(barlist)
    for i in range(LOOKBACK, n):
        # a bar that follows a tape hole restarts the window (no cross-session features)
        if bts[i] - bts[i - LOOKBACK] > (LOOKBACK + 5) * 60:
            continue
        w = barlist[i - LOOKBACK + 1: i + 1]
        f = compute_features(w)
        if f.atr <= 0:
            continue
        dec_ms = (int(bts[i]) + 60) * 1000            # decide at the bar CLOSE
        tape_net, _dpx, ntk = flow(dec_ms - 60_000, dec_ms)   # md.recent_tape 60 s window
        if ntk < 3:
            continue
        er = efficiency_ratio(w)
        common = dict(ts=int(bts[i]), dec_ms=dec_ms, atr=f.atr, er=er,
                      atr_pct=f.atr_pct, ext=f.ext_atr, slope=f.vwap_slope_atr,
                      slope_fast=f.vwap_slope_fast, net30=f.net30_pt)

        e = gate_grind(f, tape_net=tape_net, slope_min=0.4, fast_slope=True, ext_hi=2.0)
        if e is not None and e.side == "LONG":
            out.append({**common, "gate": "grind_long", "side": "LONG"})

        e = gate_thrust(f, thr=1.5, amp_floor=0.0004)
        if e is not None:
            # ── the 55 s absorption VETO, faithful to tournament.run() ──
            # arm at dec_ms; VETO_SECS later the thrust must STILL fire (it does: the same
            # minute bars are in force 5 s before the next close) AND the burst must NOT
            # have absorbed. <5 ticks in the window => default-VETO (never a bad fill).
            fl, dp, nt = flow(dec_ms, dec_ms + VETO_SECS * 1000)
            if nt >= 5:
                side = e.side
                absorbed = ((side == "SHORT" and fl <= -VETO_FLOW_MIN and dp >= 0)
                            or (side == "LONG" and fl >= VETO_FLOW_MIN and dp <= 0))
                if not absorbed:
                    out.append({**common, "gate": f"abs_veto_{side.lower()}", "side": side,
                                "dec_ms": dec_ms + VETO_SECS * 1000})

        e = gate_reversal_grab(f, tape_net=tape_net, **_RGV_SHORT)
        if e is not None and e.side == "SHORT":
            out.append({**common, "gate": "rgv_short", "side": "SHORT"})

    s = pd.DataFrame(out)
    print(s.gate.value_counts().to_string())
    with open(f"{SCR}/ar_signals.pkl", "wb") as fh:
        pickle.dump(s, fh)
    print(f"\n{len(s)} signals -> {SCR}/ar_signals.pkl")
    return s


# ══ exits (vectorised on the tick slice) ════════════════════════════════════════════
def run_exit(fav: np.ndarray, atr: float, rule) -> tuple[int, float]:
    """First index at which `rule` fires on the favourable-excursion path, and the fav
    there. The native 1-ATR stop is ALWAYS armed and wins ties (a stop and a target in
    the same tick resolves to the stop — deliberately unkind). Returns (idx, fav)."""
    kind = rule[0]
    stop_hit = fav <= -atr
    if kind == "scalp":
        hit = fav >= rule[1] * atr
    elif kind == "dollar":          # FIXED-DOLLAR clip: target in POINTS, ATR-independent.
        hit = fav >= rule[1]        # this is the operator's mental model ("$15 / $30 / $50")
    else:
        peak = np.maximum.accumulate(fav)
        peak_r = peak / atr
        if kind == "tight":                       # exit_chandelier k1.5, tighten .75
            k = np.maximum(0.5, 1.5 - 0.75 * peak_r)
        elif kind == "chand":                     # exit_chandelier start_k, tighten .75
            k = np.maximum(0.5, rule[1] - 0.75 * peak_r)
        else:                                     # "wide" = exit_chandelier_lock 3.5 -> .5 @6R
            k = np.where(peak_r < rule[1], rule[2], rule[3])
        hit = (peak > 0) & (fav > 0) & (fav <= peak - k * atr)
    both = stop_hit | hit
    if not both.any():
        return len(fav) - 1, float(fav[-1])
    i = int(np.argmax(both))
    if stop_hit[i]:
        return i, -atr                            # fill AT the stop level (ceiling)
    if kind == "scalp":
        return i, rule[1] * atr                   # fill AT the target level (ceiling)
    if kind == "dollar":
        return i, rule[1]
    return i, float(fav[i])


RULES = {**{f"A{r}": ("scalp", r) for r in
            (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0)},
         **{f"D{d}": ("dollar", d / VPP) for d in (10, 15, 20, 25, 30, 40, 50, 60, 80)},
         "tight": ("tight",), "wide": ("wide", 6.0, 3.5, 0.5), "k2.5": ("chand", 2.5),
         "k3.5": ("chand", 3.5)}


def simulate(sig: pd.DataFrame, rule_of, ts, px, ends, slip_ticks=0.0, tag="") -> pd.DataFrame:
    """Sequential single-slot walk. `rule_of(row) -> rule key` lets the policy be
    STATE-DEPENDENT (that is the whole point: a tape-adaptive R picks the rule at entry)."""
    rows = []
    free_ms = 0
    for r in sig.itertuples():
        if r.dec_ms < free_ms:
            continue                                    # slot busy — the live desk skips it
        a = np.searchsorted(ts, r.dec_ms, "left")
        if a >= len(ts):
            continue
        se = ends[np.searchsorted(ends, a, "left")]      # last tick of this session
        b = min(se + 1, np.searchsorted(ts, ts[a] + MAXHOLD_MS, "right"))
        if b - a < 2:
            continue
        entry = px[a]
        seg = px[a:b]
        fav = (seg - entry) if r.side == "LONG" else (entry - seg)
        key = rule_of(r)
        i, f = run_exit(fav, r.atr, RULES[key])
        gross = (f - slip_ticks * TICK) * VPP
        rows.append({"gate": r.gate, "side": r.side, "dec_ms": r.dec_ms,
                     "exit_ms": int(ts[a + i]), "atr": r.atr, "er": r.er,
                     "atr_pct": r.atr_pct, "rule": key, "fav": f,
                     "pnl": gross - FEE, "hold_s": (ts[a + i] - ts[a]) / 1000.0,
                     "mfe": float(np.maximum.accumulate(fav)[i]), "tag": tag})
        free_ms = int(ts[a + i])
    return pd.DataFrame(rows)


def window_of(ms):
    sod = (ms // 1000) % 86400
    return "QUIET" if (sod >= QUIET_LO or sod < QUIET_HI) else "US"


def day_of(ms):
    return str(pd.Timestamp(int(ms + 2 * 3600 * 1000) * 1_000_000, tz="UTC").date())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="signals")
    a = ap.parse_args()
    if a.stage == "signals":
        build_signals()


if __name__ == "__main__":
    main()
