#!/usr/bin/env python3
"""GF_MGC TOUCH — the barrier instrument. Which comes first, the target or the stop?

    PYTHONPATH=src .venv/bin/python scripts/gf_mgc_touch.py

★ WHY THIS EXISTS, AND WHY THE MAP WAS NOT ENOUGH. `gf_mgc_map.py` measures the mean move over a
FIXED horizon. That is the honest instrument for a MOMENTUM trade, which boards and holds. It is the
WRONG instrument for a REVERSION trade, which puts a target a short way out and leaves. A snapback
can pay handsomely while its 60-minute mean return is exactly zero, because the trade harvests the
PATH and then goes flat — the endpoint never sees it.

So before concluding anything about the two reversion cells, the question has to be re-asked in the
geometry a reversion trade actually lives in:

    from this entry, does price touch +k ATR before it touches -k ATR, inside a time cap?

★ THAT IS ALSO THE HONEST FORM OF THE EXIT GRID. A target/stop pair is exactly a pair of barriers,
so the same scan prices every cell of the tight-R sweep at once, and it does it WITHOUT the
look-ahead that comes from evaluating a stop and a target on the same bar close.

★ CONSERVATIVE TIE-BREAKING. The scan runs on 5-SECOND bars of the bid and the ask. When a 5s bar
touches both barriers, the STOP is booked, never the target. That biases every number here DOWNWARD,
which is the only direction a bias is allowed to point.

★ SPREAD-HONEST. A long is measured on the BID (what it can sell into) and a short on the ASK. The
entry crosses. MGC's spread is a flat 0.30pt = $3.00 and its ATR is 1.1-2.6pt, so the spread is
roughly a fifth of an R — on gold this is not a rounding error, it is the main term.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_mgc_tape import FEE_RT, VPP, build_tape, load_quotes  # noqa: E402

pd.set_option("display.width", 250)


def five_second(q: pd.DataFrame) -> pd.DataFrame:
    """5s bars of the BID and the ASK separately — the two prices a position is actually marked at."""
    g = q.resample("5s")
    out = pd.DataFrame({
        "bid_hi": g["bid1p"].max(), "bid_lo": g["bid1p"].min(), "bid_cl": g["bid1p"].last(),
        "ask_hi": g["ask1p"].max(), "ask_lo": g["ask1p"].min(), "ask_cl": g["ask1p"].last(),
    }).dropna()
    return out


def barrier_scan(f: pd.DataFrame, entries: pd.DataFrame, *, tp_atr: float, sl_atr: float,
                 cap_min: int) -> pd.DataFrame:
    """First-touch outcome for every entry. `entries` needs columns ts, side, atr.

    Returns the entry frame plus fill_in / exit / reason / minutes / true_pnl / desk_pnl.
    Vectorised per-entry over a bounded window; the cap keeps each scan short.
    """
    # ⚠ the depth index is datetime64[ms], so a bare `.view("int64")` yields MILLISECONDS while
    # `Timestamp.value` yields NANOSECONDS. That mismatch makes every searchsorted fall off the end
    # and the scan returns silently empty — a zero-row "result", not an error. Normalise to ns.
    idx = f.index
    ts_ns = idx.tz_convert("UTC").tz_localize(None).astype("datetime64[ns]").astype("int64").to_numpy()
    bid_hi, bid_lo = f["bid_hi"].to_numpy(), f["bid_lo"].to_numpy()
    ask_hi, ask_lo = f["ask_hi"].to_numpy(), f["ask_lo"].to_numpy()
    bid_cl, ask_cl = f["bid_cl"].to_numpy(), f["ask_cl"].to_numpy()
    n = len(f)
    span = int(cap_min * 12)  # 12 five-second bars per minute

    rows = []
    for e in entries.itertuples():
        i = int(np.searchsorted(ts_ns, np.int64(pd.Timestamp(e.ts).value), side="left"))
        if i >= n - 1:
            continue
        side, a = int(e.side), float(e.atr)
        if not np.isfinite(a) or a <= 0:
            continue
        # entry CROSSES the spread
        fill_in = ask_cl[i] if side > 0 else bid_cl[i]
        mid_in = (ask_cl[i] + bid_cl[i]) / 2.0
        j = min(i + 1 + span, n)
        tp, sl = tp_atr * a, sl_atr * a
        if side > 0:
            tgt, stp = fill_in + tp, fill_in - sl
            hit_t = bid_hi[i + 1:j] >= tgt
            hit_s = bid_lo[i + 1:j] <= stp
        else:
            tgt, stp = fill_in - tp, fill_in + sl
            hit_t = ask_lo[i + 1:j] <= tgt
            hit_s = ask_hi[i + 1:j] >= stp
        it = int(np.argmax(hit_t)) if hit_t.any() else 10**9
        iss = int(np.argmax(hit_s)) if hit_s.any() else 10**9
        if iss <= it and iss < 10**9:          # ★ ties go to the STOP, always
            k, fill_out, reason = iss, stp, "STOP"
        elif it < 10**9:
            k, fill_out, reason = it, tgt, "TARGET"
        else:
            k = j - i - 2
            fill_out = bid_cl[j - 1] if side > 0 else ask_cl[j - 1]
            reason = "TIME_CAP"
        k_abs = i + 1 + k
        mid_out = (ask_cl[min(k_abs, n - 1)] + bid_cl[min(k_abs, n - 1)]) / 2.0
        rows.append({
            **{c: getattr(e, c) for c in entries.columns if c != "ts"},
            "ts": e.ts, "fill_in": fill_in, "fill_out": fill_out, "reason": reason,
            "minutes": (k + 1) * 5.0 / 60.0,
            "true_pnl": round(side * (fill_out - fill_in) * VPP - FEE_RT, 2),
            "desk_pnl": round(side * (mid_out - mid_in) * VPP - FEE_RT, 2),
        })
    return pd.DataFrame(rows)


def stat(df: pd.DataFrame, col: str = "true_pnl") -> dict:
    if df.empty:
        return {"n": 0, "net$": 0.0, "win%": 0.0, "$/tr": 0.0}
    v = df[col]
    return {"n": len(v), "net$": round(float(v.sum()), 0), "win%": round(100.0 * float((v > 0).mean()), 1),
            "$/tr": round(float(v.mean()), 2)}


# ── the entry families under test ────────────────────────────────────────────────────────────────
def extension_entries(m: pd.DataFrame, *, k: int, ext_atr: float, side_mode: str,
                      cooldown_min: int = 30) -> pd.DataFrame:
    """A move of `ext_atr` ATR over the prior k minutes. `side_mode` decides what we do about it:

        "fade"   -> trade AGAINST the impulse  (the REVERSION cells)
        "follow" -> trade WITH the impulse     (the MOMENTUM cells)

    ⚠ THE BAR-LABEL TRAP. `resample` stamps a minute bar with its LEFT edge, so the bar labelled
    10:00 only closes at 10:01. Entry is therefore taken at ts + 60s. Getting this wrong halved a
    gold result on 2026-08-14 (+$906 -> +$470) and it is the single easiest way to fake an edge here.
    """
    d = m.copy()
    d["imp"] = (d["close"] - d["close"].shift(k)) / d["atr"]
    d = d.dropna(subset=["imp", "atr"])
    up, dn = d["imp"] >= ext_atr, d["imp"] <= -ext_atr
    rows = []
    for ts, is_up, is_dn in zip(d.index, up.to_numpy(), dn.to_numpy()):
        if not (is_up or is_dn):
            continue
        raw = 1 if is_up else -1
        side = -raw if side_mode == "fade" else raw
        rows.append({"ts": ts + pd.Timedelta(seconds=60), "side": side,
                     "atr": float(d.at[ts, "atr"]), "regime": d.at[ts, "regime"],
                     "session": d.at[ts, "session"], "day": d.at[ts, "day"],
                     "er": float(d.at[ts, "er"]) if np.isfinite(d.at[ts, "er"]) else np.nan})
    e = pd.DataFrame(rows)
    return _cooldown(e, cooldown_min)


def _cooldown(e: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """One position at a time per side — otherwise a single move produces 30 correlated 'trades' and
    every n in the report is a lie."""
    if e.empty:
        return e
    keep, last = [], {}
    for r in e.itertuples():
        if r.side in last and (r.ts - last[r.side]).total_seconds() < minutes * 60:
            continue
        last[r.side] = r.ts
        keep.append(r.Index)
    return e.loc[keep].reset_index(drop=True)


def main() -> None:
    m, q = build_tape()
    print("building 5s bid/ask frame ...", flush=True)
    f = five_second(q)
    print(f"  {len(f):,} five-second bars\n")

    print("=" * 118)
    print("[A] THE REVERSION GEOMETRY — fade a k-minute extension, symmetric barriers")
    print("    (win% here is a FIRST-TOUCH probability, not a P&L claim; ties go to the stop)")
    print("=" * 118)
    for k, ext in ((20, 1.5), (30, 2.0), (60, 2.5)):
        e = extension_entries(m, k=k, ext_atr=ext, side_mode="fade")
        if e.empty:
            continue
        print(f"\n  ── fade a {k}min move of >= {ext} ATR   (n={len(e)} entries) ──")
        for tp, sl in ((0.5, 0.5), (1.0, 1.0), (1.0, 1.5), (1.5, 1.5), (0.75, 1.5)):
            r = barrier_scan(f, e, tp_atr=tp, sl_atr=sl, cap_min=120)
            if r.empty:
                continue
            allr = stat(r)
            lo = stat(r[r.side > 0])
            sh = stat(r[r.side < 0])
            print(f"    tp {tp:>4} / sl {sl:>4} ATR   ALL n={allr['n']:>4} net${allr['net$']:>8.0f} "
                  f"win {allr['win%']:>5.1f}% ${allr['$/tr']:>7.2f}/tr   |   "
                  f"LONG n={lo['n']:>4} ${lo['$/tr']:>7.2f}   SHORT n={sh['n']:>4} ${sh['$/tr']:>7.2f}")

    print("\n" + "=" * 118)
    print("[B] SAME GEOMETRY, BY REGIME — the router question. tp/sl = 1.0/1.0 ATR, 120min cap")
    print("=" * 118)
    e = extension_entries(m, k=30, ext_atr=2.0, side_mode="fade")
    r = barrier_scan(f, e, tp_atr=1.0, sl_atr=1.0, cap_min=120)
    if not r.empty:
        rows = []
        for (reg, sd), g in r.groupby(["regime", r["side"].map({1: "LONG", -1: "SHORT"})]):
            rows.append({"regime": reg, "side": sd, **stat(g)})
        print(pd.DataFrame(rows).sort_values(["side", "regime"]).to_string(index=False))

    print("\n" + "=" * 118)
    print("[C] THE MOMENTUM GEOMETRY — FOLLOW the extension instead. Same barriers, same rows.")
    print("=" * 118)
    for k, ext in ((20, 1.5), (30, 2.0)):
        e = extension_entries(m, k=k, ext_atr=ext, side_mode="follow")
        if e.empty:
            continue
        print(f"\n  ── follow a {k}min move of >= {ext} ATR   (n={len(e)} entries) ──")
        for tp, sl in ((1.0, 1.0), (2.0, 1.0), (3.0, 1.5), (4.0, 2.0)):
            r = barrier_scan(f, e, tp_atr=tp, sl_atr=sl, cap_min=240)
            if r.empty:
                continue
            allr = stat(r)
            lo, sh = stat(r[r.side > 0]), stat(r[r.side < 0])
            print(f"    tp {tp:>4} / sl {sl:>4} ATR   ALL n={allr['n']:>4} net${allr['net$']:>8.0f} "
                  f"win {allr['win%']:>5.1f}% ${allr['$/tr']:>7.2f}/tr   |   "
                  f"LONG n={lo['n']:>4} ${lo['$/tr']:>7.2f}   SHORT n={sh['n']:>4} ${sh['$/tr']:>7.2f}")

    print("\n" + "=" * 118)
    print("[D] MOMENTUM BY REGIME — does the map's BUILDING finding survive a real target/stop?")
    print("    follow a 20min >= 1.5 ATR move, tp 3.0 / sl 1.5 ATR, 240min cap")
    print("=" * 118)
    e = extension_entries(m, k=20, ext_atr=1.5, side_mode="follow")
    r = barrier_scan(f, e, tp_atr=3.0, sl_atr=1.5, cap_min=240)
    if not r.empty:
        rows = []
        for (reg, sd), g in r.groupby(["regime", r["side"].map({1: "LONG", -1: "SHORT"})]):
            rows.append({"regime": reg, "side": sd, **stat(g)})
        t = pd.DataFrame(rows).sort_values(["side", "regime"])
        print(t.to_string(index=False))
        print("\n  and the same table on the DESK's old $1.50-only cost convention, for scale:")
        rows = []
        for (reg, sd), g in r.groupby(["regime", r["side"].map({1: "LONG", -1: "SHORT"})]):
            rows.append({"regime": reg, "side": sd, **stat(g, "desk_pnl")})
        print(pd.DataFrame(rows).sort_values(["side", "regime"]).to_string(index=False))
        print(f"\n  ★ the gap between those two tables is the SPREAD, and it is "
              f"${r['desk_pnl'].mean() - r['true_pnl'].mean():.2f} per trade.")


if __name__ == "__main__":
    main()
