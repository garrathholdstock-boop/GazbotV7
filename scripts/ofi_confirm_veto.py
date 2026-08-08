#!/usr/bin/env python3
"""Seconds-scale OFI confirm / veto as a FAKEOUT FILTER on the already-earning momentum gates.

READ-ONLY. NOT for commit. No live service. Run with /home/alphabot/gazbot7/.venv/bin/python

Operator's idea: the abs_veto_55s mechanism (thrust + a continuation-confirm) but at the 2-15s
scale the 250ms L2 capture allows. This is NOT run-prediction (a confirmed null). It is a
CONDITIONAL confirm/veto on entries a gate ALREADY chose — legit even though OFI is
concurrent-with-price, because concurrent OFI reads "is this move OFI-backed or absorbed right now".
Hard constraint (from the failed AFC veto sweep): a filter can only sharpen a base that already has
edge; it cannot flip a coin-flip. So test on thrust_short + grind_long (the live momentum gates).

Base entries reconstructed to match the LIVE desk:
  thrust_short : gate_thrust(thr=1.5, amp_floor=0.0004) SHORT  + ER floor 0.20 + ATR floor 16
  grind_long   : gate_grind(slope_min=0.4, fast_slope=True) LONG + ER floor 0.20 + ATR floor 20
  exit = vol-adaptive chandelier + native 1-ATR stop, tick-honest, 60-min max hold.
  cost = 2pt round-trip * $2/pt = $4/trade.

Filters (all enter tick-honest at the entry second; delayed variants HONESTLY charge the give-up):
  Variant A  contemporaneous CONFIRM (no give-up): keep iff OFI over [t-q,t+q] aligns >= thr; enter at t.
  Variant B1 delay VETO   (abs_veto polarity): wait d s; take UNLESS OFI over [t,t+d] OPPOSES >= thr; enter at t+d.
  Variant B2 delay CONFIRM: wait d s; take ONLY IF OFI over [t,t+d] ALIGNS >= thr; enter at t+d.
  d in {1,2,3,5,8,10,15}s ; plus d=55 as an OFI-horizon-matched proxy for the live 55s abs_veto.

Threshold thr is a multiple m of the per-cell std of signed-OFI across the base entries (m in {0,0.5,1.0}).
OFI variants: L1-OFI and MLOFI(1-3), both swept; best reported.

Retention check: which DN runs (thrust_short) / UP runs (grind_long) does the base catch, and does the
filter KEEP them? A cell that goes green only by dropping the caught runs is a FAKE win — flagged.

CAVEATS: in-sample 07-09..07-24 (OFI needs depth.db, which starts 07-09); one summer regime; MNQ;
250ms-cadence-limited (OFI aggregated to 1s buckets). A LEAD, not a verdict.
"""
from __future__ import annotations
import os
import sys
import datetime as dt
import numpy as np
import pandas as pd
import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")
import archive_data as A
from gazbot7.deciders import (Bar, Position, compute_features, gate_thrust, gate_grind,
                              chandelier_start_k, exit_chandelier, exit_scalp,
                              efficiency_ratio, er_blocks, atr_blocks)

