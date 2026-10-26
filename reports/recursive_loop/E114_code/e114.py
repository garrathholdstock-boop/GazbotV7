"""E114 - order flow before the entry (spec reports/recursive_loop/E114_change.txt). Read-only, zero Claude tokens.

    nice -n 15 .venv/bin/python reports/recursive_loop/E114_code/e114.py > reports/recursive_loop/E114_result.txt
"""
from __future__ import annotations

import collections
import datetime as dt
import glob
import json
import os
import sys

import duckdb
import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/reports/recursive_loop/E113_code")
import e113 as E  # noqa: E402

TICKS = f"{GB}/data/tape/ticks/MNQ"
D0, D1 = "2026-07-24", "2026-10-23"
RNG = np.random.default_rng(114)


def day_ticks(day: dt.date):
    files = [f"{TICKS}/{(day + dt.timedelta(days=k)).isoformat()}.parquet" for k in (-1, 0)]
    files = [f for f in files if os.path.exists(f)]
    if not files:
        return None
    d0 = int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp())
    a = duckdb.connect().execute(
        f"SELECT ts_ms, price, size, CASE aggressor WHEN 'buy' THEN 1 WHEN 'sell' THEN -1 ELSE 0 END FROM read_parquet({files!r}) "
        "WHERE ts_ms >= ? AND ts_ms < ? ORDER BY ts_ms", [(d0 - 7200) * 1000, (d0 + 14 * 3600) * 1000]).fetchnumpy()
    ts, px, sz, sg = (a[k] for k in a)
    if len(ts) < 1000:
        return None
    return {"ts": ts.astype(np.int64), "px": px.astype(float), "cv": np.r_[0, np.cumsum(sz)], "cs": np.r_[0, np.cumsum(sz * sg)]}


def feats(T, s, d, atr):
    ms = s * 1000
    j = int(np.searchsorted(T["ts"], ms))
    if j < 10:
        return None
    w = lambda m: int(np.searchsorted(T["ts"], ms - m * 60000))
    def cvd(m):
        i = w(m); v = T["cv"][j] - T["cv"][i]
        return d * (T["cs"][j] - T["cs"][i]) / v if v > 0 else np.nan
    p = T["px"][j - 1]
    p30 = T["px"][max(w(30) - 1, 0)]; p15 = T["px"][max(w(15) - 1, 0)]
    i15 = w(15); vol15 = T["cv"][j] - T["cv"][i15]
    c30 = cvd(30)
    prog15 = d * (p - p15)
    return {"cvd30": c30, "cvd5": cvd(5), "div30": int(d * (p - p30) >= atr and c30 < 0),
            "absorb_raw": vol15 / prog15 if prog15 > 0 else np.inf, "vol15": vol15}


