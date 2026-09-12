#!/usr/bin/env python3
"""GF2 — THE VOLATILITY GATE, re-raced on the 250ms QUOTE tape where the ordering is KNOWN.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_volgate_ticks.py

★ WHY. On 1-minute bars the breakout-either-way gate reads +$3.90 a trade before the intrabar
tiebreak and -$7.96 after it. The entire result - three times the apparent edge - is one assumption
about WHICH LEG OF THE STRADDLE FILLED FIRST when a minute touched both, and a minute bar physically
cannot answer that. So the twelve-month tape CANNOT decide this gate, in either direction, and any
verdict taken from it is an artefact of the tiebreak I happened to choose.

★ WHAT CAN. Our own depth capture is 250ms with bid AND ask, 27 contiguous days (2026-07-16..08-21).
There the order of events is observed, not assumed: the straddle is armed, the quotes are walked
forward one snapshot at a time, and whichever level the market REACHES FIRST is the one that fills.
Small sample, honest mechanics - the opposite trade-off from the year tape, which is the point of
running both.

Fills: a stop-buy fills when the ASK trades up to the level (you pay the ask); a stop-sell when the
BID trades down to it. Exits mark a long out on the bid and a short on the ask. Every leg crosses.
"""
from __future__ import annotations

import json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from gf_mgc_tape import FEE_RT, VPP, build_tape  # noqa: E402
from gf_mgc_cells import five_second, stat  # noqa: E402

pd.set_option("display.width", 300)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf2"
SLIP = 0.10
R: dict = {}


def run_gate(m, f, *, band=0.25, hold=60, every=60, stop=5.0, arm=3.0, trail=3.0, cap_min=480,
             flip=False, one_at_a_time=True, slip=SLIP, force_side=None, seed=0):
    """m = 1-minute mid bars (for the ATR + the arming clock); f = 5s bid/ask (the race tape).

    ★ The straddle is ARMED on the minute clock but RESOLVED on the quote tape - a 5-second bar
    still cannot say which of its own high and low came first, so the resolution is done at 5s
    granularity, which is 12x finer than the minute and is what our capture actually holds. Where a
    single 5s bucket STILL touches both levels the tie is resolved AGAINST the trade, exactly as
    before; the point of this run is how much rarer that case becomes.
    """
    ts5 = f.index.tz_convert("UTC").tz_localize(None).astype("datetime64[ns]").astype("int64").to_numpy()
    bh, bl, bc = (f[c].to_numpy() for c in ("bid_hi", "bid_lo", "bid_cl"))
    ah, al, ac = (f[c].to_numpy() for c in ("ask_hi", "ask_lo", "ask_cl"))
    day5 = f.index.strftime("%Y-%m-%d").to_numpy()
    n5 = len(f)
    rng = np.random.default_rng(seed)
    rows = []; busy = -1; ties = 0
    mi = m.index
    for t in range(60, len(m) - 60):
        if mi[t].minute % every or not np.isfinite(m["atr"].iloc[t]) or m["atr"].iloc[t] <= 0:
            continue
        i = int(np.searchsorted(ts5, np.int64(pd.Timestamp(mi[t]).value), side="left"))
        if i <= 0 or i >= n5 - 200 or (one_at_a_time and i < busy):
            continue
        a = float(m["atr"].iloc[t]); px = float(m["close"].iloc[t])
        up, dn = px + band * a, px - band * a
        end = min(i + hold * 12, n5)
        trig = None
        for k in range(i, end):
            if day5[k] != day5[i]:
                break
            hit_u, hit_d = ah[k] >= up, bl[k] <= dn
            if hit_u and hit_d:
                ties += 1
                trig = (k, -1 if bc[k] >= bc[i] else 1); break     # still resolved AGAINST us
            if hit_u:
                trig = (k, 1); break
            if hit_d:
                trig = (k, -1); break
        if trig is None:
            continue
        k, side = trig
        if flip:
            side = -side
        if force_side is not None:
            side = int(rng.choice([1, -1]))
        lvl = up if side > 0 else dn
        # gap-honest: if the 5s bucket OPENED through the level, you fill worse than the level
        touch = max(lvl, al[k]) if side > 0 else min(lvl, bh[k])
        fill_in = touch + side * slip
        sl = fill_in - side * stop * a
        peak = 0.0; armed = False; tl = None; out = None
        last = min(k + cap_min * 12, n5 - 1)
        for j in range(k + 1, last + 1):
            if day5[j] != day5[k]:
                out = (bc[j - 1] if side > 0 else ac[j - 1], j - 1, "EOD"); break
            adv = bl[j] if side > 0 else ah[j]
            fav = bh[j] if side > 0 else al[j]
            if not (np.isfinite(adv) and np.isfinite(fav)):
                continue
            if (adv <= sl) if side > 0 else (adv >= sl):
                out = (sl, j, "STOP"); break
            if armed and tl is not None and ((adv <= tl) if side > 0 else (adv >= tl)):
                out = (tl, j, "TRAIL"); break
            peak = max(peak, side * (fav - fill_in))
            if peak >= arm * a:
                armed = True
            if armed:
                tl = fill_in + side * (peak - trail * a)
        if out is None:
            out = (bc[last] if side > 0 else ac[last], last, "CAP")
        pxo, j, why = out
        fill_out = pxo - side * slip
        busy = j + 1
        rows.append({"day": day5[k], "ts": f.index[k], "side": side, "atr": a,
                     "regime": m["regime"].iloc[t], "session": m["session"].iloc[t],
                     "reason": why, "minutes": round((j - k) / 12.0, 1),
                     "mfe_pt": round(float(peak), 2),
                     "true_pnl": round(side * (fill_out - fill_in) * VPP - FEE_RT, 2)})
    d = pd.DataFrame(rows)
    d.attrs["ties"] = ties
    return d