DEPTH = "/home/alphabot/gazbot7/data/depth.db"
VPP = 2.0
# ★2026-08-01 COST FIX (operator) — was `COST = 2.0 * VPP` ("2pt round-trip = $4"), a blanket all-in
# friction number 2.7x the real commission. Venue truth: MNQ commission is $1.50 per ROUND TRIP
# ($0.75/side) — all 487 closed trades in data/gazbot7.db carry fees_usd = 1.50 exactly. Matching the
# desk exemplar (scripts/grave_newsfade.py): model the FEE at its real value and keep slippage a
# SEPARATE, explicit, overridable term rather than folding it into the fee. Conflating the two is what
# produced the wrong $5/RT that inverted the NIPC verdict today. Any conclusion this script produced
# before this date was computed at $4/RT and should be re-run before it is cited.
# Revert: COST = 2.0 * VPP.
FEE_RT = float(os.environ.get("OFI_FEE_RT", "1.50"))     # commission only
SLIP_RT = float(os.environ.get("OFI_SLIP_RT", "0.0"))    # explicit slippage $; 0 = the optimistic bound
COST = FEE_RT + SLIP_RT
CAP_MIN = 60               # max-hold backstop
DELAYS = [1, 2, 3, 5, 8, 10, 15]
REF_DELAY = 55             # OFI-horizon-matched proxy for the live 55s abs_veto
Q_A = [1, 2, 3, 5]         # Variant A half-window
M_GRID = [0.0, 0.5, 1.0]   # threshold = m * std(signed_ofi over base entries)
SESSION_GAP_MS = 3000
# ★2026-08-04 was hardcoded to 2026-07-09. depth_capture.py PRUNES on RETENTION_DAYS, so the real
# start walks forward — it is 07-15 today, not 07-09. A stale constant does not filter the dead zone,
# so pre-depth entries would survive into the sweep carrying no OFI and be scored as "no signal",
# quietly polluting every cell. Read the actual floor from the table instead of asserting it.
_dc = duckdb.connect()
_dc.execute(f"ATTACH '{DEPTH}' AS _d (TYPE sqlite, READ_ONLY)")
DEPTH_START = _dc.execute("SELECT min(ts_ms)/1000.0 FROM _d.depth_snap WHERE symbol='MNQ'").fetchone()[0]
_dc.close()
print(f"depth.db MNQ floor: {dt.datetime.fromtimestamp(DEPTH_START, dt.UTC):%Y-%m-%d %H:%M} UTC")
W = 15                     # run detection window (min)
GAP_MAX = 20 * 60

# ───────────────────────────── 1. OFI 1-second series from depth.db ─────────────────────────────
print("Loading depth.db + building 1s OFI series ...", flush=True)
con = duckdb.connect()
con.execute(f"ATTACH '{DEPTH}' AS d (TYPE sqlite, READ_ONLY)")
cols = ["ts_ms", "bid1p", "bid1s", "ask1p", "ask1s", "bid2p", "bid2s", "ask2p", "ask2s",
        "bid3p", "bid3s", "ask3p", "ask3s"]
dfk = con.execute(f"SELECT {','.join(cols)} FROM d.depth_snap WHERE symbol='MNQ' ORDER BY ts_ms").df()
con.close()
dfk = dfk[(dfk.bid1p > 0) & (dfk.ask1p > 0) & (dfk.ask1p >= dfk.bid1p)].reset_index(drop=True)
dfk["mid"] = (dfk.bid1p + dfk.ask1p) / 2.0


def level_ofi(bp, bs, ap, a_s):
    bp0, ap0, bs0, as0 = bp.shift(1), ap.shift(1), bs.shift(1), a_s.shift(1)
    eb = (bp >= bp0).astype(float) * bs - (bp <= bp0).astype(float) * bs0
    ea = -(ap <= ap0).astype(float) * a_s + (ap >= ap0).astype(float) * as0
    return eb + ea


dt_ms = dfk.ts_ms.diff()
dfk["session"] = (dt_ms > SESSION_GAP_MS).cumsum()
e1p, emlp = [], []
for _, g in dfk.groupby("session", sort=False):
    e1 = level_ofi(g.bid1p, g.bid1s, g.ask1p, g.ask1s)
    e2 = level_ofi(g.bid2p, g.bid2s, g.ask2p, g.ask2s)
    e3 = level_ofi(g.bid3p, g.bid3s, g.ask3p, g.ask3s)
    e1p.append(e1)
    emlp.append(e1.add(e2, fill_value=0).add(e3, fill_value=0))
