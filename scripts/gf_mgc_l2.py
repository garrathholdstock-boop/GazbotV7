#!/usr/bin/env python3
"""GF_MGC L2 — the order-book cut on the break, and the 2x2 it is supposed to produce.

    PYTHONPATH=src .venv/bin/python scripts/gf_mgc_l2.py

★ THE ONE ANGLE THE SCOPE CALLS MOST PROMISING AND THE LEAST EXPLORED: gold's book is far thinner
than MNQ's (a handful of lots at the touch against MNQ's tens), so absorption / depletion mechanics
that wash out in Nasdaq depth ought to be visible here.

★ AND IT IS NOT THE REFUTED ATTACK. `[[mgc-momentum-greenfield-null]]` closed "L2 book direction" —
asking the book, at an arbitrary moment, WHICH WAY price will go. It flipped sign across five
disjoint samples. This asks the book nothing about direction. The break has already picked the
side; the book is asked only whether the side it picked will HOLD. That is a liquidity question,
and liquidity is the one thing a book genuinely knows.

★ THE PAYOFF IF IT SEPARATES IS THE WHOLE 2x2 FROM ONE TRIGGER:
      break + far side DEPLETED / EMPTY  ->  ?
      break + far side ABSORBING         ->  ?
  The Movement-1 census already priced the first line at the 4.8th percentile of its own placebo
  with the sign INVERTED: a gold level that breaks into a vacuum is one NOBODY IS DEFENDING, and
  price comes straight back. This file re-derives that from scratch and, crucially, prices it with
  a REAL TRADED EXIT rather than a 60-minute endpoint move.

★ DATA. depth.db.depth_snap, 10 levels, 250ms — MGC's L2 does NOT live in capture.db.book (that is
MNQ-only; IBKR allows just three depth subscriptions). 22 contiguous days, and 12 of them
(07-20..08-04) have no L1 tape at all, so no previous gold study has ever seen them.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7 import lake  # noqa: E402
from gf_mgc_cells import (  # noqa: E402
    Racer, battery, break_entries, five_second, line, placebo, run_entries, side_split, stat,
)
from gf_mgc_tape import SYMBOL, VPP, build_tape  # noqa: E402

pd.set_option("display.width", 260)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
BAND_PT = 1.0          # "in front of the break" = this many points beyond the level
CHAND = dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)
SCALP = dict(stop=1.0, target=1.0, cap_min=120)
R: dict = {}


def load_book_5s() -> pd.DataFrame:
    """10-level book, LAST snapshot in each 5s bucket — sampled, not averaged, because a break is
    an instant and what matters is the book standing when price arrives, not the bucket's mean."""
    con = lake.connect(symbol=SYMBOL)
    cols = ", ".join([f"bid{i}p, bid{i}s, ask{i}p, ask{i}s" for i in range(1, 11)])
    df = con.execute(f"""
        WITH b AS (
            SELECT ts_ms - (ts_ms % 5000) AS b5, {cols},
                   row_number() OVER (PARTITION BY ts_ms - (ts_ms % 5000) ORDER BY ts_ms DESC) rn
            FROM depth
            WHERE symbol='{SYMBOL}' AND bid1p > 0 AND ask1p > 0 AND ask1p - bid1p BETWEEN 0 AND 5
        )
        SELECT b5, {cols} FROM b WHERE rn = 1 ORDER BY b5
    """).df()
    df["ts"] = pd.to_datetime(df["b5"], unit="ms", utc=True)
    return df.set_index("ts").drop(columns=["b5"])


def _band(row, side: str, lvl: float, band: float = BAND_PT) -> float:
    t = 0.0
    for k in range(1, 11):
        p, s = row[f"{side}{k}p"], row[f"{side}{k}s"]
        if not (np.isfinite(p) and np.isfinite(s)):
            continue
        if side == "ask" and lvl <= p <= lvl + band:
            t += s
        elif side == "bid" and lvl - band <= p <= lvl:
            t += s
    return t


