"""Shared constants + the SIGNED book/tape features. One home for the cost model."""
import glob, os
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/sections/cs2"

# ⚠⚠ COST MODEL — the two constants the desk keeps getting reversed. MNQ.
VPP  = 2.00      # $ per POINT, MNQ  (MGC is 10.00 — do not cross them)
FEE  = 1.50      # $ per ROUND TRIP  (not $5, not $2, not per side)
TICK = 0.25
SLIP_STOP_PT = 0.25   # stop-market fills one tick beyond the trigger

IS_DAYS  = ["2026-07-31", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07",
            "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"]
OOS_DAYS = ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24"]
WEEK     = ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]


def load_events():
    con = duckdb.connect()
    files = sorted(glob.glob(f"{OUT}/ev/*.parquet"))
    d = con.execute(f"SELECT * FROM read_parquet({files!r})").df()
    # regime: atr_rel comes from the global 1-min frame (trailing 1-session median), er30 is local
    b = pd.read_csv(f"{OUT}/bars_1m.csv", usecols=["ts", "atr_rel", "regime"])
    d["m"] = (d.dts // 60) * 60 - 60          # the last COMPLETED minute, same lag as the features
    d = d.merge(b.rename(columns={"ts": "m"}), on="m", how="left")
    return sign_feats(d)


def sign_feats(d):
    """Orient every book/tape term to the FADE. A SHORT fires at a high: the aggressors are BUYERS
    lifting the ASK, so the ASK is the wall that must hold and the BID is the support that must
    fail. A LONG at a low is the mirror. Every `f_*` column is 'higher = more bullish for the fade'."""
    sh = (d.side == "SHORT").values
    wall_1 = np.where(sh, d.d_a1, d.d_b1)          # resting size on the side being HIT
    supp_1 = np.where(sh, d.d_b1, d.d_a1)
    wall_5 = np.where(sh, d.d_a5, d.d_b5)
    supp_5 = np.where(sh, d.d_b5, d.d_a5)
    wall_10 = np.where(sh, d.d_a10, d.d_b10)
    supp_10 = np.where(sh, d.d_b10, d.d_a10)
    d["f_wall1"] = wall_1 / np.maximum(supp_1, 1e-9)
    d["f_wall5"] = wall_5 / np.maximum(supp_5, 1e-9)
    d["f_wall10"] = wall_10 / np.maximum(supp_10, 1e-9)
    d["f_imb"] = np.where(sh, d.d_imb, -d.d_imb)
    # 20s trend in the resting book: wall BUILDING and support DEPLETING are both pro-fade
    d["f_wall_build"] = np.where(sh, d.d_a1_d20, d.d_b1_d20)
    d["f_supp_drain"] = -np.where(sh, d.d_b1_d20, d.d_a1_d20)
    d["f_wall5_build"] = np.where(sh, d.d_a5_d20, d.d_b5_d20)
    d["f_supp5_drain"] = -np.where(sh, d.d_b5_d20, d.d_a5_d20)
    # 41ms L1 event stream
    d["f_refill"] = np.where(sh, d.l1_a_refill, d.l1_b_refill)
    d["f_pull"] = np.where(sh, d.l1_b_pull, d.l1_a_pull)
    d["f_refill_net"] = d.f_refill - np.where(sh, d.l1_b_refill, d.l1_a_refill)
    d["f_l1ratio"] = np.where(sh, d.l1_a_mean, d.l1_b_mean) / np.maximum(
        np.where(sh, d.l1_b_mean, d.l1_a_mean), 1e-9)
    # footprint: aggression INTO the fade, and the STALL (price refused to follow)
    for W in (20, 60):
        agg = np.where(sh, d[f"net{W}"], -d[f"net{W}"])
        mv = np.where(sh, d[f"mv{W}"], -d[f"mv{W}"])
        d[f"f_agg{W}"] = agg
        d[f"f_mv{W}"] = mv
        d[f"f_stall{W}"] = agg / np.maximum(np.abs(mv), 0.25)     # exhaustion_short's own ratio
        d[f"f_aggfrac{W}"] = agg / np.maximum(d[f"vol{W}"], 1e-9)
    # price geometry
    d["f_ext_atr"] = np.where(sh, (d.close - d.vwap), (d.vwap - d.close)) / d.atr14
    d["f_vwap_slope"] = np.where(sh, -d.vwap_slope15, d.vwap_slope15) / d.atr14   # fade a FLAT/adverse vwap
    d["f_vwap_flat"] = d.vwap_slope15.abs() / d.atr14
    rng60 = (d.hi60 - d.lo60).replace(0, np.nan)
    d["f_rangepos"] = np.where(sh, (d.close - d.lo60) / rng60, (d.hi60 - d.close) / rng60)
    # ⚠ TWO extreme definitions, kept SEPARATE on purpose. f_extH = the WICK touched the trailing
    # L-minute extreme; f_extC = the bar CLOSED at it, which is far stricter (the close must be the
    # highest high of L minutes). An earlier pass used close at L=30 and wick at L=15/20 and read the
    # difference as "a step at L=30" — that step was the DEFINITION, not the lookback.
    for L in (10, 15, 20, 30):
        d[f"f_extH{L}"] = np.where(sh, d.high >= d[f"hi{L}"] - 1e-9,
                                       d.low <= d[f"lo{L}"] + 1e-9).astype(float)
        d[f"f_extC{L}"] = np.where(sh, d.close >= d[f"hi{L}"] - 1e-9,
                                       d.close <= d[f"lo{L}"] + 1e-9).astype(float)
    d["f_ext30"], d["f_ext20"], d["f_ext15"] = d.f_extC30, d.f_extH20, d.f_extH15
    d["hh"] = pd.to_datetime(d.dts, unit="s", utc=True).dt.hour
    d["sess"] = np.where((d.hh >= 13) & (d.hh < 20), "US", np.where((d.hh >= 7) & (d.hh < 13), "EU", "ASIA"))
    return d


def net_usd(res_pt, kind, tp, sp):
    """$ per 1 lot, net. Target = limit (no extra slip). Stop = market, one tick beyond."""
    pts = np.where(kind == "STOP", -(sp + SLIP_STOP_PT), res_pt)
    return pts * VPP - FEE
