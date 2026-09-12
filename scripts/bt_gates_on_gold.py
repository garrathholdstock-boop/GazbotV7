#!/usr/bin/env python3
"""DO MNQ'S GATE SIGNALS EARN ON GOLD? The study that should have come BEFORE shipping them.

Operator, 2026-09-12: "putting the live mnq gates on to mgc feels extremely lazy. have you studied
that?" No. The cost-ratio argument that justified it came from the REGIME signal, not these gates,
and the desk's own gold work argues the other way: gold's runs are GRINDS (ER 0.23) and
momentum-null, and gf_MGC built six purpose-made gold gates that ALL failed, every one beaten by a
fixed-time short. So this tests it properly, on both instruments, with a same-entry sign-flip
control and gold's own cost.
"""
from __future__ import annotations
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
MKT = {"MNQ": dict(path=f"{GB}/reports/regime_2026-09-12/leadlag/front_MNQ_1min.parquet",
                   fric=1.25, atr_max=22.0, vpp=2.0),
       "MGC": dict(path=f"{GB}/reports/regime_2026-09-12/leadlag/front_MGC_1min.parquet",
                   fric=0.45, atr_max=4.64, vpp=10.0)}
OPEN_S, CLOSE_S = 13*3600 + 30*60, 20*3600


def load(p):
    d = duckdb.connect().execute(
        f"select ts,open,high,low,close,volume from read_parquet('{p}') order by ts").df()
    d["m"] = (d.ts // 60) * 60
    g = d.groupby("m").agg(o=("open", "first"), h=("high", "max"), l=("low", "min"),
                           c=("close", "last")).reset_index()
    g["sec"] = g.m % 86400
    g["d"] = pd.to_datetime(g.m, unit="s", utc=True).dt.date
    return g


def signals(g, atr_max):
    atr = pd.Series(np.maximum(g.h - g.l, .25)).rolling(14).mean()
    ret5 = g.c.diff(5)
    amp = (g.h - g.l) / g.c
    slope = (g.c - g.c.rolling(60).mean()) / atr
    ok = (atr <= atr_max) & (g.sec >= OPEN_S) & (g.sec <= CLOSE_S)
    return {
      "abs_veto_long":  (ok & (ret5 >= 1.5*atr) & (amp >= 0.0004), 1),
      "abs_veto_short": (ok & (ret5 <= -1.5*atr) & (amp >= 0.0004), -1),
      "grind_long":     (ok & (slope >= 0.4) & (slope <= 2.0), 1),
      "capit_long":     (ok & (ret5 <= -2.5*atr) & (g.c > g.o), 1),   # climax down then flip up
    }, atr


def run(sym, cooldown=45):
    m = MKT[sym]; g = load(m["path"]); sig, atr = signals(g, m["atr_max"])
    c, h, l, o = g.c.values, g.h.values, g.l.values, g.o.values
    day = g.d.values; A = atr.values
    out = {}
    for name, (mask, side) in sig.items():
        idx = np.where(mask.fillna(False).values)[0]
        rows, last = [], -10**9
        for i in idx:
            if i - last < cooldown or i + 2 >= len(c) or not np.isfinite(A[i]):
                continue
            last = i
            e = o[i+1]; stop = 7.0 * A[i]
            end = i + 1
            while end < len(c) - 1 and day[end+1] == day[i] and g.sec.values[end+1] <= CLOSE_S:
                end += 1
                adv = (e - l[end]) if side > 0 else (h[end] - e)
                if adv >= stop:
                    rows.append((day[i], -stop, side)); break
            else:
                rows.append((day[i], side * (c[end] - e), side))
                continue
            if not rows or rows[-1][0] != day[i]:
                rows.append((day[i], side * (c[end] - e), side))
        R = pd.DataFrame(rows, columns=["d", "gross", "side"])
        if len(R) < 30:
            out[name] = None; continue
        R["net"] = R.gross - m["fric"]
        R["flip"] = -R.gross - m["fric"]
        out[name] = R
    return out, m


def main():
    rng = np.random.default_rng(3)
    def ci(x):
        x = np.asarray(x); idx = rng.integers(0, len(x), size=(5000, len(x)))
        b = x[idx].mean(axis=1); return np.percentile(b, 2.5), np.percentile(b, 97.5)
    print(f"{'gate':<17}{'mkt':>5}{'n':>7}{'net pt':>9}{'net $':>9}{'flipped $':>11}"
          f"{'GROSS edge':>12}{'95% CI on gross':>22}")
    for sym in ("MNQ", "MGC"):
        res, m = run(sym)
        for name, R in res.items():
            if R is None:
                print(f"{name:<17}{sym:>5}{'<30 trades':>7}"); continue
            lo, hi = ci(R.gross.values)
            print(f"{name:<17}{sym:>5}{len(R):>7}{R.net.mean():>9.2f}"
                  f"{R.net.mean()*m['vpp']:>9.2f}{R.flip.mean()*m['vpp']:>11.2f}"
                  f"{R.gross.mean():>12.3f}   [{lo:>7.3f},{hi:>7.3f}]")
        print()
    print("  entry = next bar open · exit = 7xATR stop or the 20:00Z session end · 1 lot")
    print("  cost: MNQ 1.25pt ($2.50) · MGC 0.45pt ($4.50) · 45-min cooldown")
    print("  'flipped' = the SAME entries with the side reversed — the control that cannot move the")
    print("  entry population. GROSS edge = the half-difference, i.e. what the signal is worth before fees.")


if __name__ == "__main__":
    raise SystemExit(main())
