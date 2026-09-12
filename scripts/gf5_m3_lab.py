#!/usr/bin/env python3
"""GF5 — MOVEMENT 3 GREENFIELD LAB, week ending 2026-08-28.

    PYTHONPATH=src .venv/bin/python scripts/gf5_m3_lab.py <stage>

Stages: prize | family | escalate | frozen | fresh | all

★ WHAT THIS IS. Movement 3's own working for the 2026-08-28 cycle. The five cluster dossiers
(gf_full_*.md) and the gold dossier were written on 2026-08-25 against the PREVIOUS week's frozen
census; this file re-asks their questions against THIS week's frozen census (65 runs, 62 sat out,
$10,278 of hindsight ceiling, 08-23 22:00 -> 08-28 20:59 UTC) and forward-tests the frozen specs on
tape that did not exist when they were chosen.

COSTS, stated once and charged in every number below:
    MNQ $2.00 per point, $1.50 per ROUND TRIP (not $5, not per side), 0.25pt (one tick) adverse
    slippage on entry and on every stop. Targets fill at the limit. Stop is checked BEFORE target
    on every 5-second bar (the pessimistic ordering). One position at a time.
"""
from __future__ import annotations

import json
import re
import sys

import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
from gazbot7.lake import connect                                     # noqa: E402

OUT = f"{GB}/reports/friday_v7/m3"
VPP, FEE, TICK = 2.00, 1.50, 0.25
CENSUS = f"{GB}/reports/friday_v7/sections/census_stdout.txt"

_B5: pd.DataFrame | None = None
_M1: pd.DataFrame | None = None


# ── TAPE ──────────────────────────────────────────────────────────────────────────────────────
def bars5s() -> pd.DataFrame:
    global _B5
    if _B5 is None:
        c = connect(symbol="MNQ")
        d = c.execute("SELECT bar_ts, open, high, low, close, volume FROM bars "
                      "WHERE symbol='MNQ' AND timeframe='5s' ORDER BY bar_ts").df()
        d.index = pd.to_datetime(d.pop("bar_ts"), unit="s", utc=True)
        _B5 = d
    return _B5


def minutes() -> pd.DataFrame:
    """1-minute OHLCV folded from the 5s tape, plus every causal feature the lab uses.

    Every rolling statistic is closed on the LEFT and shifted, so a row stamped ts is knowable at
    ts+60s and nothing reads its own bar. `ok` marks rows whose 30-minute lookback is contiguous —
    across a weekend or the daily halt a .shift(30) silently compares two different tapes.
    """
    global _M1
    if _M1 is not None:
        return _M1
    b = bars5s()
    m = pd.DataFrame({
        "open": b["open"].resample("1min").first(),
        "high": b["high"].resample("1min").max(),
        "low": b["low"].resample("1min").min(),
        "close": b["close"].resample("1min").last(),
        "volume": b["volume"].resample("1min").sum(),
    }).dropna(subset=["close"])
    rng = m["high"] - m["low"]
    m["atr20"] = rng.rolling(20, min_periods=15).mean().shift(1)
    m["atr_rel"] = m["atr20"] / m["atr20"].rolling(1440, min_periods=200).median().shift(1)
    ch = m["close"].diff()
    m["mv5"] = m["close"] - m["close"].shift(5)
    m["mv10"] = m["close"] - m["close"].shift(10)
    path30 = ch.abs().rolling(30, min_periods=25).sum()
    m["er30"] = (m["close"] - m["close"].shift(30)).abs() / path30.replace(0, np.nan)
    path10 = ch.abs().rolling(10, min_periods=8).sum()
    m["er10"] = m["mv10"].abs() / path10.replace(0, np.nan)
    path15 = ch.abs().rolling(15, min_periods=12).sum()
    m["er15"] = (m["close"] - m["close"].shift(15)).abs() / path15.replace(0, np.nan)
    v = m["volume"]
    mu, sd = v.rolling(120, min_periods=60).mean().shift(1), v.rolling(120, min_periods=60).std().shift(1)
    m["volz"] = (v - mu) / sd.replace(0, np.nan)
    a5 = m["atr20"].rolling(5, min_periods=4).mean()
    a60 = m["atr20"].rolling(60, min_periods=40).mean()
    m["atr_exp"] = a5 / a60.replace(0, np.nan)
    m["brk30"] = (m["close"] - m["close"].shift(30)) / m["atr20"].replace(0, np.nan)
    m["fwd15"] = m["close"].shift(-15) - m["close"]
    # contiguity: the 30-minute lookback must be real minutes of the same session
    idx = m.index.to_series()
    m["ok"] = (idx - idx.shift(30)) <= pd.Timedelta("31min")
    m["ok10"] = (idx - idx.shift(10)) <= pd.Timedelta("11min")
    _M1 = m
    return m


def ticks_min() -> pd.DataFrame:
    """Per-minute trade COUNT and net aggressor flow, from the tick tape (2026-07-05 onward)."""
    c = connect(symbol="MNQ")
    d = c.execute("""SELECT date_trunc('minute', to_timestamp(ts_ms/1000)) mt,
                            count(*) nt,
                            sum(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size
                                     ELSE 0 END) flow
                     FROM ticks WHERE symbol='MNQ' GROUP BY 1 ORDER BY 1""").df()
    d.index = pd.to_datetime(d.pop("mt"), utc=True)
    for col, z in (("nt", "ntz"), ("flow", "fz")):
        s = d[col].astype(float)
        mu = s.rolling(120, min_periods=60).mean().shift(1)
        sd = s.rolling(120, min_periods=60).std().shift(1)
        d[z] = (s - mu) / sd.replace(0, np.nan)
    return d


# ── THE RACER ─────────────────────────────────────────────────────────────────────────────────
def race(sig_ts, side, stop_pt, targ_pt, cap_min, b5=None):
    """Enter at the OPEN of the first 5s bar after the signal minute closes, 1 tick adverse.

    Walk 5s bars; the STOP is tested before the TARGET on every bar (a bar touching both is a
    loss). Returns (entry, exit, pnl_net, reason, minutes, mfe_pt, mae_pt) or None.
    """
    b = bars5s() if b5 is None else b5
    i = b.index.searchsorted(sig_ts, side="left")
    if i >= len(b) - 2:
        return None
    ent = float(b["open"].iloc[i]) + side * TICK
    stop = ent - side * stop_pt
    targ = (ent + side * targ_pt) if targ_pt else None
    j_end = b.index.searchsorted(sig_ts + pd.Timedelta(minutes=cap_min), side="left")
    hi = b["high"].to_numpy()[i:j_end + 1]
    lo = b["low"].to_numpy()[i:j_end + 1]
    mfe = mae = 0.0
    for k in range(len(hi)):
        up, dn = hi[k] - ent, ent - lo[k]
        mfe = max(mfe, up if side > 0 else dn)
        mae = max(mae, dn if side > 0 else up)
        if (lo[k] <= stop) if side > 0 else (hi[k] >= stop):
            px = stop - side * TICK
            return ent, px, side * (px - ent) * VPP - FEE, "STOP", (k * 5) / 60.0, mfe, mae
        if targ is not None and ((hi[k] >= targ) if side > 0 else (lo[k] <= targ)):
            return ent, targ, side * (targ - ent) * VPP - FEE, "TGT", (k * 5) / 60.0, mfe, mae
    if len(hi) == 0:
        return None
    px = float(b["close"].iloc[min(i + len(hi) - 1, len(b) - 1)])
    return ent, px, side * (px - ent) * VPP - FEE, "TIME", cap_min, mfe, mae