dfk["ofi_l1"] = pd.concat(e1p).fillna(0.0)
dfk["ofi_ml"] = pd.concat(emlp).fillna(0.0)
dfk["sec"] = (dfk.ts_ms // 1000).astype(np.int64)
agg = dfk.groupby("sec").agg(ofi_l1=("ofi_l1", "sum"), ofi_ml=("ofi_ml", "sum"),
                             mid=("mid", "last"), session=("session", "last"))
ofi1_at = agg.ofi_l1.to_dict()
ofiml_at = agg.ofi_ml.to_dict()
sess_at = agg.session.to_dict()
OFI = {"L1": ofi1_at, "ML": ofiml_at}
print(f"  1s OFI buckets: {len(agg):,}  sessions: {agg.session.nunique()}", flush=True)

# ───────────────────────────── 2. bars + ticks from the unified loader ─────────────────────────────
print("Loading unified tape (archive_data) ...", flush=True)
D = A.load()
tts, tpx = D.tts, D.tpx      # tick ms / price (sorted)
mins, cls, hh, ll, vv = D.mins, D.cls, D.hh, D.ll, D.vv


def px_at(sec):
    """First trade tick at/after `sec`; (px, ms) or None if none within 10s."""
    j = np.searchsorted(tts, sec * 1000, "left")
    if j >= len(tts) or tts[j] > (sec + 10) * 1000:
        return None
    return float(tpx[j]), int(tts[j])


def replay_exit(side, entry_px, atr, entry_ms):
    """Vol-adaptive chandelier + native 1-ATR stop on real ticks after entry; 60-min cap.
    Returns (exit_px, exit_ms)."""
    j = np.searchsorted(tts, entry_ms, "right")
    end = entry_ms + CAP_MIN * 60000
    k = chandelier_start_k(atr)
    peak = 0.0
    while j < len(tts) and tts[j] <= end:
        px = float(tpx[j])
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak:
            peak = fav
        pos = Position(side, entry_px, atr, peak)
        r = (exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75)
             or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))
        if r:
            return px, int(tts[j])
        j += 1
    jj = min(j, len(tts) - 1)
    return float(tpx[jj]), int(tts[jj])


# ───────────────────────────── 3. reconstruct LIVE base entries ─────────────────────────────
# group bars by UTC day; trailing 60-bar window per day (matches gate_backtest*), reset each day.
days: dict = {}
for i in range(len(mins)):
    d = dt.datetime.fromtimestamp(int(mins[i]), dt.UTC).strftime("%Y-%m-%d")
    days.setdefault(d, []).append(Bar(int(mins[i]), float(cls[i]), float(hh[i]), float(ll[i]),
                                      float(cls[i]), float(vv[i])))  # open unused by features/gates

GATES = {
    "thrust_short": dict(side="SHORT", kind="thrust"),
    "grind_long":   dict(side="LONG",  kind="grind"),
}


def fires(kind, side, f):
    if kind == "thrust":
        e = gate_thrust(f, thr=1.5, amp_floor=0.0004)
    else:
        e = gate_grind(f, tape_net=0.0, slope_min=0.4, fast_slope=True)
    return e is not None and e.side == side


