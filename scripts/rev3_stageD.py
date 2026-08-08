#!/usr/bin/env python3
"""REV-3c — the four numbers the operator asked for, plus the attempts to kill them.

  D1  LAG COST per big run on 07-29 / 07-30, in POINTS and DOLLARS: the price the FAST layer would
      first have signalled at, against the price the closed-minute SLOW layer fired at.
  D2  ANCHOR TO LIVE: for every real abs_veto / grind fill on those two days, would the two-layer
      build have entered earlier, and at what price?  Points and dollars per live trade.
  D3  CHURN on the chop days: extra fires the fast layer adds where the slow layer never fired,
      and their raced P&L.
  D4  THE KILL BATTERY — side symmetry, strip-best-3, leave-one-day-out, one extra tick of
      slippage each way, the escalation-parameter plateau, partial-ATR, and the faders with the
      escalation gate removed entirely.

  PYTHONPATH=src ./.venv/bin/python scripts/rev3_stageD.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb

import rev3_two_layer as R

OUT = f"{R.SCRATCH}/rev3_stageD.json"
TREND_DAYS = ["2026-07-29", "2026-07-30"]
BAR_GATES = ["abs_veto_long", "abs_veto_short", "grind_long"]
ALL = set(R.REGIMES)
TREND_CELLS = {"TREND_ALIGNED"}


def fires_for(d, tag, cells, filt):
    _, fires = R.simulate(d, tag, fast_cells=cells, filt=filt, collect=True)
    return fires


# ══════════════════════════════════════════════════════════════════════════════════════════
def d1_runs(data, min_atr=1.5):
    """run_census's own run definition (15-min close-to-close move >= min_atr x the typical 15-min
    range), then for each run the first SLOW fire and the first FAST fire aligned with it."""
    con = duckdb.connect()
    rows = con.execute(f"SELECT bar_ts,open,high,low,close FROM '{R.SCRATCH}/bars5s.parquet' ORDER BY bar_ts").fetchall()
    con.close()
    W, STEP = 180, 12
    rng = [max(x[2] for x in rows[i:i + W]) - min(x[3] for x in rows[i:i + W])
           for i in range(0, len(rows) - W, STEP)]
    typ = sorted(rng)[len(rng) // 2]
    thr = min_atr * typ
    cands = sorted(((abs(rows[i + W][4] - rows[i][4]), i, rows[i + W][4] - rows[i][4])
                    for i in range(0, len(rows) - W, STEP)
                    if abs(rows[i + W][4] - rows[i][4]) >= thr), reverse=True)
    runs, used = [], []
    for _, i, mv in cands:
        if not any(abs(i - j) < W for j in used):
            used.append(i)
            runs.append((rows[i][0], mv))
    runs.sort()

    out = []
    for day in TREND_DAYS:
        d = data[day]
        allf = {}
        for tag in BAR_GATES:
            allf[tag] = dict(slow=[f for f in fires_for(d, tag, set(), R.BASE) if f[1] == "slow"],
                             fast=[f for f in fires_for(d, tag, ALL, R.BASE) if f[1] == "fast"])
        for start, mv in runs:
            if not (d["t0"] <= start < d["t1"]):
                continue
            side = "LONG" if mv > 0 else "SHORT"
            lo, hi = start - 300, start + 900
            rec = dict(day=day, start=start,
                       t=dt.datetime.fromtimestamp(start, dt.UTC).strftime("%m-%d %H:%M"),
                       dir="UP" if mv > 0 else "DN", move=round(mv, 1),
                       ceil_1lot=round(abs(mv) * R.VPP, 0), gates={})
            for tag in BAR_GATES:
                if R.GATES[tag]["side"] != side:
                    continue
                s = [f for f in allf[tag]["slow"] if lo <= f[0] <= hi]
                fa = [f for f in allf[tag]["fast"] if lo <= f[0] <= hi]
                if not s and not fa:
                    continue
                s0 = s[0] if s else None
                f0 = fa[0] if fa else None
                g = dict(slow_sec=s0[0] if s0 else None, slow_px=s0[2] if s0 else None,
                         fast_sec=f0[0] if f0 else None, fast_px=f0[2] if f0 else None)
                # the live abs_veto fill is 55s AFTER the slow signal (the absorption veto)
                if s0 and R.GATES[tag]["veto"]:
                    i = s0[0] + R.VETO_SECS - d["t_lo"]
                    g["live_fill_sec"] = s0[0] + R.VETO_SECS
                    g["live_fill_px"] = float(d["dec"][i]) if 0 <= i < len(d["dec"]) else None
                else:
                    g["live_fill_sec"], g["live_fill_px"] = g["slow_sec"], g["slow_px"]
                if f0 and g["live_fill_px"] is not None:
                    imp = (g["live_fill_px"] - f0[2]) if side == "LONG" else (f0[2] - g["live_fill_px"])
                    g["lag_pt"] = round(imp, 2)
                    g["lag_usd_2lot"] = round(imp * R.VPP * 2, 1)
                    g["seconds_earlier"] = g["live_fill_sec"] - f0[0]
                rec["gates"][tag] = g
            if rec["gates"]:
                out.append(rec)
    return dict(typ_15m_range=round(typ, 1), threshold_pt=round(thr, 1), runs=out)


# ══════════════════════════════════════════════════════════════════════════════════════════
def d2_live(data):
    """Every real abs_veto / grind fill on the two trend days, matched to the nearest EARLIER fast
    fire on the same gate+side (within 180s — the widest the lag can be: 65s bar + 55s veto + slack)."""
    con = duckdb.connect()
    con.execute("ATTACH '/home/alphabot/gazbot7/data/gazbot7.db' AS g (TYPE sqlite, READ_ONLY)")
    tr = con.execute("""
        SELECT gate, side, CAST(epoch(opened_at::TIMESTAMPTZ) AS BIGINT) te, entry_price, exit_price,
               pnl_usd, exit_reason, qty
        FROM g.trades WHERE symbol='MNQ'
          AND epoch(opened_at::TIMESTAMPTZ) >= epoch('2026-07-28 22:00:00'::TIMESTAMP)
          AND epoch(opened_at::TIMESTAMPTZ) <  epoch('2026-07-30 21:00:00'::TIMESTAMP)
        ORDER BY te""").fetchall()
    con.close()
    fast = {}
    for day in TREND_DAYS:
        for tag in BAR_GATES:
            fast[(day, tag)] = [f for f in fires_for(data[day], tag, ALL, R.BASE) if f[1] == "fast"]
    rows = []
    for gate, side, te, ep, xp, pnl, reason, qty in tr:
        base = gate[:-2] if gate.endswith(("_A", "_B")) else gate
        if base not in BAR_GATES:
            continue
        day = TREND_DAYS[0] if te < R.paris_window(TREND_DAYS[1])[0] else TREND_DAYS[1]
        cands = [f for f in fast.get((day, base), []) if te - 180 <= f[0] <= te]
        rec = dict(gate=gate, side=side, te=te,
                   t=dt.datetime.fromtimestamp(te, dt.UTC).strftime("%m-%d %H:%M:%S"),
                   entry=ep, live_pnl=pnl, reason=reason, qty=qty)
        if cands:
            f0 = cands[0]
            imp = (ep - f0[2]) if side == "LONG" else (f0[2] - ep)
            rec.update(fast_sec=f0[0], fast_px=f0[2], earlier_s=te - f0[0],
                       better_pt=round(imp, 2), better_usd=round(imp * R.VPP * qty, 1))
        rows.append(rec)
    return rows


# ══════════════════════════════════════════════════════════════════════════════════════════
def d4_kill(data):
    days = R.DAYS
    k = {}

    def totals(tag, cells, filt, **kw):
        per = {}
        base = {}
        for d in days:
            per[d] = R.agg(R.simulate(data[d], tag, fast_cells=cells, filt=filt, **kw)[0])
            base[d] = R.agg(R.simulate(data[d], tag, fast_cells=set(), filt=filt, **kw)[0])
        return {d: round(per[d]["pnl"] - base[d]["pnl"], 2) for d in days}, per, base

    # 1. SIDE SYMMETRY — the pair-sum surface for thrust in an aligned trend
    sym = []
    for m in (1.0, 1.15, 1.3, 1.5):
        for p in (1, 2, 3, 4):
            filt = dict(pers=p, mag=m, elap=15, flow=0.0)
            dl, _, _ = totals("abs_veto_long", TREND_CELLS, filt)
            ds, _, _ = totals("abs_veto_short", TREND_CELLS, filt)
            sym.append(dict(pers=p, mag=m, long=round(sum(dl.values()), 1),
                            short=round(sum(ds.values()), 1),
                            pair=round(sum(dl.values()) + sum(ds.values()), 1)))
    k["side_symmetry"] = sym

    # 2. the winner cell under stress
    win = ("abs_veto_long", TREND_CELLS, dict(pers=2, mag=1.15, elap=15, flow=0.0))
    stress = {}
    for name, kw in (("as_measured", {}), ("slip_1tick", dict(slip=1.0)),
                     ("partial_ATR", dict(atr_mode="partial"))):
        dl, per, base = totals(*win, **kw)
        stress[name] = dict(per_day=dl, total=round(sum(dl.values()), 1),
                            lodo_worst=round(min(sum(dl.values()) - v for v in dl.values()), 1))
    # strip-best-3 fast trades
    tr_all, tr_base = [], []
    for d in days:
        tr_all += [t for t in R.simulate(data[d], win[0], fast_cells=win[1], filt=win[2])[0]]
        tr_base += [t for t in R.simulate(data[d], win[0], fast_cells=set(), filt=win[2])[0]]
    ft = sorted((t for t in tr_all if t["kind"] == "fast"), key=lambda t: -t["pnl"])
    stress["strip_best3_fast"] = dict(
        n_fast=len(ft), pnl_fast=round(sum(t["pnl"] for t in ft), 1),
        pnl_fast_minus_best3=round(sum(t["pnl"] for t in ft[3:]), 1),
        top3=[t["pnl"] for t in ft[:3]],
        delta_after_strip=round(sum(t["pnl"] for t in tr_all) - sum(t["pnl"] for t in ft[:3])
                                - sum(t["pnl"] for t in tr_base), 1))
    k["winner_under_stress"] = stress

    # 3. escalation-parameter plateau (the escalation is the only slow-side design choice)
    esc_rows = []
    save = dict(R.ESC)
    for em in (1.00, 1.05, 1.10, 1.20, 1.30):
        for bb in (0.0, 0.25, 0.50):
            R.ESC.update(exp_mult=em, brk_buf=bb)
            for d in days:                       # escalation is baked into the cache -> rebuild
                cache = f"{R.SCRATCH}/ck_{d}.pkl"
                if os.path.exists(cache):
                    os.remove(cache)
            reb = {d: R.build_day(d) for d in days}
            dl, _, _ = totals("abs_veto_long", TREND_CELLS, win[2])
            ds, _, _ = totals("abs_veto_short", TREND_CELLS, win[2])
            esc_rows.append(dict(exp_mult=em, brk_buf=bb, long=round(sum(dl.values()), 1),
                                 short=round(sum(ds.values()), 1),
                                 pair=round(sum(dl.values()) + sum(ds.values()), 1)))
            print(f"  esc exp={em} buf={bb} long={esc_rows[-1]['long']:+.0f} "
                  f"short={esc_rows[-1]['short']:+.0f}", flush=True)
    R.ESC.update(save)
    for d in days:
        cache = f"{R.SCRATCH}/ck_{d}.pkl"
        if os.path.exists(cache):
            os.remove(cache)
    k["escalation_plateau"] = esc_rows
    return k


def main():
    data = {d: R.build_day(d) for d in R.DAYS}
    res = {}
    print("D1 runs ...", flush=True)
    res["D1"] = d1_runs(data)
    print("D2 live anchor ...", flush=True)
    res["D2"] = d2_live(data)
    print("D3 churn ...", flush=True)
    churn = {}
    for d in R.DAYS:
        row = {}
        for tag in R.GATES:
            b = R.agg(R.simulate(data[d], tag, fast_cells=set(), filt=R.BASE)[0])
            a = R.agg(R.simulate(data[d], tag, fast_cells=ALL, filt=R.BASE)[0])
            row[tag] = dict(base_n=b["n"], base_pnl=b["pnl"], n=a["n"], pnl=a["pnl"],
                            n_fast=a["n_fast"], pnl_fast=a["pnl_fast"],
                            extra_n=a["n"] - b["n"], delta=round(a["pnl"] - b["pnl"], 2))
        churn[d] = row
    res["D3"] = churn
    print("D4 kill battery ...", flush=True)
    res["D4"] = d4_kill(data)
    # faders with the escalation gate removed entirely (the only way they get any n)
    print("D5 faders, escalation OFF ...", flush=True)
    save = dict(R.ESC)
    R.ESC.update(atr_min=0.0, exp_mult=0.0, brk_buf=99.0)
    for d in R.DAYS:
        c = f"{R.SCRATCH}/ck_{d}.pkl"
        if os.path.exists(c):
            os.remove(c)
    reb = {d: R.build_day(d) for d in R.DAYS}
    fade = {}
    for tag in ("rgv_short", "rgv_long"):
        for nm, filt in (("crude", R.CRUDE), ("filtered", R.BASE)):
            dl = {}
            for d in R.DAYS:
                b = R.agg(R.simulate(reb[d], tag, fast_cells=set(), filt=filt)[0])
                a = R.agg(R.simulate(reb[d], tag, fast_cells=ALL, filt=filt)[0])
                dl[d] = dict(delta=round(a["pnl"] - b["pnl"], 2), n_fast=a["n_fast"],
                             base_n=b["n"], base_pnl=b["pnl"])
            fade[f"{tag}|{nm}"] = dict(per_day=dl, total=round(sum(v["delta"] for v in dl.values()), 1),
                                       n_fast=sum(v["n_fast"] for v in dl.values()))
    # and the momentum gates with escalation off, for contrast
    for tag in BAR_GATES:
        dl = {}
        for d in R.DAYS:
            b = R.agg(R.simulate(reb[d], tag, fast_cells=set(), filt=R.BASE)[0])
            a = R.agg(R.simulate(reb[d], tag, fast_cells=ALL, filt=R.BASE)[0])
            dl[d] = dict(delta=round(a["pnl"] - b["pnl"], 2), n_fast=a["n_fast"])
        fade[f"{tag}|noesc"] = dict(per_day=dl, total=round(sum(v["delta"] for v in dl.values()), 1),
                                    n_fast=sum(v["n_fast"] for v in dl.values()))
    R.ESC.update(save)
    for d in R.DAYS:
        c = f"{R.SCRATCH}/ck_{d}.pkl"
        if os.path.exists(c):
            os.remove(c)
    res["D5"] = fade
    with open(OUT, "w") as f:
        json.dump(res, f)
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