def serial(rows):
    """One position at a time: a signal arriving before the previous trade closed is SKIPPED."""
    out, busy_until = [], pd.Timestamp("2000-01-01", tz="UTC")
    for r in sorted(rows, key=lambda x: x["ts"]):
        if r["ts"] < busy_until:
            continue
        busy_until = r["ts"] + pd.Timedelta(minutes=r["minutes"])
        out.append(r)
    return pd.DataFrame(out)


def stat(d, key="pnl"):
    if d is None or len(d) == 0:
        return {"n": 0, "net": 0.0, "per": 0.0, "win": 0.0, "days": 0}
    v = pd.Series(d[key] if hasattr(d, "columns") else d, dtype=float)
    days = int(pd.Series(d["ts"]).dt.date.nunique()) if hasattr(d, "columns") else 0
    return {"n": int(len(v)), "net": round(float(v.sum()), 2), "per": round(float(v.mean()), 3),
            "win": round(100 * float((v > 0).mean()), 1), "days": days}


# ── THE FROZEN CENSUS ─────────────────────────────────────────────────────────────────────────
ROW = re.compile(r"^(\d\d-\d\d \d\d:\d\d)\s+(UP|DN)\s+([+-]\d+)\s+(\d+)\s+(sat out|caught|FOUGHT)"
                 r"\s+(\S+)\s+([+-]\d+)\s+([+-]?\d+|—)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")


def census():
    runs = []
    for ln in open(CENSUS):
        m = ROW.match(ln.strip())
        if not m:
            continue
        t, d, mv, ceil, us, gate, real, flow, amp, book, cl = m.groups()
        runs.append({"ts": pd.Timestamp("2026-" + t.replace(" ", "T"), tz="UTC"),
                     "dir": 1 if d == "UP" else -1, "move": int(mv), "ceil": int(ceil),
                     "us": us, "gate": gate, "real": int(real), "cluster": cl,
                     "flow": None if flow == "—" else int(flow),
                     "amp": None if amp == "—" else float(amp),
                     "book": None if book == "—" else float(book)})
    return pd.DataFrame(runs)


# ── STAGE 1 — THE PRIZE ───────────────────────────────────────────────────────────────────────
def stage_prize():
    """Can a dumb, direction-agnostic late boarder get inside this week's runs, and what is left?"""
    m, runs = minutes(), census()
    sat = runs[runs.us == "sat out"].reset_index(drop=True)
    b5 = bars5s()
    R = {"census": {"runs": int(len(runs)), "sat": int(len(sat)),
                    "ceiling": int(sat.ceil.sum()),
                    "caught": int((runs.us == "caught").sum()),
                    "fought": int((runs.us == "FOUGHT").sum()),
                    "clusters": runs.cluster.value_counts().to_dict()}}

    print("\n=== BOARDING CURVE — 62 sat-out runs, week ending 2026-08-28 ===")
    curve = []
    for W, k in ((3, 1.5), (5, 1.5), (5, 2.0), (5, 2.5), (10, 2.0), (10, 2.5), (15, 2.5)):
        mv = m["close"] - m["close"].shift(W)
        fires_in, late, left, oracle, nothing = 0, [], [], 0.0, 0
        for _, r in sat.iterrows():
            w = m.loc[r.ts: r.ts + pd.Timedelta(minutes=15)]
            hit = None
            for ts, row in w.iterrows():
                if not np.isfinite(row.atr20) or row.atr20 <= 0:
                    continue
                v = mv.get(ts, np.nan)
                if not np.isfinite(v):
                    continue
                if abs(v) >= k * row.atr20 and np.sign(v) == r["dir"]:
                    hit = (ts, float(row.close))
                    break
            if hit is None:
                continue
            fires_in += 1
            ts0, px = hit
            late.append((ts0 - r.ts).total_seconds() / 60.0)
            seg = b5.loc[ts0: r.ts + pd.Timedelta(minutes=15)]
            if len(seg) == 0:
                continue
            term = float(seg["high"].max()) if r["dir"] > 0 else float(seg["low"].min())
            pts = (term - px) * r["dir"]
            left.append(pts)
            oracle += max(0.0, pts) * VPP
            nothing += int(pts <= 2.0)
        curve.append({"W": W, "k": k, "fires_in": fires_in, "of": int(len(sat)),
                      "late_med": round(float(np.median(late)), 1) if late else None,
                      "left_med": round(float(np.median(left)), 1) if left else None,
                      "left_p25": round(float(np.percentile(left, 25)), 1) if left else None,
                      "nothing_left": nothing,
                      "oracle": round(oracle, 0),
                      "pct_ceiling": round(100 * oracle / sat.ceil.sum(), 1)})
        print(f"  W={W:>2} k={k:<4} fires in {fires_in:>2}/{len(sat)}  median {curve[-1]['late_med']}min late"
              f"  median {curve[-1]['left_med']}pt left  ORACLE ${oracle:,.0f}"
              f" = {curve[-1]['pct_ceiling']}% of ${sat.ceil.sum():,}")
    R["boarding"] = curve

    # fire rate of the same trigger on the whole week's tape, with a 15-minute lockout so the
    # number is ENTRIES a day (one position at a time), not minutes-in-which-it-was-true.
    print("\n=== …and how often that same trigger fires on tape that is NOT a run ===")
    wk = m.loc["2026-08-23 22:00":"2026-08-28 21:00"]
    runwin = [(r.ts - pd.Timedelta(minutes=5), r.ts + pd.Timedelta(minutes=15))
              for _, r in sat.iterrows()]
    rate = []
    for W, k in ((5, 1.5), (5, 2.0), (5, 2.5), (10, 2.5)):
        mv = wk["close"] - wk["close"].shift(W)
        fire = (mv.abs() >= k * wk["atr20"]) & wk["atr20"].gt(0) & wk["ok10"]
        taken, until = [], pd.Timestamp("2000-01-01", tz="UTC")
        for ts in wk.index[fire.fillna(False)]:
            if ts < until:
                continue
            until = ts + pd.Timedelta(minutes=15)
            taken.append(ts)
        inrun = sum(any(a <= t <= b for a, b in runwin) for t in taken)
        rate.append({"W": W, "k": k, "entries_week": len(taken),
                     "per_day": round(len(taken) / 5.0, 1), "in_a_run": inrun,
                     "pct_in_run": round(100.0 * inrun / max(1, len(taken)), 1)})
        print(f"  W={W} k={k}: {len(taken)} entries over 5 sessions = {len(taken)/5:.0f} a day, "
              f"{inrun} of them ({100*inrun/max(1,len(taken)):.0f}%) land inside a census run")
    R["fire_rate"] = rate
    json.dump(R, open(f"{OUT}/prize.json", "w"), indent=1, default=str)
    return R


