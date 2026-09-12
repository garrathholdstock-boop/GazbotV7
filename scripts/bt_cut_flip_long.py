#!/usr/bin/env python3
"""CUT-AND-FLIP OVER 10.5 YEARS — because the forward trial cannot answer this and the tape can.

Power, measured 2026-09-12 on the driftlab window: the CUT effect (+21 to +32pt/session) needs
450-800 sessions for 80% power and the FLIP increment (+4 to +10pt) needs 419-2,900, because the
per-session sd is 213-239pt. A 60-session forward trial is INCONCLUSIVE BY CONSTRUCTION. So the
edge question goes to the long tape and the forward trial is left to test the IMPLEMENTATION.

★ THE ENTRY IS THE REAL DETECTOR, REPLAYED CAUSALLY. For each session the minute bars from 13:30Z
  are fed to drift.compute() one minute at a time, and the FIRST minute that confirms is the entry
  — exactly what the live rider does. The search stops at 15:00Z because ENTRY_CUTOFF_MIN does.
⚠ VALIDATED AGAINST driftlab: on the overlap window this replay must agree with the recorded
  confirmations, or the 10.5-year run is measuring a different detector and is worthless.
"""
from __future__ import annotations
import argparse, glob, json
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
FRIC = 1.25
OPEN_S, CUTOFF_S, FLAT_S = 13*3600+30*60, 15*3600, 20*3600+40*60


def sessions(src: str):
    con = duckdb.connect()
    q = (f"select bar_ts ts, open, high, low, close from read_parquet("
         f"'{GB}/data/tape/bars/NQ/*.parquet') where timeframe='1min'" if src == "nq_long"
         else f"select ts, open, high, low, close from read_parquet("
              f"'{GB}/data/driftlab/{src}_*.parquet')")
    df = con.execute(q + " order by 1").df().drop_duplicates("ts")
    df["d"] = pd.to_datetime(df.ts, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    df["sec"] = df.ts % 86400
    return df


def entry_of(g) -> tuple[int, int] | None:
    """First minute drift CONFIRMS, searched only inside the live entry window."""
    from gazbot7.drift import compute
    w = g[(g.sec >= OPEN_S) & (g.sec <= CUTOFF_S)]
    if len(w) < 12:
        return None
    rows = list(zip(w.ts.astype(int), w.high, w.low, w.close))
    for n in range(8, len(rows) + 1):
        r = compute(rows[:n])
        if r.confirmed and r.direction in ("UP", "DOWN"):
            return int(rows[n-1][0]), (1 if r.direction == "UP" else -1)
    return None


def simulate(g, t_conf, side, cut, target, max_flips, flip):
    s = g[(g.ts > t_conf) & (g.sec <= FLAT_S)]
    if len(s) < 30:
        return None
    o, h, l, c = s.open.values, s.high.values, s.low.values, s.close.values
    i, flips, pnl, e = 0, 0, 0.0, o[0]
    while i < len(s):
        hit_c = hit_t = None
        for j in range(i, len(s)):
            fav = (h[j]-e) if side > 0 else (e-l[j])
            adv = (e-l[j]) if side > 0 else (h[j]-e)
            if adv >= cut: hit_c = j; break           # CUT scored first when a bar holds both
            if target and fav >= target: hit_t = j; break
        if hit_t is not None:
            pnl += target - FRIC; flips += 1; break
        if hit_c is None:
            pnl += side*(c[-1]-e) - FRIC; flips += 1; break
        pnl += -cut - FRIC; flips += 1
        if not flip or flips > max_flips or hit_c >= len(s)-2:
            break
        side, e, i = -side, o[hit_c+1], hit_c+1
    return pnl, flips


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="nq_long")
    ap.add_argument("--cut", type=float, default=40.0)
    ap.add_argument("--target", type=float, default=100.0)
    ap.add_argument("--max-flips", type=int, default=3)
    a = ap.parse_args()
    df = sessions(a.src)
    rows = []
    for day, g in df.groupby("d", sort=True):
        ent = entry_of(g)
        if ent is None:
            continue
        t, side = ent
        A = simulate(g, t, side, 1e9, 0, 0, False)
        B = simulate(g, t, side, a.cut, a.target, a.max_flips, False)
        C = simulate(g, t, side, a.cut, a.target, a.max_flips, True)
        if None in (A, B, C):
            continue
        rows.append((day, side, A[0], B[0], C[0], C[1]))
    R = pd.DataFrame(rows, columns=["day", "side", "A", "B", "C", "flips"])
    R["yr"] = R.day.str[:4]
    print(f"{a.src}: {len(R)} sessions with a causal drift confirmation, "
          f"{R.day.min()} .. {R.day.max()}\n")

    rng = np.random.default_rng(7)
    def boot(d):
        idx = rng.integers(0, len(d), size=(10000, len(d)))
        m = np.asarray(d)[idx].mean(axis=1)
        return np.percentile(m, 2.5), np.percentile(m, 97.5)

    print(f"{'arm':<28}{'pt/session':>12}{'green%':>9}{'95% CI':>22}")
    for lbl, col in (("A  hold naked to 20:40", "A"), ("B  cut only", "B"),
                     ("C  cut and flip", "C")):
        lo, hi = boot(R[col].values)
        print(f"{lbl:<28}{R[col].mean():>12.1f}{100*(R[col] > 0).mean():>8.0f}%"
              f"   [{lo:>7.1f},{hi:>7.1f}]")
    for lbl, d in (("THE CUT   (B-A)", R.B-R.A), ("THE FLIP  (C-B)", R.C-R.B)):
        lo, hi = boot(d.values)
        v = "REAL" if lo > 0 else ("NEGATIVE" if hi < 0 else "inside noise")
        print(f"\n  {lbl}: {d.mean():+.1f} pt/session   95% CI [{lo:+.1f}, {hi:+.1f}]   -> {v}")
    print(f"\n  by era (pt/session):")
    print(R.groupby("yr")[["A", "B", "C"]].mean().round(1).to_string())
    print(f"\n  mean flips/session {R.flips.mean():.2f} · cut {a.cut:g}pt · target {a.target:g}pt "
          f"· {FRIC}pt per flip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
