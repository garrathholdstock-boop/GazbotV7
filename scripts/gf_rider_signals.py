#!/usr/bin/env python3
"""GF RIDER — the signal set. ONE direction-agnostic run-catcher, fired on the WHOLE tape.

    BOARD(w, k):  at the CLOSE of minute t, if the last w minutes have covered at least k x ATR
                  net, in one direction, take that direction at the OPEN of minute t+1.

That is it. No cluster labels, no prediction of a run's start, no news calendar. It boards a move
that has already proven itself and asks to be paid for what is left.

Carries, on every fire, ONLY information available BEFORE the fill — so any filter built from these
columns in step 3 is causal by construction and cannot be accused of reading its own outcome.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CTX = ["day", "hh", "dow", "regime", "atr", "atr_pr", "rvol", "er5", "er10", "er15", "er30",
       "flow5", "flow15", "has_flow", "v", "vol30"]


def signals(m1: pd.DataFrame, w: int = 10, k: float = 1.5) -> pd.DataFrame:
    """Every BOARD(w,k) fire on the tape, with its causal context attached."""
    net = m1[f"net{w}"]
    fire = (net.abs() >= k * m1["atr"]) & m1["atr"].notna() & net.notna()
    # the fill bar is the NEXT one; require it to be contiguous (same session block)
    nxt = m1.shift(-1)
    ok = fire & (nxt["blk"] == m1["blk"])
    s = m1[ok].copy()
    n = m1.shift(-1)[ok]
    out = pd.DataFrame({
        "ts": n["ts"].to_numpy(np.int64),
        "sig_ts": s["ts"].to_numpy(np.int64),
        "side": np.sign(net[ok]).to_numpy(np.int64),
        "entry": n["o"].to_numpy(np.float64),
    })
    for c in CTX:
        out[c] = s[c].to_numpy()
    out["prove_pt"] = net[ok].abs().to_numpy()          # how far it had already come
    out["prove_r"] = out["prove_pt"] / out["atr"]
    # distance from the w-minute extreme it is chasing — an EXTENSION measure, causal
    ext_hi = s[f"hh{w}"].to_numpy(np.float64)
    ext_lo = s[f"ll{w}"].to_numpy(np.float64)
    close = s["c"].to_numpy(np.float64)
    out["ext_r"] = np.where(out["side"] > 0, (close - ext_lo), (ext_hi - close)) / out["atr"]
    out["pull_r"] = np.where(out["side"] > 0, (ext_hi - close), (close - ext_lo)) / out["atr"]
    # is the fire aligned with the aggressor flow behind it? (only meaningful on flow days)
    out["flow_align"] = np.where(out["has_flow"], np.sign(out["flow15"]) == out["side"], np.nan)
    # session bucket — overnight/pre-open vs the US session, per the backtest-discipline rule
    out["tod"] = np.where((out["hh"] >= 13.5) & (out["hh"] < 20.0), "US-session", "overnight")
    out["tod"] = np.where((out["hh"] >= 13.0) & (out["hh"] < 13.5), "US-open", out["tod"])
    return out.reset_index(drop=True)
