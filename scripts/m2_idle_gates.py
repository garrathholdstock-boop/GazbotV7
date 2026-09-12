"""MOVEMENT 2 — THE IDLE-GATE LAB.

Fire ALL SIX live gates (deciders.py, via the real tournament slate) mechanically at the
frozen census's SAT-OUT runs: in-direction, in the 10 minutes before ignition, tick-honest
exits, $1.50/RT, $2.00/pt MNQ.

Faithful to the live desk:
  · 1-min bars folded from the 5s stream (integer floor), deque of 60 (cfg.bar_lookback)
  · features via deciders.compute_features — the SAME function the desk calls
  · the six BASE gate specs pulled from slot_strategy.tournament_slots()
  · the exit stack rebuilt from data/exit_overrides.json via scaleout_slots() (2 lots/gate)
  · 1Hz decision clock (md publishes the tape ~1/s and the tournament decides on it)
  · the 55s abs_veto absorption-veto, the 5s exhaustion confirm, the counter-regime veto,
    the ATR floors, the ASIA 00-07Z no-open block — each individually switchable so the
    MECHANISM of every miss is attributable.
"""
from __future__ import annotations
import json, sys, math
from bisect import bisect_left, bisect_right
from dataclasses import replace
import numpy as np, pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import (Bar, Position, compute_features, efficiency_ratio, atr_blocks,
                              er_blocks, exit_absorption, exit_scalp, exit_chandelier,
                              exit_chandelier_lock, gate_grind, gate_capitulation,
                              gate_reversal_grab, gate_thrust, ATR_FLOOR,
                              VETO_SECS, VETO_FLOW_MIN, EXH_CONFIRM_SECS, EXH_ADVERSE_PT)
from gazbot7.footprint import exhaustion_signal
from gazbot7.slot_strategy import tournament_slots, scaleout_slots
from gazbot7.direction_router import ER_TREND, NET_MIN, WINDOW as RWINDOW

M2 = "/home/alphabot/gazbot7/reports/friday_v7/sections/m2"
VPP, FEE = 2.0, 1.5           # MNQ $2.00/point · $1.50 per ROUND TRIP  (data contract §4/§5)
MAX_HOLD_S = 120 * 60         # RunConfig.max_hold_minutes
FLAT_BY_UTC_S = 20 * 3600 + 55 * 60   # the desk's eod flatten

# ── caches ────────────────────────────────────────────────────────────────────
import duckdb
_dk = duckdb.connect()
def _pq(name):
    return _dk.execute(f"SELECT * FROM '{M2}/{name}.parquet'").df()
_t = _pq("ticks")
TK_TS = _t.ts_ms.to_numpy(np.int64); TK_PX = _t.price.to_numpy(np.float64)
_s = _pq("tape_sec")
SEC = _s.s.to_numpy(np.int64)
BUY = _s.buy_v.to_numpy(np.float64); SELL = _s.sell_v.to_numpy(np.float64)
TOT = _s.tot_v.to_numpy(np.float64); NTK = _s.n.to_numpy(np.int64)
FPX = _s.first_px.to_numpy(np.float64); LPX = _s.last_px.to_numpy(np.float64)
_cb = np.concatenate([[0.0], np.cumsum(BUY)]); _cs = np.concatenate([[0.0], np.cumsum(SELL)])
_ct = np.concatenate([[0.0], np.cumsum(TOT)]); _cn = np.concatenate([[0], np.cumsum(NTK)])
_b = _pq("book1_sec")
BK_S = _b.s.to_numpy(np.int64)
BK = {c: _b[c].to_numpy(np.float64) for c in ("bid_px", "bid_sz", "ask_px", "ask_sz")}
_bar = _pq("bars1m")
BAR_M = _bar.m.to_numpy(np.int64)
BARS = [Bar(int(r.m), float(r.o), float(r.h), float(r.l), float(r.cl), float(r.v))
        for r in _bar.itertuples()]


def _rng(lo_s: int, hi_s: int):
    """index range for whole seconds [lo_s, hi_s] in the per-second tape table"""
    return bisect_left(SEC, lo_s), bisect_right(SEC, hi_s)


