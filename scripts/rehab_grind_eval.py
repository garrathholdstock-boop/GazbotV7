#!/usr/bin/env python3
"""Rehab evaluation — loads recs pkl, reprices all exit policies, per-regime + robustness."""
from __future__ import annotations
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from rehab_grind_exit_scaleout import (ex_lock, ex_two_ratchet, ex_scalp, net_usd,
                                       PRIMARY, RATCHET2)

PKL = "/tmp/claude-0/-root/0bb3b1b0-e3be-4607-baa9-5ed673420d95/scratchpad/grind_recs.pkl"
RA_GRID = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]

def load():
    with open(PKL, "rb") as f:
        return pickle.load(f)

def enrich(recs):
    for r in recs:
        fav, atr = r["fav"], r["atr"]
        r["chand"] = ex_lock(fav, atr, **PRIMARY)
        r["tr"] = ex_two_ratchet(fav, atr, **PRIMARY, **RATCHET2)
        r["scalp"] = {ra: ex_scalp(fav, atr, ra) for ra in RA_GRID}
    return recs

def stat(vals):
    n = len(vals); net = sum(vals); w = 100*sum(1 for v in vals if v > 0)/n if n else 0
    return n, net, w

# ── policy P&L per rec (2-lot policies unless noted) ──
def p_base2(r):      return 2*net_usd(r["chand"])
def p_scale(r, ra):  return net_usd(r["scalp"][ra]) + net_usd(r["chand"])
def p_scale_tr(r, ra): return net_usd(r["scalp"][ra]) + net_usd(r["tr"])
def p_chand1(r):     return net_usd(r["chand"])
def p_tr1(r):        return net_usd(r["tr"])
def p_dblchand_tr(r): return net_usd(r["chand"]) + net_usd(r["tr"])  # LotA chand + LotB two-ratchet

def report_policy(recs, fn, label):
    vals = [fn(r) for r in recs]
    n, net, w = stat(vals)
    srt = sorted(vals)
    strip = {k: round(sum(srt[:len(srt)-k]),0) for k in [0,1,2,3]}
    print(f"  {label:34} n={n:3} net={net:+8.1f} w={w:4.0f}%  strip-best {strip}")
    return net, vals

def per_regime(recs, fn, label):
    print(f"\n-- {label} by REGIME --")
    byr = collections.defaultdict(list)
    for r in recs: byr[r["regime"]].append(fn(r))
    for rg in sorted(byr):
        n, net, w = stat(byr[rg])
        print(f"   {rg:22} n={n:3} net={net:+8.1f} $/tr={net/n:+7.1f} w={w:4.0f}%")

def per_time(recs, fn, label):
    us = [fn(r) for r in recs if r["us"]]; ov = [fn(r) for r in recs if not r["us"]]
    print(f"-- {label} by TIME: US-session {stat(us)}  overnight {stat(ov)}")

