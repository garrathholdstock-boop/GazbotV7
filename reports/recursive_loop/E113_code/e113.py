"""E113 - the claims pause grid (spec reports/recursive_loop/E113_change.txt). Read-only, zero Claude tokens.

    nice -n 15 .venv/bin/python reports/recursive_loop/E113_code/e113.py > reports/recursive_loop/E113_result.txt
"""
from __future__ import annotations

import datetime as dt
import glob
import itertools
import json
import multiprocessing as mp
import sys
from zoneinfo import ZoneInfo

import duckdb
import numpy as np

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
from gazbot7.bible import gate  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
LOCK = 1000.0
PERIODS = ("TRAIN", "TEST", "FORWARD")
CS, AS, XS = (0, 1, 2, 3), (None, 60, 90, 120, 180, 240, 360), (None, 100, 150, 200, 250, 300, 400)


def load():
    df = duckdb.connect().execute(f"""SELECT c.inst, c.sess, c.slot_ts, c.dir, c.leg_age_min, c.leg_ext_pts, c.hit37_min, c.usd_allout, c.period
        FROM read_parquet('{GB}/data/research/E110_census.parquet') c WHERE c.in_live_window ORDER BY c.inst, c.sess, c.slot_ts""").df()
    df["leg"] = (df.slot_ts - (df.leg_age_min * 60).round().astype(np.int64)) * df.dir
    days = []
    for (inst, sess), g in df.groupby(["inst", "sess"], sort=False):
        d = dt.date(1970, 1, 1) + dt.timedelta(days=int(sess))
        m0 = int(dt.datetime(d.year, d.month, d.day, 7, 0, tzinfo=PARIS).timestamp())
        m1 = int(dt.datetime(d.year, d.month, d.day, 8, 30, tzinfo=PARIS).timestamp())
        s = g.slot_ts.to_numpy()
        days.append({"period": g.period.iat[0], "sess": int(sess), "inst": inst, "slot": s, "leg": g.leg.to_numpy(),
                     "age": g.leg_age_min.to_numpy(), "ext": g.leg_ext_pts.to_numpy(), "hit": g.hit37_min.to_numpy(),
                     "usd": g.usd_allout.to_numpy(), "morn": (s >= m0) & (s < m1)})
    return days


def run_day(D, C, A, X, morning_only):
    slot, leg, age, ext, hit, usd, morn = D["slot"], D["leg"], D["age"], D["ext"], D["hit"], D["usd"], D["morn"]
    n, i, free, real, claims, out = len(slot), 0, -1, 0.0, {}, []
    while i < n:
        if slot[i] < free:
            i = int(np.searchsorted(slot, free)); continue
        if real >= LOCK:
            break
        if C is not None:
            cond = (A is None and X is None) or (A is not None and age[i] >= A) or (X is not None and ext[i] >= X)
            if cond and claims.get(leg[i], 0) >= C and (not morning_only or morn[i]):
                i += 1; continue
        real += usd[i]; out.append(usd[i])
        if np.isfinite(hit[i]):
            free = slot[i] + hit[i] * 60; claims[leg[i]] = claims.get(leg[i], 0) + 1; i += 1
        else:
            break
    return real, out


def metrics(days, cell):
    daily, ents = [], []
    for D in days:
        r, o = run_day(D, *cell)
        daily.append(r); ents += o
    daily = np.array(daily); ents = np.array(ents)
    mean, sd = daily.mean(), daily.std()
    return {"usd_per_day": mean, "daily_sd": sd, "days_positive": int((daily > 0).sum()), "worst_day": float(daily.min()),
            "cv": sd / mean if mean > 0 else float("inf"), "le1k": int((ents <= -1000).sum()), "le2k_days": int((daily <= -2000).sum()),
            "le4k_days": int((daily <= -4000).sum()), "trades_per_day": len(ents) / len(days), "n_days": len(days)}


def _work(args):
    cell, period = args
    return cell, period, metrics(DAYS[period], cell)


DAYS = {}


def cells():
    out = [(None, None, None, False)]
    for C, A, X in itertools.product(CS, AS, XS):
        if C == 0 and A is None and X is None:
            continue                                   # would pause every entry
        for m in (False, True):
            out.append((C, A, X, m))
    return out