def tape_window(lo_s: int, hi_s: int):
    """(buy, sell, tot, nticks, first_px, last_px) over whole seconds [lo_s, hi_s]."""
    i, j = _rng(lo_s, hi_s)
    if i >= j:
        return 0.0, 0.0, 0.0, 0, None, None
    return (_cb[j] - _cb[i], _cs[j] - _cs[i], _ct[j] - _ct[i], int(_cn[j] - _cn[i]),
            float(FPX[i]), float(LPX[j - 1]))


def last_tick_px(s: int):
    k = bisect_right(TK_TS, s * 1000 + 999) - 1
    return float(TK_PX[k]) if k >= 0 else None


def bars_at(s: int):
    """the completed 1-min bars the live MinuteBars deque (maxlen 60) would hold at second s"""
    j = bisect_right(BAR_M, s - 60)
    return BARS[max(0, j - 60):j]


def footprint_at(s: int):
    """footprint_summary() rebuilt: capitulation_tape(20s/180s) + the 20s exhaustion inputs + L1."""
    sb, ss, _st, sn, sf, sl = tape_window(s - 20, s - 1)          # short 20s window
    _b1, _s1, base_tot, _n1, _f1, _l1 = tape_window(s - 180, s - 21)
    hb, hs, _ht, _hn, _hf, _hl = tape_window(s - 10, s - 1)       # the flip half
    base = base_tot / max(1.0, (180 - 20) / 20)
    dpx = (sl - sf) if (sf is not None and sl is not None) else 0.0
    k = bisect_right(BK_S, s) - 1
    bp = bs = ap = az = 0.0
    if k >= 0:
        bp, bs, ap, az = (float(BK["bid_px"][k]), float(BK["bid_sz"][k]),
                          float(BK["ask_px"][k]), float(BK["ask_sz"][k]))
    return {"cap_sell": ss, "cap_buy": sb, "cap_base": base, "cap_dpx": dpx,
            "cap_flip": hb > hs,
            "net_signed": (sb - ss) if sn >= 1 else 0.0,
            "price_move_pt": dpx if sn >= 2 else 0.0,
            "bid1_size": bs or 0.0, "ask1_size": az or 0.0,
            "bid1_price": bp or 0.0, "ask1_price": ap or 0.0}


def regime_mode(side: str, bars):
    """slot_strategy._regime_mode — used by the exhaustion counter-regime entry veto."""
    cl = [b.close for b in bars[-RWINDOW:]]
    if len(cl) < 6:
        return "tight"
    path = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1.0
    er = abs(cl[-1] - cl[0]) / path
    net = cl[-1] - cl[0]
    up = er >= ER_TREND and net >= NET_MIN
    down = er >= ER_TREND and net <= -NET_MIN
    if (side == "SHORT" and down) or (side == "LONG" and up):
        return "wide"
    if (side == "SHORT" and up) or (side == "LONG" and down):
        return "mid"
    return "tight"


# ── the six live base gates ───────────────────────────────────────────────────
BASE = {s.tag: s for s in tournament_slots()}
LOTS: dict[str, list] = {}
for sp in scaleout_slots():
    LOTS.setdefault(sp.tag[:-2], []).append(sp)
GATES = list(BASE)            # grind_long capitulation_long abs_veto_long rgv_short exhaustion_short abs_veto_short
SIDE = {g: BASE[g].side for g in GATES}


def gate_fires(g: str, f, net_flow: float, fp: dict) -> bool:
    sp = BASE[g]
    if sp.kind == "grind":
        e = gate_grind(f, tape_net=net_flow, **sp.params)
    elif sp.kind == "reversal_grab":
        e = gate_reversal_grab(f, tape_net=net_flow, **sp.params)
    elif sp.kind == "thrust":
        e = gate_thrust(f, **sp.params)
    elif sp.kind == "capitulation":
        e = gate_capitulation(f, cap_sell=fp["cap_sell"], cap_buy=fp["cap_buy"],
                              cap_base=fp["cap_base"], cap_dpx=fp["cap_dpx"],
                              cap_flip=fp["cap_flip"], **sp.params)
    elif sp.kind == "exhaustion":
        sig = exhaustion_signal(fp["net_signed"], fp["price_move_pt"], fp["bid1_size"],
                                fp["ask1_size"], fp["bid1_price"], fp["ask1_price"])
        return sig is not None and sig[0] == sp.side
    else:
        return False
    return e is not None and e.side == sp.side


