"""GF7 — the MGC order-book panel, minute-aligned and STRICTLY CAUSAL.

★ WHY. Last Friday's gold section ended with one stone unturned: gold's book is far thinner than
MNQ's, the only live gold arm that earns anything (`mgc_holebreak_fade_long`) earns it entirely
from a BOOK condition, and we could not tell whether the LEVEL or the BOOK carried that edge.
Everything in gf7 is measured off this panel.

★ THE CAUSALITY RULE. A bar stamped `m*60` closes at `m*60+60`. The book row kept for that bar is
the LAST depth snapshot whose timestamp falls inside [m*60, m*60+60) — i.e. strictly before the
close. A decision taken on bar m therefore sees only book state that existed during bar m.
Using the snapshot AT the close (or after it) would be the same left-edge look-ahead that cost the
coil gate +$906 -> +$470 on 08-14.

★ MISSING RUNGS ARE UNKNOWN, NOT EMPTY — same rule as levelbreak.band_size. Calling an absent rung
zero manufactures the very liquidity hole the gate trades on.
"""
from __future__ import annotations
import sqlite3, os
import numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/gf7"
L = 10


def build() -> pd.DataFrame:
    con = sqlite3.connect(f"{GB}/data/depth.db")
    cols = ["ts_ms"] + [f"{s}{k}{f}" for k in range(1, L + 1) for s in ("bid", "ask") for f in ("p", "s")]
    df = pd.read_sql(f"SELECT {','.join(cols)} FROM depth_snap WHERE symbol='MGC' ORDER BY ts_ms", con)
    con.close()
    df["m"] = (df.ts_ms // 60000).astype("int64")
    df = df.groupby("m", as_index=False).last()          # last snapshot INSIDE the minute
    df["ts"] = df.m * 60                                  # the bar this book belongs to

    bp = df[[f"bid{k}p" for k in range(1, L + 1)]].to_numpy(float)
    bs = df[[f"bid{k}s" for k in range(1, L + 1)]].to_numpy(float)
    ap = df[[f"ask{k}p" for k in range(1, L + 1)]].to_numpy(float)
    asz = df[[f"ask{k}s" for k in range(1, L + 1)]].to_numpy(float)
    # a rung is only real if price>0 and size>0 and both finite
    bok = np.isfinite(bp) & np.isfinite(bs) & (bp > 0) & (bs > 0)
    aok = np.isfinite(ap) & np.isfinite(asz) & (ap > 0) & (asz > 0)
    bp = np.where(bok, bp, np.nan); bs = np.where(bok, bs, 0.0)
    ap = np.where(aok, ap, np.nan); asz = np.where(aok, asz, 0.0)

    out = pd.DataFrame({"ts": df.ts.to_numpy()})
    out["bid1"] = bp[:, 0]; out["ask1"] = ap[:, 0]
    out["mid"] = (out.bid1 + out.ask1) / 2
    out["spread"] = out.ask1 - out.bid1
    out["bid_sz"] = bs.sum(1); out["ask_sz"] = asz.sum(1)
    out["imb"] = (out.bid_sz - out.ask_sz) / (out.bid_sz + out.ask_sz).replace(0, np.nan)

    mid = out.mid.to_numpy()[:, None]
    for r in (0.5, 1.0, 2.0):
        out[f"bid_d{r}"] = np.where(bp >= mid - r, bs, 0.0).sum(1)
        out[f"ask_d{r}"] = np.where(ap <= mid + r, asz, 0.0).sum(1)
    # how far you must walk from the touch to find `n` lots resting
    for n in (5.0, 20.0):
        cb = np.nan_to_num(bs).cumsum(1); ca = np.nan_to_num(asz).cumsum(1)
        ib = (cb >= n).argmax(1); ia = (ca >= n).argmax(1)
        hb = (cb[:, -1] >= n); ha = (ca[:, -1] >= n)
        out[f"bwall{int(n)}"] = np.where(hb, mid[:, 0] - bp[np.arange(len(bp)), ib], np.nan)
        out[f"awall{int(n)}"] = np.where(ha, ap[np.arange(len(ap)), ia] - mid[:, 0], np.nan)
    out["depth_span_b"] = mid[:, 0] - np.nanmin(bp, 1)
    out["depth_span_a"] = np.nanmax(ap, 1) - mid[:, 0]
    # the raw rungs travel too — the level-break obstacle/support read needs them
    for k in range(1, L + 1):
        out[f"bid{k}p"] = bp[:, k - 1]; out[f"bid{k}s"] = bs[:, k - 1]
        out[f"ask{k}p"] = ap[:, k - 1]; out[f"ask{k}s"] = asz[:, k - 1]
    os.makedirs(OUT, exist_ok=True)
    out.to_pickle(f"{OUT}/book_min.pkl")
    return out


if __name__ == "__main__":
    b = build()
    d = pd.to_datetime(b.ts, unit="s", utc=True)
    print(f"minutes={len(b):,}  {d.min()} -> {d.max()}  days={d.dt.date.nunique()}")
    print(b[["spread", "bid_sz", "ask_sz", "bid_d1.0", "ask_d1.0", "bwall5", "awall5"]]
          .describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_string())