def attach(e: pd.DataFrame, bk: pd.DataFrame) -> pd.DataFrame:
    """Book state AT the break and 60s BEFORE it. Strictly causal — the snapshot used is the last
    one at or before the entry stamp, never the next one."""
    ts_ns = bk.index.tz_convert("UTC").tz_localize(None).astype("datetime64[ns]").astype("int64").to_numpy()
    out = []
    for r in e.itertuples():
        v = np.int64(pd.Timestamp(r.ts).value)
        i = int(np.searchsorted(ts_ns, v, side="left")) - 1
        j = int(np.searchsorted(ts_ns, v - 60 * 10**9, side="left")) - 1
        if i < 0 or j < 0 or i >= len(bk):
            continue
        far = "ask" if r.brk > 0 else "bid"        # what stands in the BREAK's way
        near = "bid" if r.brk > 0 else "ask"       # what would catch it if it fails
        ri, rj = bk.iloc[i], bk.iloc[j]
        obstacle, obst_pre = _band(ri, far, r.level), _band(rj, far, r.level)
        support = _band(ri, near, r.level)
        tb = sum(ri[f"bid{k}s"] for k in range(1, 11) if np.isfinite(ri[f"bid{k}s"]))
        ta = sum(ri[f"ask{k}s"] for k in range(1, 11) if np.isfinite(ri[f"ask{k}s"]))
        out.append({**{c: getattr(r, c) for c in e.columns},
                    "obstacle": obstacle, "obst_pre": obst_pre, "support": support,
                    "depletion": (1.0 - obstacle / obst_pre) if obst_pre > 0 else np.nan,
                    "ratio": (obstacle / support) if support > 0 else np.nan,
                    "imb_brk": ((tb - ta) / (tb + ta) * r.brk) if (tb + ta) > 0 else np.nan})
    return pd.DataFrame(out)