# ── STAGE 2 — FAMILY A/B, AND THE PROOF THAT THE PROBLEM IS THE ENTRY ─────────────────────────
def stage_family():
    m, runs = minutes(), census()
    sat = runs[runs.us == "sat out"].reset_index(drop=True)
    tk = ticks_min()
    m = m.join(tk[["nt", "ntz", "flow", "fz"]], how="left")
    R = {}

    # ---- A / B: is there a PRECURSOR in the ten minutes before the run starts? ----------------
    def pre(ts, col, agg="max"):
        w = m.loc[ts - pd.Timedelta(minutes=10): ts - pd.Timedelta(minutes=1), col].dropna()
        if len(w) == 0:
            return np.nan
        return float(w.max() if agg == "max" else w.mean())

    rows = []
    for _, r in sat.iterrows():
        rows.append({"ts": r.ts, "move": abs(r.move), "ceil": r.ceil, "cluster": r.cluster,
                     "dir": r["dir"],
                     "volz": pre(r.ts, "volz"), "ntz": pre(r.ts, "ntz"),
                     "atr_exp": pre(r.ts, "atr_exp"), "afz": pre(r.ts, "fz"),
                     "er15": pre(r.ts, "er15", "mean"),
                     "atr20": pre(r.ts, "atr20", "mean")})
    P = pd.DataFrame(rows)
    P["famA"] = (P.volz >= 2.0) | (P.atr_exp >= 1.15)
    R["family"] = {}
    for nm, g in (("A — a precursor is visible", P[P.famA]), ("B — nothing to see", P[~P.famA])):
        R["family"][nm] = {"n": int(len(g)), "ceiling": int(g.ceil.sum()),
                           "median_move": round(float(g.move.median()), 0) if len(g) else None,
                           "med_volz": round(float(g.volz.median()), 2) if len(g) else None,
                           "med_atrexp": round(float(g.atr_exp.median()), 2) if len(g) else None,
                           "up": int((g["dir"] > 0).sum()), "dn": int((g["dir"] < 0).sum())}
        print(f"  FAMILY {nm}: n={len(g)} ceiling=${g.ceil.sum():,} median move {g.move.median():.0f}pt "
              f"UP {int((g['dir']>0).sum())}/DN {int((g['dir']<0).sum())}")

    # base rate of that same precursor on ALL tape — the label-interrogation step
    wk = m.loc["2026-08-23 22:00":"2026-08-28 21:00"]
    pv = wk["volz"].rolling(10, min_periods=5).max().shift(1)
    pa = wk["atr_exp"].rolling(10, min_periods=5).max().shift(1)
    base = ((pv >= 2.0) | (pa >= 1.15))
    R["family_base_rate"] = {"minutes": int(base.notna().sum()),
                             "pct_true": round(100 * float(base.mean()), 1),
                             "famA_share_of_runs": round(100 * float(P.famA.mean()), 1)}
    print(f"  precursor base rate on all tape: {100*base.mean():.1f}% of minutes; "
          f"{100*P.famA.mean():.1f}% of the runs — lift {P.famA.mean()/max(1e-9,base.mean()):.2f}x")

    # ---- THE ORACLE PROOF ---------------------------------------------------------------------
    print("\n=== THE ORACLE PROOF — same boards, three different direction rules ===")
    W, k, LOCK = 5, 2.0, 15
    wk2 = m.loc["2026-08-23 22:00":"2026-08-28 21:00"]
    mv = wk2["close"] - wk2["close"].shift(W)
    fire = (mv.abs() >= k * wk2["atr20"]) & wk2["atr20"].gt(0) & wk2["ok10"]
    runwin = [(r.ts - pd.Timedelta(minutes=5), r.ts + pd.Timedelta(minutes=15)) for _, r in sat.iterrows()]
    boards, until = [], pd.Timestamp("2000-01-01", tz="UTC")
    for ts in wk2.index[fire.fillna(False)]:
        if ts < until:
            continue
        until = ts + pd.Timedelta(minutes=LOCK)
        boards.append(ts)
    print(f"  {len(boards)} boards over the 5 sessions")

    STOP_A, TARG_A, CAP = 2.5, 6.0, 60
    out = {"RULE (board the proven move)": [], "ORACLE (know the next 15 min)": [],
           "ANTI-ORACLE (get it backwards)": [], "RULE, boards inside a run only": [],
           "RULE, boards NOT in a run": []}
    for ts in boards:
        row = wk2.loc[ts]
        atr = float(row.atr20)
        if not np.isfinite(atr) or atr <= 0:
            continue
        d_rule = int(np.sign(mv.loc[ts]))
        fw = row.fwd15
        d_or = int(np.sign(fw)) if np.isfinite(fw) and fw != 0 else d_rule
        inrun = any(a <= ts <= b for a, b in runwin)
        for nm, side in (("RULE (board the proven move)", d_rule),
                         ("ORACLE (know the next 15 min)", d_or),
                         ("ANTI-ORACLE (get it backwards)", -d_or)):
            res = race(ts + pd.Timedelta(minutes=1), side, STOP_A * atr, TARG_A * atr, CAP)
            if res:
                out[nm].append({"ts": ts, "pnl": res[2], "minutes": res[4], "reason": res[3]})
        res = race(ts + pd.Timedelta(minutes=1), d_rule, STOP_A * atr, TARG_A * atr, CAP)
        if res:
            out["RULE, boards inside a run only" if inrun else "RULE, boards NOT in a run"].append(
                {"ts": ts, "pnl": res[2], "minutes": res[4], "reason": res[3]})
    R["oracle"] = {}
    for nm, rows2 in out.items():
        d = serial(rows2) if rows2 else pd.DataFrame()
        st = stat(d)
        R["oracle"][nm] = st
        print(f"  {nm:<36} n={st['n']:<4} net=${st['net']:>9,.0f}  $/tr={st['per']:>+8.2f}  win={st['win']:>5.1f}%")
    json.dump(R, open(f"{OUT}/family.json", "w"), indent=1, default=str)
    return R


