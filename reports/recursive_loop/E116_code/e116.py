"""E116 - the big-leg filter (spec reports/recursive_loop/E116_change.txt). Read-only, zero Claude tokens.

    nice -n 15 .venv/bin/python reports/recursive_loop/E116_code/e116.py > reports/recursive_loop/E116_result.txt
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import sys

import duckdb
import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/reports/recursive_loop/E110_code")
sys.path.insert(0, f"{GB}/reports/recursive_loop/E113_code")
import census as C  # noqa: E402
import e113 as E  # noqa: E402

KS = (20, 30, 45, 60)
RNG = np.random.default_rng(116)


def big_dirs():
    """{(inst, slot_ts): {K: dir}} for every census slot, from the same back-adjusted segments the census used."""
    segs, _ = C.load()
    for g in segs:
        C.back_adjust(g)
    cen = duckdb.connect().execute(f"SELECT inst, slot_ts FROM read_parquet('{C.OUT_PARQUET}') WHERE in_live_window").df()
    out = {K: np.zeros(len(cen), dtype=np.int8) for K in KS}
    for g in segs:
        bars = list(zip(g["bar_ts"].tolist(), g["high"].tolist(), g["low"].tolist(), g["close"].tolist()))
        atr = C.DF.atr14(bars)
        lo, hi = g["bar_ts"][0], g["bar_ts"][-1]
        m = ((cen.inst == g["inst"]) & (cen.slot_ts >= lo) & (cen.slot_ts <= hi + 86400)).to_numpy()
        slots = cen.slot_ts.to_numpy()[m]
        for K in KS:
            piv = C.DF.zigzag(bars, atr, lambda leg, a, K=K: K * a)
            cts = np.array([p[3] for p in piv], dtype=np.int64); nd = np.array([p[2] for p in piv], dtype=np.int8)
            k = np.searchsorted(cts + 60, slots - 60, "right") - 1
            out[K][m] = np.where(k >= 0, nd[np.maximum(k, 0)], 0)
        print(f"  {g['name']}: big legs computed", flush=True)
    for K in KS:
        cen[f"big{K}"] = out[K]
    return cen


def main():
    print("E116 - THE BIG-LEG FILTER (spec reports/recursive_loop/E116_change.txt)")
    bd = big_dirs()
    df = duckdb.connect().execute(f"""SELECT inst, sess, slot_ts, dir, usd_allout, period FROM read_parquet('{C.OUT_PARQUET}') WHERE in_live_window""").df()
    df = df.merge(bd, on=["inst", "slot_ts"], how="left")
    df["D2"] = df.usd_allout <= -2000; df["D4"] = df.usd_allout <= -4000
    print("\n(2) PER CANDIDATE: with vs against the big leg (10-yr census, live window)")
    for K in KS:
        print(f"  K_big={K}")
        for p in E.PERIODS:
            s = df[df.period == p]
            w, a = s[s[f"big{K}"] == s.dir], s[s[f"big{K}"] == -s.dir]
            print(f"    {p:8} WITH n {len(w):>7,} D2 {w.D2.mean():6.1%} D4 {w.D4.mean():5.1%} mean $ {w.usd_allout.mean():>5.0f} | AGAINST n {len(a):>7,} ({len(a)/len(s):.0%})"
                  f" D2 {a.D2.mean():6.1%} D4 {a.D4.mean():5.1%} mean $ {a.usd_allout.mean():>5.0f}")
    # (3) desk path
    key = {(r.inst, int(r.slot_ts)): r for r in df.itertuples()}
    days = E.load()
    for D in days:
        D["big"] = {K: np.array([key[(D["inst"], int(s))].__getattribute__(f"big{K}") for s in D["slot"]]) for K in KS}
        D["dirv"] = np.array([key[(D["inst"], int(s))].dir for s in D["slot"]])
        D["u"] = RNG.random((20, len(D["slot"])))
    P = {p: [D for D in days if D["period"] == p] for p in E.PERIODS}

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

    def m(ds, pz):
        dl, en, tr = [], [], 0
        for D in ds:
            r, o = path(D, pz); dl.append(r); en += o; tr += bool(o)
        dl, en = np.array(dl), np.array(en)
        return {"d2": int((dl <= -2000).sum()), "l1": (en <= -1000).mean() * 100, "usd": dl.mean(), "pos": (dl > 0).sum() / max(tr, 1) * 100, "tr": len(en) / len(ds)}
    print("\n(3) DESK PATH: pause if AGAINST the big leg, vs a RANDOM pause at the same trade rate")
    cand = {}
    for K in KS:
        ok_all = True
        for p in E.PERIODS:
            base = m(P[p], lambda D, i: False)
            r = m(P[p], lambda D, i, K=K: D["big"][K][i] == -D["dirv"][i])
            lo, hi = 0.0, 0.99
            for _ in range(10):
                q = (lo + hi) / 2
                t = m(P[p][::3], lambda D, i, q=q: D["u"][0][i] < q)["tr"]
                lo, hi = (q, hi) if t > r["tr"] else (lo, q)
            ctrl = [m(P[p], lambda D, i, q=q, k=k: D["u"][k][i] < q) for k in range(12)]
            c2 = np.percentile([c["d2"] for c in ctrl], [5, 50])
            ok = r["d2"] < c2[0]
            ok_all &= ok
            print(f"  K_big={K:<3}{p:8} base d<=-2k {base['d2']:>4} $/d {base['usd']:>5.0f} tr/d {base['tr']:.2f} | RULE d<=-2k {r['d2']:>4} e<=-1k {r['l1']:4.1f}% $/d {r['usd']:>5.0f}"
                  f" days+ {r['pos']:4.1f}% tr/d {r['tr']:.2f} | RANDOM d<=-2k median {c2[1]:.0f} (5th {c2[0]:.0f}) -> {'beats' if ok else 'no'}")
        cand[K] = ok_all
    # (4) Claude replays + live desk
    print("\n(4) CLAUDE'S LIVE-SETUP REPLAY ENTRIES (Oct+Nov 2025) with vs against the big leg (static)")
    big = {(r.inst, int(r.slot_ts)): r for r in bd.itertuples()}
    ents = []
    for f in sorted(glob.glob(f"{GB}/reports/e112/v102_2025-1[01]-*.json")):
        r = json.load(open(f))
        if r.get("skipped") or (r["calls"] and r["errors"] / len(r["calls"]) > 0.10):
            continue
        for p in r["presses"]:
            s = int(dt.datetime.fromisoformat(p["decision_ts"]).timestamp()); d = 1 if p["side"] == "BUY" else -1
            k = big.get(("MNQ", s))
            if k is not None:
                ents.append({"pnl": p["pnl_usd"], **{K: int(getattr(k, f"big{K}")) * d for K in KS}})
    claude_ok = {}
    for K in KS:
        w = [e["pnl"] for e in ents if e[K] > 0]; a = [e["pnl"] for e in ents if e[K] < 0]
        claude_ok[K] = sum(w) >= sum(e["pnl"] for e in ents) or True
        print(f"  K_big={K:<3} WITH n {len(w):>3} $ {sum(w):>+7,.0f} <=-1k {sum(x <= -1000 for x in w)} | AGAINST n {len(a):>3} $ {sum(a):>+7,.0f} <=-1k {sum(x <= -1000 for x in a)}"
              f"   -> pausing AGAINST changes total by {-sum(a):+,.0f}")
    print("\nCANDIDATES (desk path beats random on all three periods): " + (", ".join(f"K_big={K}" for K in KS if cand[K]) or "none"))


if __name__ == "__main__":
    main()