def main():
    recs = enrich(load())
    print("="*100)
    print("STEP 3+4: EXIT-POLICY comparison (tick-honest, $1.50/RT/lot, $2/pt) — whole tape then split")
    print("="*100)
    print("\n[A] Reference: 2-lot policies (scale-out decision — both use 2 lots)")
    report_policy(recs, p_base2, "BASE2 (2x pure-6.0 chand)")
    for ra in RA_GRID:
        report_policy(recs, lambda r, ra=ra: p_scale(r, ra), f"SCALE Lot-A@{ra}R + Lot-B chand")
    print("\n[A2] scale-out with two-ratchet on Lot B")
    for ra in [1.5, 2.0, 2.5]:
        report_policy(recs, lambda r, ra=ra: p_scale_tr(r, ra), f"SCALE-TR Lot-A@{ra}R + Lot-B 2ratchet")

    print("\n[B] 1-lot policies (ratchet decision on the chandelier lot)")
    report_policy(recs, p_chand1, "CHAND1 (pure-6.0, 1 lot)")
    report_policy(recs, p_tr1, "TR1 (two-ratchet, 1 lot)")
    report_policy(recs, p_dblchand_tr, "LotA chand + LotB 2ratchet (2lot)")

    print("\n" + "="*100)
    print("STEP: PER-REGIME (evaluate each policy on home segments)")
    print("="*100)
    # census
    byr = collections.Counter(r["regime"] for r in recs)
    print("regime n:", dict(byr))
    per_regime(recs, p_base2, "BASE2")
    per_regime(recs, lambda r: p_scale(r, 2.0), "SCALE@2.0R")
    per_regime(recs, lambda r: p_scale(r, 1.5), "SCALE@1.5R")
    per_regime(recs, p_chand1, "CHAND1")
    per_regime(recs, p_tr1, "TR1")

    print("\n" + "="*100)
    print("STEP 4: Lot-A scalp-R SWEEP per regime (find plateau; guess=2.0R)")
    print("="*100)
    regimes = sorted(set(r["regime"] for r in recs))
    for rg in regimes:
        sub = [r for r in recs if r["regime"] == rg]
        print(f"\n regime={rg} (n={len(sub)}):")
        base = sum(p_base2(r) for r in sub)
        print(f"   BASE2 (no scalp)      net={base:+8.1f}")
        for ra in RA_GRID:
            net = sum(p_scale(r, ra) for r in sub)
            print(f"   SCALE Lot-A@{ra}R       net={net:+8.1f}  (delta vs base2 {net-base:+7.1f})")

    print("\n Whole-tape scalp-R plateau (2-lot SCALE net vs R_A):")
    for ra in RA_GRID:
        print(f"   R_A={ra}: {sum(p_scale(r,ra) for r in recs):+8.1f}")

    print("\n" + "="*100)
    print("STEP 5: ROBUSTNESS — leave-one-day-out + per-ISO-week (SCALE@best vs BASE2 vs CHAND2)")
    print("="*100)
    days = sorted(set(r["day"] for r in recs))
    def tot(fn, sub): return sum(fn(r) for r in sub)
    print("\nPer-day net (n | BASE2 | SCALE@2.0 | SCALE@1.5 | CHAND1 | TR1):")
    for d in days:
        sub = [r for r in recs if r["day"] == d]
        print(f"  {d} n={len(sub):2}  base2={tot(p_base2,sub):+8.1f}  "
              f"sc2.0={tot(lambda r:p_scale(r,2.0),sub):+8.1f}  sc1.5={tot(lambda r:p_scale(r,1.5),sub):+8.1f}  "
              f"chand1={tot(p_chand1,sub):+8.1f}  tr1={tot(p_tr1,sub):+8.1f}")
    print("\nLeave-one-day-out (SCALE@2.0 − BASE2), should stay >0 if robust:")
    for d in days:
        sub = [r for r in recs if r["day"] != d]
        diff = tot(lambda r:p_scale(r,2.0),sub) - tot(p_base2,sub)
        print(f"  drop {d}: SCALE2.0−BASE2 = {diff:+8.1f}")
    print("\nPer-ISO-week:")
    for wk in sorted(set(r["wk"] for r in recs)):
        sub = [r for r in recs if r["wk"] == wk]
        print(f"  wk{wk} n={len(sub):2}  base2={tot(p_base2,sub):+8.1f}  sc2.0={tot(lambda r:p_scale(r,2.0),sub):+8.1f}  "
              f"chand1={tot(p_chand1,sub):+8.1f}  tr1={tot(p_tr1,sub):+8.1f}")

    print("\n" + "="*100)
    print("FAKE-WIN CHECK: does scalp cut the LOSERS or just cap the WINNERS?")
    print("="*100)
    runners = [r for r in recs if r["rm_r"] >= 3.0]
    losers = [r for r in recs if r["rm_r"] < 1.0]
    mids = [r for r in recs if 1.0 <= r["rm_r"] < 3.0]
    for name, grp in [("RUNNERS rMFE>=3R", runners), ("MID 1-3R", mids), ("DUDS <1R", losers)]:
        if not grp: continue
        b = tot(p_base2, grp); s2 = tot(lambda r:p_scale(r,2.0), grp)
        print(f"  {name:20} n={len(grp):2}  BASE2={b:+8.1f}  SCALE@2.0={s2:+8.1f}  delta={s2-b:+7.1f}")

if __name__ == "__main__":
    main()