def main():
    m, q = build_tape()
    f = five_second(q)
    print("=" * 130)
    print(f"THE VOLATILITY GATE ON THE QUOTE TAPE — {m['day'].nunique()} days, "
          f"{len(f):,} 5-second bid/ask bars")
    print("=" * 130)
    d = run_gate(m, f)
    print(f"\n  unresolvable ties (both levels inside ONE 5-second bucket): {d.attrs['ties']} "
          f"of {len(d)} = {100*d.attrs['ties']/max(len(d),1):.1f}%")
    print("  (on 1-MINUTE bars that figure was the thing that decided the whole gate)")
    print()
    for lbl, dd in (("as built", d), ("THE MIRROR (side flipped, re-raced)", run_gate(m, f, flip=True))):
        s = stat(dd)
        print(f"  {lbl:<40} n={s['n']:>4} {s['days']:>3}d net ${s['net']:>8,.0f} "
              f"{s['per']:>7.2f}/tr win {s['win']:>5.1f}% med {s['med']:>7.2f}")
        R[lbl] = s
    L, S = stat(d[d.side > 0]), stat(d[d.side < 0])
    print(f"  {'LONG':<40} n={L['n']:>4} net ${L['net']:>8,.0f} {L['per']:>7.2f}/tr")
    print(f"  {'SHORT':<40} n={S['n']:>4} net ${S['net']:>8,.0f} {S['per']:>7.2f}/tr")
    R["sides"] = {"LONG": L, "SHORT": S}

    print("\n  random side at the same moments, 20 draws:")
    real = float(d["true_pnl"].sum())
    coins = [float(run_gate(m, f, force_side=True, seed=s)["true_pnl"].sum()) for s in range(20)]
    print(f"    real ${real:,.0f}   coin mean ${np.mean(coins):,.0f}  "
          f"beaten {sum(1 for x in coins if x>=real)}/20")
    R["coin"] = {"real": round(real, 0), "mean": round(float(np.mean(coins)), 0),
                 "beaten": int(sum(1 for x in coins if x >= real))}

    print("\n  band sweep (quote tape):")
    rows = []
    for band in (0.10, 0.25, 0.50, 0.75, 1.0):
        for st, ar, tr in ((3.0, 2.0, 2.0), (5.0, 3.0, 3.0)):
            dd = run_gate(m, f, band=band, stop=st, arm=ar, trail=tr)
            s = stat(dd)
            rows.append({"band": band, "exit": f"sl{st:g}/a{ar:g}/t{tr:g}", **s,
                         "ties%": round(100 * dd.attrs["ties"] / max(len(dd), 1), 1)})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    R["sweep"] = rows
    print(f"\n  {int((t['net']>0).sum())} of {len(t)} cells positive on the quote tape.")

    # in-sample vs forward, same split as the rest of the section
    print("\n  the same 22/5-day split used everywhere else in this section:")
    for lbl, sub in (("07-16..08-14", d[d["day"] < "2026-08-17"]), ("08-17..08-21 FORWARD", d[d["day"] >= "2026-08-17"])):
        s = stat(sub)
        print(f"    {lbl:<24} n={s['n']:>4} net ${s['net']:>8,.0f} {s['per']:>7.2f}/tr win {s['win']:.1f}%")
        R.setdefault("split", {})[lbl] = s
    print("\n  by regime:")
    print(pd.DataFrame([{"regime": k, "side": s, **stat(g)} for (k, s), g in
                        d.groupby(["regime", d["side"].map({1: "LONG", -1: "SHORT"})])]
                       ).sort_values("per", ascending=False).to_string(index=False))
    R["regime"] = [{"regime": k, "side": s, **stat(g)} for (k, s), g in
                   d.groupby(["regime", d["side"].map({1: "LONG", -1: "SHORT"})])]
    json.dump(R, open(f"{OUT}/volgate_ticks.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/volgate_ticks.json")


if __name__ == "__main__":
    main()