# ── STAGE 3 — THE ESCALATION: does a footprint appear as the runs get bigger? ─────────────────
def auc(x, y):
    """Rank AUC. x = feature, y = boolean label. Ties handled by average ranks."""
    x, y = np.asarray(x, float), np.asarray(y, bool)
    ok = np.isfinite(x)
    x, y = x[ok], y[ok]
    if y.sum() < 5 or (~y).sum() < 5:
        return np.nan
    r = pd.Series(x).rank().to_numpy()
    n1, n0 = y.sum(), (~y).sum()
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def stage_escalate(nperm=2000, seed=7):
    """Measured on the UNSELECTED population — every minute with a resolvable forward 15 minutes —
    never on the census's keep-strongest run list, whose pre-run statistics are a picker artefact."""
    rng = np.random.default_rng(seed)
    m = minutes().join(ticks_min()[["nt", "ntz", "flow", "fz"]], how="left")
    d = m.loc["2026-07-06":"2026-08-28"].copy()
    d["pre_volz"] = d["volz"].rolling(10, min_periods=5).max().shift(1)
    d["pre_ntz"] = d["ntz"].rolling(10, min_periods=5).max().shift(1)
    d["pre_atrexp"] = d["atr_exp"].shift(1)
    d["pre_afz"] = d["fz"].abs().rolling(10, min_periods=5).max().shift(1)
    d["pre_er15"] = d["er15"].shift(1)
    d["pre_atr"] = d["atr20"]
    d = d[d["ok"] & d["fwd15"].notna()]
    feats = ["pre_volz", "pre_ntz", "pre_atrexp", "pre_afz", "pre_er15", "pre_atr"]
    R = {"n_minutes": int(len(d)), "days": int(d.index.normalize().nunique()), "bands": []}
    print(f"\n=== ESCALATION — {len(d):,} unselected tape-minutes over "
          f"{d.index.normalize().nunique()} sessions ===")
    for thr in (55, 80, 100, 120, 160, 200):
        y = d["fwd15"].abs() >= thr
        row = {"thr": thr, "n_pos": int(y.sum())}
        for f in feats:
            a = auc(d[f], y)
            if not np.isfinite(a):
                row[f] = None
                continue
            # permutation p: shuffle the label, keep the feature
            xs = d[f].to_numpy()
            yy = y.to_numpy()
            null = np.empty(nperm)
            for i in range(nperm):
                null[i] = auc(xs, rng.permutation(yy))
            row[f] = round(a, 3)
            row[f + "_p"] = round(float((np.abs(null - .5) >= abs(a - .5)).mean()), 4)
        R["bands"].append(row)
        print(f"  |fwd15| >= {thr:>3}pt  n={int(y.sum()):>5}  " +
              "  ".join(f"{f.replace('pre_',''):}={row[f]}" for f in feats))
    # ⚠ THE SCALE CONTROL. A 15-minute move measured in POINTS is mechanically bigger on a loud
    # minute, so an ATR AUC of 0.80 mostly re-measures the volatility level. Re-run the same
    # escalation with the label expressed in ATRs — "was this a big move FOR THIS TAPE".
    print("\n=== the same escalation with the move measured in ATRs (the scale control) ===")
    R["bands_atr"] = []
    d["fwd_atr"] = d["fwd15"].abs() / d["atr20"].replace(0, np.nan)
    for thr in (3, 5, 8, 12):
        y = d["fwd_atr"] >= thr
        row = {"thr_atr": thr, "n_pos": int(y.sum())}
        for f in feats:
            a = auc(d[f], y)
            row[f] = None if not np.isfinite(a) else round(a, 3)
        R["bands_atr"].append(row)
        print(f"  |fwd15| >= {thr:>2} ATR  n={int(y.sum()):>5}  " +
              "  ".join(f"{f.replace('pre_','')}={row[f]}" for f in feats))

    # ★★ THE DECIDING CONTROL. Both labels above are contaminated by the volatility term, with
    # OPPOSITE signs: |fwd15| in POINTS is mechanically bigger on a loud minute, and |fwd15| in
    # ATRs has that same loud minute in its denominator. The scale-free question is whether any
    # feature adds anything ON TOP OF the ATR level, so: stratify on ATR decile and compute the
    # AUC INSIDE each stratum, then pool weighted by stratum size.
    print("\n=== the deciding control — AUC measured INSIDE ATR deciles (points label) ===")
    R["within_atr"] = []
    dec = pd.qcut(d["atr20"], 10, labels=False, duplicates="drop")
    for thr in (55, 80, 120, 160):
        y = (d["fwd15"].abs() >= thr).to_numpy()
        row = {"thr": thr}
        for f in feats:
            num = den = 0.0
            for q in range(int(np.nanmax(dec)) + 1):
                sel = (dec == q).to_numpy()
                a = auc(d[f].to_numpy()[sel], y[sel])
                if np.isfinite(a):
                    num += a * sel.sum()
                    den += sel.sum()
            row[f] = round(num / den, 3) if den else None
        R["within_atr"].append(row)
        print(f"  >= {thr:>3}pt   " + "  ".join(f"{f.replace('pre_','')}={row[f]}" for f in feats))

    # DIRECTION, among the minutes that DID produce a move
    print("\n=== …and DIRECTION, among the minutes that did produce a move ===")
    R["direction"] = []
    for thr in (55, 80, 120, 160):
        g = d[d["fwd15"].abs() >= thr]
        up = g["fwd15"] > 0
        row = {"thr": thr, "n": int(len(g)), "up_pct": round(100 * float(up.mean()), 1)}
        for f, lab in (("mv5", "prior 5-min move"), ("brk30", "30-min range break"),
                       ("flow", "60s net aggressor flow")):
            if f in g:
                row[lab] = round(auc(g[f], up), 3)
        # the crudest rule: does the move continue the prior 15 minutes?
        cont = (np.sign(g["close"] - g["close"].shift(15)) == np.sign(g["fwd15"]))
        row["continuation_agrees_pct"] = round(100 * float(cont.mean()), 1)
        R["direction"].append(row)
        print(f"  >= {thr:>3}pt  n={len(g):>5}  up {row['up_pct']}%  "
              f"continuation agrees {row['continuation_agrees_pct']}%  " +
              "  ".join(f"{k}={v}" for k, v in row.items() if k.startswith(('prior', '30-', '60s'))))
    json.dump(R, open(f"{OUT}/escalate.json", "w"), indent=1, default=str)
    return R


