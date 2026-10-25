"""E111 features (spec reports/recursive_loop/E111_change.txt): G1-G4 and the one-minute ENTRY-DELAY outcomes, for every
E110 census candidate. Walks the same segments, back-adjustment, detector run and slots as E110_code/census.py, then joins on
(inst, slot_ts) and asserts the row sets are identical.

    nice -n 19 .venv/bin/python reports/recursive_loop/E111_code/features.py
"""
from __future__ import annotations

import os
import sys
import time

import duckdb
import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/reports/recursive_loop/E110_code")
import census as C  # noqa: E402

OUT = f"{GB}/data/research/E111_features.parquet"


def segment_rows(g: dict, sref: float) -> list:
    t, h, l, c = g["bar_ts"], g["high"], g["low"], g["close"]
    atr, piv = C.run_detector(t, h, l, c)
    sb, se, s_keys, s_day = C.sessions(g)
    p_ts = np.array([p[0] for p in piv], dtype=np.int64)
    p_dir = np.array([p[2] for p in piv], dtype=np.int64)
    p_cts = np.array([p[3] for p in piv], dtype=np.int64)
    p_idx = np.searchsorted(t, p_ts)
    rows = []
    for si, (a, b) in enumerate(zip(sb, se)):
        if not np.isfinite(s_day[si]):
            continue
        k = sref / s_day[si]
        day = int(s_keys[si]); d0 = day * 86400
        e = int(np.searchsorted(t, d0 + 20 * 3600 + 40 * 60, "left")) - 1
        if e <= a or int(t[a]) > d0 + 3600:
            continue
        s_first = (int(t[a]) // 300 + 6) * 300
        for s in range(s_first, d0 + 19 * 3600 + 35 * 60 + 1, 300):
            j = int(np.searchsorted(t, s - 60, "right")) - 1
            if j < a or j + 1 > e:
                continue
            kp = int(np.searchsorted(p_cts, s - 60, "right")) - 1
            if kp < 0:
                continue
            d = int(p_dir[kp]); pi = int(p_idx[kp])
            seg_c = c[pi:j + 1] * d                      # leg closes in the trade direction
            run = np.maximum.accumulate(seg_c)
            ix = int(np.argmax(seg_c))                   # first bar that set the running close extreme
            since_ext = (s - (int(t[pi + ix]) + 60)) / 60
            pull = (seg_c[ix] - d * c[j]) / atr[j] if atr[j] > 0 else np.nan
            ext_h = (h[pi:j + 1].max() if d > 0 else -l[pi:j + 1].min())
            i30 = int(np.searchsorted(t, s - 1800, "left"))
            rec_h = (h[i30:j + 1].max() if d > 0 else -l[i30:j + 1].min()) if j >= i30 else np.nan
            retest = (ext_h - rec_h) / atr[j] if atr[j] > 0 else np.nan
            new_n = valid = 0
            for kb in range(12):
                be = s - 300 * kb
                jb = int(np.searchsorted(t, be - 60, "right")) - 1
                jp = int(np.searchsorted(t, be - 360, "right")) - 1
                if jb < pi or jb == jp:
                    continue
                valid += 1
                at_ext = seg_c[jb - pi] >= run[jb - pi]          # the block's CLOSE is the leg's close extreme
                if at_ext and (jp < pi or seg_c[jb - pi] > run[jp - pi]):
                    new_n += 1
            rate = new_n / valid if valid else np.nan
            # one-minute entry delay: entry = close of the next bar (the one opening at/after the slot)
            j2 = j + 1
            if j2 + 1 <= e:
                ent2 = c[j2]
                ph, pl, tp = h[j2 + 1:e + 1], l[j2 + 1:e + 1], t[j2 + 1:e + 1]
                fav = ((ph - ent2) if d > 0 else (ent2 - pl)) * k - C.ADV
                w = np.flatnonzero(np.maximum.accumulate(fav) >= 37.5 + C.THRU)
                fin = d * (c[e] - ent2) * k - C.ADV
                hit2 = (int(tp[w[0]]) + 60 - s) / 60 if len(w) else np.nan
                usd2 = (C.QTY * C.PV * 37.5 if len(w) else C.QTY * C.PV * fin) - C.FEE
            else:
                hit2, usd2 = np.nan, np.nan
            rows.append((g["inst"], s, since_ext, float(pull), float(retest), rate, hit2, usd2))
    return rows


def main():
    t0 = time.time()
    assert C.detector_sha() == C.SHA
    segs, _ = C.load()
    for g in segs:
        C.back_adjust(g)
    sref = C.s_ref(segs[0])
    rows = []
    for g in segs:
        rows += segment_rows(g, sref)
        print(f"  {g['name']}: {len(rows):,} rows so far ({time.time()-t0:.0f}s)")
    f = pd.DataFrame(rows, columns=["inst", "slot_ts", "since_ext_min", "pullback_atr", "retest_gap_atr", "new_ext_rate",
                                    "hit37_delay_min", "usd_allout_delay"])
    con = duckdb.connect()
    base = con.execute(f"SELECT inst, slot_ts FROM read_parquet('{C.OUT_PARQUET}')").df()
    m = base.merge(f, on=["inst", "slot_ts"], how="outer", indicator=True)
    assert (m["_merge"] == "both").all() and len(m) == len(base) == len(f), m["_merge"].value_counts()
    con.register("f", f)
    con.execute(f"COPY f TO '{OUT}' (FORMAT PARQUET)")
    print(f"wrote {len(f):,} rows -> {OUT}; row set identical to the E110 census ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
