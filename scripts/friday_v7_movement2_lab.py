#!/usr/bin/env python3
"""MOVEMENT 2 — THE IDLE-GATE LAB (Friday V7).

Fires all six LIVE gates (deciders.py, exactly the live entry stack) mechanically at every
SAT-OUT run in the frozen census, in the 10 minutes before ignition, and reprices every fill
on the real tick/quote path. Three layers:

  L1 MECHANICAL — every gate ARMED (gate_switches ignored), full live entry stack:
                  ER floors, ATR floors, 55s abs-veto, 5s exhaustion confirm, counter-regime veto.
  L2 UNGATED    — same geometry, every floor / veto / confirm layer REMOVED.
  BLOCK CENSUS  — for every (run, gate, second) the FIRST failing predicate, so "why it misses"
                  is a measured mechanism, not a story.

Honest money: $2.00/pt MNQ, $1.50 per round trip per lot, far-touch entry AND exit,
native stop_atr_mult x ATR stop, live per-gate exit (data/exit_overrides.json scale-out slate),
120-min max hold, 21:00Z session flat.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections import defaultdict, deque
from dataclasses import dataclass

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import (  # noqa: E402
    ATR_FLOOR, ER_BAND, ER_CEIL, ER_FLOOR, Bar, Features, Position,
    compute_features, efficiency_ratio, exit_absorption, exit_chandelier,
    exit_chandelier_lock, gate_capitulation, gate_grind, gate_reversal_grab, gate_thrust,
)
from gazbot7.footprint import exhaustion_signal  # noqa: E402
from gazbot7.slot_strategy import scaleout_slots, tournament_slots  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
CENSUS = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
SYM = "MNQ"
VPP = 2.0          # MNQ $/point
FEE_RT = 1.5       # per round trip, per lot
PRE_S = 600        # the 10 minutes before ignition
MAX_HOLD_S = 120 * 60
WARM_S = 70 * 60   # 5s-bar warm-up so the 60-bar deque is full
VETO_SECS, VETO_MAX_SECS, VETO_FLOW_MIN = 55, 75, 50.0
EXH_SECS, EXH_MAX_SECS, EXH_ADVERSE_PT = 5, 20, 5.0
ER_TREND, NET_MIN, RWINDOW = 0.15, 30.0, 30

BASE = ["grind_long", "capitulation_long", "abs_veto_long",
        "rgv_short", "exhaustion_short", "abs_veto_short"]
SIDE_OF = {"grind_long": "LONG", "capitulation_long": "LONG", "abs_veto_long": "LONG",
           "rgv_short": "SHORT", "exhaustion_short": "SHORT", "abs_veto_short": "SHORT"}


# ── the frozen census ────────────────────────────────────────────────────────────────────
RE_ROW = re.compile(
    r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]\d+)\s+(\d+)\s+(sat out|caught|FOUGHT)\s+(\S+)")


def load_runs():
    import datetime as dt
    out = []
    for ln in open(CENSUS):
        m = RE_ROW.match(ln)
        if not m:
            continue
        tm, d, mv, ceil, us, gate = m.groups()
        t = dt.datetime.strptime("2026-" + tm, "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC)
        out.append({"tm": tm, "ts": int(t.timestamp()), "dir": d, "move": int(mv),
                    "ceil": int(ceil), "us": us, "gate": gate,
                    "hour": t.hour, "dow": t.strftime("%a")})
    return out


# ── the live slate, as configured ────────────────────────────────────────────────────────
def live_specs():
    """base gate -> (entry spec, [lot A spec, lot B spec]) from the ACTUAL live slate."""
    base = {s.tag: s for s in tournament_slots()}
    lots = defaultdict(list)
    for s in scaleout_slots():
        lots[s.tag[:-2]].append(s)
    return {g: (base[g], lots[g]) for g in BASE}


# ── data loads ───────────────────────────────────────────────────────────────────────────
def q(con, sql, args):
    return con.execute(sql, args).fetchall()


def load_window(con, t0, t1):
    """5s bars (warmed), ticks, level-1 book for [t0, t1] decisions."""
    bars5 = q(con, "SELECT bar_ts,open,high,low,close,volume FROM bars WHERE symbol=? AND "
                   "timeframe='5s' AND bar_ts>=? AND bar_ts<=? ORDER BY bar_ts",
              (SYM, t0 - WARM_S, t1))
    ticks = q(con, "SELECT ts_ms,price,size,aggressor FROM ticks WHERE symbol=? AND ts_ms>=? "
                   "AND ts_ms<=? ORDER BY ts_ms", (SYM, (t0 - 200) * 1000, t1 * 1000))
    book = q(con, "SELECT ts_ms,side,price,size FROM book WHERE symbol=? AND level=1 AND "
                  "ts_ms>=? AND ts_ms<=? ORDER BY ts_ms", (SYM, (t0 - 120) * 1000, t1 * 1000))
    return bars5, ticks, book


# ── per-second feature tape (computed ONCE per run, reused by every layer + every sweep) ──
@dataclass(slots=True)
class Snap:
    ms: int
    f: Features
    price: float
    er: float
    tape_net: float
    fp: dict
    mode_long: str
    mode_short: str


def regime_mode(side, closes):
    if len(closes) < 6:
        return "tight"
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))) or 1.0
    er = abs(closes[-1] - closes[0]) / path
    net = closes[-1] - closes[0]
    up = er >= ER_TREND and net >= NET_MIN
    down = er >= ER_TREND and net <= -NET_MIN
    if (side == "SHORT" and down) or (side == "LONG" and up):
        return "wide"
    if (side == "SHORT" and up) or (side == "LONG" and down):
        return "mid"
    return "tight"


class Folder:
    """MinuteBars, byte-faithful (agg.py) — 60 completed 1-min bars folded from 5s."""

    def __init__(self):
        self.b = deque(maxlen=60)
        self.cur = None
        self.last_bar_ms = 0

    def fold(self, ts, o, h, l, c, v):
        self.last_bar_ms = ts * 1000
        m = (ts // 60) * 60
        cur = self.cur
        if cur is None or m > cur["min"]:
            if cur is not None:
                self.b.append(Bar(cur["min"], cur["o"], cur["h"], cur["l"], cur["c"], cur["v"]))
            self.cur = {"min": m, "o": o, "h": h, "l": l, "c": c, "v": v}
        elif m == cur["min"]:
            cur["h"] = max(cur["h"], h); cur["l"] = min(cur["l"], l)
            cur["c"] = c; cur["v"] += v


def build_snaps(t0, t1, bars5, ticks, book):
    """One Snap per decision second, exactly what step()/decide() would have seen."""
    fold = Folder()
    bi = 0
    # tick cursors
    ti_hi = 0
    tix = ticks
    # book cursors
    bkb = bka = (0.0, 0.0)
    bk_i = 0
    snaps = []
    for now in range(t0, t1):
        now_ms = now * 1000
        while bi < len(bars5) and bars5[bi][0] + 5 <= now:      # bar completes 5s after its start
            r = bars5[bi]; fold.fold(r[0], r[1], r[2], r[3], r[4], r[5]); bi += 1
        while bk_i < len(book) and book[bk_i][0] <= now_ms:
            r = book[bk_i]
            if r[1] == "bid":
                bkb = (r[2], r[3])
            else:
                bka = (r[2], r[3])
            bk_i += 1
        while ti_hi < len(tix) and tix[ti_hi][0] <= now_ms:
            ti_hi += 1
        bars = list(fold.b)
        if len(bars) < 6 or not fold.last_bar_ms or (now_ms - fold.last_bar_ms) > 30_000:
            continue                                            # step() would return [] (stale)
        win = tix[:ti_hi]
        # tape (md.recent_tape, 60s)
        lo60 = now_ms - 60_000
        j = _lower(win, lo60)
        seg = win[j:]
        if not seg:
            continue                                            # no tape -> md publishes nothing
        net60 = sum((r[2] if r[3] == "buy" else (-r[2] if r[3] == "sell" else 0.0)) for r in seg)
        last = seg[-1][1]
        if (now_ms - seg[-1][0]) > 10_000:
            pass                                                # tape ts is now_ms in md, not tick ts
        # footprint (capitulation_tape 20/180 + exhaustion 20s + L1 book)
        s20 = win[_lower(win, now_ms - 20_000):]
        s180 = win[_lower(win, now_ms - 180_000):]
        half = win[_lower(win, now_ms - 10_000):]
        base_tot = sum(r[2] for r in s180[:len(s180) - len(s20)])
        sell = sum(r[2] for r in s20 if r[3] == "sell")
        buy = sum(r[2] for r in s20 if r[3] == "buy")
        hs = sum(r[2] for r in half if r[3] == "sell")
        hb = sum(r[2] for r in half if r[3] == "buy")
        dpx = (s20[-1][1] - s20[0][1]) if len(s20) >= 2 else 0.0
        windows = max(1.0, (180 - 20) / 20)
        net20 = sum((r[2] if r[3] == "buy" else (-r[2] if r[3] == "sell" else 0.0)) for r in s20)
        move20 = (s20[-1][1] - s20[0][1]) if len(s20) >= 2 else 0.0
        fp = {"cap_sell": sell, "cap_buy": buy, "cap_base": base_tot / windows,
              "cap_dpx": dpx, "cap_flip": hb > hs,
              "net_signed": net20, "price_move_pt": move20,
              "bid1_size": bkb[1] or 0.0, "ask1_size": bka[1] or 0.0,
              "bid1_price": bkb[0] or 0.0, "ask1_price": bka[0] or 0.0}
        f = compute_features(bars)
        er = efficiency_ratio(bars)
        cl = [b.close for b in bars[-RWINDOW:]]
        snaps.append(Snap(now_ms, f, last or f.price, er, net60, fp,
                          regime_mode("LONG", cl), regime_mode("SHORT", cl)))
    return snaps


def _lower(rows, ms):
    lo, hi = 0, len(rows)
    while lo < hi:
        mid = (lo + hi) // 2
        if rows[mid][0] < ms:
            lo = mid + 1
        else:
            hi = mid
    return lo


# ── gate evaluation: raw geometry, then the live filter stack, with a BLOCK reason ───────
def raw_fire(gate, spec, s: Snap):
    p = dict(spec.params)
    if spec.kind == "grind":
        e = gate_grind(s.f, tape_net=s.tape_net, **p)
    elif spec.kind == "reversal_grab":
        e = gate_reversal_grab(s.f, tape_net=s.tape_net, **p)
    elif spec.kind == "thrust":
        e = gate_thrust(s.f, **p)
    elif spec.kind == "capitulation":
        e = gate_capitulation(s.f, cap_sell=s.fp["cap_sell"], cap_buy=s.fp["cap_buy"],
                              cap_base=s.fp["cap_base"], cap_dpx=s.fp["cap_dpx"],
                              cap_flip=s.fp["cap_flip"], **p)
    elif spec.kind == "exhaustion":
        sig = exhaustion_signal(s.fp["net_signed"], s.fp["price_move_pt"], s.fp["bid1_size"],
                                s.fp["ask1_size"], s.fp["bid1_price"], s.fp["ask1_price"])
        return bool(sig and sig[0] == spec.side)
    else:
        return False
    return bool(e and e.side == spec.side)


def raw_fire_ungated(gate, spec, s: Snap):
    """Same geometry with every OPTIONAL floor stripped out of the gate's own params:
    ATR floors, amplitude floor, flow confirm, net30 depth floor, ext floors relaxed."""
    p = dict(spec.params)
    if spec.kind == "thrust":
        p["amp_floor"] = 0.0
    if spec.kind == "reversal_grab":
        p["atr_min"] = 0.0
        p["flow_min"] = None
        p["net30_floor"] = None
    return raw_fire(gate, spec, s)


def blocked_by(gate, spec, s: Snap):
    """Which live filter kills this second, in the live order. None = passes to the veto stage."""
    if ER_FLOOR.get(gate) is not None and s.er < ER_FLOOR[gate]:
        return "ER_FLOOR"
    if gate in ER_CEIL and s.er > ER_CEIL[gate]:
        return "ER_CEIL"
    if gate in ER_BAND and not (ER_BAND[gate][0] <= s.er <= ER_BAND[gate][1]):
        return "ER_BAND"
    if gate in ATR_FLOOR and s.f.atr < ATR_FLOOR[gate]:
        return "ATR_FLOOR"
    if spec.veto_counter_regime:
        mode = s.mode_long if spec.side == "LONG" else s.mode_short
        if mode == "mid":
            return "COUNTER_REGIME"
    return None



# ── WHY IT MISSES: the first failing predicate inside the gate's own geometry ────────────
def why_miss(gate, spec, s: Snap):
    """The binding constraint, in the gate's own evaluation order. None = the geometry passed."""
    p = spec.params
    f = s.f
    if spec.kind == "thrust":
        thr = p.get("thr", 1.5)
        net = f.net_atr_2 if p.get("fast") else f.net_atr_5
        if abs(net) < thr:
            return "THRUST<1.5ATR"
        if p.get("amp_floor") and f.atr_pct < p["amp_floor"]:
            return "AMP_FLOOR"
        if not f.vol_surge:
            return "NO_VOL_SURGE"
        if ("LONG" if net > 0 else "SHORT") != spec.side:
            return "WRONG_SIDE"
        return None
    if spec.kind == "reversal_grab":
        slope = f.vwap_slope_fast if p.get("fast_slope") else f.vwap_slope_atr
        if f.atr_pct > 0.09 or abs(slope) > 1.0:
            return "REGIME_STANDDOWN"
        if p.get("atr_min") and f.atr < p["atr_min"]:
            return "ATR_MIN"
        turn = f.net_atr_2 if p.get("fast_turn") else f.net_atr_5
        if spec.side == "SHORT":
            if f.ext_atr < p.get("ext_min", 2.5):
                return "NOT_EXTENDED"
            if turn > -p.get("turn_atr", 0.5):
                return "NO_TURN"
            if p.get("flow_min") is not None and s.tape_net > -p["flow_min"]:
                return "NO_FLOW_CONFIRM"
        else:
            if f.ext_atr > -p.get("ext_min", 2.5):
                return "NOT_EXTENDED"
            if turn < p.get("turn_atr", 0.5):
                return "NO_TURN"
        return None
    if spec.kind == "grind":
        slope = f.vwap_slope_fast if p.get("fast_slope") else f.vwap_slope_atr
        lo, hi = p.get("ext_lo", 0.3), p.get("ext_hi", 4.0)
        want = 1 if spec.side == "LONG" else -1
        if want * slope < p.get("slope_min", 0.5):
            return "NO_TREND_SLOPE"
        if not (lo <= want * f.ext_atr <= hi):
            return "EXT_BAND" if want * f.ext_atr < lo else "OVEREXTENDED"
        if want * s.tape_net < p.get("flow_min", 0.0):
            return "NO_FLOW"
        return None
    if spec.kind == "capitulation":
        tot = s.fp["cap_sell"] + s.fp["cap_buy"]
        if s.fp["cap_base"] <= 0 or tot <= 0:
            return "NO_TAPE"
        want_sell = spec.side == "LONG"
        vol = s.fp["cap_sell"] if want_sell else s.fp["cap_buy"]
        if (s.fp["cap_dpx"] >= 0) if want_sell else (s.fp["cap_dpx"] <= 0):
            return "NO_FLUSH_MOVE"
        if vol / s.fp["cap_base"] < p.get("climax_min", 3.0):
            return "NO_VOLUME_CLIMAX"
        if vol / tot < p.get("dom_min", 0.7):
            return "NOT_ONE_SIDED"
        if p.get("require_flip") and not (s.fp["cap_flip"] if want_sell else not s.fp["cap_flip"]):
            return "NO_FLIP"
        return None
    if spec.kind == "exhaustion":
        if abs(s.fp["net_signed"]) < 400.0:
            return "FLOW<400"
        if abs(s.fp["price_move_pt"]) > 2.0:
            return "PRICE_MOVED>2PT"
        if s.fp["bid1_size"] <= 0 or s.fp["ask1_size"] <= 0:
            return "NO_BOOK"
        if s.fp["net_signed"] > 0:
            if s.fp["ask1_size"] < 1.5 * s.fp["bid1_size"]:
                return "NO_WALL"
            return None if spec.side == "SHORT" else "WRONG_SIDE"
        if s.fp["bid1_size"] < 1.5 * s.fp["ask1_size"]:
            return "NO_WALL"
        return None if spec.side == "LONG" else "WRONG_SIDE"
    return "UNKNOWN"