# ── STAGE 4 — THE FRESH CANDIDATE: COIL-BRK, built on the within-ATR finding ──────────────────
def coil_signals(d, coil_q=0.30, wait=10, rng_win=15, arm_col="atr_exp"):
    """ARM on a CONTRACTING minute — atr_exp in the bottom `coil_q` of its trailing 2-day
    distribution, measured causally. TRIGGER on the first close outside the trailing `rng_win`
    range within `wait` minutes. Two-sided: the tape picks the side, the gate picks the moment."""
    q = d[arm_col].rolling(2880, min_periods=400).quantile(coil_q).shift(1)
    armed = (d[arm_col] <= q) & d["ok"]
    hi = d["high"].rolling(rng_win, min_periods=rng_win).max().shift(1)
    lo = d["low"].rolling(rng_win, min_periods=rng_win).min().shift(1)
    up = d["close"] > hi
    dn = d["close"] < lo
    a = armed.to_numpy()
    U, D = up.to_numpy(), dn.to_numpy()
    idx = d.index
    sig, last_arm = [], -10**9
    for i in range(len(d)):
        if a[i]:
            last_arm = i
        if i - last_arm <= wait and i > last_arm:
            if U[i]:
                sig.append((idx[i], 1, i))
            elif D[i]:
                sig.append((idx[i], -1, i))
    return sig


def run_candidate(sig, d, stop_k, targ_k, cap, lock=30):
    rows, until = [], pd.Timestamp("2000-01-01", tz="UTC")
    for ts, side, i in sig:
        if ts < until:
            continue
        atr = d["atr20"].iat[i]
        if not np.isfinite(atr) or atr <= 0:
            continue
        r = race(ts + pd.Timedelta(minutes=1), side, stop_k * atr,
                 (targ_k * atr) if targ_k else None, cap)
        if not r:
            continue
        until = ts + pd.Timedelta(minutes=max(lock, r[4]))
        rows.append({"ts": ts, "side": side, "atr": float(atr), "pnl": r[2],
                     "reason": r[3], "minutes": r[4], "mfe": r[5], "mae": r[6]})
    return pd.DataFrame(rows)


def battery(d, sig, stop_k, targ_k, cap, label, oos_from="2026-08-17", seed=11):
    t = run_candidate(sig, d, stop_k, targ_k, cap)
    if t.empty:
        return {"label": label, "n": 0}
    t["day"] = t["ts"].dt.date.astype(str)
    v = t["pnl"].to_numpy()
    srt = np.sort(v)[::-1]
    days = t.groupby("day")["pnl"].sum()
    loo = [(v.sum() - g) / (len(v) - (t.day == dnm).sum()) for dnm, g in days.items()
           if len(v) - (t.day == dnm).sum() > 0]
    isl, oosl = t[t.day < oos_from], t[t.day >= oos_from]
    lo, sh = t[t.side > 0], t[t.side < 0]
    res = {"label": label, "spec": f"stop {stop_k}xATR / target {targ_k}xATR / cap {cap}m",
           **stat(t),
           "strip1": round(float((v.sum() - srt[:1].sum()) / max(1, len(v) - 1)), 3),
           "strip3": round(float((v.sum() - srt[:3].sum()) / max(1, len(v) - 3)), 3),
           "strip5": round(float((v.sum() - srt[:5].sum()) / max(1, len(v) - 5)), 3),
           "days_green": int((days > 0).sum()), "days_total": int(len(days)),
           "loo_worst": round(float(min(loo)), 3) if loo else None,
           "loo_med": round(float(np.median(loo)), 3) if loo else None,
           "IS": stat(isl), "OOS": stat(oosl),
           "LONG": stat(lo), "SHORT": stat(sh)}
    # sign-flip control
    flip = run_candidate([(ts, -s, i) for ts, s, i in sig], d, stop_k, targ_k, cap)
    res["signflip"] = stat(flip)
    # time-shifted placebo: keep the trigger, shift the ARM series
    rng = np.random.default_rng(seed)
    pl = []
    for sh_min in (30, 60, 120, 240, 480):
        d2 = d.copy()
        d2["atr_exp"] = d2["atr_exp"].shift(sh_min)
        s2 = coil_signals(d2)
        p = run_candidate(s2, d, stop_k, targ_k, cap)
        pl.append({"shift_min": sh_min, **stat(p)})
    res["placebo"] = pl
    res["placebo_beat"] = int(sum(1 for p in pl if p["per"] >= res["per"]))
    return res


def stage_fresh():
    m = minutes()
    d = m.loc["2026-06-22":"2026-08-28"].copy()
    R = {"window": ["2026-06-22", "2026-08-28"], "sessions": int(d.index.normalize().nunique())}
    print(f"\n=== COIL-BRK — {R['sessions']} sessions of 5s tape ===")

    print("\n-- the arm ladder (stop 2.0 / target 4.0 / cap 60) --")
    R["arm_ladder"] = []
    for q in (0.10, 0.20, 0.30, 0.40, 0.50, 0.70, 1.00):
        sig = coil_signals(d, coil_q=q)
        t = run_candidate(sig, d, 2.0, 4.0, 60)
        st = stat(t)
        R["arm_ladder"].append({"coil_q": q, **st})
        print(f"  coil_q={q:<5} n={st['n']:<5} net=${st['net']:>9,.0f}  $/tr={st['per']:>+7.2f}  win={st['win']}%")

    print("\n-- the exit surface at coil_q=0.30 (rows=stop xATR, cols=target xATR) --")
    sig = coil_signals(d, coil_q=0.30)
    R["exit_surface"] = {}
    for s_k in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
        row = {}
        for t_k in (1.5, 2.0, 3.0, 4.0, 6.0, 8.0):
            st = stat(run_candidate(sig, d, s_k, t_k, 60))
            row[str(t_k)] = st["per"]
        R["exit_surface"][str(s_k)] = row
        print(f"  stop {s_k:<4} " + "  ".join(f"t{k}={v:>+7.2f}" for k, v in row.items()))

    print("\n-- the window sweep (wait x range window) at stop 2.0 / target 4.0 --")
    R["win_sweep"] = []
    for wait in (5, 10, 20):
        for rw in (10, 15, 30):
            st = stat(run_candidate(coil_signals(d, 0.30, wait, rw), d, 2.0, 4.0, 60))
            R["win_sweep"].append({"wait": wait, "rng_win": rw, **st})
            print(f"  wait={wait:<3} rng={rw:<3} n={st['n']:<5} $/tr={st['per']:>+7.2f}")
    json.dump(R, open(f"{OUT}/fresh.json", "w"), indent=1, default=str)
    return R


def plain_break(d, rng_win=15):
    """The same two-sided break with NO arm at all — the control the coil ladder needs."""
    hi = d["high"].rolling(rng_win, min_periods=rng_win).max().shift(1)
    lo = d["low"].rolling(rng_win, min_periods=rng_win).min().shift(1)
    U, D, ok = (d["close"] > hi).to_numpy(), (d["close"] < lo).to_numpy(), d["ok"].to_numpy()
    return [(d.index[i], 1 if U[i] else -1, i) for i in range(len(d))
            if ok[i] and (U[i] or D[i])]


