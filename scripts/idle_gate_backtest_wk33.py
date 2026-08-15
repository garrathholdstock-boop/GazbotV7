#!/usr/bin/env python3
"""MOVEMENT 2 (week ending 2026-08-14) — THE IDLE-GATE LAB.

Fire ALL SIX live tournament gates (grind_long, capitulation_long, abs_veto_long,
rgv_short, exhaustion_short, abs_veto_short) MECHANICALLY (live params + the live
favourable-condition filters and vetoes) AND UNGATED (the raw gate shape, floors and
vetoes stripped) at the FROZEN sat-out runs of the Movement-1 census, IN-DIRECTION,
anywhere in the 10 minutes BEFORE ignition, with TICK-HONEST exits repriced on this
week's capture.db trade ticks under each gate's DEPLOYED dual-lot exit
(data/exit_overrides.json — Lot A + Lot B, 1 lot each, $1.50/RT/lot, $2/pt).

★ WHAT CHANGED SINCE wk32 (the config this re-run is actually testing):
  · grind_long ATR_FLOOR 10 -> 22   (deciders.ATR_FLOOR, operator 2026-08-08)
  · grind_long ext_hi 2.0 DELETED   (slot_strategy, falls back to gate_grind's 4.0)
  Last week's Movement 2 said grind_long could never fire because ext_hi 2.0 blocked it.
  Both knobs moved, so this run ALSO re-fires grind_long under the OLD cell for a
  like-for-like delta (see GRIND_VARIANTS).
  · exhaustion_short's live veto_counter_regime (skip a fade fired INTO a local trend)
  is now applied in mech mode — wk32 omitted it.

Also: a WHY-IT-MISSES mechanism census (which clause of each gate binds, and how deep
the gate ever got), a blind in-direction control (the money WAS there), regime +
time-of-day segmentation per the backtest-discipline rule, and per-regime R sweeps.

  PYTHONPATH=src .venv/bin/python scripts/idle_gate_backtest_wk33.py
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import re
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import (  # noqa: E402
    Bar, Position, compute_features, efficiency_ratio, exit_absorption,
    exit_chandelier, exit_chandelier_lock, exit_scalp, gate_capitulation,
    gate_grind, gate_reversal_grab, gate_thrust,
)
from gazbot7.footprint import exhaustion_signal, footprint_summary  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
CENSUS = "/home/alphabot/gazbot7/reports/friday_v7/sections/census_stdout.txt"
VPP, FEE_PER_LOT, HOLD_CAP_MIN = 2.0, 1.5, 60
YEAR = 2026
PRE_S = 600          # the 10-minute pre-ignition window
ATR_SPLIT = 22.0     # data/exit_overrides.json quiet-tape clip
LO_A_USD, LO_B_R, LO_B_FLOOR = 40.0, 1.75, 60.0

# ── live gate roster (slot_strategy.tournament_slots) ────────────────────────
GATES = [
    # tag, kind, side, live params, exit-override entry
    ("grind_long",        "grind",        "LONG",  dict(slope_min=0.4, fast_slope=True), (2.5, "wide")),
    ("capitulation_long", "capitulation", "LONG",  dict(climax_min=2.5, dom_min=0.6, require_flip=True), (1.5, "tight")),
    ("abs_veto_long",     "thrust",       "LONG",  dict(thr=1.5, amp_floor=0.0004), (1.0, 1.5)),
    ("rgv_short",         "reversal_grab","SHORT", dict(side="SHORT", ext_min=1.5, turn_atr=0.25, flow_min=None,
                                                       atr_min=20.0, fast_slope=False, fast_turn=False), (1.5, "tight")),
    ("exhaustion_short",  "exhaustion",   "SHORT", dict(), (0.75, "tight")),
    ("abs_veto_short",    "thrust",       "SHORT", dict(thr=1.5, amp_floor=0.0004), (1.5, 2.5)),
]
ATR_FLOOR_LIVE = {"grind_long": 22.0, "capitulation_long": 10.0}   # deciders.ATR_FLOOR (08-08: grind 10->22)

# grind_long config A/B — the two cells the desk has actually shipped, fired on the same runs.
#   deployed = today's live cell (ATR>=22, no ext ceiling)
#   wk32     = the cell Movement 2 judged LAST week (ATR>=10, ext_hi 2.0)
GRIND_VARIANTS = {
    "deployed_0808": (dict(slope_min=0.4, fast_slope=True), 22.0),
    "wk32_0801": (dict(slope_min=0.4, fast_slope=True, ext_hi=2.0), 10.0),
    "no_atr_floor": (dict(slope_min=0.4, fast_slope=True), 0.0),
    "ext_hi_3.0": (dict(slope_min=0.4, fast_slope=True, ext_hi=3.0), 22.0),
}

# exhaustion_short veto_counter_regime — direction_router ER/NET thresholds, mirrored
ROUTER_ER_TREND, ROUTER_NET_MIN, ROUTER_WINDOW = 0.15, 30.0, 30


def regime_mode(side, closes):
    """slot_strategy.SlotStrategy._regime_mode, on a list of trailing 1-min closes."""
    cl = closes[-ROUTER_WINDOW:]
    if len(cl) < 6:
        return "tight"
    path = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1.0
    er = abs(cl[-1] - cl[0]) / path
    net = cl[-1] - cl[0]
    up = er >= ROUTER_ER_TREND and net >= ROUTER_NET_MIN
    down = er >= ROUTER_ER_TREND and net <= -ROUTER_NET_MIN
    if (side == "SHORT" and down) or (side == "LONG" and up):
        return "wide"
    if (side == "SHORT" and up) or (side == "LONG" and down):
        return "mid"
    return "tight"


# ── frozen census ────────────────────────────────────────────────────────────
def load_census():
    rows = []
    for ln in open(CENSUS):
        if not re.match(r"^\d\d-\d\d \d\d:\d\d", ln):
            continue
        tm = ln[0:14].strip(); d = ln[14:18].strip(); mv = int(ln[18:25])
        us = ln[34:42].strip(); cl = ln[85:].strip()
        rows.append(dict(t=tm, dir=d, move=mv, us=us, cluster=cl))
    return rows


def to_epoch(s):
    return int(dt.datetime.strptime(f"{YEAR}-{s}", "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())


# ── in-memory tape (so the REAL footprint functions run at speed) ────────────
class _Row(tuple):
    _F = ("ts_ms", "price", "size", "aggressor")

    def __getitem__(self, k):
        if isinstance(k, str):
            return tuple.__getitem__(self, self._F.index(k))
        return tuple.__getitem__(self, k)


class _Res:
    def __init__(self, rows): self._r = rows
    def fetchall(self): return self._r
    def fetchone(self): return self._r[0] if self._r else None


class FakeCap:
    """Mimics the sqlite cursor footprint_summary/capitulation_tape use, off in-memory arrays."""

    def __init__(self, ts, px, sz, ag, bids, asks):
        self.ts, self.px, self.sz, self.ag = ts, px, sz, ag
        self.bids, self.asks = bids, asks   # (ts array, price array, size array)

    def execute(self, sql, params):
        if "FROM ticks" in sql:
            _sym, lo, hi = params
            i = int(np.searchsorted(self.ts, lo, "left"))
            j = int(np.searchsorted(self.ts, hi, "right"))
            return _Res([_Row((int(self.ts[k]), float(self.px[k]), float(self.sz[k]), self.ag[k]))
                         for k in range(i, j)])
        _sym, side, at = params
        arr = self.bids if side == "bid" else self.asks
        i = int(np.searchsorted(arr[0], at, "right")) - 1
        return _Res([(float(arr[1][i]), float(arr[2][i]))] if i >= 0 else [])


# ── the deployed dual-lot exit, repriced tick by tick ────────────────────────
def _lot_exit(lot, side, entry_px, atr, tk, cfg, clip=True):
    """One lot's tick-honest exit. cfg = ('A', a_r) | ('B', spec). The native 1-ATR STP
    owns the loss side in every branch (that is how the desk is actually armed)."""
    quiet = clip and atr < ATR_SPLIT
    peak = 0.0
    for ts, px in tk:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak:
            peak = fav
        pos = Position(side, entry_px, atr, peak)
        # loss side: the native 1-ATR protective stop, always armed
        if fav <= -atr:
            return px, ts, "STOP"
        if quiet:                                    # ★ quiet-tape clip pre-empts everything
            if lot == "A":
                if fav * VPP >= LO_A_USD:
                    return px, ts, "TARGET"
            else:
                tgt = max(LO_B_R * atr, LO_B_FLOOR / VPP)
                if fav >= tgt:
                    return px, ts, "TARGET"
            continue
        if lot == "A":
            if exit_scalp(pos, px, target_r=cfg, stop_atr_mult=1.0) == "TARGET":
                return px, ts, "TARGET"
        elif cfg == "wide":
            if exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5):
                return px, ts, "CHANDELIER"
        elif cfg == "tight":
            if exit_chandelier(pos, px, start_k=1.5, min_k=0.5, tighten=0.75):
                return px, ts, "CHANDELIER"
        else:
            if exit_scalp(pos, px, target_r=float(cfg), stop_atr_mult=1.0) == "TARGET":
                return px, ts, "TARGET"
    return tk[-1][1], tk[-1][0], "TIMEOUT"


class Tape:
    def __init__(self, ts, px):
        self.ts, self.px = ts, px

    def slice(self, from_ms, span_ms):
        i = int(np.searchsorted(self.ts, from_ms, "right"))
        j = int(np.searchsorted(self.ts, from_ms + span_ms, "right"))
        return [(int(self.ts[k]), float(self.px[k])) for k in range(i, j)]


def trade(tape, decision_ms, side, atr, exits, clip=True):
    """Enter on the first tick after decision_ms; run BOTH lots; return the honest $."""
    tk = tape.slice(decision_ms, HOLD_CAP_MIN * 60000)
    if len(tk) < 5 or tk[0][0] - decision_ms > 120000:
        return None
    entry_px, entry_ms = tk[0][1], tk[0][0]
    a_r, b = exits
    out = {}
    tot = 0.0
    for lot, cfg in (("A", a_r), ("B", b)):
        xp, xms, why = _lot_exit(lot, side, entry_px, atr, tk[1:], cfg, clip=clip)
        g = ((xp - entry_px) if side == "LONG" else (entry_px - xp)) * VPP - FEE_PER_LOT
        out[lot] = dict(net=round(g, 2), why=why, hold_s=(xms - entry_ms) // 1000)
        tot += g
    return dict(net=round(tot, 2), entry=entry_px, entry_ms=entry_ms, atr=round(atr, 2),
                A=out["A"], B=out["B"], why=f"A:{out['A']['why']}/B:{out['B']['why']}")


# ── gate evaluation with a "how deep did it get" blocker trace ───────────────
def grind_trace(f, side, p):
    slope = f.vwap_slope_fast if p.get("fast_slope") else f.vwap_slope_atr
    ext_hi = p.get("ext_hi", 4.0)
    if side == "LONG":
        if slope < p["slope_min"]:
            return 1, "vwap slope not up (no established up-trend)"
        if f.ext_atr < 0.3:
            return 2, "price not riding above VWAP (ext<0.3 ATR)"
        if f.ext_atr > ext_hi:
            return 3, f"already stretched (ext>{ext_hi} ATR)"
    else:
        if slope > -p["slope_min"]:
            return 1, "vwap slope not down"
        if f.ext_atr > -0.3:
            return 2, "price not riding below VWAP"
        if f.ext_atr < -ext_hi:
            return 3, f"already stretched (ext<-{ext_hi} ATR)"
    return 99, "FIRES"


def thrust_trace(f, side, p):
    net = f.net_atr_5
    if abs(net) < p["thr"]:
        return 1, "no 5-bar thrust >= 1.5 ATR"
    if (net > 0) != (side == "LONG"):
        return 1, "thrust is the wrong way"
    if p.get("amp_floor") and f.atr_pct < p["amp_floor"]:
        return 2, "amp floor: tape too thin (atr% < 0.04%)"
    if not f.vol_surge:
        return 3, "no volume surge on the thrust bar"
    return 99, "FIRES"


def rgv_trace(f, side, p):
    slope = f.vwap_slope_fast if p.get("fast_slope") else f.vwap_slope_atr
    if f.atr_pct > 0.09 or abs(slope) > 1.0:
        return 1, "regime stand-down (vol too high / slope too steep)"
    if p.get("atr_min") and f.atr < p["atr_min"]:
        return 2, f"ATR floor {p['atr_min']:.0f}pt not met"
    turn = f.net_atr_2 if p.get("fast_turn") else f.net_atr_5
    if side == "SHORT":
        if f.ext_atr < p["ext_min"]:
            return 3, f"not stretched >= {p['ext_min']} ATR above VWAP"
        if turn > -p["turn_atr"]:
            return 4, "no fresh down-turn"
    else:
        if f.ext_atr > -p["ext_min"]:
            return 3, "not stretched below VWAP"
        if turn < p["turn_atr"]:
            return 4, "no fresh up-turn"
    return 99, "FIRES"


def exh_trace(fp, side):
    if abs(fp["net_signed"]) < 400:
        return 1, "20s net aggressor flow < 400 (no aggression to fade)"
    want = "SHORT" if fp["net_signed"] > 0 else "LONG"
    if want != side:
        return 1, "aggression is the wrong way for this side"
    if abs(fp["price_move_pt"]) > 2.0:
        return 2, "the aggression DID move price >2pt (not absorption)"
    if fp["bid1_size"] <= 0 or fp["ask1_size"] <= 0:
        return 2, "no L1 book"
    if side == "SHORT":
        if fp["ask1_size"] < 1.5 * fp["bid1_size"]:
            return 3, "no ask wall (hit side not 1.5x)"
    else:
        if fp["bid1_size"] < 1.5 * fp["ask1_size"]:
            return 3, "no bid wall"
    return 99, "FIRES"


def cap_trace(fp, side, climax_min, dom_min, require_flip):
    tot = fp["cap_sell"] + fp["cap_buy"]
    if fp["cap_base"] <= 0 or tot <= 0:
        return 0, "no tape"
    if side == "LONG":
        if fp["cap_dpx"] >= 0:
            return 1, "price not flushing DOWN in the window"
        if fp["cap_sell"] / fp["cap_base"] < climax_min:
            return 2, f"sell volume < {climax_min}x baseline (no climax)"
        if fp["cap_sell"] / tot < dom_min:
            return 3, f"sellers not {dom_min:.0%} dominant"
        if require_flip and not fp["cap_flip"]:
            return 4, "buyers never flipped at the low (require_flip)"
    else:
        if fp["cap_dpx"] <= 0:
            return 1, "price not blowing off UP in the window"
        if fp["cap_buy"] / fp["cap_base"] < climax_min:
            return 2, f"buy volume < {climax_min}x baseline"
        if fp["cap_buy"] / tot < dom_min:
            return 3, "buyers not dominant"
        if require_flip and fp["cap_flip"]:
            return 4, "sellers never flipped at the high"
    return 99, "FIRES"


def main():
    census = load_census()
    sat = [r for r in census if r["us"] == "sat out"]
    print(f"frozen census: {len(census)} runs, {len(sat)} sat out")

    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    rows = con.execute("""
        WITH m AS (SELECT (bar_ts - (bar_ts % 60)) AS mt, bar_ts, open, high, low, close, volume
                   FROM c.bars WHERE symbol='MNQ' AND timeframe='5s')
        SELECT mt, arg_min(open,bar_ts), max(high), min(low), arg_max(close,bar_ts), sum(volume)
        FROM m GROUP BY mt ORDER BY mt""").fetchall()
    bars = [Bar(int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rows]
    idx = {b.ts: i for i, b in enumerate(bars)}
    print(f"1-min bars: {len(bars)}  {dt.datetime.fromtimestamp(bars[0].ts, dt.UTC)} .. "
          f"{dt.datetime.fromtimestamp(bars[-1].ts, dt.UTC)}")

    t = con.execute("SELECT ts_ms, price, size, aggressor FROM c.ticks WHERE symbol='MNQ' ORDER BY ts_ms").fetchnumpy()
    ts_a = t["ts_ms"].astype("int64"); px_a = t["price"].astype("float64")
    sz_a = t["size"].astype("float64"); ag_a = list(t["aggressor"])
    print(f"ticks: {len(ts_a):,}  {dt.datetime.fromtimestamp(ts_a[0]/1000, dt.UTC)} .. "
          f"{dt.datetime.fromtimestamp(ts_a[-1]/1000, dt.UTC)}")
    bk = {}
    for s in ("bid", "ask"):
        q = con.execute(f"""SELECT ts_ms, price, size FROM c.book
                            WHERE symbol='MNQ' AND side='{s}' AND level=1 ORDER BY ts_ms""").fetchnumpy()
        bk[s] = (q["ts_ms"].astype("int64"), q["price"].astype("float64"), q["size"].astype("float64"))
    print(f"L1 book rows: bid {len(bk['bid'][0]):,} ask {len(bk['ask'][0]):,}")

    cap = FakeCap(ts_a, px_a, sz_a, ag_a, bk["bid"], bk["ask"])
    tape = Tape(ts_a, px_a)
    tick_lo, tick_hi = int(ts_a[0]), int(ts_a[-1])

    def feats(bar_ts):
        i = idx.get(bar_ts)
        if i is None or i < 6:
            return None, None
        w = bars[max(0, i - 59):i + 1]
        if len(w) < 6:
            return None, None
        return compute_features(w), efficiency_ratio(w)

    def flow_window(a_ms, b_ms):
        i = int(np.searchsorted(ts_a, a_ms, "left")); j = int(np.searchsorted(ts_a, b_ms, "left"))
        if j - i < 5:
            return None, None
        net = float(sum(sz_a[k] if ag_a[k] == "buy" else -sz_a[k] for k in range(i, j)))
        return net, float(px_a[j - 1] - px_a[i])

    # ── ignition context + regime label per run ──────────────────────────────
    ctx = {}
    for r in sat:
        T = to_epoch(r["t"])
        f, er = feats(T - 60)
        # 60-min range break: is the last pre-run close outside the prior hour's range?
        i = idx.get(T - 60)
        rb = None
        if i is not None and i >= 61:
            prior = bars[i - 60:i]
            hi, lo = max(b.high for b in prior), min(b.low for b in prior)
            c = bars[i].close
            rb = (c > hi) or (c < lo)
        hh, mm = int(r["t"][-5:-3]), int(r["t"][-2:])
        ctx[r["t"]] = dict(T=T, dir=r["dir"], move=r["move"], cluster=r["cluster"],
                           atr=(f.atr if f else None), er=er, rb=rb,
                           us_sess=(13 * 60 + 30 <= hh * 60 + mm < 20 * 60),
                           has_tape=(T - PRE_S) * 1000 >= tick_lo and T * 1000 <= tick_hi)

    atrs = sorted(c["atr"] for c in ctx.values() if c["atr"])
    a_lo, a_hi = atrs[len(atrs) // 4], atrs[3 * len(atrs) // 4]

    def regime(c):
        a, e = c["atr"], c["er"]
        if a is None or e is None:
            return "UNKNOWN"
        if e >= 0.45:
            return "CLEAN-TREND" if c["rb"] else "TREND-NO-BREAK"
        if e >= 0.25:
            return "BUILDING"
        if a >= a_hi:
            return "VIOLENT-WHIPSAW"
        if a < a_lo:
            return "DEAD-CHOP"
        return "NORMAL-CHOP"

    for k, c in ctx.items():
        c["regime"] = regime(c)
    print(f"\nregime cut points: ATR p25={a_lo:.1f}pt  p75={a_hi:.1f}pt")

    # ── the mechanical + ungated fire hunt ──────────────────────────────────
    modes = ("mech", "ungated")
    fires = {(g[0], m): [] for g in GATES for m in modes}
    depth = {(g[0], m): {} for g in GATES for m in modes}     # run -> (max depth, label)
    blocked_by_filter = {(g[0], m): [] for g in GATES for m in modes}   # raw fire killed by a live filter

    for r in sat:
        s = r["t"]; c = ctx[s]; T = c["T"]
        side_run = "LONG" if r["dir"] == "UP" else "SHORT"
        if not c["has_tape"]:
            continue
        pre_bars = [T - 60 * k for k in range(1, 11)][::-1]      # T-600 .. T-60 (completed bars)
        for tag, kind, gside, params, exits in GATES:
            if gside != side_run:
                continue
            for mode in modes:
                p = dict(params)
                if mode == "ungated":
                    if kind == "grind":
                        p["ext_hi"] = 99.0        # no stretch ceiling at all (live default is 4.0)
                    if kind == "thrust":
                        p.pop("amp_floor", None)
                    if kind == "reversal_grab":
                        p["atr_min"] = 0.0
                    if kind == "capitulation":
                        p["require_flip"] = False
                best = (-1, "no bars")
                fired = None
                if kind in ("grind", "thrust", "reversal_grab"):
                    for bt in pre_bars:
                        f, _er = feats(bt)
                        if f is None:
                            continue
                        if kind == "grind":
                            d, lab = grind_trace(f, gside, p)
                        elif kind == "thrust":
                            d, lab = thrust_trace(f, gside, p)
                        else:
                            d, lab = rgv_trace(f, gside, p)
                        if d > best[0]:
                            best = (d, lab)
                        if d != 99:
                            continue
                        # the raw gate agrees?
                        if kind == "grind":
                            e = gate_grind(f, tape_net=0.0, **p)
                        elif kind == "thrust":
                            e = gate_thrust(f, **p)
                        else:
                            e = gate_reversal_grab(f, tape_net=0.0, in_rth=True, **p)
                        if not (e and e.side == gside):
                            continue
                        dec_ms = (bt + 60) * 1000
                        if mode == "mech":
                            if tag in ATR_FLOOR_LIVE and f.atr < ATR_FLOOR_LIVE[tag]:
                                blocked_by_filter[(tag, mode)].append((s, f"ATR floor {ATR_FLOOR_LIVE[tag]:.0f}"))
                                best = (4, f"ATR floor {ATR_FLOOR_LIVE[tag]:.0f}pt not met")
                                continue
                            if tag.startswith("abs_veto"):       # 55s absorption veto
                                fl, dpx = flow_window(dec_ms, dec_ms + 55000)
                                absorbed = True
                                if fl is not None:
                                    absorbed = exit_absorption(Position(gside, 0.0, 0.0, 0.0), tape_net=fl,
                                                               window_price_delta=dpx, flow_min=50.0) is not None
                                if absorbed:
                                    blocked_by_filter[(tag, mode)].append((s, "55s absorption veto"))
                                    best = (4, "55s absorption VETO (burst absorbed)")
                                    continue
                                dec_ms += 55000
                        fired = (dec_ms, f.atr, bt)
                        break
                else:
                    for nm in range(T - PRE_S, T - 60 + 1, 5):
                        fp = footprint_summary(cap, "MNQ", nm * 1000)
                        if kind == "capitulation":
                            d, lab = cap_trace(fp, gside, p["climax_min"], p["dom_min"], p["require_flip"])
                        else:
                            d, lab = exh_trace(fp, gside)
                        if d > best[0]:
                            best = (d, lab)
                        if d != 99:
                            continue
                        if kind == "capitulation":
                            e = gate_capitulation(None, cap_sell=fp["cap_sell"], cap_buy=fp["cap_buy"],
                                                  cap_base=fp["cap_base"], cap_dpx=fp["cap_dpx"],
                                                  cap_flip=fp["cap_flip"], **p)
                            ok = e is not None and e.side == gside
                        else:
                            sig = exhaustion_signal(fp["net_signed"], fp["price_move_pt"], fp["bid1_size"],
                                                    fp["ask1_size"], fp["bid1_price"], fp["ask1_price"])
                            ok = sig is not None and sig[0] == gside
                        if not ok:
                            continue
                        fi, _e = feats(nm - (nm % 60))
                        atr = fi.atr if fi else 20.0
                        dec_ms = nm * 1000
                        if mode == "mech":
                            if tag in ATR_FLOOR_LIVE and atr < ATR_FLOOR_LIVE[tag]:
                                blocked_by_filter[(tag, mode)].append((s, "ATR floor 10"))
                                best = (5, "ATR floor 10pt not met")
                                continue
                            if tag == "exhaustion_short":       # 5s confirm-veto + counter-regime veto
                                i0 = int(np.searchsorted(ts_a, dec_ms, "left"))
                                i1 = int(np.searchsorted(ts_a, dec_ms + 5000, "left"))
                                sig_px = sig[1]        # the mid the signal fired at
                                adverse = True
                                if i1 - i0 >= 3:
                                    adverse = (float(px_a[i0:i1].max()) - sig_px) > 5.0
                                if adverse:
                                    blocked_by_filter[(tag, mode)].append((s, "5s confirm-veto (went adverse)"))
                                    best = (5, "5s confirm-veto: price ran against the fade")
                                    continue
                                # ★ live veto_counter_regime — skip a fade fired INTO a local trend
                                bi = idx.get(nm - (nm % 60))
                                if bi is not None and bi >= 30:
                                    cl = [b.close for b in bars[bi - 29:bi + 1]]
                                    if regime_mode(gside, cl) == "mid":
                                        blocked_by_filter[(tag, mode)].append((s, "counter-regime veto"))
                                        best = (5, "counter-regime VETO (short fired into a local up-trend)")
                                        continue
                                dec_ms += 5000
                        fired = (dec_ms, atr, nm)
                        break
                depth[(tag, mode)][s] = best
                if fired:
                    dec_ms, atr, bt = fired
                    res = trade(tape, dec_ms, gside, atr, exits)
                    if res:
                        res.update(run=s, dir=r["dir"], move=r["move"], cluster=c["cluster"],
                                   regime=c["regime"], us_sess=c["us_sess"],
                                   lead_s=(T * 1000 - dec_ms) / 1000.0)
                        fires[(tag, mode)].append(res)

    # ── TAPE SHAPE in the 10-min pre-window (the mechanism, in numbers) ──────
    # For every eligible run: how big did ATR ever get, how stretched did price ever get from
    # VWAP, how steep did the fast VWAP slope ever get. This is what decides whether a floor is
    # "never reachable this week" or "just missed".
    shape = {}
    for r in sat:
        s = r["t"]; c = ctx[s]
        if not c["has_tape"]:
            continue
        mx = dict(atr=0.0, ext=0.0, ext_signed=0.0, slope=0.0, thrust=0.0, n=0)
        for bt in [c["T"] - 60 * k for k in range(1, 11)]:
            f, _e = feats(bt)
            if f is None:
                continue
            mx["n"] += 1
            mx["atr"] = max(mx["atr"], f.atr)
            if abs(f.ext_atr) > abs(mx["ext_signed"]):
                mx["ext_signed"] = f.ext_atr
            mx["ext"] = max(mx["ext"], abs(f.ext_atr))
            mx["slope"] = max(mx["slope"], abs(f.vwap_slope_fast))
            mx["thrust"] = max(mx["thrust"], abs(f.net_atr_5))
        shape[s] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in mx.items()}

    # ── grind_long CONFIG A/B: the shipped cells, same runs, same exits ──────
    gvar = {}
    for vname, (vp, vfloor) in GRIND_VARIANTS.items():
        tr, blk, reach = [], 0, {}
        for r in sat:
            s = r["t"]; c = ctx[s]
            if not c["has_tape"] or r["dir"] != "UP":
                continue
            best = (-1, "no bars")
            for bt in [c["T"] - 60 * k for k in range(1, 11)][::-1]:
                f, _e = feats(bt)
                if f is None:
                    continue
                d, lab = grind_trace(f, "LONG", vp)
                if d > best[0]:
                    best = (d, lab)
                if d != 99:
                    continue
                e = gate_grind(f, tape_net=0.0, **vp)
                if not (e and e.side == "LONG"):
                    continue
                if vfloor and f.atr < vfloor:
                    blk += 1
                    best = (4, f"ATR floor {vfloor:.0f}pt not met")
                    continue
                res = trade(tape, (bt + 60) * 1000, "LONG", f.atr, (2.5, "wide"))
                if res:
                    res.update(run=s, move=r["move"], regime=c["regime"])
                    tr.append(res)
                break
            reach[s] = best[1]
        n = len(tr); net = sum(x["net"] for x in tr)
        hist = {}
        for v in reach.values():
            hist[v] = hist.get(v, 0) + 1
        gvar[vname] = dict(fires=n, net=round(net, 1), blocked_by_atr=blk,
                           per=round(net / n, 1) if n else 0,
                           win=round(100 * sum(1 for x in tr if x["net"] > 0) / n) if n else 0,
                           reach=sorted(hist.items(), key=lambda z: -z[1]),
                           trades=[dict(run=x["run"], move=x["move"], net=x["net"], why=x["why"],
                                        atr=x["atr"], regime=x["regime"]) for x in tr])
    print("\n" + "=" * 100)
    print("GRIND_LONG CONFIG A/B — the shipped cells, fired on the same sat-out runs")
    for k, v in gvar.items():
        print(f"  {k:16} fires {v['fires']:>2}  net ${v['net']:>+8.1f}  ${v['per']:>+7.1f}/fire "
              f" win {v['win']:>3}%  ATR-blocked {v['blocked_by_atr']}")
        for lab, cnt in v["reach"][:4]:
            print(f"        {cnt:>3}  {lab}")

    # ── blind in-direction controls (the money WAS there) ───────────────────
    blind = {}
    for r in sat:
        s = r["t"]; c = ctx[s]
        if not c["has_tape"]:
            continue
        side = "LONG" if r["dir"] == "UP" else "SHORT"
        atr = c["atr"] or 20.0
        for lbl, dec in (("ign", c["T"] * 1000), ("t-60", (c["T"] - 60) * 1000),
                         ("t-300", (c["T"] - 300) * 1000)):
            res = trade(tape, dec, side, atr, (1.5, "wide"))
            if res:
                blind.setdefault(lbl, []).append(dict(res, run=s, regime=c["regime"],
                                                      us_sess=c["us_sess"], move=r["move"]))

    # ── R sweep on the blind population, per regime (the population WITH n) ──
    # ★ clip=False: the deployed quiet-tape clip ($40 Lot-A / 1.75R-or-$60 Lot-B below 22pt ATR)
    # PRE-EMPTS the R target on every quiet entry, so a swept R would be a no-op there. To PROVE
    # an R optimum the clip must be off; the clip-on number is reported separately as the live one.
    rsweep, rsweep_day = {}, {}
    for R in (0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0):
        acc, dacc = {}, {}
        for r in sat:
            s = r["t"]; c = ctx[s]
            if not c["has_tape"]:
                continue
            side = "LONG" if r["dir"] == "UP" else "SHORT"
            res = trade(tape, (c["T"] - 60) * 1000, side, c["atr"] or 20.0, (R, R), clip=False)
            if not res:
                continue
            for key in ("ALL", c["regime"], "US" if c["us_sess"] else "ON"):
                a = acc.setdefault(key, [0, 0.0, 0])
                a[0] += 1; a[1] += res["net"]; a[2] += (res["net"] > 0)
            d = dacc.setdefault(s[:5], [0, 0.0])
            d[0] += 1; d[1] += res["net"]
        rsweep[R] = {k: dict(n=v[0], net=round(v[1], 1), win=round(100 * v[2] / v[0])) for k, v in acc.items()}
        rsweep_day[R] = {k: dict(n=v[0], net=round(v[1], 1)) for k, v in dacc.items()}

    # ── BASE RATE: how often does each gate fire ANYWHERE on the week's tape? ────
    # The mechanism question is not "is the gate dead" but "does it fire in the right PLACE".
    base = {g[0]: {"mech": 0, "ungated": 0} for g in GATES}
    pre_windows = [(c["T"] - PRE_S, c["T"]) for c in ctx.values() if c["has_tape"]]

    def in_pre(t):
        return any(a <= t <= b for a, b in pre_windows)

    base_in_pre = {g[0]: {"mech": 0, "ungated": 0} for g in GATES}
    lo_s, hi_s = tick_lo // 1000, tick_hi // 1000
    for b in bars:
        if not (lo_s <= b.ts <= hi_s):
            continue
        f, _e = feats(b.ts)
        if f is None:
            continue
        for tag, kind, gside, params, exits in GATES:
            if kind not in ("grind", "thrust", "reversal_grab"):
                continue
            for mode in modes:
                p = dict(params)
                if mode == "ungated":
                    if kind == "grind":
                        p["ext_hi"] = 4.0
                    if kind == "thrust":
                        p.pop("amp_floor", None)
                    if kind == "reversal_grab":
                        p["atr_min"] = 0.0
                if kind == "grind":
                    e = gate_grind(f, tape_net=0.0, **p)
                elif kind == "thrust":
                    e = gate_thrust(f, **p)
                else:
                    e = gate_reversal_grab(f, tape_net=0.0, in_rth=True, **p)
                if e and e.side == gside:
                    if mode == "mech" and tag in ATR_FLOOR_LIVE and f.atr < ATR_FLOOR_LIVE[tag]:
                        continue
                    base[tag][mode] += 1
                    if in_pre(b.ts):
                        base_in_pre[tag][mode] += 1
    for nm in range(lo_s + 200, hi_s, 20):        # footprint gates, sampled every 20s
        fp = footprint_summary(cap, "MNQ", nm * 1000)
        for tag, kind, gside, params, exits in GATES:
            if kind not in ("capitulation", "exhaustion"):
                continue
            for mode in modes:
                if kind == "capitulation":
                    p = dict(params)
                    if mode == "ungated":
                        p["require_flip"] = False
                    e = gate_capitulation(None, cap_sell=fp["cap_sell"], cap_buy=fp["cap_buy"],
                                          cap_base=fp["cap_base"], cap_dpx=fp["cap_dpx"],
                                          cap_flip=fp["cap_flip"], **p)
                    ok = e is not None and e.side == gside
                else:
                    sg = exhaustion_signal(fp["net_signed"], fp["price_move_pt"], fp["bid1_size"],
                                           fp["ask1_size"], fp["bid1_price"], fp["ask1_price"])
                    ok = sg is not None and sg[0] == gside
                if ok:
                    base[tag][mode] += 1
                    if in_pre(nm):
                        base_in_pre[tag][mode] += 1

    # ══ OUTPUT ══
    out = {}
    print("\n" + "=" * 100)
    print("PER-GATE SCOREBOARD — fires at the sat-out runs, in-direction, 10min pre-ignition")
    print(f"{'gate':20}{'mode':9}{'elig':>5}{'fires':>7}{'net$':>9}{'$/fire':>8}{'win%':>6}  exits")
    board = []
    up = sum(1 for r in sat if r["dir"] == "UP" and ctx[r["t"]]["has_tape"])
    dn = sum(1 for r in sat if r["dir"] == "DN" and ctx[r["t"]]["has_tape"])
    for tag, kind, gside, params, exits in GATES:
        for mode in modes:
            tr = fires[(tag, mode)]
            n = len(tr); net = sum(x["net"] for x in tr); w = sum(1 for x in tr if x["net"] > 0)
            elig = up if gside == "LONG" else dn
            whys = {}
            for x in tr:
                whys[x["why"]] = whys.get(x["why"], 0) + 1
            ws = " ".join(f"{k}:{v}" for k, v in sorted(whys.items(), key=lambda z: -z[1]))
            print(f"{tag:20}{mode:9}{elig:>5}{n:>7}{net:>+9.1f}{(net/n if n else 0):>+8.1f}"
                  f"{(100*w/n if n else 0):>5.0f}%  {ws}")
            board.append(dict(tag=tag, side=gside, mode=mode, elig=elig, fires=n, net=round(net, 1),
                              per=round(net / n, 1) if n else 0, win=round(100 * w / n) if n else 0,
                              exits=ws, blocked=len(blocked_by_filter[(tag, mode)]),
                              trades=[dict(run=x["run"], move=x["move"], net=x["net"], why=x["why"],
                                           regime=x["regime"], lead_s=x["lead_s"], atr=x["atr"]) for x in tr]))
    out["board"] = board

    print("\n" + "=" * 100)
    print("WHY IT MISSES — how far each gate ever got in its own rule chain (per eligible run)")
    mech_reason = {}
    for tag, kind, gside, params, exits in GATES:
        for mode in modes:
            hist = {}
            for s, (d, lab) in depth[(tag, mode)].items():
                hist[lab] = hist.get(lab, 0) + 1
            tot = sum(hist.values())
            mech_reason[f"{tag}|{mode}"] = dict(n=tot, hist=sorted(hist.items(), key=lambda z: -z[1]))
            print(f"\n  {tag} [{mode}] — {tot} eligible runs")
            for lab, k in sorted(hist.items(), key=lambda z: -z[1]):
                print(f"      {k:>3}  {lab}")
            bf = blocked_by_filter[(tag, mode)]
            if bf:
                print(f"      -> {len(bf)} raw fires killed by a LIVE filter: "
                      + ", ".join(f"{a}({b})" for a, b in bf[:8]))
    out["why"] = mech_reason
    out["blocked"] = {f"{t}|{m}": v for (t, m), v in blocked_by_filter.items() if v}

    print("\n" + "=" * 100)
    print("BLIND IN-DIRECTION CONTROL (hindsight direction, Lot A 1.5R + Lot B wide chandelier)")
    bl = {}
    for lbl, arr in blind.items():
        n = len(arr); net = sum(x["net"] for x in arr); w = sum(1 for x in arr if x["net"] > 0)
        srt = sorted((x["net"] for x in arr), reverse=True)
        print(f"  enter {lbl:6}  n={n:>3}  net ${net:>+9.1f}  ${net/n:>+7.1f}/run  win {100*w/n:>3.0f}%"
              f"   strip-best-3 ${sum(srt[3:]):+.1f}")
        bl[lbl] = dict(n=n, net=round(net, 1), per=round(net / n, 1), win=round(100 * w / n),
                       strip3=round(sum(srt[3:]), 1))
        if lbl == "t-60":
            for seg in sorted({x["regime"] for x in arr}):
                sa = [x for x in arr if x["regime"] == seg]
                sn = sum(x["net"] for x in sa); sw = sum(1 for x in sa if x["net"] > 0)
                print(f"        {seg:18} n={len(sa):>3}  net ${sn:>+8.1f}  ${sn/len(sa):>+7.1f}/run  win {100*sw/len(sa):>3.0f}%")
                bl.setdefault("t-60_regime", {})[seg] = dict(n=len(sa), net=round(sn, 1),
                                                             per=round(sn / len(sa), 1), win=round(100 * sw / len(sa)))
            for lab, pred in (("US session", True), ("overnight", False)):
                sa = [x for x in arr if x["us_sess"] == pred]
                if not sa:
                    continue
                sn = sum(x["net"] for x in sa); sw = sum(1 for x in sa if x["net"] > 0)
                print(f"        {lab:18} n={len(sa):>3}  net ${sn:>+8.1f}  ${sn/len(sa):>+7.1f}/run  win {100*sw/len(sa):>3.0f}%")
                bl.setdefault("t-60_tod", {})[lab] = dict(n=len(sa), net=round(sn, 1),
                                                          per=round(sn / len(sa), 1), win=round(100 * sw / len(sa)))
    out["blind"] = bl

    print("\n" + "=" * 100)
    print("R SWEEP on the blind t-60 population (both lots at the same R) — per regime")
    keys = ["ALL", "US", "ON", "DEAD-CHOP", "NORMAL-CHOP", "VIOLENT-WHIPSAW", "BUILDING",
            "TREND-NO-BREAK", "CLEAN-TREND"]
    hdr = "  R    " + "".join(f"{k:>18}" for k in keys)
    print(hdr)
    for R in sorted(rsweep):
        line = f"  {R:<5}"
        for k in keys:
            v = rsweep[R].get(k)
            cell = "-" if not v else "%+.0f/%d/%d%%" % (v["net"], v["n"], v["win"])
            line += "%18s" % cell
        print(line)
    out["rsweep"] = {str(R): rsweep[R] for R in sorted(rsweep)}
    out["rsweep_day"] = {str(R): rsweep_day[R] for R in sorted(rsweep_day)}
    print("  leave-one-day-out on the best-R cell (ALL segment):")
    bestR = max(rsweep, key=lambda R: rsweep[R]["ALL"]["net"])
    tot = rsweep[bestR]["ALL"]["net"]
    print(f"    best R = {bestR}  net ${tot:+.1f}; " + "  ".join(
        f"-{d} ${tot - v['net']:+.0f}" for d, v in sorted(rsweep_day[bestR].items())))
    out["rsweep_best"] = dict(R=bestR, net=tot,
                              lodo={d: round(tot - v["net"], 1) for d, v in rsweep_day[bestR].items()})

    print("\n" + "=" * 100)
    print("BASE RATE — does the gate fire at all this week, and does it fire NEAR a sat-out run?")
    print(f"{'gate':20}{'mode':9}{'fires/week':>12}{'in a pre-run 10m window':>26}{'share':>8}")
    for tag, kind, gside, params, exits in GATES:
        for mode in modes:
            b, ip = base[tag][mode], base_in_pre[tag][mode]
            print(f"{tag:20}{mode:9}{b:>12}{ip:>26}{(100*ip/b if b else 0):>7.1f}%")
    out["base_rate"] = {t: dict(all=base[t], in_pre=base_in_pre[t]) for t in base}

    print("\n" + "=" * 100)
    print("COVERAGE — which sat-out runs drew ANY in-direction fire")
    n_tape = sum(1 for c in ctx.values() if c["has_tape"])
    top15 = [x["time"] for x in json.load(open(
        "/home/alphabot/gazbot7/reports/friday_v7/sections/census_summary.json"))["top15"]]
    top25 = [x["time"] for x in json.load(open(
        "/home/alphabot/gazbot7/reports/friday_v7/sections/census_summary.json"))["top25"]]
    cov = {}
    for mode in modes:
        hit = {x["run"] for g in GATES for x in fires[(g[0], mode)]}
        c15 = sum(1 for t in top15 if t in hit); c25 = sum(1 for t in top25 if t in hit)
        ceil_hit = sum(abs(ctx[t]["move"]) * VPP for t in hit)
        netm = sum(x["net"] for g in GATES for x in fires[(g[0], mode)])
        nfire = sum(len(fires[(g[0], mode)]) for g in GATES)
        print(f"  {mode:9} runs touched {len(hit):>2}/{n_tape}  "
              f"top-15 {c15}/15  top-25 {c25}/25  fires {nfire}  net ${netm:+.1f}  "
              f"ceiling touched ${ceil_hit:.0f}")
        cov[mode] = dict(runs=len(hit), top15=c15, top25=c25, fires=nfire, net=round(netm, 1),
                         ceiling=round(ceil_hit), runs_list=sorted(hit))
        nets = sorted((x["net"] for g in GATES for x in fires[(g[0], mode)]), reverse=True)
        for k in (1, 3):
            print(f"      strip-best-{k}: {len(nets)-k} fires  net ${sum(nets[k:]):+.1f}")
        cov[mode]["strip"] = {str(k): round(sum(nets[k:]), 1) for k in (1, 3)}
        for extra in (3.0, 6.0):        # cost stress: $/RT/lot on top of the $1.50 baseline
            cov[mode][f"cost{extra}"] = round(sum(nets) - nfire * 2 * (extra - FEE_PER_LOT), 1)
        print(f"      cost-stress $3.00/RT/lot ${cov[mode]['cost3.0']:+.1f}   "
              f"$6.00/RT/lot ${cov[mode]['cost6.0']:+.1f}")
        days = {}
        for g in GATES:
            for x in fires[(g[0], mode)]:
                d = days.setdefault(x["run"][:5], [0, 0.0]); d[0] += 1; d[1] += x["net"]
        print("      per-day: " + "  ".join(f"{k} {v[0]}f ${v[1]:+.0f}" for k, v in sorted(days.items())))
        cov[mode]["days"] = {k: dict(n=v[0], net=round(v[1], 1)) for k, v in days.items()}
        tot = sum(v[1] for v in days.values())
        cov[mode]["lodo"] = {k: round(tot - v[1], 1) for k, v in days.items()}
        print("      leave-one-day-out: " + "  ".join(f"-{k} ${tot-v[1]:+.0f}" for k, v in sorted(days.items())))
    out["coverage"] = cov

    print("\n" + "=" * 100)
    print("THE 55s VETO — what it saved vs what the WAIT cost (abs_veto_short/long)")
    veto = {}
    for tag in ("abs_veto_long", "abs_veto_short"):
        m = {x["run"]: x for x in fires[(tag, "mech")]}
        u = {x["run"]: x for x in fires[(tag, "ungated")]}
        saved = sum(-u[r]["net"] for r, _w in blocked_by_filter[(tag, "mech")] if r in u)
        delay = sum(m[r]["net"] - u[r]["net"] for r in m if r in u)
        print(f"  {tag}: blocked {len(blocked_by_filter[(tag,'mech')])} raw fires "
              f"(saved ${saved:+.1f}) · 55s WAIT on the {len(set(m)&set(u))} survivors cost ${delay:+.1f}")
        veto[tag] = dict(blocked=len(blocked_by_filter[(tag, "mech")]), saved=round(saved, 1),
                         delay_cost=round(delay, 1),
                         pairs=[dict(run=r, ungated=u[r]["net"], mech=m[r]["net"]) for r in m if r in u])
    out["veto"] = veto

    print("\n" + "=" * 100)
    print("RUN CONTEXT (regime / cluster / tape availability)")
    reg_n = {}
    for s, c in ctx.items():
        reg_n[c["regime"]] = reg_n.get(c["regime"], 0) + 1
    for k, v in sorted(reg_n.items(), key=lambda z: -z[1]):
        print(f"   {k:18} {v:>3} runs")
    out["ctx"] = {s: dict(dir=c["dir"], move=c["move"], cluster=c["cluster"], regime=c["regime"],
                          atr=round(c["atr"], 1) if c["atr"] else None,
                          er=round(c["er"], 3) if c["er"] else None, rb=c["rb"],
                          us=c["us_sess"], tape=c["has_tape"]) for s, c in ctx.items()}
    out["regime_n"] = reg_n
    out["atr_cuts"] = [round(a_lo, 1), round(a_hi, 1)]
    out["n_sat"] = len(sat)
    out["n_tape"] = sum(1 for c in ctx.values() if c["has_tape"])
    out["no_tape_runs"] = sorted(s for s, c in ctx.items() if not c["has_tape"])
    out["shape"] = shape
    out["grind_variants"] = gvar
    out["tick_window"] = [str(dt.datetime.fromtimestamp(tick_lo / 1000, dt.UTC)),
                          str(dt.datetime.fromtimestamp(tick_hi / 1000, dt.UTC))]

    with open("/home/alphabot/gazbot7/reports/friday_v7/sections/movement2_wk33.json", "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print("\nJSON -> reports/friday_v7/sections/movement2_wk33.json")


if __name__ == "__main__":
    main()
