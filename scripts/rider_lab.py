#!/usr/bin/env python3
"""RIDER LAB — one harness for designing the 4-lot day-rider. Import it; do not re-derive it.

Operator, 2026-08-19: *"design a complete robust system. that buys 4 lots. identifies quickly if
its a bad buy and its turning around. gets out quick via a market sell … then assess the best R
profit takes … 3 and 4 need to be generous as they are the ones to let run and i will claim
profit."*

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IS ALREADY ESTABLISHED (do not re-derive; build on it)
  · 231 confirmed sessions, 2025-09-15 .. 2026-08-18, from driftlab's causal replay of drift.compute()
  · Reaching a level (2-lot $4/pt labels): 50pt 71% · 100pt 39% · 200pt 11% · 400pt 1.7%
  · PEAK BUCKET -> OUTCOME is monotone and is the core design fact:
        peak   0-12.5pt  n=10  100% end red      peak 100-200pt n=66  44% red
        peak  12.5-25pt  n=17   94% end red      peak 200-400pt n=46  13% red
        peak    25-50pt  n=25   92% end red      peak    400+pt n=22   0% RED, median +377
        peak   50-100pt  n=45   87% end red
    A day that cannot make 100pt is a losing day. A day that makes 400pt has never lost.
  · DISASTERS PEAK SMALL AND EARLY: 19 of the worst 22 peaked <130pt, most within 6 minutes.
  · 10 sessions never go green at all. Adverse-cut separation: 200pt kills 4 winners whose COMBINED
    peak is 229pt and saves 523pt; 250pt kills 1 (peak 90pt) and saves 373pt; 400pt kills none.
  · MAE BEFORE the first rung: median 15pt, p75 37.5, p90 70, max 373. Anything tighter than ~50pt
    cuts real winners. A cut at 0 ("sell when red") exits every session at fees — 0% green days.
  · THE OPERATOR CLAIMS BY HAND at a measured median 86% of peak, ~33s and 7.2pt off the high.
  · Full per-session table: reports/rider_sessions_full.csv

★★★ THE TRAP THAT HAS ALREADY KILLED ONE RESULT. A 4-lot ladder at 12.5/25/50/100pt with
breakeven-after-lot-1 scored +$7,194 and survived strip-best-10, both years and both directions —
then went to −$12,090 on TWO MINUTES of entry delay. driftlab's own docstring says the live service
confirms ~8 min / 52pt later than the lab, so its entries are optimistic. ANY candidate must be
reported across `entry_delay_min` 0/2/4/8 and is only real if it survives all of them.
────────────────────────────────────────────────────────────────────────────────────────────────

SIZING: 4 lots x $2.00/pt = $8.00/pt for the position. Fee $1.50/RT per lot.
A dollar figure quoted for the POSITION is points x 8. Per LOT it is points x 2.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field

GB = "/home/alphabot/gazbot7"
VPP, FEE_RT = 2.0, 1.50
OPEN_MIN, FLAT_MIN, WARM = 13 * 60 + 30, 20 * 60 + 40, 60


@dataclass
class Cfg:
    """One system design. All distances in POINTS unless the name says usd."""
    rungs: list = field(default_factory=lambda: [12.5, 25.0, 50.0, 100.0])  # None = no target
    lots: int = 4
    # ── the adverse cut (the "bad buy" market-sell) ──
    adverse_cut_pt: float = 200.0        # hard cut, points against entry. 0 disables
    # ★2026-08-26 REV2 — an ATR-MULTIPLE hard cut, so the venue-stop question ("3.0xATR or naked?")
    # can be raced on the SAME 231 sessions the no-stop decision was taken on. Points-based cuts
    # are not comparable across a year of changing volatility; the live proposal is stated in ATR.
    # Ignored when adverse_cut_pt is set. The ATR is the SAME arm_atr frozen at entry that the live
    # trail uses, so the stop and the trail are measured off one number, not two.
    adverse_cut_atr: float = 0.0         # 0 disables
    # progress test: if peak < progress_pt by minute progress_by_min, flatten at market
    progress_pt: float = 0.0             # 0 disables
    progress_by_min: int = 0
    # ── management after fills ──
    breakeven_after_lot: int = 1         # 0 disables; move remainder to entry after lot N fills
    be_offset_pt: float = 0.0            # place the breakeven this far in profit
    trail_arm_pt: float = 0.0            # 0 = use the ATR trail; else arm at this many points
    trail_atr_arm: float = 4.0           # ARM_ATR_MULT (the live rider)
    trail_atr_mult: float = 2.0          # TRAIL_ATR_MULT
    # ── the operator's hand on the last lots ──
    manual_lots: tuple = ()              # lot indices exited by the operator, not by a target
    manual_capture: float = 0.86         # fraction of that lot's PEAK he banks (measured)
    # ── realism ──
    entry_delay_min: int = 0
    slippage_pt: float = 0.0             # charged on every market exit (cut/flat), not on targets


def sessions():
    d = json.load(open(f"{GB}/data/driftlab/_persistence_lake.json"))
    return [r for r in d["by_symbol"]["MNQ_lake"]
            if r.get("confirmed") and r.get("minute") is not None]


def day_bars(con, day):
    from gazbot7.deciders import Bar
    t0 = dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp()
    rows = con.execute(
        "SELECT bar_ts,open,high,low,close,volume FROM bars WHERE symbol='MNQ' "
        "AND timeframe='1min' AND bar_ts>=? AND bar_ts<? ORDER BY bar_ts",
        [int(t0), int(t0 + 86400)]).fetchall()
    return [Bar(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5] or 0))
            for r in rows]


def run_session(bars, conf_min, direction, cfg: Cfg):
    """One session. Returns dict or None.

    ★ RACE DISCIPLINE: within every bar the ADVERSE extreme is applied first — cuts, stops and the
      progress test are evaluated against it BEFORE any target may fill on the favourable extreme.
      Intrabar ordering is unknowable on 1-min bars, so the pessimistic order is the honest one.
    ★ CAUSAL: driftlab's confirmation bar N is complete only at N+1, so entry is the OPEN of N+1.
    """
    from gazbot7.deciders import _atr
    by_min = {}
    for i, b in enumerate(bars):
        t = dt.datetime.fromtimestamp(b.ts, dt.UTC)
        by_min[t.hour * 60 + t.minute] = i
    ci = by_min.get(OPEN_MIN + conf_min + cfg.entry_delay_min)
    if ci is None or ci + 1 >= len(bars) or ci < WARM:
        return None
    ei = ci + 1
    entry = bars[ei].open
    arm_atr = _atr(bars[max(0, ei - WARM):ei])
    d = 1 if direction == "UP" else -1

    n = cfg.lots
    open_lots = list(range(n))
    fills = [None] * n
    peak = 0.0                      # favourable excursion, points
    peak_by_lot = [0.0] * n
    be_level = None
    t_peak = 0

    def close_all(px, reason, i):
        for k in list(open_lots):
            fills[k] = (px, reason, i)
        open_lots.clear()

    for i in range(ei, len(bars)):
        if not open_lots:
            break
        b = bars[i]
        t = dt.datetime.fromtimestamp(b.ts, dt.UTC)
        mins = i - ei
        if t.hour * 60 + t.minute >= FLAT_MIN:
            close_all(b.open - d * cfg.slippage_pt, "FLAT_2040", i)
            break
        lo = d * ((b.low if d > 0 else b.high) - entry)     # adverse extreme, signed
        hi = d * ((b.high if d > 0 else b.low) - entry)     # favourable extreme, signed

        # ── 1. ADVERSE FIRST ──────────────────────────────────────────────
        cut_pt = cfg.adverse_cut_pt or (cfg.adverse_cut_atr * arm_atr)
        if cut_pt and lo <= -cut_pt:
            close_all(entry - d * (cut_pt + cfg.slippage_pt), "ADVERSE_CUT", i)
            break
        if be_level is not None and lo <= be_level:
            close_all(entry + d * (be_level - cfg.slippage_pt), "BREAKEVEN", i)
            break
        if cfg.trail_arm_pt or arm_atr > 0:
            arm = cfg.trail_arm_pt or cfg.trail_atr_arm * arm_atr
            width = (cfg.trail_atr_mult * arm_atr) if not cfg.trail_arm_pt else cfg.trail_arm_pt / 2
            if peak >= arm and lo <= peak - width:
                close_all(entry + d * (peak - width - cfg.slippage_pt), "TRAIL", i)
                break
        # progress test — evaluated on the running peak, so it can only fire on a day that
        # has FAILED to get going. Checked after the adverse extreme, before any target.
        if cfg.progress_pt and mins >= cfg.progress_by_min and peak < cfg.progress_pt:
            close_all(b.close - d * cfg.slippage_pt, "NO_PROGRESS", i)
            break

        # ── 2. targets / peak ─────────────────────────────────────────────
        for k in list(open_lots):
            if k in cfg.manual_lots:
                continue
            tgt = cfg.rungs[k] if k < len(cfg.rungs) else None
            if tgt is not None and hi >= tgt:
                fills[k] = (entry + d * tgt, "TARGET", i)
                open_lots.remove(k)
                if cfg.breakeven_after_lot and (k + 1) == cfg.breakeven_after_lot:
                    be_level = cfg.be_offset_pt
        if hi > peak:
            peak, t_peak = hi, mins
        for k in open_lots:
            peak_by_lot[k] = peak

    for k in list(open_lots):        # tape ran out
        fills[k] = (bars[-1].close, "EOD", len(bars) - 1)

    # the operator's lots: he banks `manual_capture` of the peak that lot saw while open
    total = 0.0
    per_lot = []
    for k in range(n):
        px, reason, i = fills[k]
        if k in cfg.manual_lots and reason in ("FLAT_2040", "EOD", "TRAIL"):
            gain = peak_by_lot[k] * cfg.manual_capture
            pnl = gain * VPP - FEE_RT
            reason = "MANUAL_CLAIM"
        else:
            pnl = d * (px - entry) * VPP - FEE_RT
        per_lot.append((reason, round(pnl, 2)))
        total += pnl
    return dict(total=round(total, 2), per_lot=per_lot, peak=round(peak, 1), t_peak=t_peak)


def run_all(con, cfg: Cfg, S=None):
    S = S or sessions()
    cache = getattr(run_all, "_cache", None)
    if cache is None:
        cache = run_all._cache = {}
    out = []
    for s in S:
        day = s["day"]
        if day not in cache:
            cache[day] = day_bars(con, day)
        r = run_session(cache[day], int(s["minute"]), s["dir"], cfg)
        if r:
            r.update(day=day, dir=s["dir"], year=s.get("year"), rt=s.get("rt"))
            out.append(r)
    return out


def summarise(rows, label=""):
    import statistics as st
    if not rows:
        return {}
    p = [r["total"] for r in rows]
    sp = sorted(p)
    return dict(label=label, n=len(p), total=round(sum(p), 0), per_session=round(sum(p) / len(p), 2),
                median=round(st.median(p), 0), green=round(100 * sum(1 for x in p if x > 0) / len(p), 1),
                worst=round(sp[0], 0), best=round(sp[-1], 0),
                strip_best5=round(sum(p) - sum(sp[-5:]), 0))


if __name__ == "__main__":
    from gazbot7.lake import connect
    con = connect(symbol="MNQ")
    base = Cfg()
    for delay in (0, 2, 4, 8):
        base.entry_delay_min = delay
        print(summarise(run_all(con, base), f"baseline delay={delay}"))
