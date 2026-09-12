#!/usr/bin/env python3
"""MOVEMENT 2 — THE IDLE-GATE LAB (Friday V7 report).

Question: the desk sat out 65 of the week's 70 big runs. Could its OWN six live gates have
caught them? Fire every gate MECHANICALLY (exact live config from deciders.py + the live
`scaleout` slate + data/exit_overrides.json) and UNGATED (every suppressor removed) at each
sat-out run, in the 10 minutes BEFORE ignition, and price the result tick-honest.

Data: capture.db ONLY where strictly inside its 5-trading-day window (verified at startup —
the census window 08-17..08-21 is entirely inside it, so no lake fallback is needed).
Fee $1.50/round-trip/lot · MNQ $2.00/point.

  PYTHONPATH=src .venv/bin/python scripts/movement2_idle_gates.py
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import re
import sqlite3
import sys
from collections import deque

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import (  # noqa: E402
    ATR_FLOOR, Bar, EXH_ADVERSE_PT, EXH_CONFIRM_MAX_SECS, EXH_CONFIRM_SECS, Entry, Position,
    VETO_FLOW_MIN, VETO_MAX_SECS, VETO_SECS, compute_features, efficiency_ratio,
    exit_absorption, exit_chandelier, exit_chandelier_lock, exit_fixed, exit_scalp,
    gate_capitulation, gate_grind, gate_reversal_grab, gate_thrust,
)
from gazbot7.footprint import exhaustion_signal  # noqa: E402
from gazbot7.direction_router import ER_TREND, NET_MIN, WINDOW as RWINDOW  # noqa: E402
from gazbot7.slot_strategy import scaleout_slots  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
SYM = "MNQ"
VPP = 2.0
FEE = 1.5          # per lot, per ROUND TRIP
PRE_S = 600        # the 10 minutes before ignition
POST_S = 300       # sensitivity arm only: the first 5 min OF the run
MAX_HOLD_S = 7200  # cfg.max_hold_minutes = 120
YEAR = 2026

CENSUS_TXT = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
OUT_JSON = "/home/alphabot/gazbot7/reports/friday_v7/sections/movement2_idle_gates.json"

BASE_GATES = ["grind_long", "capitulation_long", "abs_veto_long",
              "rgv_short", "exhaustion_short", "abs_veto_short"]


# ── the frozen census ────────────────────────────────────────────────────────
def load_runs():
    rows = []
    pat = re.compile(r"^(\d\d)-(\d\d) (\d\d):(\d\d)\s+(UP|DN)\s+([+-]\d+)\s+(\d+)\s+(sat out|caught|FOUGHT)")
    for ln in open(CENSUS_TXT):
        m = pat.match(ln)
        if not m:
            continue
        mo, da, hh, mi, d, mv, ceil, us = m.groups()
        ts = int(dt.datetime(YEAR, int(mo), int(da), int(hh), int(mi), tzinfo=dt.UTC).timestamp())
        rows.append({"t": ts, "label": f"{mo}-{da} {hh}:{mi}", "dir": d, "move": int(mv),
                     "ceil": int(ceil), "us": us, "cluster": ln.split()[-1]})
    return rows


# ── tape loaders ─────────────────────────────────────────────────────────────
class Tape:
    """All the per-second inputs the live decision cycle reads, precomputed for one window."""

    def __init__(self, con, t_lo: int, t_hi: int):
        # 5s bars — warm 60 completed 1-min bars, so reach back ~75 min
        rows = con.execute(
            "SELECT bar_ts,open,high,low,close,volume FROM bars WHERE symbol=? AND timeframe='5s' "
            "AND bar_ts>=? AND bar_ts<=? ORDER BY bar_ts", (SYM, t_lo - 5400, t_hi)).fetchall()
        self.mins: list[Bar] = []     # completed 1-min bars, in order
        self.avail: list[int] = []    # epoch-s at which each became visible to the deque
        self.last_bar_ts = []         # for the freshness check
        cur = None
        for ts, o, h, l, c, v in rows:
            m = (ts // 60) * 60
            if cur is None or m > cur[0]:
                if cur is not None:
                    self.mins.append(Bar(cur[0], cur[1], cur[2], cur[3], cur[4], cur[5]))
                    self.avail.append(ts)
                cur = [m, o, h, l, c, v]
            elif m == cur[0]:
                cur[2] = max(cur[2], h); cur[3] = min(cur[3], l); cur[4] = c; cur[5] += v
        self.bar_ts = [r[0] for r in rows]

        # ticks
        tr = con.execute(
            "SELECT ts_ms,price,size,aggressor FROM ticks WHERE symbol=? AND ts_ms>=? AND ts_ms<=? "
            "ORDER BY ts_ms", (SYM, (t_lo - 300) * 1000, t_hi * 1000)).fetchall()
        self.tk_ms = [r[0] for r in tr]
        self.tk_px = [r[1] for r in tr]
        self.tk_sz = [r[2] for r in tr]
        self.tk_ag = [r[3] for r in tr]
        n = len(tr)
        self.c_net = [0.0] * (n + 1)   # cum signed size (buy +, sell -)
        self.c_all = [0.0] * (n + 1)   # cum total size
        self.c_buy = [0.0] * (n + 1)
        self.c_sell = [0.0] * (n + 1)
        for i in range(n):
            sz, ag = self.tk_sz[i], self.tk_ag[i]
            b = sz if ag == "buy" else 0.0
            s = sz if ag == "sell" else 0.0
            self.c_buy[i + 1] = self.c_buy[i] + b
            self.c_sell[i + 1] = self.c_sell[i] + s
            self.c_net[i + 1] = self.c_net[i] + b - s
            self.c_all[i + 1] = self.c_all[i] + sz

        # level-1 book (the exhaustion wall test)
        bk = con.execute(
            "SELECT ts_ms,side,price,size FROM book WHERE symbol=? AND level=1 AND ts_ms>=? AND ts_ms<=? "
            "ORDER BY ts_ms", (SYM, (t_lo - 120) * 1000, t_hi * 1000)).fetchall()
        self.bk_ms = [r[0] for r in bk]
        self.bk = bk

    # -- helpers -------------------------------------------------------------
    def idx(self, t_ms):
        return bisect.bisect_right(self.tk_ms, t_ms)

    def last_px(self, t_ms):
        i = self.idx(t_ms)
        return self.tk_px[i - 1] if i > 0 else None

    def bars_at(self, t: int):
        """The completed 1-min deque as the live MinuteBars would hold it at epoch-second t."""
        k = bisect.bisect_right(self.avail, t)
        return self.mins[max(0, k - 60):k]

    def bar_fresh(self, t: int) -> bool:
        j = bisect.bisect_right(self.bar_ts, t)
        return j > 0 and (t - self.bar_ts[j - 1]) <= 30

    def net_flow(self, t: int, win_s: int = 60):
        """md.recent_tape: (net, price delta over window, last)."""
        hi = self.idx(t * 1000)
        lo = self.idx((t - win_s) * 1000 - 1)
        if hi <= lo:
            return 0.0, 0.0, None
        return (self.c_net[hi] - self.c_net[lo],
                self.tk_px[hi - 1] - self.tk_px[lo], self.tk_px[hi - 1])

    def cap_tape(self, t: int, short_s=20, base_s=180):
        """capture.capitulation_tape, precomputed."""
        now = t * 1000
        i_now = self.idx(now)
        i_short = self.idx(now - short_s * 1000 - 1)
        i_half = self.idx(now - (short_s * 1000) // 2 - 1)
        i_base = self.idx(now - base_s * 1000 - 1)
        if i_now <= i_base:
            return {"sell": 0.0, "buy": 0.0, "base": 0.0, "dpx": 0.0, "flip": False}
        sell = self.c_sell[i_now] - self.c_sell[i_short]
        buy = self.c_buy[i_now] - self.c_buy[i_short]
        base_tot = self.c_all[i_short] - self.c_all[i_base]
        windows = max(1.0, (base_s - short_s) / short_s)
        dpx = (self.tk_px[i_now - 1] - self.tk_px[i_short]) if i_now > i_short else 0.0
        h_sell = self.c_sell[i_now] - self.c_sell[i_half]
        h_buy = self.c_buy[i_now] - self.c_buy[i_half]
        return {"sell": sell, "buy": buy, "base": base_tot / windows, "dpx": dpx,
                "flip": h_buy > h_sell}

    def book_l1(self, t: int):
        """Most recent level-1 (bid_px, bid_sz, ask_px, ask_sz) at or before t."""
        j = bisect.bisect_right(self.bk_ms, t * 1000)
        bp = bs = ap = asz = None
        for k in range(j - 1, max(-1, j - 400), -1):
            _, side, px, sz = self.bk[k]
            if side == "bid" and bp is None:
                bp, bs = px, sz
            elif side == "ask" and ap is None:
                ap, asz = px, sz
            if bp is not None and ap is not None:
                break
        return bp, bs, ap, asz

    def footprint(self, t: int):
        c = self.cap_tape(t)
        hi = self.idx(t * 1000)
        lo = self.idx((t - 20) * 1000 - 1)
        net = self.c_net[hi] - self.c_net[lo] if hi > lo else 0.0
        move = (self.tk_px[hi - 1] - self.tk_px[lo]) if hi - lo >= 2 else 0.0
        bp, bs, ap, asz = self.book_l1(t)
        return {"cap_sell": c["sell"], "cap_buy": c["buy"], "cap_base": c["base"],
                "cap_dpx": c["dpx"], "cap_flip": c["flip"], "net_signed": net,
                "price_move_pt": move, "bid1_size": bs or 0.0, "ask1_size": asz or 0.0,
                "bid1_price": bp or 0.0, "ask1_price": ap or 0.0}


# ── the live entry gates, exactly as slot_strategy._gate_fires calls them ────
def gate_fires(spec, f, tape_net, fp) -> bool:
    if spec.kind == "grind":
        e = gate_grind(f, tape_net=tape_net, **spec.params)
    elif spec.kind == "reversal_grab":
        e = gate_reversal_grab(f, tape_net=tape_net, **spec.params)
    elif spec.kind == "thrust":
        e = gate_thrust(f, **spec.params)
    elif spec.kind == "capitulation":
        e = gate_capitulation(f, cap_sell=fp["cap_sell"], cap_buy=fp["cap_buy"],
                              cap_base=fp["cap_base"], cap_dpx=fp["cap_dpx"],
                              cap_flip=fp["cap_flip"], **spec.params)
    elif spec.kind == "exhaustion":
        sig = exhaustion_signal(fp["net_signed"], fp["price_move_pt"], fp["bid1_size"],
                                fp["ask1_size"], fp["bid1_price"], fp["ask1_price"])
        return sig is not None and sig[0] == spec.side
    else:
        return False
    return e is not None and e.side == spec.side


def regime_mode(side: str, bars) -> str:
    closes = [b.close for b in bars[-RWINDOW:]]
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


# ── tick-honest exit for one lot ─────────────────────────────────────────────
def run_exit(spec, tape: Tape, t_entry: int, entry_px: float, entry_atr: float, side: str):
    """Walk the real tick path from entry and return (exit_ms, exit_px, reason)."""
    i = tape.idx(t_entry * 1000)
    peak = 0.0
    vpp = VPP
    lo_mode = bool(spec.atr_split and entry_atr < spec.atr_split)
    stop_dist = entry_atr * (spec.stop_atr_mult or 1.0)
    end_ms = (t_entry + MAX_HOLD_S) * 1000
    n = len(tape.tk_ms)
    while i < n and tape.tk_ms[i] <= end_ms:
        px = tape.tk_px[i]
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak:
            peak = fav
        # the native 1-ATR (x stop_atr_mult) server-side STP owns the loss side for every exit style
        if stop_dist > 0 and -fav >= stop_dist:
            return tape.tk_ms[i], entry_px - stop_dist if side == "LONG" else entry_px + stop_dist, "STOP"
        pos = Position(side, entry_px, entry_atr, peak)
        if lo_mode:                                   # quiet-tape clip (frozen at entry)
            if spec.lo_target_usd and fav * vpp >= spec.lo_target_usd:
                return tape.tk_ms[i], px, "TARGET_LO"
            if spec.lo_target_r and entry_atr > 0:
                tgt = spec.lo_target_r * entry_atr
                if spec.lo_floor_usd:
                    tgt = max(tgt, spec.lo_floor_usd / vpp)
                if fav >= tgt:
                    return tape.tk_ms[i], px, "TARGET_LO"
            i += 1
            continue
        if spec.exit == "chandelier":
            if exit_chandelier(pos, px, start_k=spec.chandelier_start_k, min_k=spec.chandelier_min_k,
                               tighten=spec.chandelier_tighten):
                return tape.tk_ms[i], px, "CHANDELIER"
        elif spec.exit == "chandelier_lock":
            if exit_chandelier_lock(pos, px, start_k=spec.chandelier_start_k,
                                    lock_r=spec.lock_r, lock_k=spec.lock_k):
                return tape.tk_ms[i], px, "CHANDELIER"
        elif spec.exit == "fixed":
            r = exit_fixed(pos, px, stop_pt=spec.fixed_stop_pt, target_pt=spec.fixed_target_pt)
            if r:
                return tape.tk_ms[i], px, r
        else:
            if exit_scalp(pos, px, target_r=spec.target_r, stop_atr_mult=spec.stop_atr_mult) == "TARGET":
                return tape.tk_ms[i], px, "TARGET"
        i += 1
    # 2h cap (cfg.max_hold_minutes) — mark at the last tick we have
    j = min(i, n - 1)
    return tape.tk_ms[j], tape.tk_px[j], "MAX_HOLD"


def lot_pnl(side, entry_px, exit_px, qty=1):
    pts = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
    return pts * VPP * qty - FEE, pts


# ── the simulation over one run window ───────────────────────────────────────
def simulate(tape: Tape, specs_by_base, t0: int, t1: int, *, ungated: bool):
    """Step the live decision cycle each second over [t0, t1] and return fills per base gate."""
    fills = {g: [] for g in specs_by_base}
    open_until = {g: 0 for g in specs_by_base}          # base gate busy until (slot single-position)
    pending_veto = {}                                    # base -> armed_s (abs_veto 55s)
    pending_exh = {}                                     # base -> (armed_s, px)
    blocked = {g: {} for g in specs_by_base}             # why a raw fire never became a trade
    raw_fires = {g: 0 for g in specs_by_base}

    def note(g, why):
        blocked[g][why] = blocked[g].get(why, 0) + 1

    for t in range(t0, t1 + 1):
        bars = tape.bars_at(t)
        if len(bars) < 6 or not tape.bar_fresh(t):
            continue
        f = compute_features(bars)
        net, dpx, last = tape.net_flow(t)
        if last is None:
            continue
        price = last
        fp = tape.footprint(t)
        er = efficiency_ratio(bars)
        for base, (sa, sb) in specs_by_base.items():
            if t < open_until[base]:
                continue
            # ---- the two delayed confirms, resolved first ----------------------
            if base in pending_veto:
                armed, apx = pending_veto[base]
                if t - armed >= VETO_SECS:
                    if t - armed > VETO_MAX_SECS:
                        pending_veto.pop(base); note(base, "veto window lapsed")
                    else:
                        still = gate_fires(sa, f, net, fp)
                        pos = Position(sa.side, apx, f.atr, 0.0)
                        absorbed = exit_absorption(pos, tape_net=net, window_price_delta=dpx,
                                                   flow_min=VETO_FLOW_MIN)
                        pending_veto.pop(base)
                        if not still:
                            note(base, "55s veto: thrust gone"); continue
                        if absorbed:
                            note(base, "55s veto: absorbed"); continue
                        fills[base].append(open_lots(tape, sa, sb, t, price, f, base))
                        open_until[base] = fills[base][-1]["until"]
                continue
            if base in pending_exh:
                armed, apx = pending_exh[base]
                if t - armed >= EXH_CONFIRM_SECS:
                    pending_exh.pop(base)
                    if t - armed > EXH_CONFIRM_MAX_SECS:
                        note(base, "exh confirm lapsed"); continue
                    adverse = (price - apx) if sa.side == "SHORT" else (apx - price)
                    if adverse > EXH_ADVERSE_PT:
                        note(base, "5s confirm: went adverse"); continue
                    fills[base].append(open_lots(tape, sa, sb, t, price, f, base))
                    open_until[base] = fills[base][-1]["until"]
                continue
            # ---- the raw gate ---------------------------------------------------
            if not gate_fires(sa, f, net, fp):
                continue
            raw_fires[base] += 1
            if not ungated:
                if base in ATR_FLOOR and f.atr < ATR_FLOOR[base]:
                    note(base, f"ATR floor {ATR_FLOOR[base]:.0f}pt"); continue
                if sa.veto_counter_regime and regime_mode(sa.side, bars) == "mid":
                    note(base, "counter-regime veto"); continue
                if base in ("abs_veto_long", "abs_veto_short"):
                    pending_veto[base] = (t, price); continue
                if base == "exhaustion_short":
                    pending_exh[base] = (t, price); continue
            fills[base].append(open_lots(tape, sa, sb, t, price, f, base))
            open_until[base] = fills[base][-1]["until"]
    return fills, blocked, raw_fires


def open_lots(tape, sa, sb, t, price, f, base):
    """Open the live 2-lot scale-out (Lot A + Lot B) and price both tick-honest."""
    out = {"t": t, "side": sa.side, "entry": price, "atr": f.atr, "lots": []}
    until = t
    for spec in (sa, sb):
        ems, epx, why = run_exit(spec, tape, t, price, f.atr, spec.side)
        usd, pts = lot_pnl(spec.side, price, epx)
        out["lots"].append({"tag": spec.tag, "exit_ms": ems, "exit": epx, "why": why,
                            "usd": round(usd, 2), "pts": round(pts, 2)})
        until = max(until, ems // 1000)
    out["usd"] = round(sum(l["usd"] for l in out["lots"]), 2)
    out["until"] = until
    return out


def main():
    con = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    lo, hi = con.execute("SELECT MIN(ts_ms),MAX(ts_ms) FROM ticks WHERE symbol=?", (SYM,)).fetchone()
    runs = load_runs()
    sat = [r for r in runs if r["us"] == "sat out"]
    need_lo = min(r["t"] for r in sat) - PRE_S
    need_hi = max(r["t"] for r in sat) + POST_S
    print(f"capture.db ticks {dt.datetime.fromtimestamp(lo/1000, dt.UTC)} .. "
          f"{dt.datetime.fromtimestamp(hi/1000, dt.UTC)}")
    print(f"census needs    {dt.datetime.fromtimestamp(need_lo, dt.UTC)} .. "
          f"{dt.datetime.fromtimestamp(need_hi, dt.UTC)}")
    assert lo / 1000 <= need_lo and hi / 1000 >= need_hi, "OUTSIDE capture.db window — use the lake"
    print(f"IN WINDOW ✓  {len(sat)} sat-out runs of {len(runs)}\n")

    specs = {s.tag: s for s in scaleout_slots()}
    by_base = {g: (specs[f"{g}_A"], specs[f"{g}_B"]) for g in BASE_GATES}
    for g, (a, b) in by_base.items():
        print(f"  {g:<20} A: {a.exit:<16} r={a.target_r} stop_k={a.stop_atr_mult} split={a.atr_split}"
              f"   B: {b.exit:<16} r={b.target_r} stop_k={b.stop_atr_mult}")
    print()

    results = {"runs": [], "meta": {"pre_s": PRE_S, "post_s": POST_S, "fee": FEE, "vpp": VPP,
                                    "n_sat": len(sat)}}
    for k, r in enumerate(sat, 1):
        t = r["t"]
        tape = Tape(con, t - PRE_S, t + POST_S + MAX_HOLD_S)
        rec = {**r, "arms": {}}
        for arm, (a0, a1) in (("pre", (t - PRE_S, t)), ("post", (t + 1, t + POST_S))):
            for mode in ("live", "ungated"):
                fills, blocked, raw = simulate(tape, by_base, a0, a1, ungated=(mode == "ungated"))
                rec["arms"][f"{arm}_{mode}"] = {
                    g: {"fills": fills[g], "blocked": blocked[g], "raw": raw[g]} for g in BASE_GATES}
        results["runs"].append(rec)
        nf = sum(len(rec["arms"]["pre_live"][g]["fills"]) for g in BASE_GATES)
        nu = sum(len(rec["arms"]["pre_ungated"][g]["fills"]) for g in BASE_GATES)
        print(f"[{k:>2}/{len(sat)}] {r['label']} {r['dir']} {r['move']:+4}pt  "
              f"pre-live fires={nf}  pre-ungated={nu}")
    with open(OUT_JSON, "w") as fh:
        json.dump(results, fh)
    print(f"\n→ {OUT_JSON}")


if __name__ == "__main__":
    main()