# ── tick-honest exit ─────────────────────────────────────────────────────────────────────
def load_quotes(con, lo_ms, hi_ms):
    return q(con, "SELECT ts_ms,bid,ask FROM quotes WHERE symbol=? AND ts_ms>=? AND ts_ms<=? "
                  "AND bid>0 AND ask>0 ORDER BY ts_ms", (SYM, lo_ms, hi_ms))


def reprice(lot, side, entry_atr, quotes, i0, flat_ms):
    """Replay ONE lot on the real quote path. Far-touch in and out. Returns dict or None."""
    if i0 >= len(quotes):
        return None
    qe = quotes[i0]
    entry = qe[2] if side == "LONG" else qe[1]
    if entry <= 0 or entry_atr <= 0:
        return None
    sm = float(lot.stop_atr_mult or 1.0)
    stop = entry - sm * entry_atr if side == "LONG" else entry + sm * entry_atr
    lo_clip = bool(lot.atr_split and entry_atr < lot.atr_split)
    peak = 0.0
    cap_ms = qe[0] + MAX_HOLD_S * 1000
    for k in range(i0 + 1, len(quotes)):
        ts, bid, ask = quotes[k]
        mid = (bid + ask) / 2.0
        fav = (mid - entry) if side == "LONG" else (entry - mid)
        peak = max(peak, fav)
        if (mid <= stop) if side == "LONG" else (mid >= stop):
            px = bid if side == "LONG" else ask
            return _mk(side, entry, px, ts, "STOP", entry_atr, peak, lot)
        reason = None
        if lo_clip:                                   # quiet-tape clip pre-empts the whole stack
            if lot.lo_target_usd and fav * VPP >= lot.lo_target_usd:
                reason = "TARGET"
            elif lot.lo_target_r:
                tgt = lot.lo_target_r * entry_atr
                if lot.lo_floor_usd:
                    tgt = max(tgt, lot.lo_floor_usd / VPP)
                if fav >= tgt:
                    reason = "TARGET"
        elif lot.exit == "chandelier_lock":
            reason = exit_chandelier_lock(Position(side, entry, entry_atr, peak), mid,
                                          start_k=lot.chandelier_start_k, lock_r=lot.lock_r,
                                          lock_k=lot.lock_k)
        elif lot.exit == "chandelier":
            if exit_chandelier(Position(side, entry, entry_atr, peak), mid,
                               start_k=lot.chandelier_start_k, min_k=lot.chandelier_min_k,
                               tighten=lot.chandelier_tighten):
                reason = "CHANDELIER"
        else:                                          # scalp: managed TARGET only
            r = sm * entry_atr
            tgt = entry + lot.target_r * r if side == "LONG" else entry - lot.target_r * r
            if (mid >= tgt) if side == "LONG" else (mid <= tgt):
                reason = "TARGET"
        if reason:
            px = bid if side == "LONG" else ask
            return _mk(side, entry, px, ts, reason, entry_atr, peak, lot)
        if ts >= cap_ms:
            px = bid if side == "LONG" else ask
            return _mk(side, entry, px, ts, "TIME_CAP", entry_atr, peak, lot)
        if ts >= flat_ms:
            px = bid if side == "LONG" else ask
            return _mk(side, entry, px, ts, "SESSION_FLAT", entry_atr, peak, lot)
    ts, bid, ask = quotes[-1]
    px = bid if side == "LONG" else ask
    return _mk(side, entry, px, ts, "TAPE_END", entry_atr, peak, lot)


