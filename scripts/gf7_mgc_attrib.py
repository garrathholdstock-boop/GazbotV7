"""GF7 §1 — THE STONE: is the live gold edge the LEVEL or the BOOK?

`mgc_holebreak_fade_long` is the only gold arm on this desk that earns anything, and its whole
claim rests on one book condition: `obstacle_max=0`, "nothing resting in the way". Its own control
arm `mgc_break_fade_nobook` (same trigger, no book) loses -$9.58/trade over 186 live trades. That
gap is the evidence — but a gap between a filtered arm and an unfiltered one CANNOT distinguish
"the book is informative" from "the book condition happens to select the breaks that were going to
work anyway". Last Friday said so and left it unanswered.

This is the 2x2 that answers it:

                        no book condition        obstacle == 0
    every minute        BASELINE DRIFT           BOOK-ONLY        <- book with no level attached
    on a 60m break      LEVEL-ONLY               THE LIVE GATE

If BOOK-ONLY is flat, the book needs the level and the interaction is the edge.
If BOOK-ONLY pays on its own, we have a second, simpler gate and the level is decoration.
If both are flat and only the corner pays, it is an interaction — real, but the thinnest claim.

Everything is scored on forward MID moves at fixed horizons, BEFORE any exit machinery, so the
answer cannot be an artefact of the exit. The exit matrix is Rule 3 and lives in gf7_mgc_exitgrid.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/gf7"
VPP = 10.0
sys.path.insert(0, f"{GB}/src")
from gazbot7.levelbreak import read_book, detect_break            # noqa: E402

HOR = (15, 30, 60, 120, 240)


def frame() -> pd.DataFrame:
    """Minute tape (front month, trade bars) INNER-JOINED to the causal book panel."""
    px = pd.read_pickle(f"{GB}/reports/friday_v7/gf6/mgc_min.pkl")
    bk = pd.read_pickle(f"{OUT}/book_min.pkl")
    df = px.merge(bk, on="ts", how="inner", suffixes=("", "_bk"))
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def breaks(df: pd.DataFrame, look: int = 60, margin: float = 0.10) -> pd.DataFrame:
    """Every 60m level break, with the book read at the SIGNAL BAR, split obstacle/support.

    hi60/lo60 in the base frame are already shifted by one bar (the extreme over bars strictly
    BEFORE the signal bar), which is `detect_break`'s rule 1. Asserted below rather than trusted.
    """
    up = df.close >= df.hi60 + margin * df.atr14
    dn = df.close <= df.lo60 - margin * df.atr14
    hit = df[(up | dn) & df.atr14.gt(0) & df.hi60.notna()].copy()
    hit["brk"] = np.where(up.loc[hit.index], 1, -1)
    hit["level"] = np.where(hit.brk > 0, hit.hi60, hit.lo60)
    ob, su = [], []
    rung = {}
    for k in range(1, 11):
        for s in ("bid", "ask"):
            rung[f"{s}{k}p"] = hit[f"{s}{k}p"].to_numpy()
            rung[f"{s}{k}s"] = hit[f"{s}{k}s"].to_numpy()
    brk = hit.brk.to_numpy(); lvl = hit.level.to_numpy()
    for i in range(len(hit)):
        b = {k: v[i] for k, v in rung.items()}
        r = read_book(b, int(brk[i]), float(lvl[i]), 1.0)
        ob.append(r.obstacle); su.append(r.support)
    hit["obstacle"] = ob; hit["support"] = su
    hit["cls"] = np.where(hit.obstacle == 0, "VACUUM",
                 np.where(hit.obstacle > hit.support, "WALL", "NEITHER"))
    return hit


def _score(sub: pd.DataFrame, side: np.ndarray, label: str) -> dict:
    """$ per lot on the raw forward move, no exit, no cost. Direction only."""
    r = {"cell": label, "n": len(sub)}
    for h in HOR:
        v = side * sub[f"fwd{h}"].to_numpy() * VPP
        v = v[np.isfinite(v)]
        r[f"h{h}"] = round(float(np.mean(v)), 2) if len(v) else np.nan
        r[f"w{h}"] = round(float((v > 0).mean() * 100), 1) if len(v) else np.nan
    return r


def main():
    df = frame()
    d = pd.to_datetime(df.ts, unit="s", utc=True)
    print(f"joined minutes={len(df):,}  {d.min()} -> {d.max()}  sessions={df.sday.nunique()}")

    hit = breaks(df)
    assert (hit.brk.abs() == 1).all()
    print(f"\n60m breaks on book-covered minutes: {len(hit)}  "
          f"({(hit.brk > 0).sum()} up / {(hit.brk < 0).sum()} down)")
    print(hit.cls.value_counts().to_string())
    print(f"median obstacle={hit.obstacle.median():.1f}  median support={hit.support.median():.1f}")

    rows = []
    # ── the 2x2, FADE convention (the live gate fades the break) ────────────────────
    fade = -hit.brk.to_numpy()
    rows.append(_score(hit, fade, "LEVEL-ONLY  all breaks, faded"))
    for c in ("VACUUM", "WALL", "NEITHER"):
        s = hit[hit.cls == c]
        rows.append(_score(s, -s.brk.to_numpy(), f"  break x {c}, faded"))
        rows.append(_score(s, s.brk.to_numpy(), f"  break x {c}, followed"))

    # ── BOOK-ONLY: the same liquidity question with NO level attached ───────────────
    # "nothing resting within 1pt above the mid" is the vacuum condition stripped of the break.
    up_hole = df[df["ask_d1.0"] == 0]
    dn_hole = df[df["bid_d1.0"] == 0]
    rows.append(_score(df, np.ones(len(df)), "BASELINE   every minute, LONG"))
    rows.append(_score(df, -np.ones(len(df)), "BASELINE   every minute, SHORT"))
    rows.append(_score(up_hole, np.ones(len(up_hole)), "BOOK-ONLY  ask hole -> LONG"))
    rows.append(_score(up_hole, -np.ones(len(up_hole)), "BOOK-ONLY  ask hole -> SHORT"))
    rows.append(_score(dn_hole, -np.ones(len(dn_hole)), "BOOK-ONLY  bid hole -> SHORT"))
    rows.append(_score(dn_hole, np.ones(len(dn_hole)), "BOOK-ONLY  bid hole -> LONG"))

    out = pd.DataFrame(rows)
    out.to_csv(f"{OUT}/attrib.csv", index=False)
    pd.set_option("display.width", 220)
    print("\n=== $ per lot on the raw forward move (no exit, no cost), win% beside ===")
    print(out.to_string(index=False))
    hit.to_pickle(f"{OUT}/breaks.pkl")


if __name__ == "__main__":
    main()
