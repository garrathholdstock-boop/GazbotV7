#!/usr/bin/env python3
"""MOVEMENT 2 — the threshold sweep on the idle gates.

The block census says each of the six live gates misses the sat-out runs for ONE dominant
reason. This relaxes exactly that reason, one gate at a time, and prices every fill that
appears on the real quote path. Same entry engine, same exits, same costs as the lab.
Reports per-regime and per-day so nothing is a blanket cross-tape number.
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict

LAB = "/home/alphabot/gazbot7/scripts/friday_v7_movement2_lab.py"
exec(open(LAB).read().split("def main()")[0])   # noqa: S102 — shared engine

from gazbot7.footprint import FootprintCfg  # noqa: E402


# ── faithful re-derivations that take the hard-coded constant as an argument ─────────────
def rgv_short_fire(f, tape_net, *, ext_min, turn_atr, atr_min, slope_max, fast_slope,
                   fast_turn, flow_min):
    """gate_reversal_grab's SHORT branch with the 1.0 slope stand-down made a parameter."""
    slope = f.vwap_slope_fast if fast_slope else f.vwap_slope_atr
    if f.atr_pct > 0.09 or abs(slope) > slope_max:
        return False
    if atr_min and f.atr < atr_min:
        return False
    turn = f.net_atr_2 if fast_turn else f.net_atr_5
    if f.ext_atr < ext_min:
        return False
    if turn > -turn_atr:
        return False
    if flow_min is not None and tape_net > -flow_min:
        return False
    return True


# ── the grid: each cell relaxes ONE binding constraint off the live config ───────────────
LIVE_RGV = dict(ext_min=1.5, turn_atr=0.25, atr_min=20.0, slope_max=1.0,
                fast_slope=False, fast_turn=False, flow_min=None)

GRID = {
    "grind_long": [
        ("LIVE atr>=22",        dict(), 22.0),
        ("atr>=18",             dict(), 18.0),
        ("atr>=14",             dict(), 14.0),
        ("atr>=10",             dict(), 10.0),
        ("no atr floor",        dict(), 0.0),
        ("slope>=0.2",          dict(slope_min=0.2), 22.0),
        ("slope>=0.6",          dict(slope_min=0.6), 22.0),
        ("ext_hi 2.0",          dict(ext_hi=2.0), 22.0),
        ("ext_hi 8.0",          dict(ext_hi=8.0), 22.0),
        ("ext_lo 0.0",          dict(ext_lo=0.0), 22.0),
    ],
    "capitulation_long": [
        ("LIVE climax 2.5+flip", dict(), 10.0),
        ("climax 2.0",           dict(climax_min=2.0), 10.0),
        ("climax 1.5",           dict(climax_min=1.5), 10.0),
        ("climax 1.5 no-flip",   dict(climax_min=1.5, require_flip=False), 10.0),
        ("no atr floor",         dict(), 0.0),
        ("dom 0.5",              dict(dom_min=0.5), 10.0),
    ],
    "abs_veto_long": [
        ("LIVE thr1.5+vol+amp", dict(), 0.0),
        ("no vol surge",        dict(require_vol=False), 0.0),
        ("no amp floor",        dict(amp_floor=0.0), 0.0),
        ("thr 1.25",            dict(thr=1.25), 0.0),
        ("thr 1.0",             dict(thr=1.0), 0.0),
        ("thr 2.0",             dict(thr=2.0), 0.0),
        ("fast (2-bar)",        dict(fast=True), 0.0),
        ("no 55s veto",         dict(), 0.0),
    ],
    "abs_veto_short": [
        ("LIVE thr1.5+vol+amp", dict(), 0.0),
        ("no vol surge",        dict(require_vol=False), 0.0),
        ("no amp floor",        dict(amp_floor=0.0), 0.0),
        ("thr 1.25",            dict(thr=1.25), 0.0),
        ("thr 1.0",             dict(thr=1.0), 0.0),
        ("thr 2.0",             dict(thr=2.0), 0.0),
        ("fast (2-bar)",        dict(fast=True), 0.0),
        ("no 55s veto",         dict(), 0.0),
    ],
    "rgv_short": [
        ("LIVE ext1.5 atr>=20", dict(), 0.0),
        ("atr>=13",             dict(atr_min=13.0), 0.0),
        ("no atr floor",        dict(atr_min=0.0), 0.0),
        ("slope_max 2.0",       dict(slope_max=2.0), 0.0),
        ("slope_max 99 (off)",  dict(slope_max=99.0), 0.0),
        ("ext 1.0 + slope off", dict(ext_min=1.0, slope_max=99.0), 0.0),
        ("fast_turn",           dict(fast_turn=True), 0.0),
    ],
    "exhaustion_short": [
        ("LIVE net>=400",       dict(), 0.0),
        ("net>=250",            dict(net_min=250.0), 0.0),
        ("net>=150",            dict(net_min=150.0), 0.0),
        ("move_max 4pt",        dict(move_max=4.0), 0.0),
        ("wall 1.2",            dict(wall_ratio=1.2), 0.0),
        ("net>=150 wall1.2",    dict(net_min=150.0, wall_ratio=1.2), 0.0),
    ],
}


