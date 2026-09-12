"""CHOP-SCALP step 8 — THE test. Give the NULL the same grid search that found the survivor.

A 3.8% placebo percentile on ONE hand-picked cell means nothing when 1,080 cells were searched
to find it. So: build the null tape (direction-flipped, or features shuffled within day), run the
ENTIRE search on it, take ITS best cell, and repeat. If the real best cell is inside the null's
own best-cell distribution, the survivor is a search artefact and it dies here.

Null A  DIRECTION  — flip each event's side at random (fade becomes chase); outcomes flip with it.
Null B  SHUFFLE    — permute the ENTRY FEATURES across events WITHIN each day. Marginals and the
                     day's outcome mix are preserved exactly; only the feature->outcome link dies.
"""
import json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, SLIP_STOP_PT, load_events

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP")).values
POOL = d[CHOP & (d.f_ext30.values > 0)].copy().reset_index(drop=True)   # the L=30 branch: 101 events
print(f"[pool] {len(POOL)} chop-tape 30-min-extreme events on {POOL.date.nunique()} days")

KS = [0.0, 2.0, 3.0, 4.0, 5.0, 6.0]
EXITS = [(t, s) for t in (5.0, 6.0, 8.0, 10.0, 12.0) for s in (6.0, 8.0, 10.0)]
med_refill = np.median(d.f_refill[CHOP].dropna())
med_pull = np.median(d.f_pull[CHOP].dropna())

def book_masks(P):
    return {
        "none":        np.ones(len(P), bool),
        "wall1>=1.5":  (P.f_wall1 >= 1.5).values,
        "wall5>=1.3":  (P.f_wall5 >= 1.3).values,
        "wall5<=1.0":  (P.f_wall5 <= 1.0).values,
        "suppdrain":   (P.f_supp_drain > 0).values,
        "wallbuild":   (P.f_wall_build > 0).values,
        "refill>=med": (P.f_refill >= med_refill).values,
        "pull>=med":   (P.f_pull >= med_pull).values,
        "agg>=100":    (P.f_agg20 >= 100).values,
        "aggfrac>=.2": (P.f_aggfrac20 >= 0.2).values,
        "imb>0":       (P.f_imb > 0).values,
        "vwapflat<=.5": (P.f_vwap_flat <= 0.5).values,
    }

def search(P, kinds, res, min_n=12):
    """Run the whole grid on one (possibly nulled) pool; return the BEST cell's $/trade."""
    dts = P.dts.values; dayv = P.date.values; mv = P.f_mv20.values
    bm = book_masks(P)
    best = -1e18; bestc = None
    for k in KS:
        km = mv >= k
        for bname, b in bm.items():
            sel = km & b
            if sel.sum() < min_n:
                continue
            idx = np.flatnonzero(sel)
            for (tp, sp) in EXITS:
                kk = kinds[(tp, sp)]; dd = res[(tp, sp)]["dur"]; rr = res[(tp, sp)]["res"]
                tot = 0.0; n = 0; free = {}
                for i in idx:
                    if kk[i] == "NOFILL":
                        continue
                    day = dayv[i]
                    if dts[i] < free.get(day, -1e18):
                        continue
                    free[day] = dts[i] + (dd[i] if np.isfinite(dd[i]) else 900.0)
                    pts = -(sp + SLIP_STOP_PT) if kk[i] == "STOP" else rr[i]
                    tot += pts * VPP - FEE; n += 1
                if n >= min_n:
                    ptr = tot / n
                    if ptr > best:
                        best, bestc = ptr, (k, bname, tp, sp, n, round(tot, 2))
    return best, bestc


def search_matched(P, kinds, res, min_n):
    """Same search, but the null is only allowed cells at least as WIDE as the real winner.
    Without this the null wins by picking 12-trade corners where the variance is enormous —
    which is not the comparison being made."""
    return search(P, kinds, res, min_n=min_n)

def pack(P, flip=None):
    kinds, res = {}, {}
    for (tp, sp) in EXITS:
        k = P[f"k_{tp}_{sp}"].values.astype(object).copy()
        r = P[f"r_{tp}_{sp}"].values.copy()
        dur = P[f"d_{tp}_{sp}"].values.copy()
        if flip is not None:
            # a flipped side turns a first-touch TARGET into a first-touch STOP only when tp==sp;
            # for tp!=sp the flipped race is genuinely different, so those rows are marked NOFILL
            # rather than guessed. That makes Null A CONSERVATIVE (it drops cells), and it is why
            # Null B is the primary test.
            same = (tp == sp)
            k = np.where(flip & (not same), "NOFILL",
                np.where(flip & (k == "TARGET"), "STOP",
                np.where(flip & (k == "STOP"), "TARGET", k)))
            r = np.where(flip, -r, r)
        kinds[(tp, sp)] = k
        res[(tp, sp)] = {"res": r, "dur": dur}
    return kinds, res

