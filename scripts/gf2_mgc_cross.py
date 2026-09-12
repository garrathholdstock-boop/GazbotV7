#!/usr/bin/env python3
"""GF2 — THE CROSS-ASSET STONE.  MGC x MNQ on the same clock, 10 months of paired minutes.

    PYTHONPATH=src .venv/bin/python scripts/gf2_mgc_cross.py

★ THIS IS THE ONE STONE LAST WEEK'S SECTION LEFT UNTURNED, named in its own closing paragraph:
  "Every source this desk has pointed at gold is gold's own price and gold's own book. The one
   genuinely different input we have never used is the relationship between MGC and MNQ on the same
   clock... A break in gold that coincides with a matching break in the Nasdaq is a different event
   from one that does not, and nothing in this section can tell them apart."

It was unturnable then: the depth tape is 27 days, and a cross-asset relationship measured on 27
days is a coin. With the 1-minute backfills there are ~10 MONTHS of paired minutes, so it is
turnable now.

★ RULE 1 COMPLIANCE. This is not an MNQ gate ported to gold. MNQ is used only as an EXOGENOUS
INPUT - the macro state of the day - exactly as an ATR or a session clock is. The trade is in gold,
the signal is "what is risk doing", and nothing about MNQ's own gates comes near it.

★ MAP BEFORE GATE. No trades until the conditional bias is measured. If there is no bias there is
no gate, and that is the honest answer.
"""
from __future__ import annotations

import json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from gf2_mgc_histlab import VPP, FEE_RT, SPREAD_PT, BarRacer, line, load_clean, run, stat  # noqa: E402

pd.set_option("display.width", 300)
OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf2"
MNQ_BF = "/home/alphabot/gazbot7/data/tape/bars/MNQ/backfill_1min.parquet"
R: dict = {}


def load_mnq() -> pd.DataFrame:
    import duckdb
    c = duckdb.connect(); c.execute("SET memory_limit='2GB'")
    df = c.execute(f"""
        SELECT bar_ts, open, high, low, close FROM read_parquet('{MNQ_BF}')
        WHERE symbol='MNQ' AND timeframe='1min' AND volume > 0 ORDER BY bar_ts
    """).df()
    df["ts"] = pd.to_datetime(df["bar_ts"], unit="s", utc=True)
    return df.set_index("ts").drop(columns=["bar_ts"])


