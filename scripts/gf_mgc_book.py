#!/usr/bin/env python3
"""GF_MGC BOOK — does gold's THIN book decide whether a level break runs or fails?

    PYTHONPATH=src .venv/bin/python scripts/gf_mgc_book.py

★ THE IDEA, AND WHY IT IS NOT THE REFUTED ONE. `[[mgc-momentum-greenfield-null]]` closed "L2 book
direction / veto" — asking the book, at an arbitrary moment, WHICH WAY price will go. That was well
powered and it flipped sign across five disjoint samples. This asks a different question, at a
different moment, and the difference is the whole design:

    at the instant price BREAKS a level, is the liquidity in front of it being EATEN or is it
    ABSORBING the break?

That is not a direction forecast. The break already picked the side. The book is asked only to say
whether the side it picked will HOLD — which is a liquidity question, and liquidity is the one thing
a book genuinely knows. Gold's book is far thinner than MNQ's (median 5 lots at the touch against
MNQ's tens), so a break either clears the offer or it does not, and that ought to be visible where
in MNQ it washes out.

★★ THE PAYOFF IF IT SEPARATES IS THE WHOLE 2x2 FROM ONE TRIGGER:
        break + DEPLETION  -> go WITH it   (momentum long / momentum short)
        break + ABSORPTION -> FADE it back (reversion long / reversion short)
    Two cells per side, one mechanism, and each has a microstructure story rather than a threshold.

★ THIS IS A MEASUREMENT, NOT A GATE. It reports separation and nothing else. A gate is only built if
the book actually splits the outcomes, and only then on the held-out leg.

★ DATA. 22 contiguous days of 10-level depth, 07-16..08-14 — and 12 of those days (07-20..08-04)
have no L1 tape at all, so NO previous gold study has seen them. They are a genuine held-out leg.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7 import lake  # noqa: E402
from gf_mgc_tape import SYMBOL, VPP, build_tape  # noqa: E402

pd.set_option("display.width", 250)

BAND_PT = 1.0     # "in front of the break" = this many points beyond the level


def load_book_5s(con=None) -> pd.DataFrame:
    """10-level book, last snapshot in each 5-second bucket.

    Sampled rather than averaged on purpose: a break is an instant, and the state that matters is
    the one standing when price arrives, not the bucket's mean.
    """
    con = con or lake.connect(symbol=SYMBOL)
    cols = ", ".join([f"bid{i}p, bid{i}s, ask{i}p, ask{i}s" for i in range(1, 11)])
    df = con.execute(f"""
        WITH b AS (
            SELECT ts_ms - (ts_ms % 5000) AS b5, ts_ms, {cols},
                   row_number() OVER (PARTITION BY ts_ms - (ts_ms % 5000) ORDER BY ts_ms DESC) rn
            FROM depth
            WHERE symbol='{SYMBOL}' AND bid1p > 0 AND ask1p > 0 AND ask1p - bid1p BETWEEN 0 AND 5
        )
        SELECT b5, {cols} FROM b WHERE rn = 1 ORDER BY b5
    """).df()
    df["ts"] = pd.to_datetime(df["b5"], unit="ms", utc=True)
    return df.set_index("ts").drop(columns=["b5"])


def band_size(bk: pd.DataFrame, level: pd.Series, side: str, band: float = BAND_PT) -> pd.Series:
    """Resting size sitting between the level and `band` points beyond it, on one side of the book.

    For an UP break the obstacle is the ASK stack from the level upward; for a DOWN break it is the
    BID stack from the level downward.
    """
    tot = pd.Series(0.0, index=bk.index)
    for i in range(1, 11):
        p, s = bk[f"{side}{i}p"], bk[f"{side}{i}s"]
        if side == "ask":
            m = (p >= level) & (p <= level + band)
        else:
            m = (p <= level) & (p >= level - band)
        tot = tot + s.where(m, 0.0).fillna(0.0)
    return tot


def find_breaks(m: pd.DataFrame, *, look: int = 60, margin_atr: float = 0.10,
                cooldown_min: int = 45) -> pd.DataFrame:
    """Price closes beyond its own `look`-minute extreme by `margin_atr` ATR.

    The extreme is taken over bars STRICTLY BEFORE the signal bar (`shift(1)`), and entry is stamped
    at ts+60s because a 1-minute bar labelled 10:00 is not closed until 10:01. Both of those are the
    traps the 08-14 session logged; either one silently manufactures an edge.
    """
    d = m.copy()
    hi = d["high"].rolling(look).max().shift(1)
    lo = d["low"].rolling(look).min().shift(1)
    d["hi"], d["lo"] = hi, lo
    d = d.dropna(subset=["hi", "lo", "atr"])
    up = d["close"] >= d["hi"] + margin_atr * d["atr"]
    dn = d["close"] <= d["lo"] - margin_atr * d["atr"]
    rows = []
    for ts, u, v in zip(d.index, up.to_numpy(), dn.to_numpy()):
        if not (u or v):
            continue
        rows.append({
            "sig_ts": ts, "ts": ts + pd.Timedelta(seconds=60),
            "brk": 1 if u else -1,
            "level": float(d.at[ts, "hi"] if u else d.at[ts, "lo"]),
            "atr": float(d.at[ts, "atr"]), "regime": d.at[ts, "regime"],
            "session": d.at[ts, "session"], "day": d.at[ts, "day"],
            "er": float(d.at[ts, "er"]) if np.isfinite(d.at[ts, "er"]) else np.nan,
        })
    e = pd.DataFrame(rows)
    if e.empty:
        return e
    keep, last = [], None
    for r in e.itertuples():
        if last is not None and (r.ts - last).total_seconds() < cooldown_min * 60:
            continue
        last = r.ts
        keep.append(r.Index)
    return e.loc[keep].reset_index(drop=True)


def attach_book(e: pd.DataFrame, bk: pd.DataFrame) -> pd.DataFrame:
    """Book state AT the break and 60s BEFORE it — all strictly causal.

    obstacle   size resting in front of the break, at the break
    obst_pre   the same, one minute earlier
    depletion  1 - obstacle/obst_pre   (positive = the wall got eaten while price approached)
    support    size resting BEHIND the break (the side that would catch a failure)
    ratio      obstacle / support      (>1 = more in the way than behind)
    """
    ts_ns = bk.index.tz_convert("UTC").tz_localize(None).astype("datetime64[ns]").astype("int64").to_numpy()
    out = []
    for r in e.itertuples():
        i = int(np.searchsorted(ts_ns, np.int64(pd.Timestamp(r.ts).value), side="left")) - 1
        j = int(np.searchsorted(ts_ns, np.int64(pd.Timestamp(r.ts).value) - 60 * 10**9, side="left")) - 1
        if i < 0 or j < 0 or i >= len(bk):
            continue
        far = "ask" if r.brk > 0 else "bid"
        near = "bid" if r.brk > 0 else "ask"
        row_i, row_j = bk.iloc[i], bk.iloc[j]

        def _band(row, sd, lvl, band=BAND_PT):
            t = 0.0
            for k in range(1, 11):
                p, s = row[f"{sd}{k}p"], row[f"{sd}{k}s"]
                if not np.isfinite(p) or not np.isfinite(s):
                    continue
                if sd == "ask" and lvl <= p <= lvl + band:
                    t += s
                elif sd == "bid" and lvl - band <= p <= lvl:
                    t += s
            return t

        obstacle = _band(row_i, far, r.level)
        obst_pre = _band(row_j, far, r.level)
        support = _band(row_i, near, r.level)
        tot_b = sum(row_i[f"bid{k}s"] for k in range(1, 11) if np.isfinite(row_i[f"bid{k}s"]))
        tot_a = sum(row_i[f"ask{k}s"] for k in range(1, 11) if np.isfinite(row_i[f"ask{k}s"]))
        out.append({
            **{c: getattr(r, c) for c in e.columns},
            "obstacle": obstacle, "obst_pre": obst_pre, "support": support,
            "depletion": (1.0 - obstacle / obst_pre) if obst_pre > 0 else np.nan,
            "ratio": (obstacle / support) if support > 0 else np.nan,
            "imb": (tot_b - tot_a) / (tot_b + tot_a) if (tot_b + tot_a) > 0 else np.nan,
        })
    return pd.DataFrame(out)


def outcomes(e: pd.DataFrame, m: pd.DataFrame, *, h: int = 60) -> pd.DataFrame:
    """What the break did next: signed move over the next h minutes, in ATR and in dollars.

    Signed so that positive ALWAYS means "the break ran". A reversion cell is simply the negative of
    this column, which keeps the two cells arithmetically tied instead of separately fitted.
    """
    c = m["close"]
    ts_ns = c.index.tz_convert("UTC").tz_localize(None).astype("datetime64[ns]").astype("int64").to_numpy()
    v = c.to_numpy()
    res = []
    for r in e.itertuples():
        i = int(np.searchsorted(ts_ns, np.int64(pd.Timestamp(r.ts).value), side="left"))
        if i >= len(v) - 1:
            continue
        j = min(i + h, len(v) - 1)
        mv = (v[j] - v[i]) * r.brk
        seg = v[i:j + 1]
        mfe = float((seg - v[i]).max() * r.brk) if r.brk > 0 else float((v[i] - seg).max())
        mae = float((seg - v[i]).min() * r.brk) if r.brk > 0 else float((v[i] - seg).min())
        res.append({**{c2: getattr(r, c2) for c2 in e.columns},
                    "fwd_pt": mv, "fwd_$": mv * VPP, "fwd_atr": mv / r.atr,
                    "ran": int(mv > 0), "mfe_atr": mfe / r.atr, "mae_atr": mae / r.atr})
    return pd.DataFrame(res)


def split_table(d: pd.DataFrame, col: str, label: str, q: float = 0.5) -> None:
    dd = d.dropna(subset=[col])
    if len(dd) < 40:
        print(f"  {label}: n={len(dd)} — too thin")
        return
    cut = dd[col].quantile(q)
    lo, hi = dd[dd[col] <= cut], dd[dd[col] > cut]
    print(f"  {label:<34} cut={cut:>7.3f}   "
          f"LOW  n={len(lo):>4} ran {100 * lo['ran'].mean():>5.1f}%  fwd ${lo['fwd_$'].mean():>7.2f}   |   "
          f"HIGH n={len(hi):>4} ran {100 * hi['ran'].mean():>5.1f}%  fwd ${hi['fwd_$'].mean():>7.2f}   "
          f"| gap ${hi['fwd_$'].mean() - lo['fwd_$'].mean():>7.2f}")


def main() -> None:
    m, _ = build_tape()
    print("loading 10-level book at 5s ...", flush=True)
    bk = load_book_5s()
    print(f"  {len(bk):,} book snapshots\n")

    e = find_breaks(m)
    print(f"level breaks (60min extreme + 0.10 ATR, 45min cooldown): n={len(e)}  "
          f"up={int((e['brk'] > 0).sum())} down={int((e['brk'] < 0).sum())}")
    e = attach_book(e, bk)
    d = outcomes(e, m, h=60)
    print(f"with book + outcome: n={len(d)}\n")

    print("=" * 118)
    print("[1] DOES THE BREAK RUN AT ALL?  (the unconditional base rate — every split is judged vs this)")
    print("=" * 118)
    print(f"  ALL   n={len(d):>4}  ran {100 * d['ran'].mean():.1f}%   mean fwd ${d['fwd_$'].mean():+.2f}   "
          f"median ${d['fwd_$'].median():+.2f}")
    for b, g in d.groupby(d["brk"].map({1: "UP break", -1: "DOWN break"})):
        print(f"  {b:<10} n={len(g):>4}  ran {100 * g['ran'].mean():.1f}%   mean fwd ${g['fwd_$'].mean():+.2f}")
    print("\n  ⚠ gold rose on 13 of 22 days in this sample, so an UP break running more often than a")
    print("    DOWN break may be nothing but that drift. The book splits below are the real test —")
    print("    they hold direction fixed and vary only the liquidity.")

    print("\n" + "=" * 118)
    print("[2] ★ THE BOOK SPLIT — median cut on each feature, outcome = did the break RUN")
    print("=" * 118)
    for col, lab in (("depletion", "DEPLETION (wall eaten, 60s)"), ("obstacle", "OBSTACLE (size in front)"),
                     ("ratio", "RATIO obstacle/support"), ("support", "SUPPORT (size behind)"),
                     ("imb", "IMBALANCE (whole book)")):
        split_table(d, col, lab)
    print("\n  the same, per direction (a feature that only works on one side is a drift artefact):")
    for b, g in d.groupby(d["brk"].map({1: "UP", -1: "DOWN"})):
        print(f"\n  --- {b} breaks (n={len(g)}) ---")
        for col, lab in (("depletion", "DEPLETION"), ("ratio", "RATIO"), ("obstacle", "OBSTACLE")):
            split_table(g, col, lab)

    print("\n" + "=" * 118)
    print("[3] ★★ THE HELD-OUT LEG — 07-20..08-04 has NO L1 tape, so no gold study has ever seen it")
    print("=" * 118)
    seen = d[~d["day"].between("2026-07-20", "2026-08-04")]
    unseen = d[d["day"].between("2026-07-20", "2026-08-04")]
    for nm, g in (("L1-covered days (previously hunted)", seen), ("L2-ONLY days (never hunted)", unseen)):
        print(f"\n  --- {nm}: n={len(g)}, {g['day'].nunique()} days ---")
        for col, lab in (("depletion", "DEPLETION"), ("ratio", "RATIO")):
            split_table(g, col, lab)

    print("\n" + "=" * 118)
    print("[4] BY REGIME — where does a break run, regardless of the book?")
    print("=" * 118)
    g = d.groupby("regime").agg(n=("ran", "size"), ran=("ran", "mean"), fwd=("fwd_$", "mean"),
                                mfe=("mfe_atr", "mean"), mae=("mae_atr", "mean"))
    g["ran"] = (100 * g["ran"]).round(1)
    print(g.round(2).to_string())
    print("\n  by session:")
    g = d.groupby("session").agg(n=("ran", "size"), ran=("ran", "mean"), fwd=("fwd_$", "mean"))
    g["ran"] = (100 * g["ran"]).round(1)
    print(g.round(2).to_string())

    d.to_json("reports/friday_v7/sections/gf_mgc_breaks.json", orient="records", date_format="iso")
    print("\n  -> reports/friday_v7/sections/gf_mgc_breaks.json")


if __name__ == "__main__":
    main()