# ── tick-honest exit replay for one LOT ───────────────────────────────────────
def replay_lot(spec, side: str, entry_ms: int, entry_px: float, atr: float, slip_pt: float = 0.0):
    """Walk the real tick path. Native server-side STP at stop_atr_mult*ATR owns the loss
    side; the managed profit exits are exactly slot_strategy._manage's stack."""
    stop_pt = spec.stop_atr_mult * atr
    lo_q = spec.atr_split and atr < spec.atr_split
    i = bisect_left(TK_TS, entry_ms)
    peak = 0.0
    cap_ms = entry_ms + MAX_HOLD_S * 1000
    for k in range(i, len(TK_TS)):
        ts, px = int(TK_TS[k]), float(TK_PX[k])
        sod = (ts // 1000) % 86400
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav <= -stop_pt:                                    # native 1(-ish)-ATR STP
            return -stop_pt - slip_pt, "STOP", ts
        if peak < fav:
            peak = fav
        pos = Position(side, entry_px, atr, peak)
        r = None
        if lo_q:                                               # quiet-tape clip pre-empts everything
            if spec.lo_target_usd and fav * VPP >= spec.lo_target_usd:
                r = "TARGET"
            elif spec.lo_target_r and atr > 0:
                tgt = spec.lo_target_r * atr
                if spec.lo_floor_usd:
                    tgt = max(tgt, spec.lo_floor_usd / VPP)
                if fav >= tgt:
                    r = "TARGET"
        elif spec.exit == "chandelier_lock":
            r = exit_chandelier_lock(pos, px, start_k=spec.chandelier_start_k,
                                     lock_r=spec.lock_r, lock_k=spec.lock_k)
        elif spec.exit == "chandelier":
            if exit_chandelier(pos, px, start_k=spec.chandelier_start_k,
                               min_k=spec.chandelier_min_k, tighten=spec.chandelier_tighten):
                r = "CHANDELIER"
        elif exit_scalp(pos, px, target_r=spec.target_r, stop_atr_mult=spec.stop_atr_mult) == "TARGET":
            r = "TARGET"
        if r:
            return fav - slip_pt, r, ts
        if ts >= cap_ms:
            return fav - slip_pt, "TIME_CAP", ts
        if sod >= FLAT_BY_UTC_S:
            return fav - slip_pt, "EOD_FLAT", ts
    k = len(TK_TS) - 1
    fav = (float(TK_PX[k]) - entry_px) if side == "LONG" else (entry_px - float(TK_PX[k]))
    return fav - slip_pt, "TAPE_END", int(TK_TS[k])


def price_fire(g: str, side: str, entry_s: int, atr: float, slip_pt: float = 0.0):
    """Both lots of a gate, from the same signal. Returns per-lot rows + gate net $."""
    i = bisect_left(TK_TS, entry_s * 1000)
    if i >= len(TK_TS):
        return None
    entry_ms, entry_px = int(TK_TS[i]), float(TK_PX[i])
    entry_px += slip_pt if side == "LONG" else -slip_pt
    out = []
    for spec in LOTS[g]:
        pt, why, ts = replay_lot(spec, side, entry_ms, entry_px, atr, slip_pt)
        out.append({"lot": spec.tag, "pt": pt, "usd": pt * VPP - FEE, "why": why,
                    "exit_ms": ts, "hold_min": (ts - entry_ms) / 60000.0})
    return {"entry_ms": entry_ms, "entry_px": entry_px, "atr": atr,
            "lots": out, "usd": sum(o["usd"] for o in out)}


# ── the run sweep ─────────────────────────────────────────────────────────────
def scan_run(t_ign_s: int, direction: str, arm: dict, lookback_s: int = 600):
    """Evaluate every gate at 1Hz over [T-lookback, T]. Returns fires (first per gate)
    plus the per-gate MECHANISM of the miss."""
    want = "LONG" if direction == "UP" else "SHORT"
    elig = [g for g in GATES if SIDE[g] == want]
    from collections import Counter
    fires = {}
    reasons = {g: Counter() for g in elig}
    geom = Counter()
    pending_veto: dict = {}
    pending_exh: dict = {}
    for s in range(t_ign_s - lookback_s, t_ign_s + 1):
        bars = bars_at(s)
        if len(bars) < 6:
            for g in elig:
                reasons[g]["no-bars"] += 1
            continue
        f = compute_features(bars)
        _w = tape_window(s - 60, s - 1); nf = _w[0] - _w[1]
        px = last_tick_px(s)
        if px is None:
            for g in elig:
                reasons[g]["no-tape"] += 1
            continue
        fp = footprint_at(s)
        er = efficiency_ratio(bars)
        asia = 0 <= ((s % 86400) // 3600) < 7
        fired_now = set()
        for g in elig:
            if g in fires:
                continue
            if not gate_fires(g, f, nf, fp):
                continue
            fired_now.add(g)
            geom[g] += 1
            if er_blocks(g, er):
                reasons[g]["er-floor"] += 1; continue
            if arm["atr_floor"] and atr_blocks(g, f.atr):
                reasons[g][f"atr-floor({ATR_FLOOR[g]:.0f})"] += 1; continue
            if arm["counter_veto"] and BASE[g].veto_counter_regime and regime_mode(SIDE[g], bars) == "mid":
                reasons[g]["counter-regime-veto"] += 1; continue
            if arm["asia"] and asia:
                reasons[g]["asia-block"] += 1; continue
            if arm["vetoes"] and g in ("abs_veto_long", "abs_veto_short"):
                pending_veto.setdefault(g, s); continue
            if arm["vetoes"] and g == "exhaustion_short":
                pending_exh.setdefault(g, (s, px)); continue
            fires[g] = {"gate": g, "side": SIDE[g], "s": s, "atr": f.atr, "er": er,
                        "ext": f.ext_atr, "px": px}
        for g in list(pending_veto):
            s0 = pending_veto[g]
            if s - s0 < VETO_SECS:
                continue
            if g not in fired_now:
                del pending_veto[g]; reasons[g]["veto:thrust-gone"] += 1; continue
            b, sl, _t2, n, fpx, lpx = tape_window(s0, s - 1)
            absorbed = True
            if n >= 5:
                absorbed = exit_absorption(Position(SIDE[g], 0.0, 0.0, 0.0), tape_net=b - sl,
                                           window_price_delta=lpx - fpx,
                                           flow_min=VETO_FLOW_MIN) is not None
            del pending_veto[g]
            if absorbed:
                reasons[g]["55s-absorption-veto"] += 1
            else:
                fires[g] = {"gate": g, "side": SIDE[g], "s": s, "atr": f.atr, "er": er,
                            "ext": f.ext_atr, "px": px}
        for g in list(pending_exh):
            s0, sig_px = pending_exh[g]
            if s - s0 < EXH_CONFIRM_SECS:
                continue
            _b2, _s2, _t3, n, _f2, _l2 = tape_window(s0, s - 1)
            adverse = True
            if n >= 3:
                j0, j1 = bisect_left(TK_TS, s0 * 1000), bisect_left(TK_TS, s * 1000)
                seg = TK_PX[j0:j1]
                adverse = (float(seg.max()) - sig_px) > EXH_ADVERSE_PT if len(seg) else True
            del pending_exh[g]
            if adverse:
                reasons[g]["5s-confirm-adverse"] += 1
            else:
                fires[g] = {"gate": g, "side": SIDE[g], "s": s, "atr": f.atr, "er": er,
                            "ext": f.ext_atr, "px": px}
    return elig, fires, reasons, geom