def base_entries(gate):
    """Live base entries: gate fires AND not er_blocks AND not atr_blocks, ONE-POSITION-AT-A-TIME
    (a new signal is ignored until the prior trade's RAW exit — exactly the live per-slot flat-gate,
    matching gate_backtest_tickhonest's next_ok=exit_ms). Each entry carries its tick-honest RAW pnl
    (enter at t0) + the raw exit ms. Returns the live base SEQUENCE; the OFI filters then keep/drop
    within this fixed set (they don't re-sequence — the position the gate ALREADY chose)."""
    spec = GATES[gate]
    side, kind = spec["side"], spec["kind"]
    out = []
    for _d, bars in days.items():
        cooldown_ms = 0
        for i in range(len(bars)):
            t0 = int(bars[i].ts) + 60          # decision = bar close second
            if t0 * 1000 < cooldown_ms:        # prior position still open
                continue
            w = bars[max(0, i - 59):i + 1]
            if len(w) < 6:
                continue
            f = compute_features(w)
            if not fires(kind, side, f):
                continue
            er = efficiency_ratio(w)
            if er_blocks(gate, er) or atr_blocks(gate, f.atr):
                continue
            pe = px_at(t0)
            if pe is None:                     # no tick fill → live desk wouldn't open either
                continue
            entry_px, entry_ms = pe
            exit_px, exit_ms = replay_exit(side, entry_px, f.atr, entry_ms)
            gross = ((exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)) * VPP
            out.append(dict(t0=t0, side=side, atr=f.atr, raw_pnl=gross - COST))
            cooldown_ms = exit_ms              # one-position-at-a-time until the RAW exit
    return out


# ───────────────────────────── 4. run detection (retention) ─────────────────────────────
N = len(mins)
rng = [hh[i:i + W + 1].max() - ll[i:i + W + 1].min()
       for i in range(0, N - W) if mins[i + W] - mins[i] <= GAP_MAX]
typ = float(np.median(rng)) if rng else 0.0
thr_run = 1.5 * typ
cands = []
for i in range(0, N - W):
    if mins[i + W] - mins[i] > GAP_MAX:
        continue
    mv = cls[i + W] - cls[i]
    if abs(mv) >= thr_run:
        cands.append((abs(mv), i, mv))
cands.sort(reverse=True)
runs, used = [], []
for _, i, mv in cands:
    if not any(abs(i - j) < W for j in used):
        used.append(i)
        runs.append((int(mins[i]), mv))
# only depth-covered runs (comparison window)
runs = [(s, mv) for s, mv in runs if s >= DEPTH_START]
UP = [s for s, mv in runs if mv > 0]
DN = [s for s, mv in runs if mv < 0]
RUN_SIDE = {"thrust_short": DN, "grind_long": UP}   # each gate's catchable runs


def runs_caught(entries, gate):
    """Set of run-start seconds this gate's entries catch (entry within [start-120, start+900])."""
    starts = RUN_SIDE[gate]
    hit = set()
    for e in entries:
        for s in starts:
            if s - 120 <= e["t0"] <= s + 900:
                hit.add(s)
    return hit


# ───────────────────────────── 5. signed OFI + trade evaluation ─────────────────────────────
def signed_ofi(t0, a, b, side, col):
    """Sum OFI over [t0+a, t0+b] (inclusive secs), same-session as t0, signed to trade side.
    None if t0 has no session or the window has zero coverage."""
    s0 = sess_at.get(t0)
    if s0 is None:
        return None
    tot, cnt = 0.0, 0
    for s in range(t0 + a, t0 + b + 1):
        v = col.get(s)
        if v is None or sess_at.get(s) != s0:
            continue
        tot += v
        cnt += 1
    if cnt == 0:
        return None
    return tot if side == "LONG" else -tot


def trade_pnl(side, atr, entry_sec):
    """Tick-honest net $ for entering at `entry_sec`; None if no fill."""
    pe = px_at(entry_sec)
    if pe is None:
        return None
    entry_px, entry_ms = pe
    exit_px, _ = replay_exit(side, entry_px, atr, entry_ms)
    gross = ((exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)) * VPP
    return gross - COST


def stat(pnls):
    n = len(pnls)
    if n == 0:
        return dict(n=0, net=0.0, win=float("nan"))
    a = np.array(pnls)
    return dict(n=n, net=float(a.sum()), win=float((a > 0).mean() * 100))


def fmt(s, kept, caught):
    if s["n"] == 0:
        return f"    ${0:>+6.0f} /   0        [{kept}/{caught}]"
    return f"    ${s['net']:>+7.0f} / {s['n']:>3} ({s['win']:>4.1f}%) [{kept}/{caught}]"