def main():
    cen = duckdb.connect().execute(f"""SELECT inst, sess, slot_ts, dir, atr, usd_allout, hit37_min FROM read_parquet('{GB}/data/research/E110_census.parquet')
        WHERE inst='MNQ' AND in_live_window ORDER BY sess, slot_ts""").df()
    cen["day"] = pd.to_datetime(cen.sess, unit="D").dt.date
    cen = cen[(cen.day >= dt.date.fromisoformat(D0)) & (cen.day <= dt.date.fromisoformat(D1))].copy()
    rows = []
    for day, g in cen.groupby("day"):
        T = day_ticks(day)
        if T is None:
            continue
        for r in g.itertuples():
            f = feats(T, int(r.slot_ts), int(r.dir), float(r.atr))
            if f:
                rows.append({"day": day, "sess": r.sess, "slot_ts": int(r.slot_ts), "usd": r.usd_allout, **f})
    df = pd.DataFrame(rows)
    med = df[np.isfinite(df.absorb_raw)].groupby("day").absorb_raw.median()
    df["absorb15"] = df.apply(lambda r: r.absorb_raw / med.get(r.day, np.nan) if np.isfinite(r.absorb_raw) else np.inf, axis=1)
    df["tod"] = df.slot_ts % 86400
    days = sorted(df.day.unique())
    vb = {d: dict(zip(g.tod, g.vol15)) for d, g in df.groupby("day")}
    df["rvol15"] = [r.vol15 / np.median([vb[p][r.tod] for p in days[max(0, days.index(r.day) - 10):days.index(r.day)] if r.tod in vb[p]] or [np.nan])
                    for r in df.itertuples()]
    df["D2"] = df.usd <= -2000
    print(f"E114 - ORDER FLOW BEFORE THE ENTRY. MNQ ticks {D0}..{D1}: {df.day.nunique()} sessions, {len(df):,} detector candidates (live window), D2 {df.D2.sum()} ({df.D2.mean():.1%})")
    allr = df.D2.mean()
    def boot(sub):
        g = sub.groupby("day").D2.agg(["sum", "count"]).to_numpy()
        if len(g) < 5:
            return (np.nan, np.nan)
        idx = RNG.integers(0, len(g), (500, len(g)))
        r = g[idx, 0].sum(1) / np.maximum(g[idx, 1].sum(1), 1)
        return tuple(np.percentile(r, [5, 95]) * 100)
    def table(col, edges, labels):
        print(f"\n  {col}")
        b = pd.cut(df[col], edges, labels=labels, right=False)
        for lab in labels:
            s = df[b == lab]
            if len(s):
                lo, hi = boot(s)
                print(f"    {lab:>12}: rows {len(s):>5} days {s.day.nunique():>3}  D2 {s.D2.mean():>6.1%}  lift {s.D2.mean() / allr:>5.2f}  90%CI {lo:5.1f}-{hi:5.1f}%  mean $ {s.usd.mean():>6.0f}")
    table("cvd30", [-9, -0.10, 0, 0.10, 9], ["<-0.10", "-0.10..0", "0..0.10", ">=0.10"])
    table("cvd5", [-9, -0.10, 0, 0.10, 9], ["<-0.10", "-0.10..0", "0..0.10", ">=0.10"])
    table("div30", [0, 1, 2], ["no", "DIVERGENCE"])
    table("absorb15", [0, 0.5, 1, 2, 4, 1e12, np.inf], ["<0.5", "0.5-1", "1-2", "2-4", ">=4", "no progress"])
    table("rvol15", [0, 0.8, 1.25, 2, 1e9], ["<0.8", "0.8-1.25", "1.25-2", ">=2"])
    # desk path with the 3 declared pause rules vs random at the same trade rate
    key = {(int(r.sess), int(r.slot_ts)): r for r in df.itertuples()}
    E_days = [D for D in E.load() if D["inst"] == "MNQ" and dt.date.fromisoformat(D0) <= dt.date(1970, 1, 1) + dt.timedelta(days=D["sess"]) <= dt.date.fromisoformat(D1)]
    rules = {"P1 div30=1": lambda r: r.div30 == 1, "P2 absorb15>=2 & cvd5<0": lambda r: r.absorb15 >= 2 and r.cvd5 < 0, "P3 cvd30<-0.10": lambda r: r.cvd30 < -0.10}
    for D in E_days:
        D["u"] = RNG.random((40, len(D["slot"])))
    def path(D, pz):
        slot, hit, usd = D["slot"], D["hit"], D["usd"]; n = len(slot); i = 0; free = -1; real = 0.0; out = []
        while i < n:
            if slot[i] < free:
                i = int(np.searchsorted(slot, free)); continue
            if real >= E.LOCK:
                break
            if pz(D, i):
                i += 1; continue
            real += usd[i]; out.append(usd[i])
            if np.isfinite(hit[i]):
                free = slot[i] + hit[i] * 60; i += 1
            else:
                break
        return real, out
    def m(pz):
        dl, en = [], []
        for D in E_days:
            r, o = path(D, pz); dl.append(r); en += o
        dl, en = np.array(dl), np.array(en)
        return {"d2": int((dl <= -2000).sum()), "l1": (en <= -1000).mean() * 100 if len(en) else np.nan, "tr": len(en) / len(E_days), "usd": dl.mean()}
    base = m(lambda D, i: False)
    print(f"\n  DESK PATH on {len(E_days)} sessions: BASELINE days<=-2k {base['d2']}  entry<=-1k rate {base['l1']:.1f}%  trades/day {base['tr']:.2f}  $/day {base['usd']:.0f}")
    for name, rule in rules.items():
        pz = lambda D, i, rule=rule: (lambda k: k is not None and rule(k))(key.get((D["sess"], int(D["slot"][i]))))
        r = m(pz)
        lo, hi = 0.0, 0.99
        for _ in range(10):
            q = (lo + hi) / 2
            t = m(lambda D, i, q=q: D["u"][0][i] < q)["tr"]
            lo, hi = (q, hi) if t > r["tr"] else (lo, q)
        ctrl = [m(lambda D, i, q=q, k=k: D["u"][k][i] < q) for k in range(20)]
        c2 = np.percentile([c["d2"] for c in ctrl], [5, 50]); cl = np.percentile([c["l1"] for c in ctrl], [5, 50])
        cand = r["d2"] < c2[0] and r["l1"] < cl[0]
        print(f"  {name:26} days<=-2k {r['d2']:>3}  entry<=-1k rate {r['l1']:4.1f}%  tr/d {r['tr']:.2f}  $/d {r['usd']:>5.0f}  | RANDOM same rate: days<=-2k median {c2[1]:.0f} (5th {c2[0]:.0f}),"
              f" <=-1k rate median {cl[1]:.1f}% (5th {cl[0]:.1f})  -> {'CANDIDATE' if cand else 'no'}")
    # (B) Claude's live presses on these days
    print("\n  (B) CLAUDE LIVE PRESSES (hybrid v1.02) with order flow, outcome = census row at the same slot:")
    for ln in open(f"{GB}/data/hybrid_robot.jsonl"):
        x = json.loads(ln)
        if x.get("event") == "DECISION" and str(x.get("entry_action", "")).startswith("PRESS"):
            s = int(dt.datetime.fromisoformat(x["decision_ts"]).timestamp())
            k = [r for r in df.itertuples() if r.slot_ts == s]
            if k:
                r = k[0]
                print(f"    {x['decision_ts'][:16]} {x['entry_action'][6:]:4}  $ {r.usd:>+6.0f}  cvd30 {r.cvd30:+.2f} cvd5 {r.cvd5:+.2f} div {r.div30} absorb {r.absorb15:.1f} rvol {r.rvol15:.2f}")


if __name__ == "__main__":
    main()