def qualifies(c, b):
    return (c["worst_day"] >= b["worst_day"] and c["days_positive"] >= b["days_positive"] and
            (c["cv"] <= b["cv"] or b["cv"] == float("inf")) and c["le1k"] < b["le1k"])


def name(cell):
    C, A, X, m = cell
    if C is None:
        return "BASELINE (no pause)"
    cond = "always" if A is None and X is None else " or ".join(([f"age>={A}m"] if A else []) + ([f"ext>={X}pt"] if X else []))
    return f"claims>={C} & {cond}{' [07:00-08:30 Paris]' if m else ''}"


def line(cell, m, b):
    ok, why = gate(m, b)
    return (f"   {name(cell):52}{m['usd_per_day']:>8.1f}{m['days_positive']:>6}{m['worst_day']:>9.0f}{m['cv']:>8.1f}{m['le1k']:>6}{m['le2k_days']:>6}"
            f"{m['le4k_days']:>6}{m['trades_per_day']:>7.2f}   gate:{'PASS' if ok else 'fail'}")


HDR = f"   {'cell':52}{'$/day':>8}{'days+':>6}{'worst':>9}{'CV':>8}{'<=-1k':>6}{'d<=-2k':>6}{'d<=-4k':>6}{'tr/day':>7}"


def main():
    days = load()
    for p in PERIODS:
        DAYS[p] = [D for D in days if D["period"] == p]
    allc = cells()
    print("E113 - THE CLAIMS PAUSE GRID (spec reports/recursive_loop/E113_change.txt). Detector-only desk path, live window, zero Claude tokens.")
    print(f"sessions TRAIN {len(DAYS['TRAIN'])}, TEST {len(DAYS['TEST'])}, FORWARD {len(DAYS['FORWARD'])}; cells {len(allc) - 1} + baseline (the search size)")
    with mp.Pool(2) as pool:
        tr = {c: m for c, _, m in pool.map(_work, [(c, "TRAIN") for c in allc], chunksize=8)}
    base = tr[allc[0]]
    q = [c for c in allc[1:] if qualifies(tr[c], base)]
    q.sort(key=lambda c: (tr[c]["le2k_days"], tr[c]["le1k"], -tr[c]["usd_per_day"]))
    print(f"\n[TRAIN] qualifiers (worst day, days+, CV no worse AND fewer entries <= -$1k): {len(q)} of {len(allc) - 1}")
    print(HDR); print(line(allc[0], base, base))
    for c in q[:10]:
        print(line(c, tr[c], base))
    print("\n[TRAIN] best cell per claims level, by days <= -$2k (whether or not it qualifies) - the operator's 1/2/3-claim question:")
    print(HDR)
    for C in CS:
        for m in (False, True):
            cs = [c for c in allc[1:] if c[0] == C and c[3] == m]
            best = min(cs, key=lambda c: (tr[c]["le2k_days"], tr[c]["le1k"], -tr[c]["usd_per_day"]))
            print(line(best, tr[best], base))
    picks = q[:2]
    if not picks:
        print("\nNO TRAIN QUALIFIER -> nothing is carried to TEST/FORWARD (REFUTED on TRAIN)."); return picks, None
    with mp.Pool(2) as pool:
        res = {(c, p): m for c, p, m in pool.map(_work, [(c, p) for c in [allc[0]] + picks for p in ("TEST", "FORWARD")])}
    for p in ("TEST", "FORWARD"):
        b = res[(allc[0], p)]
        print(f"\n[{p}] read once - the pick and the runner-up vs baseline")
        print(HDR); print(line(allc[0], b, b))
        for c in picks:
            print(line(c, res[(c, p)], b) + f"   qualifies: {'YES' if qualifies(res[(c, p)], b) else 'no'}")
    lab = ["PROMISING" if all(qualifies(res[(c, p)], res[(allc[0], p)]) for p in ("TEST", "FORWARD")) else "NOT CONFIRMED" for c in picks]
    for c, l in zip(picks, lab):
        print(f"\nVERDICT {name(c)}: {l}")
    return picks, lab


if __name__ == "__main__":
    main()