def stage_fresh2():
    m = minutes()
    d = m.loc["2026-06-22":"2026-08-28"].copy()
    R = {}
    print("\n=== the control the arm ladder needs: the SAME break with no arm ===")
    for s_k, t_k in ((2.0, 4.0), (3.0, 8.0)):
        st = stat(run_candidate(plain_break(d), d, s_k, t_k, 60))
        R[f"unarmed_{s_k}_{t_k}"] = st
        print(f"  unarmed break, stop {s_k}/targ {t_k}: n={st['n']} net=${st['net']:,.0f} "
              f"$/tr={st['per']:+.2f} win={st['win']}%")
    print("\n=== the battery on COIL-BRK's two best cells ===")
    sig = coil_signals(d, coil_q=0.30)
    R["battery"] = []
    for s_k, t_k in ((3.0, 8.0), (3.0, 4.0), (2.0, 4.0)):
        b = battery(d, sig, s_k, t_k, 60, f"COIL-BRK stop{s_k}/targ{t_k}")
        R["battery"].append(b)
        print(f"\n  {b['label']}: n={b['n']} net=${b['net']:,.0f} $/tr={b['per']:+.2f} win={b['win']}%")
        print(f"    strip1/3/5 {b['strip1']:+.2f} / {b['strip3']:+.2f} / {b['strip5']:+.2f}"
              f"   days green {b['days_green']}/{b['days_total']}   LOO worst {b['loo_worst']:+.2f}")
        print(f"    IS {b['IS']['n']}/{b['IS']['per']:+.2f}   OOS {b['OOS']['n']}/{b['OOS']['per']:+.2f}"
              f"   LONG {b['LONG']['n']}/{b['LONG']['per']:+.2f}  SHORT {b['SHORT']['n']}/{b['SHORT']['per']:+.2f}")
        pls = ", ".join("%dm %+.2f" % (p["shift_min"], p["per"]) for p in b["placebo"])
        print(f"    sign-flip control {b['signflip']['per']:+.2f}   "
              f"placebos beating it: {b['placebo_beat']}/5  ({pls})")
    json.dump(R, open(f"{OUT}/fresh2.json", "w"), indent=1, default=str)
    return R


# ── STAGE 5 — THE FROZEN SPECS, WALKED FORWARD ONTO TAPE THEY HAVE NEVER SEEN ─────────────────
#
# Each dossier froze a mechanical spec on a stated window. Those windows all end before this
# week's tape. Re-deriving the specs here and running them unchanged on the days after each
# dossier's own cut-off is the only test on this page where the TAPE was chosen after the RULE.
# ⚠ The instruments are MINE, not the dossiers' (my ATR is the 20-minute mean 1-min range, theirs
# vary), so the ABSOLUTE levels will not match. Read the IS -> OOS SHAPE, which is what a forward
# walk is for, and the in-sample column is printed so the shape can be checked against the dossier.
FROZEN = {
    "UNCL-RIDE-ER   (UNCLASS lab, frozen 08-25)": dict(cut="2026-08-25", stop=2.0, targ=10.0,
                                                       cap=240, lock=60),
    "board_atrband  (RIDER_ALL lab, frozen 08-25)": dict(cut="2026-08-25", stop=3.0, targ=6.0,
                                                         cap=240, lock=60),
    "FL-4 flow_ignition (FLOW-LED lab, frozen 08-25)": dict(cut="2026-08-26", stop=1.0, targ=1.5,
                                                            cap=15, lock=15),
    "MOMBRK         (OPEN/NEWS lab, frozen 08-25)": dict(cut="2026-08-24", stop=0.5, targ=None,
                                                         cap=30, lock=15),
    "VAC-IGN-BRK    (VACUUM lab, frozen 08-22)": dict(cut="2026-08-24", stop=1.5, targ=None,
                                                      cap=30, lock=15),
}


def frozen_signals(name, d):
    idx = d.index
    if name.startswith("UNCL-RIDE-ER"):
        mv = d["close"] - d["close"].shift(5)
        f = (mv.abs() >= 2.5 * d["atr20"]) & (d["er30"] >= 0.40) & d["ok"]
    elif name.startswith("board_atrband"):
        mv = d["close"] - d["close"].shift(10)
        f = ((d["atr20"] >= 11) & (d["atr20"] < 16) & (mv.abs() >= 2.5 * d["atr20"])
             & (d["er10"] >= 0.50) & d["ok"])
    elif name.startswith("FL-4"):
        mv = d["fz"]
        f = ((d["fz"].abs() >= 1.5) & (np.sign(d["brk30"]) == np.sign(d["fz"]))
             & (d["brk30"].abs() >= 0.5) & (d["atr_rel"] >= 1.6) & (d["er30"] < 0.35) & d["ok"])
    elif name.startswith("MOMBRK"):
        mv = d["close"] - d["close"].shift(15)
        f = ((d["ntz"] >= 1.5) & (idx.hour >= 13) & (idx.hour < 15) & d["ok"])
    else:                                                        # VAC-IGN-BRK
        hi = d["high"].rolling(5, min_periods=5).max().shift(1)
        lo = d["low"].rolling(5, min_periods=5).min().shift(1)
        armed = ((d["volz"] >= 2.0) & (d["atr_exp"] >= 1.15)).to_numpy()
        U, D = (d["close"] > hi).to_numpy(), (d["close"] < lo).to_numpy()
        sig, last = [], -10**9
        for i in range(len(d)):
            if armed[i]:
                last = i
            if 0 < i - last <= 10 and d["ok"].iat[i]:
                if U[i]:
                    sig.append((idx[i], 1, i))
                elif D[i]:
                    sig.append((idx[i], -1, i))
        return sig
    f = f.fillna(False).to_numpy()
    sd = np.sign(mv.to_numpy())
    return [(idx[i], int(sd[i]), i) for i in range(len(d)) if f[i] and sd[i] != 0]


def stage_frozen():
    m = minutes().join(ticks_min()[["nt", "ntz", "flow", "fz"]], how="left")
    d = m.loc["2026-07-06":"2026-08-28"].copy()
    R = {}
    print("\n=== FIVE FROZEN SPECS, WALKED FORWARD ===")
    for name, cfg in FROZEN.items():
        sig = frozen_signals(name, d)
        t = run_candidate(sig, d, cfg["stop"], cfg["targ"], cfg["cap"], lock=cfg["lock"])
        if t.empty:
            R[name] = {"n": 0}
            print(f"  {name}: NO FIRES")
            continue
        t["day"] = t["ts"].dt.date.astype(str)
        isl, oosl = t[t.day < cfg["cut"]], t[t.day >= cfg["cut"]]
        R[name] = {"cut": cfg["cut"], "ALL": stat(t), "IS": stat(isl), "OOS": stat(oosl),
                   "OOS_long": stat(oosl[oosl.side > 0]), "OOS_short": stat(oosl[oosl.side < 0]),
                   "spec": f"stop {cfg['stop']}xATR / target {cfg['targ']} / cap {cfg['cap']}m"}
        a, i_, o = R[name]["ALL"], R[name]["IS"], R[name]["OOS"]
        print(f"  {name}")
        print(f"      IS  (to {cfg['cut']})  n={i_['n']:<5} net=${i_['net']:>9,.0f}  $/tr={i_['per']:>+7.2f}  win={i_['win']:>5.1f}%")
        print(f"      OOS (from {cfg['cut']})  n={o['n']:<5} net=${o['net']:>9,.0f}  $/tr={o['per']:>+7.2f}  win={o['win']:>5.1f}%")
    json.dump(R, open(f"{OUT}/frozen.json", "w"), indent=1, default=str)
    return R


