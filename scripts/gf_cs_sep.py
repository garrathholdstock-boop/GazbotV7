"""CHOP-DAY SCALP — Step 3b: where (if anywhere) does the BOOK separate?

The marginal quintile tables say the resting book barely conditions the turn.  But
exhaustion_short's lineage is an INTERACTION — heavy aggression + no price progress
+ a wall on the side being hit.  This mines the interactions and the two-way splits
so the "L2 doesn't separate" claim is earned rather than assumed.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs"


def z(p, n):
    return (n * p - n * 0.5) / np.sqrt(n * 0.25) if n else float("nan")


def main() -> None:
    d = pd.read_csv(f"{OUT}/race_events.csv")
    d = d[d["chop"] == "chop"].copy()
    d["l1"] = np.where(d["at"] == "HIGH",
                       d["ask1s"] / d["bid1s"].replace(0, np.nan),
                       d["bid1s"] / d["ask1s"].replace(0, np.nan))
    d["far10"] = np.where(d["at"] == "HIGH",
                          d["ask10"] / d["bid10"].replace(0, np.nan),
                          d["bid10"] / d["ask10"].replace(0, np.nan))
    d["near_refill"] = np.where(d["at"] == "HIGH", d["dbid_n"], d["dask_n"])
    d["far_abs"] = np.where(d["at"] == "HIGH", d["ask5"], d["bid5"])
    d["near_abs"] = np.where(d["at"] == "HIGH", d["bid5"], d["ask5"])
    print(f"chop-block decided races: n={len(d)}  base P(revert)={100*d['revert'].mean():.1f}%")

    # ---- 1. the exhaustion interaction ------------------------------------
    print("\n############ 1. THE EXHAUSTION INTERACTION ############")
    print("   push = aggressor delta INTO the extreme; prog = points it bought;")
    print("   wall = resting size on the continuation side / the near side.\n")
    hdr = f"{'push':>12s} {'progress':>14s} {'wall':>10s} {'n':>6s} {'P(rev)':>8s} {'z':>7s}"
    print(hdr)
    for pcut, plab in [((d["push"] > 0.05), "delta>+5%"),
                       ((d["push"] > 0.10), "delta>+10%"),
                       ((d["push"].abs() <= 0.05), "delta flat")]:
        for gcut, glab in [((d["prog"].abs() <= 2), "|move|<=2pt"),
                           ((d["prog"] > 6), "move>6pt"),
                           (pd.Series(True, index=d.index), "any")]:
            for wcut, wlab in [((d["farwall"] >= 1.5), "far>=1.5x"),
                               ((d["farwall"] >= 1.2), "far>=1.2x"),
                               ((d["farwall"] <= 0.8), "far<=0.8x"),
                               (pd.Series(True, index=d.index), "any")]:
                s = d[pcut & gcut & wcut]
                if len(s) < 40:
                    continue
                p = s["revert"].mean()
                print(f"{plab:>12s} {glab:>14s} {wlab:>10s} {len(s):6d} "
                      f"{100*p:7.1f}% {z(p, len(s)):+7.2f}")

    # ---- 2. every book measure, both tails --------------------------------
    print("\n############ 2. EVERY BOOK MEASURE, TOP/BOTTOM DECILE ############")
    print(f"{'measure':>14s} {'tail':>8s} {'n':>6s} {'P(rev)':>8s} {'z':>7s}")
    for col in ["farwall", "l1", "far10", "far_refill", "near_refill",
                "far_abs", "near_abs", "absorb", "push", "prog"]:
        s = d.dropna(subset=[col])
        if len(s) < 200:
            continue
        for lab, sub in [("bottom10%", s[s[col] <= s[col].quantile(0.10)]),
                         ("top10%", s[s[col] >= s[col].quantile(0.90)])]:
            p = sub["revert"].mean()
            print(f"{col:>14s} {lab:>8s} {len(sub):6d} {100*p:7.1f}% {z(p, len(sub)):+7.2f}")

    # ---- 3. book conditioned on the regime that actually works ------------
    print("\n############ 3. BOOK INSIDE THE STRONGEST NON-BOOK SEGMENT ############")
    print("   (ER30 < 0.09 = dead chop, which alone runs ~61%)")
    dd = d[d["er30"] < 0.09]
    print(f"   segment n={len(dd)}  P(revert)={100*dd['revert'].mean():.1f}%  "
          f"z={z(dd['revert'].mean(), len(dd)):+.2f}")
    for col in ["farwall", "l1", "far_refill", "absorb", "push"]:
        s = dd.dropna(subset=[col])
        if len(s) < 120:
            continue
        b = pd.qcut(s[col], 3, duplicates="drop")
        g = s.groupby(b, observed=True)["revert"].agg(["size", "mean"])
        g["P"] = (100 * g["mean"]).round(1)
        g["z"] = [round(z(m, n), 2) for n, m in zip(g["size"], g["mean"])]
        print(f"\n   -- {col}")
        print(g[["size", "P", "z"]].to_string())

    # ---- 4. the non-book segmentation, ranked -----------------------------
    print("\n############ 4. THE NON-BOOK SEGMENTATION, RANKED ############")
    combos = []
    for er in [0.06, 0.09, 0.12, 0.30]:
        for vf in [0.0, 0.7, 1.0]:
            for rg in [0.0, 4.7, 5.3]:
                s = d[(d["er30"] < er) & (d["vs_flat"] >= vf) & (d["rng_atr"] >= rg)]
                if len(s) < 150:
                    continue
                p = s["revert"].mean()
                combos.append((er, vf, rg, len(s), 100 * p, z(p, len(s))))
    c = pd.DataFrame(combos, columns=["er30<", "|vslope|>=", "rng_atr>=", "n", "P", "z"])
    print(c.sort_values("z", ascending=False).head(18).round(2).to_string(index=False))

    # ---- 5. does the book add ANYTHING on top of the best segment? --------
    print("\n############ 5. DOES THE BOOK ADD ON TOP? ############")
    best = d[(d["er30"] < 0.09) & (d["vs_flat"] >= 0.7)]
    p = best["revert"].mean()
    print(f"   base segment (ER<0.09, |vslope|>=0.7): n={len(best)} P={100*p:.1f}% z={z(p,len(best)):+.2f}")
    for col in ["farwall", "l1", "far_refill", "absorb", "push", "near_refill"]:
        s = best.dropna(subset=[col])
        med = s[col].median()
        for lab, sub in [("<=med", s[s[col] <= med]), (">med", s[s[col] > med])]:
            pp = sub["revert"].mean()
            print(f"      {col:>12s} {lab:>6s}  n={len(sub):4d}  P={100*pp:5.1f}%  z={z(pp,len(sub)):+.2f}")


if __name__ == "__main__":
    main()