# ───────────────────────────── 6. RUN per gate ─────────────────────────────
def run_gate(gate):
    spec = GATES[gate]
    side = spec["side"]
    ents = base_entries(gate)
    # base population = the live sequence, restricted to depth-covered entries (OFI readable)
    base = [e for e in ents if sess_at.get(e["t0"]) is not None]
    caught_base = runs_caught(base, gate)
    ncaught = len(caught_base)

    raw_stat = stat([e["raw_pnl"] for e in base])
    lines = [f"\n{'='*104}",
             f"### {gate}   (side={side})   depth-covered base entries: n={len(base)}   "
             f"catchable {'DN' if gate=='thrust_short' else 'UP'} runs in window: {ncaught}",
             f"{'='*104}",
             f"  RAW baseline:{fmt(raw_stat, ncaught, ncaught)}"]

    # precompute per-entry signed OFI for each (variant-family, window, ofivar)
    results = []   # (label, d_or_q, ofivar, m, kind) -> stat + kept

    def eval_delay(d, ofivar, m, mode):
        """mode: 'veto' (skip only opposing) or 'confirm' (require aligned). Enter at t0+d."""
        col = OFI[ofivar]
        so = []
        for e in base:
            so.append(signed_ofi(e["t0"], 0, d, side, col))
        arr = np.array([x for x in so if x is not None], dtype=float)
        thr = m * arr.std() if len(arr) else 0.0
        kept_ents, pnls = [], []
        for e, s in zip(base, so):
            if mode == "veto":
                if s is not None and s < -thr:
                    continue         # clearly OPPOSING beyond thr -> the fakeout we skip
                # s is None (no reading) or not-opposing -> KEEP (veto only cuts fakeouts)
            else:  # confirm
                if s is None or s < thr:
                    continue         # not affirmatively aligned (or no reading) -> drop
            p = trade_pnl(side, e["atr"], e["t0"] + d)   # HONEST give-up: enter at t0+d
            if p is None:
                continue
            kept_ents.append(e)
            pnls.append(p)
        st = stat(pnls)
        kept = len(runs_caught(kept_ents, gate) & caught_base)
        return st, kept

    def eval_confirm_a(q, ofivar, m):
        """Contemporaneous confirm [t0-q,t0+q], NO give-up (enter at t0)."""
        col = OFI[ofivar]
        so = [signed_ofi(e["t0"], -q, q, side, col) for e in base]
        arr = np.array([x for x in so if x is not None], dtype=float)
        thr = m * arr.std() if len(arr) else 0.0
        kept_ents, pnls = [], []
        for e, s in zip(base, so):
            if s is None or s < thr:
                continue
            kept_ents.append(e)
            pnls.append(e["raw_pnl"])   # no give-up: same fill as raw
        st = stat(pnls)
        kept = len(runs_caught(kept_ents, gate) & caught_base)
        return st, kept

    # sweep
    veto_cells, confirm_cells, a_cells, ref_cells = [], [], [], []
    for ofivar in ("L1", "ML"):
        for m in M_GRID:
            for d in DELAYS:
                st, kept = eval_delay(d, ofivar, m, "veto")
                veto_cells.append((st, kept, dict(d=d, ofi=ofivar, m=m)))
                st2, kept2 = eval_delay(d, ofivar, m, "confirm")
                confirm_cells.append((st2, kept2, dict(d=d, ofi=ofivar, m=m)))
            for q in Q_A:
                sta, kepta = eval_confirm_a(q, ofivar, m)
                a_cells.append((sta, kepta, dict(q=q, ofi=ofivar, m=m)))
            # 55s reference proxy (both polarities)
            for mode, bucket in (("veto", "V"), ("confirm", "C")):
                st, kept = eval_delay(REF_DELAY, ofivar, m, mode)
                ref_cells.append((st, kept, dict(d=REF_DELAY, ofi=ofivar, m=m, mode=mode)))

    def best(cells):
        # best by net$ among cells that KEEP the winners (kept == ncaught if ncaught else n>0)
        pool = [c for c in cells if c[0]["n"] >= 10]
        if not pool:
            pool = cells
        # prefer retention-preserving cells
        keepers = [c for c in pool if c[1] >= ncaught] if ncaught else pool
        cand = keepers if keepers else pool
        return max(cand, key=lambda c: c[0]["net"]), max(pool, key=lambda c: c[0]["net"])

    def cell_line(tag, cell, note=""):
        st, kept, p = cell
        params = " ".join(f"{k}={v}" for k, v in p.items())
        fake = ""
        if ncaught and kept < ncaught and st["net"] > raw_stat["net"]:
            fake = "  ⚠FAKE-WIN (beats RAW only by dropping caught runs)"
        return f"  {tag:22}{fmt(st, kept, ncaught)}   [{params}]{note}{fake}"

    (bv_keep, bv_any) = best(veto_cells)
    (bc_keep, bc_any) = best(confirm_cells)
    (ba_keep, ba_any) = best(a_cells)
    # 55s reference: best of each polarity that keeps winners
    ref_v = [c for c in ref_cells if c[2]["mode"] == "veto"]
    ref_c = [c for c in ref_cells if c[2]["mode"] == "confirm"]
    brv = max([c for c in ref_v if not ncaught or c[1] >= ncaught] or ref_v, key=lambda c: c[0]["net"])
    brc = max([c for c in ref_c if not ncaught or c[1] >= ncaught] or ref_c, key=lambda c: c[0]["net"])

    lines.append("\n  -- best RETENTION-PRESERVING cell (keeps all caught runs) --")
    lines.append(cell_line("delay VETO (B1)", bv_keep))
    lines.append(cell_line("delay CONFIRM (B2)", bc_keep))
    lines.append(cell_line("contemp CONFIRM (A)", ba_keep))
    lines.append(cell_line("55s VETO  proxy (ref)", brv))
    lines.append(cell_line("55s CONFIRM proxy(ref)", brc))
    lines.append("\n  -- best cell by net$ IGNORING retention (may be a fake win) --")
    lines.append(cell_line("delay VETO (B1)", bv_any))
    lines.append(cell_line("delay CONFIRM (B2)", bc_any))
    lines.append(cell_line("contemp CONFIRM (A)", ba_any))
    return "\n".join(lines), dict(gate=gate, raw=raw_stat, ncaught=ncaught,
                                  bv_keep=bv_keep, bc_keep=bc_keep, ba_keep=ba_keep,
                                  bv_any=bv_any, bc_any=bc_any, brv=brv, brc=brc)


_w0 = dt.datetime.fromtimestamp(DEPTH_START, dt.UTC)
print(f"\nWindow: {_w0:%Y-%m-%d}..{dt.datetime.now(dt.UTC):%Y-%m-%d} (actual depth.db extent) | "
      f"MNQ ${VPP}/pt | cost ${COST:.2f}/tr (fee ${FEE_RT:.2f} + slip ${SLIP_RT:.2f}) | "
      f"exit=chandelier+1ATR stop tick-honest, {CAP_MIN}min cap")
print(f"Runs in depth window: UP={len(UP)}  DN={len(DN)}  (typical 15m range {typ:.0f}pt, run>=1.5x)")

summaries = {}
for gate in ("thrust_short", "grind_long"):
    txt, summ = run_gate(gate)
    print(txt)
    summaries[gate] = summ

print(f"\n{'='*104}\nREADING: 'net$ / n (win%) [runs-kept/caught]'.  A cell beats RAW only by dropping "
      f"caught runs = FAKE (flagged).\nGive-up is charged honestly (delayed variants enter at t0+d "
      f"tick price).  In-sample, one summer regime, MNQ, 250ms-cadence.\n{'='*104}")