# ── STAGE 6 — THE SIZE THRESHOLD IN MONEY ─────────────────────────────────────────────────────
def _boards(d, stop_pt=None, stop_k=2.5, targ_k=6.0, cap=60):
    mv = d["close"] - d["close"].shift(5)
    fire = (mv.abs() >= 2.0 * d["atr20"]) & d["atr20"].gt(0) & d["ok10"]
    rows, until = [], pd.Timestamp("2000-01-01", tz="UTC")
    for i, ts in enumerate(d.index):
        if not bool(fire.iat[i]) or ts < until:
            continue
        atr = d["atr20"].iat[i]
        side = int(np.sign(mv.iat[i]))
        if side == 0 or not np.isfinite(atr) or atr <= 0:
            continue
        sp = stop_pt if stop_pt else stop_k * atr
        tp = None if stop_pt else targ_k * atr
        r = race(ts + pd.Timedelta(minutes=1), side, sp, tp, cap)
        if not r:
            continue
        until = ts + pd.Timedelta(minutes=max(15, r[4]))
        fw = d["fwd15"].iat[i]
        rows.append({"ts": ts, "side": side, "pnl": r[2], "reason": r[3], "minutes": r[4],
                     "follow": float(side * fw) if np.isfinite(fw) else np.nan, "atr": float(atr)})
    return pd.DataFrame(rows).dropna(subset=["follow"])


def stage_size():
    """At what realised follow-through does a board stop losing money? Measured on the boards the
    dumb trigger actually took, over the whole 5s lake, so the buckets have n.

    ★ AND THE CONTROL THE DESK'S OWN "120pt" LORE HAS NEVER HAD: the same measurement with an
    ATR-SCALED stop and with the FIXED 22-point stop the OPEN/NEWS lab used. If the threshold moves
    with the stop, it is a property of the stop and not of the tape."""
    d = minutes().loc["2026-06-22":"2026-08-28"].copy()
    bins = [-1e9, -60, -20, 20, 60, 120, 1e9]
    lab = ["went hard against (<= -60pt)", "-60 .. -20pt", "-20 .. +20pt (nothing happened)",
           "+20 .. +60pt", "+60 .. +120pt", ">= +120pt"]
    R = {}
    for nm, kw in (("ATR-scaled stop 2.5xATR / target 6xATR", dict()),
                   ("FIXED 22pt stop, no target (the OPEN/NEWS ruler)", dict(stop_pt=22.0))):
        t = _boards(d, **kw)
        t["band"] = pd.cut(t["follow"], bins, labels=lab)
        g = t.groupby("band", observed=True)["pnl"].agg(["count", "sum", "mean"])
        cum = {}
        for x in (0, 20, 40, 60, 80, 120):
            sel = t[t["follow"] >= x]
            cum[str(x)] = {"n": int(len(sel)), "per": round(float(sel.pnl.mean()), 2) if len(sel) else None,
                           "pct": round(100 * len(sel) / len(t), 1)}
        R[nm] = {"n": int(len(t)), "net": round(float(t.pnl.sum()), 0),
                 "per": round(float(t.pnl.mean()), 3),
                 "bands": {str(k): {"n": int(v["count"]), "net": round(float(v["sum"]), 0),
                                    "per": round(float(v["mean"]), 2),
                                    "pct": round(100 * v["count"] / len(t), 1)}
                           for k, v in g.iterrows()},
                 "cumulative_at_or_above": cum}
        print(f"\n=== {nm} — {len(t)} boards, net ${t.pnl.sum():,.0f} (${t.pnl.mean():+.2f}/trade) ===")
        for k, v in R[nm]["bands"].items():
            print(f"  {k:<34} n={v['n']:>4} ({v['pct']:>4.1f}%)  net=${v['net']:>+9,.0f}  $/tr={v['per']:>+8.2f}")
        print("  cumulative $/trade for boards whose follow-through reached at least:")
        for x, v in cum.items():
            print(f"    >= {x:>3}pt   n={v['n']:>4} ({v['pct']:>4.1f}% of boards)   $/tr={v['per']:>+8.2f}")
    json.dump(R, open(f"{OUT}/size.json", "w"), indent=1, default=str)
    return R


# ── STAGE 7 — BIG-MOVES-CAUGHT against THIS week's frozen census ──────────────────────────────
def stage_catches():
    """A gate is credited with a run if it opened a CORRECTLY-SIGNED position between 5 minutes
    before the run's stamp and 15 minutes after it. Scored against this week's frozen 62."""
    m = minutes().join(ticks_min()[["nt", "ntz", "flow", "fz"]], how="left")
    d = m.loc["2026-08-23 22:00":"2026-08-28 21:00"].copy()
    runs = census()
    sat = runs[runs.us == "sat out"].reset_index(drop=True)
    top25 = sat.reindex(sat.move.abs().sort_values(ascending=False).index).head(25)
    top15 = top25.head(15)
    wins = [(r.ts - pd.Timedelta(minutes=5), r.ts + pd.Timedelta(minutes=15), r["dir"], r.ceil)
            for _, r in sat.iterrows()]
    w25 = set(top25.ts)
    w15 = set(top15.ts)
    R = {}

    cands = {"the dumb boarder (5-min thrust >= 2.0xATR)":
             ([(ts, int(np.sign(v)), i) for i, (ts, v) in
               enumerate(zip(d.index, (d["close"] - d["close"].shift(5)).to_numpy()))
               if np.isfinite(v) and d["atr20"].iat[i] > 0 and abs(v) >= 2.0 * d["atr20"].iat[i]
               and bool(d["ok10"].iat[i]) and np.sign(v) != 0], 2.5, 6.0, 60),
             "COIL-BRK (this week's fresh candidate)": (coil_signals(d, 0.30), 3.0, 8.0, 60)}
    for nm in FROZEN:
        cfg = FROZEN[nm]
        cands[nm.split("(")[0].strip()] = (frozen_signals(nm, d), cfg["stop"], cfg["targ"], cfg["cap"])

    for nm, (sig, sk, tk, cap) in cands.items():
        t = run_candidate(sig, d, sk, tk, cap)
        if t.empty:
            R[nm] = {"n": 0, "caught": 0, "top25": 0, "top15": 0, "net": 0.0}
            continue
        caught, c25, c15, money = set(), 0, 0, 0.0
        for _, tr in t.iterrows():
            for a, b, dr, ce in wins:
                if a <= tr.ts <= b and tr.side == dr:
                    if a + pd.Timedelta(minutes=5) not in caught:
                        pass
                    caught.add(a)
                    money += tr.pnl
                    break
        c25 = sum(1 for a in caught if a + pd.Timedelta(minutes=5) in w25)
        c15 = sum(1 for a in caught if a + pd.Timedelta(minutes=5) in w15)
        R[nm] = {**stat(t), "caught": len(caught), "of": int(len(sat)),
                 "top25": c25, "top15": c15, "money_on_those": round(money, 2)}
        print(f"  {nm:<45} n={R[nm]['n']:<4} net=${R[nm]['net']:>+8,.0f} "
              f"$/tr={R[nm]['per']:>+7.2f}  caught {len(caught)}/{len(sat)}  "
              f"top25 {c25}/25  top15 {c15}/15  (${money:+,.0f} on those)")
    json.dump(R, open(f"{OUT}/catches.json", "w"), indent=1, default=str)
    return R