def main():
    g = load_clean()
    n = load_mnq()
    print("=" * 130)
    print("THE PAIRED TAPE")
    print("=" * 130)
    print(f"  MGC clean 1-min: {len(g):,} minutes, {g['day'].nunique()} days, "
          f"{g['day'].min()} .. {g['day'].max()}")
    nd = n.index.strftime('%Y-%m-%d')
    print(f"  MNQ clean 1-min: {len(n):,} minutes, {nd.nunique()} days, {nd.min()} .. {nd.max()}")
    j = g.join(n[["close", "high", "low"]].add_prefix("nq_"), how="inner").dropna(subset=["nq_close"])
    print(f"  PAIRED:          {len(j):,} minutes, {j['day'].nunique()} days, "
          f"{j['day'].min()} .. {j['day'].max()}")
    R["paired"] = {"minutes": len(j), "days": int(j["day"].nunique()),
                   "span": [j["day"].min(), j["day"].max()]}

    # ── the relationship itself, before any trade ────────────────────────────────────────────
    print("\n" + "=" * 130)
    print("STEP 1 — WHAT IS THE RELATIONSHIP?  (contemporaneous, then lead-lag)")
    print("=" * 130)
    j = j.copy()
    j["g_r"] = j["close"].pct_change() * 10000            # gold return, bp
    j["n_r"] = j["nq_close"].pct_change() * 10000
    z = j.dropna(subset=["g_r", "n_r"])
    z = z[(z["g_r"].abs() < 100) & (z["n_r"].abs() < 100)]
    print(f"  contemporaneous corr(1-min returns): {z['g_r'].corr(z['n_r']):+.4f}   n={len(z):,}")
    for k in (5, 15, 60):
        gg = j["close"].pct_change(k) * 10000
        nn = j["nq_close"].pct_change(k) * 10000
        w = pd.concat([gg, nn], axis=1).dropna()
        w.columns = ["g", "n"]
        w = w[(w["g"].abs() < 500) & (w["n"].abs() < 500)]
        print(f"  corr over {k:>2}-min windows: {w['g'].corr(w['n']):+.4f}")
    print("\n  LEAD-LAG — does MNQ's last move predict GOLD's NEXT move?")
    print("  (a positive number means gold FOLLOWS the Nasdaq; negative = gold is the hedge)")
    rows = []
    for back in (5, 15, 30, 60):
        for fwd in (5, 15, 30, 60):
            nb = (j["nq_close"] / j["nq_close"].shift(back) - 1) * 10000
            gf = (j["close"].shift(-fwd) / j["close"] - 1) * 10000
            w = pd.concat([nb, gf], axis=1).dropna(); w.columns = ["nb", "gf"]
            w = w[(w["nb"].abs() < 500) & (w["gf"].abs() < 500)]
            w = w[w.index.minute % 15 == 0]
            rows.append({"MNQ back": back, "MGC fwd": fwd, "n": len(w),
                         "corr": round(float(w["nb"].corr(w["gf"])), 4)})
    t = pd.DataFrame(rows)
    print(t.pivot(index="MNQ back", columns="MGC fwd", values="corr").to_string())
    R["leadlag"] = rows

    # ── the conditional bias map ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 130)
    print("STEP 2 — THE CONDITIONAL MAP. split gold's next hour by what the NASDAQ just did")
    print("=" * 130)
    w = j.copy()
    w["nq_60"] = (w["nq_close"] / w["nq_close"].shift(60) - 1) * 10000
    w["g_fwd60"] = (w["close"].shift(-60) / w["close"] - 1) * 10000
    w["g_rng60"] = ((w["high"].shift(-60).rolling(60).max() - w["low"].shift(-60).rolling(60).min())
                    / w["close"] * 10000)
    s = w.dropna(subset=["nq_60", "g_fwd60"])
    s = s[s.index.minute % 15 == 0]
    s = s[(s["nq_60"].abs() < 500)]
    s["bucket"] = pd.qcut(s["nq_60"], 5, labels=["NQ -- (worst)", "NQ -", "NQ flat", "NQ +", "NQ ++ (best)"])
    gb = s.groupby("bucket", observed=True).agg(
        n=("g_fwd60", "size"), nq_move_bp=("nq_60", "median"),
        gold_next_hr_bp=("g_fwd60", "median"), gold_mean_bp=("g_fwd60", "mean"),
        gold_up_pct=("g_fwd60", lambda x: 100 * (x > 0).mean()),
        gold_range_bp=("g_rng60", "median"))
    print(gb.round(2).to_string())
    print("\n  ★ READ THE `gold_up_pct` COLUMN. 50% is a coin. A monotone gradient across the five")
    print("    buckets would be a real conditional bias; a flat line is the honest null.")
    R["map_nq60"] = gb.round(3).reset_index().astype(str).to_dict("records")

    # the same, US session only (where the correlation should be strongest)
    su = s[s["session"] == "US"]
    if len(su) > 200:
        gu = su.groupby("bucket", observed=True).agg(
            n=("g_fwd60", "size"), gold_next_hr_bp=("g_fwd60", "median"),
            gold_up_pct=("g_fwd60", lambda x: 100 * (x > 0).mean()))
        print("\n  US SESSION ONLY (13:30-21:00Z), where the two instruments actually overlap:")
        print(gu.round(2).to_string())
        R["map_us"] = gu.round(3).reset_index().astype(str).to_dict("records")

    # ── the divergence idea, which is the one with a mechanism ───────────────────────────────
    print("\n" + "=" * 130)
    print("STEP 3 — THE DIVERGENCE GATE. gold is a HAVEN: does a Nasdaq break WITHOUT a gold move")
    print("         predict gold catching up?")
    print("=" * 130)
    w2 = j.copy()
    w2["nq_z"] = ((w2["nq_close"] / w2["nq_close"].shift(30) - 1) * 10000)
    w2["g_z"] = ((w2["close"] / w2["close"].shift(30) - 1) * 10000)
    w2["nq_sd"] = w2["nq_z"].rolling(600).std()
    w2["g_sd"] = w2["g_z"].rolling(600).std()
    w2["nq_n"] = w2["nq_z"] / w2["nq_sd"]
    w2["g_n"] = w2["g_z"] / w2["g_sd"]
    racer = BarRacer(g)
    pos = {t: i for i, t in enumerate(g.index)}
    rows = []
    for thr in (1.5, 2.0, 2.5):
        ents = []
        last = {}
        for ts, r in w2.dropna(subset=["nq_n", "g_n", "atr"]).iterrows():
            if not (abs(r["nq_n"]) >= thr and abs(r["g_n"]) < 0.5):
                continue
            side = -int(np.sign(r["nq_n"]))          # NQ down hard, gold flat -> BUY gold
            if side in last and (ts - last[side]).total_seconds() < 60 * 60:
                continue
            last[side] = ts
            i = pos.get(ts)
            if i is None or i >= len(g) - 500 or not np.isfinite(r["atr"]) or r["atr"] <= 0:
                continue
            ents.append({"i": i, "ts": ts, "side": side, "atr": float(r["atr"]),
                         "regime": r["regime"], "session": r["session"], "day": r["day"]})
        e = pd.DataFrame(ents)
        if e.empty:
            continue
        for nm, sgn in (("HAVEN (buy gold when NQ breaks DOWN)", 1),
                        ("the MIRROR (follow NQ's direction)", -1)):
            ee = e.copy(); ee["side"] = ee["side"] * sgn
            for exlbl, kw in (("chand sl3/a2/t2", dict(stop=3.0, arm=2.0, trail=2.0, cap_min=480)),
                              ("chand sl5/a3/t3", dict(stop=5.0, arm=3.0, trail=3.0, cap_min=480))):
                rr = run(racer, ee, **kw)
                st = stat(rr)
                rows.append({"thr": thr, "rule": nm, "exit": exlbl, **st})
                print(line(f"  |NQ|>={thr}sd & |gold|<0.5sd · {nm[:34]} · {exlbl}", st))
    R["divergence"] = rows

    # ── does the cross-asset state IMPROVE the break trigger? (the filter question) ──────────
    print("\n" + "=" * 130)
    print("STEP 4 — AS A FILTER, not a gate: does 'what was the Nasdaq doing' improve the break?")
    print("         placebo-controlled against dropping the SAME NUMBER of firings at random.")
    print("=" * 130)
    from gf2_mgc_histlab import breaks
    ef = breaks(g, fade=True)
    ef = ef[ef["ts"].isin(j.index)].reset_index(drop=True)
    nq60 = (j["nq_close"] / j["nq_close"].shift(60) - 1) * 10000
    ef["nq60"] = ef["ts"].map(nq60)
    ef = ef.dropna(subset=["nq60"])
    rf = run(racer, ef, stop=3.0, arm=2.0, trail=2.0, cap_min=480)
    print(line("  all breaks faded (paired days only)", stat(rf)))
    rng = np.random.default_rng(20260821)
    for lbl, mask in (("NQ aligned with the fade (haven story)", (np.sign(rf["nq60"]) == -np.sign(rf["side"]))),
                      ("NQ against the fade", (np.sign(rf["nq60"]) == np.sign(rf["side"]))),
                      ("NQ quiet (|60m move| < 10bp)", rf["nq60"].abs() < 10),
                      ("NQ moving (|60m move| > 30bp)", rf["nq60"].abs() > 30)):
        sub = rf[mask.fillna(False)]
        if len(sub) < 30:
            continue
        real = float(sub["true_pnl"].sum()); k = len(sub)
        draws = [float(rf["true_pnl"].iloc[rng.choice(len(rf), size=k, replace=False)].sum())
                 for _ in range(200)]
        beaten = sum(1 for x in draws if x >= real)
        print(f"    {lbl:<42} n={k:>4} ${real:>8,.0f} ({real/k:+6.2f}/tr)  "
              f"random-keep mean ${np.mean(draws):>8,.0f}  beaten {beaten}/200")
        R.setdefault("filter", {})[lbl] = {"n": k, "real": round(real, 0),
                                           "rand_mean": round(float(np.mean(draws)), 0),
                                           "beaten": beaten}
    json.dump(R, open(f"{OUT}/cross.json", "w"), indent=1, default=str)
    print(f"\nJSON -> {OUT}/cross.json")


if __name__ == "__main__":
    main()
