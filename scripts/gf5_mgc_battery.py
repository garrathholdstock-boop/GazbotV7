#!/usr/bin/env python3
"""GF5_MGC — THE ROBUSTNESS BATTERY on the gold level-break family, 33 days.

    PYTHONPATH=src .venv/bin/python scripts/gf5_mgc_battery.py

★ WHY. `gf4_mgc_barsource.py` (08-28) re-ran last Friday's headline — "the shadow loses because the
lab reads depth-mid bars and production reads trade bars" — on 32 days instead of 6, and the claim
did not hold: BOTH tapes are negative on the forward blocks. That kills the recommendation but it
does not tell us whether anything in the family survives. This is the battery that decides.

Everything here races the SAME 250ms quote tape, both legs crossing, $1.50 commission on top
(= the $4.50-from-mid convention). The gate, the exit and the cooldown are gf4's, unchanged.

★ THE FOUR CONTROLS, all at the gate's OWN stamps, because a stamp-matched control is the only kind
that cannot be beaten by the tape's drift:
    MIRROR         follow the break instead of fading it
    ALWAYS LONG    buy at every stamp regardless of the break's direction
    ALWAYS SHORT   sell at every stamp
    PLACEBO        the same NUMBER of trades, same day, same side, at a RANDOM minute (30 draws)

MGC = $10.00/point. Fee $1.50 per ROUND TRIP on top of two crossed legs.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")

from gf_mgc_barsource import atr14, fires, trade_bars              # noqa: E402
from gf_mgc_tape import VPP, load_quotes, minute_bars              # noqa: E402
from gf5_fastrace import fast_race as race                         # noqa: E402
from gazbot7.levelbreak import read_book                           # noqa: E402

OUT = f"{GB}/reports/friday_v7/sections"
FEE = 1.50
IS_END = "2026-08-15"
F2_START = "2026-08-26"
SEED = 20260829
R: dict = {}


def line(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100, flush=True)


def book_rows():
    from gazbot7 import lake
    c = lake.connect(symbol="MGC")
    cols = ", ".join([f"bid{k}p, bid{k}s, ask{k}p, ask{k}s" for k in range(1, 11)])
    return c.execute(f"SELECT ts_ms, {cols} FROM depth WHERE symbol='MGC' ORDER BY ts_ms").df()


class Racer:
    """Holds the quote tape once and races anything against it."""

    def __init__(self, q, bars):
        self.qt = (q.index.tz_convert("UTC").tz_localize(None)
                   .astype("datetime64[ms]").astype("int64").to_numpy())
        self.bid, self.ask = q["bid1p"].to_numpy(), q["ask1p"].to_numpy()
        self.a = atr14(bars)

    def atr_at(self, ts):
        k = self.a.index.get_indexer([pd.Timestamp(ts - 60_000, unit="ms", tz="UTC")],
                                     method="ffill")[0]
        return float(self.a.iloc[k]) if k >= 0 else 0.0

    def one(self, ts, side, *, stop_atr=3.0, trail_atr=2.0, arm_atr=2.0, cap_min=480,
            target_r=None, atr=None):
        atr = self.atr_at(ts) if atr is None else atr
        if not (atr > 0):
            return None
        i = np.searchsorted(self.qt, ts, side="left")
        if i >= len(self.qt) - 2:
            return None
        fill_in = self.ask[i] if side > 0 else self.bid[i]
        mid_in = (self.bid[i] + self.ask[i]) / 2.0
        stop = mid_in - side * stop_atr * atr
        tgt = (mid_in + side * target_r * stop_atr * atr) if target_r else None
        fo, mo, reason, mins, mfe, mae = race(
            self.qt[i:], self.bid[i:], self.ask[i:], side, fill_in=fill_in, mid_in=mid_in,
            stop=stop, target=tgt, trail=(trail_atr * atr) if trail_atr else None,
            cap_ms=cap_min * 60_000, arm_at=(arm_atr * atr) if trail_atr else None)
        return {"ts": ts, "side": side, "atr": atr, "reason": reason, "minutes": mins,
                "mfe_pt": mfe, "mae_pt": mae,
                "day": pd.Timestamp(ts, unit="ms", tz="UTC").strftime("%Y-%m-%d"),
                "pnl": round(side * (fo - fill_in) * VPP - FEE, 2)}


def s(d):
    if d is None or len(d) == 0:
        return {"n": 0, "net": 0.0, "per": 0.0, "win": 0.0, "days": 0}
    v = d["pnl"] if isinstance(d, pd.DataFrame) else pd.Series(d)
    return {"n": int(len(v)), "net": round(float(v.sum()), 0), "per": round(float(v.mean()), 2),
            "win": round(100.0 * float((v > 0).mean()), 1),
            "days": int(d["day"].nunique()) if isinstance(d, pd.DataFrame) else 0}


def show(tag, d):
    r = s(d)
    lo = s(d[d["side"] > 0]) if len(d) else r
    sh = s(d[d["side"] < 0]) if len(d) else r
    print(f"  {tag:<46} n={r['n']:<5} net={r['net']:>+8.0f}  $/tr={r['per']:>+7.2f}  "
          f"win={r['win']:>5.1f}%  d={r['days']:<3}| L {lo['n']:>3}/{lo['per']:>+7.2f}"
          f"  S {sh['n']:>3}/{sh['per']:>+7.2f}")
    return {"pooled": r, "long": lo, "short": sh}


def blocks(d):
    return {"IS": d[d["day"] < IS_END], "F1": d[(d["day"] >= IS_END) & (d["day"] < F2_START)],
            "F2": d[d["day"] >= F2_START], "FWD": d[d["day"] >= IS_END]}


def battery(d, tag):
    """strip-best, drop-best-day, LOO, per-ISO-week, per-session."""
    out = {}
    v = np.sort(d["pnl"].to_numpy())
    for k in (3, 5, 10):
        out[f"strip_best_{k}"] = round(float(v[:-k].sum()), 0) if len(v) > k else None
    byday = d.groupby("day")["pnl"].sum()
    out["drop_best_day"] = round(float(d["pnl"].sum() - byday.max()), 0)
    out["days_green"] = round(100.0 * float((byday > 0).mean()), 1)
    out["loo_min"] = round(float((d["pnl"].sum() - byday).min()), 0)
    out["loo_all_green"] = bool((d["pnl"].sum() - byday > 0).all())
    ts = pd.to_datetime(d["day"])
    wk = ts.dt.isocalendar().week.astype(int).to_numpy()
    wks = pd.Series(d["pnl"].to_numpy()).groupby(wk).sum()
    out["weeks"] = {int(k): round(float(x), 0) for k, x in wks.items()}
    out["weeks_green"] = f"{int((wks > 0).sum())}/{len(wks)}"
    print(f"  {tag}: strip3 {out['strip_best_3']}  strip5 {out['strip_best_5']}  "
          f"strip10 {out['strip_best_10']}  drop-best-day {out['drop_best_day']}  "
          f"days-green {out['days_green']}%  weeks {out['weeks_green']}  "
          f"LOO all green: {out['loo_all_green']}")
    print(f"      weeks: {out['weeks']}")
    return out


def slippage(d, racer, ticks=(1, 2, 3)):
    """Charge k extra ticks (0.10pt = $1.00) adverse on EACH leg."""
    return {f"+{k}tick": round(float(d["pnl"].sum() - 2 * k * 1.0 * len(d)), 0) for k in ticks}


def main():
    q = load_quotes()
    mid = minute_bars(q, col="mid")
    t0, t1 = int(q.index[0].value // 10**6), int(q.index[-1].value // 10**6)
    trd = trade_bars(t0, t1)
    trd = trd[(trd.index >= mid.index[0]) & (trd.index <= mid.index[-1])]
    days = sorted(set(mid.index.strftime("%Y-%m-%d")))
    print(f"quote tape {q.index[0]} .. {q.index[-1]}  {len(q):,} snaps   {len(days)} days")
    R["days"] = days

    bk = book_rows()
    bk_ts = bk["ts_ms"].to_numpy()
    print(f"book {len(bk):,} snapshots", flush=True)

    fm, ft = fires(mid), fires(trd)
    rc_mid, rc_trd = Racer(q, mid), Racer(q, trd)

    def arm(hits, racer, *, hole=True, fade=True, mirror=False, force_side=None, **kw):
        out, cool = [], {1: -1, -1: -1}
        for ts, brk, level in hits:
            if ts - cool[brk] < 45 * 60_000:
                continue
            j = np.searchsorted(bk_ts, ts, side="right") - 1
            if j < 0 or ts - bk_ts[j] > 5_000:
                continue
            b = read_book(bk.iloc[j].to_dict(), brk, level, 1.0)
            if hole and b.obstacle != 0:
                continue
            if (not hole) and not (b.obstacle > b.support):
                continue
            side = (-brk) if fade else brk
            if mirror:
                side = -side
            if force_side is not None:
                side = force_side
            t = racer.one(ts, side, **kw)
            if t is None:
                continue
            cool[brk] = ts
            t.update(brk=brk, level=level, obstacle=b.obstacle, support=b.support)
            out.append(t)
        return pd.DataFrame(out)

    line("★★★ THE HOLE-FADE FAMILY AND ITS FOUR STAMP-MATCHED CONTROLS — 33 days")
    R["controls"] = {}
    for lbl, hits, rcr in (("DEPTH-MID", fm, rc_mid), ("TRADE-BAR", ft, rc_trd)):
        print(f"\n── {lbl} tape ──")
        base = arm(hits, rcr)
        R["controls"][lbl] = {"gate": {}, "mirror": {}, "always_long": {}, "always_short": {}}
        for nm, d in (("gate  (FADE the break)", base),
                      ("MIRROR (follow instead)", arm(hits, rcr, mirror=True)),
                      ("always LONG  at same stamps", arm(hits, rcr, force_side=1)),
                      ("always SHORT at same stamps", arm(hits, rcr, force_side=-1))):
            key = {"g": "gate", "M": "mirror", "a": "x"}.get(nm[0], "x")
            k = ("gate" if nm.startswith("gate") else "mirror" if nm.startswith("MIRROR")
                 else "always_long" if "LONG" in nm else "always_short")
            R["controls"][lbl][k] = {"ALL": show(f"{nm}  ALL", d)}
            for w in ("IS", "F1", "F2", "FWD"):
                R["controls"][lbl][k][w] = show(f"{nm}  {w}", blocks(d)[w])
            print()
        R[f"trades_{lbl}"] = base.to_dict("records")

        line(f"ROBUSTNESS — {lbl} hole-fade")
        R["controls"][lbl]["battery_all"] = battery(base, "ALL 33d")
        for sd, nm in ((1, "LONG only"), (-1, "SHORT only")):
            g = base[base["side"] == sd]
            if len(g) > 10:
                R["controls"][lbl][f"battery_{nm[:4].strip()}"] = battery(g, nm)
        R["controls"][lbl]["slippage"] = slippage(base, rcr)
        print(f"  slippage {R['controls'][lbl]['slippage']}")

    line("★★ THE RANDOM-MINUTE PLACEBO — same day, same side, same count, 30 draws")
    R["placebo"] = {}
    rng = np.random.default_rng(SEED)
    for lbl, hits, rcr, bars in (("DEPTH-MID", fm, rc_mid, mid), ("TRADE-BAR", ft, rc_trd, trd)):
        base = pd.DataFrame(R[f"trades_{lbl}"])
        real = float(base["pnl"].sum())
        # minute stamps available per day
        pool = {}
        idx = bars.index
        for dd in sorted(set(idx.strftime("%Y-%m-%d"))):
            pool[dd] = (idx[idx.strftime("%Y-%m-%d") == dd].astype("int64") // 10**6).to_numpy()
        draws = []
        for _ in range(30):
            tot = 0.0
            for _, row in base.iterrows():
                p = pool.get(row["day"])
                if p is None or len(p) < 5:
                    continue
                t = rcr.one(int(rng.choice(p)) + 60_000, int(row["side"]))
                if t:
                    tot += t["pnl"]
            draws.append(tot)
        draws = np.array(draws)
        beaten = int((draws >= real).sum())
        pct = round(100.0 * float((draws < real).mean()), 1)
        print(f"  {lbl}: real {real:+.0f}   placebo mean {draws.mean():+.0f}  "
              f"min {draws.min():+.0f}  max {draws.max():+.0f}   "
              f"BEATEN {beaten}/30  ({pct}th pctile)")
        R["placebo"][lbl] = {"real": round(real, 0), "mean": round(float(draws.mean()), 0),
                             "min": round(float(draws.min()), 0), "max": round(float(draws.max()), 0),
                             "beaten": beaten, "pctile": pct,
                             "draws": [round(float(x), 0) for x in draws]}
        # and the same placebo on the FORWARD block only
        fwd = base[base["day"] >= IS_END]
        if len(fwd) > 10:
            rf = float(fwd["pnl"].sum())
            dr = []
            for _ in range(30):
                tot = 0.0
                for _, row in fwd.iterrows():
                    p = pool.get(row["day"])
                    if p is None or len(p) < 5:
                        continue
                    t = rcr.one(int(rng.choice(p)) + 60_000, int(row["side"]))
                    if t:
                        tot += t["pnl"]
                dr.append(tot)
            dr = np.array(dr)
            print(f"  {lbl} FORWARD only: real {rf:+.0f}  placebo mean {dr.mean():+.0f}  "
                  f"BEATEN {int((dr >= rf).sum())}/30")
            R["placebo"][lbl + "_FWD"] = {"real": round(rf, 0),
                                          "mean": round(float(dr.mean()), 0),
                                          "beaten": int((dr >= rf).sum())}

    with open(f"{OUT}/gf5_mgc_battery.json", "w") as fh:
        json.dump(R, fh, indent=1, default=str)
    print(f"\nwrote {OUT}/gf5_mgc_battery.json")


if __name__ == "__main__":
    main()