def main() -> None:
    m, q = build_tape()
    f = five_second(q)
    racer = Racer(f)
    print("loading 10-level MGC depth ...", flush=True)
    bk = load_book_5s()
    print(f"  {len(bk):,} book snapshots, {bk.index.min()} .. {bk.index.max()}\n")

    ef = attach(break_entries(m, fade=True), bk)      # side = fade
    ec = ef.copy()
    ec["side"] = -ec["side"]                          # side = follow, identical rows
    print(f"breaks with a causal book read: n={len(ef)}")
    print(f"  far side EMPTY (0 lots within {BAND_PT}pt): {int((ef['obstacle'] == 0).sum())}  "
          f"({100 * float((ef['obstacle'] == 0).mean()):.0f}%)")
    print(f"  median obstacle {ef['obstacle'].median():.0f} lots · median support "
          f"{ef['support'].median():.0f} lots\n")
    R["n_breaks"] = len(ef)
    R["pct_empty"] = round(100 * float((ef["obstacle"] == 0).mean()), 1)

    cuts = {
        "far side EMPTY (obstacle = 0)": ef["obstacle"] == 0,
        "far side THIN (< 5 lots)": ef["obstacle"] < 5,
        "far side DEFENDED (>= 5 lots)": ef["obstacle"] >= 5,
        "wall EATEN in the last 60s (depletion > 0.5)": ef["depletion"] > 0.5,
        "wall INTACT (depletion <= 0)": ef["depletion"] <= 0,
        "more in the way than behind (ratio > 1)": ef["ratio"] > 1,
        "more behind than in the way (ratio < 1)": ef["ratio"] < 1,
        "book leaning WITH the break (imb > 0.10)": ef["imb_brk"] > 0.10,
        "book leaning AGAINST the break (imb < -0.10)": ef["imb_brk"] < -0.10,
    }

    for exit_name, kw in (("TIGHT SCALP (tp 1.0 / sl 1.0 ATR, 120m)", SCALP),
                          ("WIDE CHANDELIER (stop 3 / arm 2 / trail 2 ATR, 480m)", CHAND)):
        print("=" * 126)
        print(f"[{exit_name}] — FADE the break, split by what the book was doing")
        print("=" * 126)
        rf = run_entries(racer, ef, **kw)
        rc = run_entries(racer, ec, **kw)
        print(line("ALL breaks — FADE", stat(rf)))
        print(line("ALL breaks — FOLLOW (the mirror)", stat(rc)))
        rows = []
        for lbl, mask in cuts.items():
            sub_f = rf[mask.reindex(rf.index).fillna(False).to_numpy()]
            sub_c = rc[mask.reindex(rc.index).fillna(False).to_numpy()]
            sf, sc = stat(sub_f), stat(sub_c)
            ss = side_split(sub_f)
            rows.append({"book cut": lbl, "n": sf["n"], "FADE net": sf["net"], "FADE $/tr": sf["per"],
                         "FADE win": sf["win"], "FOLLOW $/tr": sc["per"],
                         "L$/tr": ss["LONG"]["per"], "S$/tr": ss["SHORT"]["per"]})
        t = pd.DataFrame(rows)
        print(t.to_string(index=False))
        R.setdefault("book_cuts", {})[exit_name] = rows
        print()

    # ── the escalation the scope mandates ───────────────────────────────────────────────────────
    print("=" * 126)
    print("[ESCALATION] narrow to the biggest breaks and hunt again — where does a footprint appear?")
    print("=" * 126)
    rf = run_entries(racer, ef, **CHAND)
    rf = rf.assign(mfe_rank=rf["mfe_pt"] / rf["atr"])
    for lbl, sub in (("FULL population", rf),
                     ("top 25 by ATR at the break", rf.nlargest(25, "atr")),
                     ("top 15 by ATR at the break", rf.nlargest(15, "atr")),
                     ("empty far side only", rf[rf["obstacle"] == 0]),
                     ("empty far side + top half by ATR",
                      rf[(rf["obstacle"] == 0) & (rf["atr"] >= rf["atr"].median())])):
        s = side_split(sub)
        print(line(lbl, stat(sub), f"LONG ${s['LONG']['per']:>6.2f}  SHORT ${s['SHORT']['per']:>6.2f}"))
        R.setdefault("escalation", {})[lbl] = {"all": stat(sub), "sides": s}

    # ── does the book cut BEAT dropping the same number at random? ──────────────────────────────
    print("\n" + "=" * 126)
    print("[FILTER PLACEBO] a filter that keeps 43% of trades looks brilliant whenever the 57% it")
    print("    dropped happened to lose. So: drop the SAME NUMBER at random, 200 times.")
    print("=" * 126)
    rng = np.random.default_rng(20260815)
    for lbl, mask in (("far side EMPTY", ef["obstacle"] == 0),
                      ("far side THIN (<5)", ef["obstacle"] < 5),
                      ("book AGAINST the break", ef["imb_brk"] < -0.10)):
        keep = mask.reindex(rf.index).fillna(False).to_numpy()
        real = float(rf[keep]["true_pnl"].sum())
        k = int(keep.sum())
        if k == 0:
            continue
        draws = [float(rf["true_pnl"].iloc[rng.choice(len(rf), size=k, replace=False)].sum())
                 for _ in range(200)]
        beaten = sum(1 for x in draws if x >= real)
        print(f"  {lbl:<26} keep n={k:>3}  real ${real:>8.0f}   random-keep mean ${np.mean(draws):>8.0f}"
              f"   beaten {beaten}/200   pctile {100 * (1 - beaten / 200):.1f}")
        R.setdefault("filter_placebo", {})[lbl] = {
            "n": k, "real": round(real, 0), "random_mean": round(float(np.mean(draws)), 0),
            "beaten": beaten, "runs": 200, "pctile": round(100 * (1 - beaten / 200), 1)}

    json.dump(R, open(f"{OUT}/gf_mgc_l2.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/gf_mgc_l2.json")


if __name__ == "__main__":
    main()
