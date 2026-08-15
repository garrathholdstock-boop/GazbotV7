#!/usr/bin/env python3
"""REV2 Q3 — is the live-vs-shadow abs_veto_short gap the LADDER, or is it FILLS?

Part 2 §3 diagnoses a $2,349 gap (shadow +$1,828.50 vs live −$520.50 over the same window)
as "the exit ladder is too wide", inferred ENTIRELY from the exit-reason mix: same winner size,
33% bigger losers. But this desk's own standing finding is that live losses run 1.1–3.1× the
modelled ones, and "we get filled worse than the repricer assumes" produces exactly the same
table. Nothing in §3 measured a single fill. This does.

METHOD
  * Every live abs_veto_short LEG from 26 July (the day the live gate started filling).
  * The desk's OWN geometry, recomputed rather than assumed: R = stop_atr_mult(=1.0) × the
    ATR-14 the gate would have read at the entry minute, using deciders._atr's halt-aware
    rule, on 1-minute bars folded from the same 5-second tape the desk folds.
  * Levels from data/exit_overrides.json as it was for this gate: stop = entry + 1.0R,
    Lot A target = entry − 1.5R, Lot B target = entry − 2.5R (a SHORT).
  * SLIPPAGE = actual fill − the level, signed so POSITIVE IS ADVERSE on a short.
  * Then the shadow twin (abs_veto_55s SHORT, 118 trades, its own recorded entry_atr /
    target_r / stop_atr_mult) is re-run with the MEASURED slippage applied to its stops and
    its targets, and we ask how much of the $2,349 survives.

  PYTHONPATH=src ./.venv/bin/python scripts/rev2_absveto_slippage.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sqlite3
import statistics

import numpy as np

DESK = "/home/alphabot/gazbot7/data/gazbot7.db"
SHADOW = "/home/alphabot/gazbot7/data/shadow.db"
TAPE = "/home/alphabot/gazbot7/scratchpad/tape5s.npz"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_absveto_slippage.json"
VPP, FEE = 2.0, 1.50
SINCE = "2026-07-26"
STOP_MULT, A_R, B_R = 1.0, 1.5, 2.5
A_LO_USD, B_LO_R, B_FLOOR_USD = 40.0, 1.75, 60.0   # the 2026-08-02 quiet-tape clip
CONTIG_S = 90

# ── 1-minute bars folded from the 5s tape (what agg.MinuteBars does live) ────────────
z = np.load(TAPE)
_ts, _h, _l, _c = z["ts"].astype(np.int64), z["h"], z["l"], z["c"]
_m: dict[int, list[float]] = {}
for i in range(len(_ts)):
    k = int(_ts[i]) // 60 * 60
    r = _m.get(k)
    if r is None:
        _m[k] = [float(_h[i]), float(_l[i]), float(_c[i])]
    else:
        r[0] = max(r[0], float(_h[i])); r[1] = min(r[1], float(_l[i])); r[2] = float(_c[i])
MIN_TS = np.array(sorted(_m))
MIN_H = np.array([_m[t][0] for t in MIN_TS])
MIN_L = np.array([_m[t][1] for t in MIN_TS])
MIN_C = np.array([_m[t][2] for t in MIN_TS])


def atr14(ts_s: int) -> float:
    """deciders._atr, halt-aware, on the 14 minutes ending at (not including) the entry minute."""
    j = int(np.searchsorted(MIN_TS, ts_s, side="right"))
    i0 = max(1, j - 15)
    trs = []
    for i in range(i0, j):
        hl = MIN_H[i] - MIN_L[i]
        if MIN_TS[i] - MIN_TS[i - 1] <= CONTIG_S:
            trs.append(max(hl, abs(MIN_H[i] - MIN_C[i - 1]), abs(MIN_L[i] - MIN_C[i - 1])))
        else:
            trs.append(hl)
    return float(sum(trs[-14:]) / len(trs[-14:])) if trs else 0.0


def main() -> None:
    con = sqlite3.connect(f"file:{DESK}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT id, gate, entry_price, exit_price, opened_at, closed_at, pnl_usd, exit_reason "
        "FROM trades WHERE gate LIKE 'abs_veto_short%' AND opened_at >= ? "
        "AND data_quality IS NULL ORDER BY opened_at", (SINCE,)).fetchall()
    con.close()
    print(f"{len(rows)} live abs_veto_short legs since {SINCE}, "
          f"net ${sum(r[6] for r in rows):,.2f}")

    legs, no_tape = [], 0
    for tid, gate, ep, xp, t0, t1, pnl, why in rows:
        ts = int(dt.datetime.fromisoformat(t0).timestamp())
        atr = atr14(ts)
        if atr <= 0:
            no_tape += 1
            continue
        # ★ THE LEVEL HAS TO BE THE ONE THAT WAS ACTUALLY RUNNING. The quiet-tape clip
        # (atr_split 22 → Lot A takes a flat $40, Lot B max(1.75R, $60)) went in on 2 August;
        # data/exit_overrides.json.pre-0801-TRUE shows the plain 1.5R/2.5R ladder before it.
        # Modelling one ladder across the whole window would manufacture ~9pt of fake target
        # slippage on every quiet-tape leg.
        b_leg = gate.endswith("_B")
        stop_lvl = ep + STOP_MULT * atr
        if t0 >= "2026-08-02" and atr < 22:                  # quiet-tape clip, per-lot qty 1
            tgt_pt = max(B_LO_R * atr, B_FLOOR_USD / VPP) if b_leg else A_LO_USD / VPP
        else:
            tgt_pt = (B_R if b_leg else A_R) * atr           # pre-split legs took Lot A's ladder
        tgt_lvl = ep - tgt_pt
        slip = None
        if why == "STOP":
            slip = xp - stop_lvl                          # + = filled ABOVE the stop = adverse
        elif why == "TARGET":
            slip = xp - tgt_lvl                           # + = filled ABOVE the target = adverse
        legs.append(dict(id=tid, gate=gate, why=why, entry=ep, exit=xp, atr=round(atr, 2),
                         stop=round(stop_lvl, 2), tgt=round(tgt_lvl, 2), pnl=pnl,
                         slip=None if slip is None else round(slip, 3),
                         day=t0[:10]))
    print(f"{len(legs)} legs priced ({no_tape} with no tape at the entry minute)\n")

    res = {"n_legs": len(rows), "n_priced": len(legs), "live_net": round(sum(r[6] for r in rows), 2),
           "by_exit": {}, "slippage": {}}

    print(f"{'exit':16s}{'legs':>5s}{'net$':>11s}{'slip legs':>10s}{'median':>9s}{'mean':>9s}"
          f"{'p90':>9s}{'worst':>9s}{'$ cost':>10s}")
    for why in sorted({l["why"] for l in legs}):
        sub = [l for l in legs if l["why"] == why]
        sl = [l["slip"] for l in sub if l["slip"] is not None]
        cost = sum(sl) * VPP if sl else 0.0
        res["by_exit"][why] = {
            "legs": len(sub), "net": round(sum(l["pnl"] for l in sub), 2),
            "measured": len(sl),
            "median_pt": round(statistics.median(sl), 3) if sl else None,
            "mean_pt": round(statistics.mean(sl), 3) if sl else None,
            "p90_pt": round(sorted(sl)[int(0.9 * (len(sl) - 1))], 3) if sl else None,
            "worst_pt": round(max(sl), 3) if sl else None,
            "dollar_cost": round(cost, 2)}
        e = res["by_exit"][why]
        print(f"{why:16s}{len(sub):5d}{e['net']:11,.2f}{len(sl):10d}"
              + ("".join(f"{v:9.2f}" for v in (e['median_pt'], e['mean_pt'], e['p90_pt'],
                                               e['worst_pt'])) if sl else " " * 36)
              + f"{cost:10,.2f}")

    allslip = [l["slip"] for l in legs if l["slip"] is not None]
    res["slippage"] = {"n": len(allslip),
                       "median_pt": round(statistics.median(allslip), 3),
                       "mean_pt": round(statistics.mean(allslip), 3),
                       "total_dollar": round(sum(allslip) * VPP, 2),
                       "adverse_legs": sum(1 for v in allslip if v > 0.01),
                       "at_or_better": sum(1 for v in allslip if v <= 0.01)}
    s = res["slippage"]
    print(f"\nALL measurable legs  n={s['n']}  median {s['median_pt']:+.2f}pt  "
          f"mean {s['mean_pt']:+.2f}pt  total ${s['total_dollar']:+,.2f}  "
          f"({s['adverse_legs']} filled worse than the level, {s['at_or_better']} at it or better)")

    # ── re-run the shadow twin with the MEASURED slippage ────────────────────────────
    sc = sqlite3.connect(f"file:{SHADOW}?mode=ro", uri=True)
    tw = sc.execute(
        "SELECT t.id, t.entry_price, t.entry_atr, t.target_r, t.stop_atr_mult, t.exit_price, "
        "t.exit_reason, r.real_pnl, t.qty FROM shadow_trades t JOIN shadow_real r "
        "ON r.trade_id = t.id WHERE t.strategy='abs_veto_55s' AND t.side='SHORT' "
        "AND t.entry_ts >= strftime('%s', ?) AND t.data_quality IS NULL", (SINCE,)).fetchall()
    sc.close()
    base = sum(r[7] for r in tw)
    stop_slip = res["by_exit"].get("STOP", {}).get("median_pt") or 0.0
    tgt_slip = res["by_exit"].get("TARGET", {}).get("median_pt") or 0.0
    mix = collections.Counter(r[6] for r in tw)
    adj = 0.0
    for _id, ep, atr, tr, sm, xp, why, pnl, qty in tw:
        extra = 0.0
        if why == "STOP":
            extra = -stop_slip * VPP * qty        # a short filled ABOVE its stop loses more
        elif why == "TARGET":
            extra = -tgt_slip * VPP * qty
        adj += pnl + extra
    live_net = res["live_net"]
    res["twin"] = {"n": len(tw), "shadow_net": round(base, 2),
                   "exit_mix": dict(mix),
                   "stop_slip_pt": round(stop_slip, 3), "tgt_slip_pt": round(tgt_slip, 3),
                   "shadow_net_with_measured_slippage": round(adj, 2),
                   "gap_before": round(base - live_net, 2),
                   "gap_after": round(adj - live_net, 2),
                   "closed_by_slippage": round(base - adj, 2),
                   "pct_of_gap_closed": round(100.0 * (base - adj) / (base - live_net), 1)}
    t = res["twin"]
    print(f"\nSHADOW TWIN abs_veto_55s SHORT  n={t['n']}  {t['exit_mix']}")
    print(f"  as scored                        ${t['shadow_net']:9,.2f}")
    print(f"  with the measured slippage       ${t['shadow_net_with_measured_slippage']:9,.2f}")
    print(f"  live                             ${live_net:9,.2f}")
    print(f"  gap before ${t['gap_before']:,.2f} → after ${t['gap_after']:,.2f}  "
          f"({t['pct_of_gap_closed']}% of the gap is fills)")

    json.dump({"legs": legs, **res}, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