def _mk(side, entry, px, ts, reason, atr, peak, lot):
    gross = (px - entry) * VPP if side == "LONG" else (entry - px) * VPP
    return {"entry": entry, "exit": px, "exit_ms": ts, "reason": reason, "atr": atr,
            "peak_pt": peak, "net": gross - FEE_RT, "lot": lot.tag}


def session_flat_ms(ms):
    """The 21:00 UTC session flat that BOUNDS this entry. CME reopens at 22:00Z, so a position
    opened after 21:00Z belongs to the NEXT day's session and is flat at the next 21:00Z — the
    same-day rule would put the flatten before the entry and close every trade at 0 seconds."""
    d = ms // 86_400_000
    sod = ms - d * 86_400_000
    if sod >= 21 * 3_600_000:
        d += 1
    return d * 86_400_000 + 21 * 3_600_000


# ── the replay ───────────────────────────────────────────────────────────────────────────
def replay_run(con, run, specs, layer, quote_cache):
    """One sat-out run, one layer. Returns list of trade dicts + a block census."""
    t1 = run["ts"]
    t0 = t1 - PRE_S
    bars5, ticks, book = load_window(con, t0, t1)
    snaps = build_snaps(t0, t1, bars5, ticks, book)
    blocks = defaultdict(lambda: defaultdict(int))
    trades = []
    if not snaps:
        for g in BASE:
            blocks[g]["NO_TAPE"] += PRE_S
        return trades, blocks, 0, None
    busy_until = {g: 0 for g in BASE}
    pend_v = {}
    pend_e = {}
    ungated = (layer == "ungated")

    def enter(g, spec, lots, s):
        key = (run["ts"],)
        if key not in quote_cache:
            quote_cache[key] = load_quotes(con, t0 * 1000, (t1 + MAX_HOLD_S + 600) * 1000)
        quotes = quote_cache[key]
        i0 = _lower(quotes, s.ms)
        flat = session_flat_ms(s.ms)
        made = []
        for lot in lots:
            t = reprice(lot, spec.side, s.f.atr, quotes, i0, flat)
            if t is None:
                continue
            t.update(gate=g, run=run["tm"], run_dir=run["dir"], run_move=run["move"],
                     side=spec.side, entry_ms=s.ms, er=s.er, atr=s.f.atr,
                     lead_s=(t1 * 1000 - s.ms) / 1000.0, layer=layer,
                     in_dir=(spec.side == ("LONG" if run["dir"] == "UP" else "SHORT")),
                     asia=(0 <= (s.ms // 1000 % 86400) // 3600 < 7))
            made.append(t)
        if not made:
            return False
        trades.extend(made)
        blocks[g]["ENTERED"] += 1
        busy_until[g] = max(t["exit_ms"] for t in made)
        return True

    for s in snaps:
        for g in BASE:
            spec, lots = specs[g]
            # ── the exhaustion 5s confirm resolves on the CLOCK, not on the signal still firing
            # (tournament.py buffers the intent and checks max adverse tick over the window) ──
            if g in pend_e:
                armed_ms, sig_px = pend_e[g]
                age = (s.ms - armed_ms) / 1000.0
                if age >= EXH_SECS:
                    rows = [r for r in ticks if armed_ms <= r[0] < s.ms]
                    adverse = True
                    if len(rows) >= 3:
                        adverse = (max(r[1] for r in rows) - sig_px) > EXH_ADVERSE_PT
                    del pend_e[g]
                    if adverse or age > EXH_MAX_SECS:
                        blocks[g]["EXH_ADVERSE"] += 1
                    elif s.ms < busy_until[g]:
                        blocks[g]["SLOT_BUSY"] += 1
                    else:
                        enter(g, spec, lots, s)
                    continue
                blocks[g]["EXH_WAIT"] += 1
                continue
            fires = (raw_fire_ungated(g, spec, s) if ungated else raw_fire(g, spec, s))
            if not fires:
                blocks[g]["NO_SIGNAL"] += 1
                blocks[g]["why:" + (why_miss(g, spec, s) or "?")] += 1
                pend_v.pop(g, None)
                continue
            blocks[g]["_raw"] += 1
            b = None if ungated else blocked_by(g, spec, s)
            if b:
                blocks[g][b] += 1
                continue
            if s.ms < busy_until[g]:
                blocks[g]["SLOT_BUSY"] += 1
                continue
            if not ungated and g in ("abs_veto_long", "abs_veto_short"):
                # the 55s veto DOES require the thrust to still be firing (live: slot in fired_now)
                if g not in pend_v:
                    pend_v[g] = s.ms
                age = (s.ms - pend_v[g]) / 1000.0
                if age < VETO_SECS:
                    blocks[g]["VETO_WAIT"] += 1
                    continue
                if age > VETO_MAX_SECS:
                    pend_v.pop(g)
                    blocks[g]["VETO_STALE"] += 1
                    continue
                lo = pend_v.pop(g)
                rows = [r for r in ticks if lo <= r[0] < s.ms]
                absorbed = True
                if len(rows) >= 5:
                    flow = sum((r[2] if r[3] == "buy" else -r[2]) for r in rows)
                    absorbed = exit_absorption(Position(spec.side, 0.0, 0.0, 0.0), tape_net=flow,
                                               window_price_delta=rows[-1][1] - rows[0][1],
                                               flow_min=VETO_FLOW_MIN) is not None
                if absorbed:
                    blocks[g]["ABS_VETO"] += 1
                    continue
            if not ungated and g == "exhaustion_short":
                pend_e[g] = (s.ms, s.price)      # arm once; the clock resolves it next loop
                blocks[g]["EXH_WAIT"] += 1
                continue
            enter(g, spec, lots, s)
    s0 = snaps[0]
    reg = {"atr": s0.f.atr, "er": s0.er, "ext": s0.f.ext_atr, "net30": s0.f.net30_pt}
    return trades, blocks, len(snaps), reg


def main():
    runs = load_runs()
    lim = int(os.environ.get("M2_LIMIT", "0"))
    off = int(os.environ.get("M2_OFFSET", "0"))
    pop = os.environ.get("M2_POP", "sat")
    keep = {"sat": ("sat out",), "caught": ("caught", "FOUGHT"), "all": ("sat out", "caught", "FOUGHT")}[pop]
    sat = [r for r in runs if r["us"] in keep][off:]
    if lim:
        sat = sat[:lim]
    specs = live_specs()
    con = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    con.execute("PRAGMA cache_size=-200000")
    out = {"runs": [], "trades": [], "blocks": {}}
    agg_blocks = {lay: defaultdict(lambda: defaultdict(int)) for lay in ("mech", "ungated")}
    qc = {}
    for n, r in enumerate(sat, 1):
        qc.clear()
        row = dict(r)
        for lay in ("mech", "ungated"):
            tr, bl, ns, reg = replay_run(con, r, specs, lay, qc)
            out["trades"] += tr
            for g, d in bl.items():
                for k, v in d.items():
                    agg_blocks[lay][g][k] += v
            row[f"n_snaps_{lay}"] = ns
            row[f"fires_{lay}"] = len({(t["gate"], t["entry_ms"]) for t in tr})
            if reg:
                row.update(reg)
        out["runs"].append(row)
        print(f"[{n}/{len(sat)}] {r['tm']} {r['dir']}{r['move']:+d} "
              f"snaps={row.get('n_snaps_mech')} mech={row['fires_mech']} ung={row['fires_ungated']}",
              flush=True)
    out["blocks"] = {lay: {g: dict(d) for g, d in v.items()} for lay, v in agg_blocks.items()}
    with open(os.environ.get("M2_OUT", "/home/alphabot/gazbot7/reports/friday_v7/sections/m2_lab.json"), "w") as f:
        json.dump(out, f)
    print("wrote m2_lab.json ·", len(out["trades"]), "lot-trades")


if __name__ == "__main__":
    main()