# ---------------- the REAL best
k0, r0 = pack(POOL)
real, realc = search(POOL, k0, r0)
print(f"[REAL] best cell $/tr = {real:.3f}   cell = k={realc[0]} book={realc[1]} tp={realc[2]} sp={realc[3]} n={realc[4]} net=${realc[5]}")

REAL_N = realc[4]
rng = np.random.default_rng(825)
FEATCOLS = ["f_mv20", "f_wall1", "f_wall5", "f_supp_drain", "f_wall_build",
            "f_refill", "f_pull", "f_agg20", "f_aggfrac20", "f_imb", "f_vwap_flat"]

N = 300
out = {"real_best_ptr": round(real, 3), "real_cell": list(map(str, realc))}
for null in ("B_shuffle", "A_direction"):
    t0 = time.time(); draws = []; draws_m = []; best_n = []
    for it in range(N):
        if null == "B_shuffle":
            P = POOL.copy()
            for day, g in POOL.groupby("date"):
                idx = g.index.values
                perm = rng.permutation(idx)
                P.loc[idx, FEATCOLS] = POOL.loc[perm, FEATCOLS].values
            kk, rr = pack(P)
            b, bc = search(P, kk, rr)
            bm_, bmc = search_matched(P, kk, rr, REAL_N)
        else:
            flip = rng.random(len(POOL)) < 0.5
            kk, rr = pack(POOL, flip=flip)
            b, bc = search(POOL, kk, rr)
            bm_, bmc = search_matched(POOL, kk, rr, REAL_N)
        draws.append(b); draws_m.append(bm_); best_n.append(bc[4] if bc else np.nan)
    draws = np.array([x for x in draws if x > -1e17])
    dm = np.array([x for x in draws_m if x > -1e17])
    out[null] = {"n_draws": int(len(draws)),
                 "unrestricted": {"null_best_mean": round(float(draws.mean()), 3),
                                  "null_best_p50": round(float(np.percentile(draws, 50)), 3),
                                  "null_best_p95": round(float(np.percentile(draws, 95)), 3),
                                  "median_n_of_null_winner": float(np.nanmedian(best_n)),
                                  "p_null_beats_real": round(float((draws >= real).mean()), 4)},
                 f"n_matched_ge_{REAL_N}": {"draws": int(len(dm)),
                                  "null_best_mean": round(float(dm.mean()), 3) if len(dm) else None,
                                  "null_best_p50": round(float(np.percentile(dm, 50)), 3) if len(dm) else None,
                                  "null_best_p95": round(float(np.percentile(dm, 95)), 3) if len(dm) else None,
                                  "p_null_beats_real": round(float((dm >= real).mean()), 4) if len(dm) else None},
                 "secs": round(time.time() - t0, 1)}
    print(f"[{null}] {out[null]}")
json.dump(out, open(f"{OUT}/null.json", "w"), indent=1)

# ---------------- the PRE-REGISTERED single-cell p-value: no search, one cell, 2000 shuffles
K, BOOK, TP, SP = 4.0, "refill>=med", 8.0, 10.0
def one_cell(P, kinds, res):
    sel = (P.f_mv20.values >= K) & (P.f_refill.values >= med_refill)
    idx = np.flatnonzero(sel); kk = kinds[(TP, SP)]; dd = res[(TP, SP)]["dur"]; rr = res[(TP, SP)]["res"]
    dts = P.dts.values; dayv = P.date.values
    tot = 0.0; n = 0; free = {}
    for i in idx:
        if kk[i] == "NOFILL":
            continue
        if dts[i] < free.get(dayv[i], -1e18):
            continue
        free[dayv[i]] = dts[i] + (dd[i] if np.isfinite(dd[i]) else 900.0)
        tot += (-(SP + SLIP_STOP_PT) if kk[i] == "STOP" else rr[i]) * VPP - FEE; n += 1
    return (tot / n if n else np.nan), n

real1, n1 = one_cell(POOL, k0, r0)
draws1 = []
for it in range(2000):
    P = POOL.copy()
    for day, g in POOL.groupby("date"):
        idx = g.index.values
        P.loc[idx, FEATCOLS] = POOL.loc[rng.permutation(idx), FEATCOLS].values
    kk, rr = pack(P)
    v, _ = one_cell(P, kk, rr)
    if np.isfinite(v):
        draws1.append(v)
draws1 = np.array(draws1)
out["pre_registered_single_cell"] = {
    "cell": f"k={K} {BOOK} {TP}/{SP}", "real_ptr": round(float(real1), 3), "n": int(n1),
    "shuffle_mean": round(float(draws1.mean()), 3),
    "p_shuffle_beats_real": round(float((draws1 >= real1).mean()), 4), "draws": len(draws1)}
print("[single-cell]", out["pre_registered_single_cell"])
json.dump(out, open(f"{OUT}/null.json", "w"), indent=1)
