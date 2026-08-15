#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 6: the 250ms L2 BOOK SEPARATION table.

Did the order book telegraph these breaks, and does it separate the winners from the losers?

For every FBREAK trade, from `depth` (the 250ms sampled MNQ ladder, 2026-07-16..08-14), over the 30
seconds BEFORE entry:
    far-side depletion = far / (far + near)  on levels 1-5, where "far" is the side price is about
    to run INTO (asks for a long, bids for a short). Below 0.5 means the side we are about to hit is
    thin — the book got out of the way, which is what a telegraphed break looks like.
Terciles of that ratio are then scored, blanket and on the US home segment.

⚠ depth.db is a 250ms SAMPLE, not the event stream — capture.db.book (41ms, MNQ-only) sees fleeting
quotes this cannot. The sample is the right instrument for a 30-second average, the wrong one for a
single-print sweep, and this table only claims the former.

Writes reports/friday_v7/sections/fl/book.json
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"
OUT = f"{DIR}/book.json"
LOOK_S = 30


def main():
    tr = pd.read_csv(f"{DIR}/trades_abl_FBREAK.csv")
    con = connect(symbol="MNQ")
    have = {r[0] for r in con.execute(
        "SELECT DISTINCT strftime(to_timestamp(ts_ms/1000),'%Y-%m-%d') FROM depth").fetchall()}
    tr = tr[tr["day"].isin(have)].copy()
    print(f"trades inside the depth window: {len(tr)} of the full book")

    cols = ", ".join([f"bid{i}s" for i in range(1, 6)] + [f"ask{i}s" for i in range(1, 6)])
    dep, imb = [], []
    for day, grp in tr.groupby("day"):
        d = con.execute(f"""
            SELECT ts_ms, {cols}, imbalance FROM depth
            WHERE ts_ms >= epoch_ms(TIMESTAMP '{day} 00:00:00')
              AND ts_ms <  epoch_ms(TIMESTAMP '{day} 00:00:00' + INTERVAL 25 HOUR)
            ORDER BY ts_ms""").fetchdf()
        ts = d["ts_ms"].to_numpy("int64")
        bid = d[[f"bid{i}s" for i in range(1, 6)]].to_numpy(float).sum(1)
        ask = d[[f"ask{i}s" for i in range(1, 6)]].to_numpy(float).sum(1)
        im = d["imbalance"].to_numpy(float)
        for i, row in grp.iterrows():
            t1 = (int(row["ts"]) + 60) * 1000          # entry is the first tick after the bucket
            a = np.searchsorted(ts, t1 - LOOK_S * 1000)
            b = np.searchsorted(ts, t1)
            if b - a < 4:
                dep.append((i, None))
                imb.append((i, None))
                continue
            far = (ask[a:b] if row["dir"] > 0 else bid[a:b]).sum()
            near = (bid[a:b] if row["dir"] > 0 else ask[a:b]).sum()
            dep.append((i, far / (far + near) if far + near else None))
            imb.append((i, float(np.nanmean(im[a:b])) * (1 if row["dir"] > 0 else -1)))
    tr["far_depletion"] = pd.Series(dict(dep))
    tr["imb_signed"] = pd.Series(dict(imb))
    tr.to_csv(f"{DIR}/trades_FBREAK_book.csv", index=False)

    def tbl(sub, col, qs=(0, 1 / 3, 2 / 3, 1)):
        s = sub[sub[col].notna()]
        if len(s) < 30:
            return {"n": len(s), "note": "too few rows to tercile"}
        cuts = s[col].quantile(list(qs)).to_list()
        out = []
        for k in range(3):
            m = (s[col] >= cuts[k]) & (s[col] <= cuts[k + 1] if k == 2 else s[col] < cuts[k + 1])
            g = s[m]
            out.append({"tercile": k + 1, "range": [round(cuts[k], 3), round(cuts[k + 1], 3)],
                        "n": int(len(g)), "net": round(float(g["net"].sum()), 2),
                        "per_trade": round(float(g["net"].mean()), 2),
                        "win_pct": round(100 * float((g["net"] > 0).mean()), 1)})
        return out

    res = {"trades_in_window": len(tr),
           "days": sorted(tr["day"].unique().tolist()),
           "far_depletion_terciles_ALL": tbl(tr, "far_depletion"),
           "far_depletion_terciles_US": tbl(tr[tr["session"] == "US"], "far_depletion"),
           "signed_imbalance_terciles_ALL": tbl(tr, "imb_signed"),
           "corr_depletion_vs_net": round(float(tr[["far_depletion", "net"]].corr().iloc[0, 1]), 3),
           "median_far_depletion": round(float(tr["far_depletion"].median()), 3),
           "pct_below_half": round(100 * float((tr["far_depletion"] < 0.5).mean()), 1)}
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps(res, indent=1))
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