# ── STAGE 8 — THE RUN CHART ───────────────────────────────────────────────────────────────────
def stage_chart(run_ts="2026-08-24 13:29", pre=14, post=32):
    """Inline self-contained SVG: the real 5s price path of the week's biggest run, with the dumb
    boarder's entry and exit marked on it. No CDN, no library, no external image."""
    d = minutes()
    b = bars5s()
    t0 = pd.Timestamp(run_ts, tz="UTC")
    seg = b.loc[t0 - pd.Timedelta(minutes=pre): t0 + pd.Timedelta(minutes=post)]
    mv = d["close"] - d["close"].shift(5)
    board = None
    for ts in d.loc[t0: t0 + pd.Timedelta(minutes=15)].index:
        atr = d["atr20"].get(ts, np.nan)
        v = mv.get(ts, np.nan)
        if np.isfinite(atr) and atr > 0 and np.isfinite(v) and abs(v) >= 2.0 * atr:
            board = (ts, float(atr), int(np.sign(v)))
            break
    trade = None
    if board:
        ts, atr, side = board
        r = race(ts + pd.Timedelta(minutes=1), side, 2.5 * atr, 6.0 * atr, 60)
        if r:
            ent, ex, pnl, reason, mins, mfe, mae = r
            i = b.index.searchsorted(ts + pd.Timedelta(minutes=1), side="left")
            trade = {"in_ts": b.index[i], "in_px": ent,
                     "out_ts": b.index[min(i + int(mins * 12), len(b) - 1)], "out_px": ex,
                     "pnl": pnl, "reason": reason, "side": side, "minutes": mins}
    W, H, L, Rm, T, B = 980, 340, 62, 18, 26, 46
    px = seg["close"].to_numpy()
    lo, hi = float(seg["low"].min()), float(seg["high"].max())
    pad = (hi - lo) * 0.06
    lo, hi = lo - pad, hi + pad
    xs = np.linspace(L, W - Rm, len(px))

    def Y(p):
        return T + (hi - p) / (hi - lo) * (H - T - B)
    path = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{Y(p):.1f}" for i, (x, p) in enumerate(zip(xs, px)))
    def X_at(ts):
        j = seg.index.searchsorted(ts, side="left")
        return float(xs[min(max(j, 0), len(xs) - 1)])
    g = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'style="font:11px/1.3 system-ui,sans-serif;background:#fff">']
    for k in range(5):
        p = lo + (hi - lo) * k / 4
        y = Y(p)
        g.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W-Rm}" y2="{y:.1f}" stroke="#e8eaee"/>'
                 f'<text x="{L-8}" y="{y+3:.1f}" text-anchor="end" fill="#7a8090">{p:,.0f}</text>')
    xr = X_at(t0)
    g.append(f'<line x1="{xr:.1f}" y1="{T}" x2="{xr:.1f}" y2="{H-B}" stroke="#c2410c" '
             f'stroke-dasharray="4 3"/>'
             f'<text x="{xr+5:.1f}" y="{T+12}" fill="#c2410c">census run stamp {run_ts[6:]}Z</text>')
    g.append(f'<path d="{path}" fill="none" stroke="#1f3b73" stroke-width="1.6"/>')
    if trade:
        xi, yi = X_at(trade["in_ts"]), Y(trade["in_px"])
        xo, yo = X_at(trade["out_ts"]), Y(trade["out_px"])
        col = "#15803d" if trade["pnl"] > 0 else "#b91c1c"
        g.append(f'<line x1="{xi:.1f}" y1="{yi:.1f}" x2="{xo:.1f}" y2="{yo:.1f}" stroke="{col}" '
                 f'stroke-width="1.2" stroke-dasharray="3 2"/>')
        g.append(f'<circle cx="{xi:.1f}" cy="{yi:.1f}" r="5" fill="#15803d"/>'
                 f'<text x="{xi+8:.1f}" y="{yi-6:.1f}" fill="#15803d">IN {trade["in_px"]:,.2f} '
                 f'({"SHORT" if trade["side"]<0 else "LONG"})</text>')
        g.append(f'<circle cx="{xo:.1f}" cy="{yo:.1f}" r="5" fill="{col}"/>'
                 f'<text x="{xo+8:.1f}" y="{yo+14:.1f}" fill="{col}">OUT {trade["out_px"]:,.2f} '
                 f'&middot; {trade["reason"]} &middot; {trade["pnl"]:+,.2f}</text>')
    # where the census's own 15-minute horizon ended — the money that sat on the table
    tend = t0 + pd.Timedelta(minutes=15)
    xe, ye = X_at(tend), Y(float(seg["close"].iloc[min(seg.index.searchsorted(tend), len(seg) - 1)]))
    g.append(f'<circle cx="{xe:.1f}" cy="{ye:.1f}" r="4" fill="none" stroke="#c2410c" stroke-width="2"/>'
             f'<text x="{xe-6:.1f}" y="{ye+16:.1f}" text-anchor="end" fill="#c2410c">'
             f'census horizon +15min &middot; &minus;231pt &middot; $462 ceiling, NOBODY ON IT</text>')
    for frac, ts in ((0.0, seg.index[0]), (0.5, seg.index[len(seg) // 2]), (1.0, seg.index[-1])):
        x = L + frac * (W - Rm - L)
        g.append(f'<text x="{x:.0f}" y="{H-B+16}" text-anchor="middle" fill="#7a8090">'
                 f'{ts.strftime("%H:%M")}Z</text>')
    g.append(f'<text x="{L}" y="{H-8}" fill="#555">MNQ 5-second closes. The census stamped this run '
             f'DN &minus;231pt with a $462 one-lot hindsight ceiling and NO gate on it.</text></svg>')
    svg = "".join(g)
    open(f"{OUT}/runchart.svg.html", "w").write(svg)
    print(f"\nrun chart written; trade = {trade}")
    return {"trade": trade, "svg": svg}