def fires(gate, spec, s, over):
    p = dict(spec.params); p.update(over)
    if spec.kind == "thrust":
        e = gate_thrust(s.f, **p)
        return bool(e and e.side == spec.side)
    if spec.kind == "grind":
        e = gate_grind(s.f, tape_net=s.tape_net, **p)
        return bool(e and e.side == spec.side)
    if spec.kind == "capitulation":
        e = gate_capitulation(s.f, cap_sell=s.fp["cap_sell"], cap_buy=s.fp["cap_buy"],
                              cap_base=s.fp["cap_base"], cap_dpx=s.fp["cap_dpx"],
                              cap_flip=s.fp["cap_flip"], **p)
        return bool(e and e.side == spec.side)
    if spec.kind == "reversal_grab":
        cfg = dict(LIVE_RGV); cfg.update(over)
        return rgv_short_fire(s.f, s.tape_net, **cfg)
    if spec.kind == "exhaustion":
        cfg = FootprintCfg(**{**dict(net_min=400.0, move_max=2.0, wall_ratio=1.5, window_s=20),
                              **over})
        sig = exhaustion_signal(s.fp["net_signed"], s.fp["price_move_pt"], s.fp["bid1_size"],
                                s.fp["ask1_size"], s.fp["bid1_price"], s.fp["ask1_price"], cfg)
        return bool(sig and sig[0] == spec.side)
    return False


def run_cell(gate, spec, lots, snaps, quotes_fn, label, over, atr_floor, run):
    """One (gate, config) over one run's second-by-second tape. Live veto layers kept unless
    the cell name says otherwise. Same semantics as the lab: the 55s abs-veto needs the thrust
    STILL firing; the 5s exhaustion confirm resolves on the clock off the window's max adverse tick."""
    no_veto = label == "no 55s veto"
    trades = []
    busy = 0
    pend_v = None
    pend_e = None

    def enter(s):
        nonlocal busy
        quotes = quotes_fn("quotes", None, None)
        i0 = _lower(quotes, s.ms)
        flat = session_flat_ms(s.ms)
        made = []
        for lot in lots:
            t = reprice(lot, spec.side, s.f.atr, quotes, i0, flat)
            if t is None:
                continue
            t.update(gate=gate, cell=label, run=run["tm"], day=run["tm"][:5], side=spec.side,
                     entry_ms=s.ms, atr=s.f.atr, er=s.er,
                     in_dir=(spec.side == ("LONG" if run["dir"] == "UP" else "SHORT")))
            made.append(t)
        if not made:
            return
        trades.extend(made)
        busy = max(t["exit_ms"] for t in made)

    for s in snaps:
        if pend_e is not None:
            armed_ms, sig_px = pend_e
            age = (s.ms - armed_ms) / 1000.0
            if age >= EXH_SECS:
                rows = quotes_fn("ticks", armed_ms, s.ms)
                adverse = True
                if len(rows) >= 3:
                    adverse = (max(r[1] for r in rows) - sig_px) > EXH_ADVERSE_PT
                pend_e = None
                if not adverse and age <= EXH_MAX_SECS and s.ms >= busy:
                    enter(s)
            continue
        if not fires(gate, spec, s, over):
            pend_v = None
            continue
        if atr_floor and s.f.atr < atr_floor:
            continue
        if spec.veto_counter_regime and (s.mode_long if spec.side == "LONG" else s.mode_short) == "mid":
            continue
        if s.ms < busy:
            continue
        if gate.startswith("abs_veto") and not no_veto:
            if pend_v is None:
                pend_v = s.ms
            age = (s.ms - pend_v) / 1000.0
            if age < VETO_SECS:
                continue
            if age > VETO_MAX_SECS:
                pend_v = None
                continue
            lo, pend_v = pend_v, None
            rows = quotes_fn("ticks", lo, s.ms)
            absorbed = True
            if len(rows) >= 5:
                flow = sum((r[2] if r[3] == "buy" else -r[2]) for r in rows)
                absorbed = exit_absorption(Position(spec.side, 0.0, 0.0, 0.0), tape_net=flow,
                                           window_price_delta=rows[-1][1] - rows[0][1],
                                           flow_min=VETO_FLOW_MIN) is not None
            if absorbed:
                continue
        if gate == "exhaustion_short":
            pend_e = (s.ms, s.price)
            continue
        enter(s)
    return trades


def main():
    runs = load_runs()
    sat = [r for r in runs if r["us"] == "sat out"]
    specs = live_specs()
    con = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    con.execute("PRAGMA cache_size=-200000")
    out = []
    for n, r in enumerate(sat, 1):
        t1 = r["ts"]; t0 = t1 - PRE_S
        b5, tk, bk = load_window(con, t0, t1)
        snaps = build_snaps(t0, t1, b5, tk, bk)
        if not snaps:
            print(f"[{n}/{len(sat)}] {r['tm']} NO TAPE", flush=True)
            continue
        quotes = load_quotes(con, t0 * 1000, (t1 + MAX_HOLD_S + 600) * 1000)

        def qf(kind, lo, hi, _tk=tk, _q=quotes):
            if kind == "quotes":
                return _q
            return [x for x in _tk if lo <= x[0] < hi]

        got = 0
        for gate, cells in GRID.items():
            spec, lots = specs[gate]
            for label, over, floor in cells:
                tr = run_cell(gate, spec, lots, snaps, qf, label, over, floor, r)
                out += tr
                got += len(tr)
        print(f"[{n}/{len(sat)}] {r['tm']} {r['dir']}{r['move']:+d} lots={got}", flush=True)
    with open("/home/alphabot/gazbot7/reports/friday_v7/sections/m2_sweep.json", "w") as f:
        json.dump(out, f)
    print("wrote m2_sweep.json ·", len(out), "lot-trades")


if __name__ == "__main__":
    main()
