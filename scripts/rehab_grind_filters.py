#!/usr/bin/env python3
"""Filter analysis (entry regime-gate), two-ratchet safety valve, malfunction normalization."""
from __future__ import annotations
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from rehab_grind_exit_scaleout import ex_lock, ex_two_ratchet, ex_scalp, net_usd, PRIMARY, RATCHET2
PKL = "/tmp/claude-0/-root/0bb3b1b0-e3be-4607-baa9-5ed673420d95/scratchpad/grind_recs.pkl"

def load():
    with open(PKL, "rb") as f: return pickle.load(f)

def enrich(recs):
    for r in recs:
        fav, atr = r["fav"], r["atr"]
        r["chand"] = ex_lock(fav, atr, **PRIMARY)
        r["tr"] = ex_two_ratchet(fav, atr, **PRIMARY, **RATCHET2)
        r["scalp2"] = ex_scalp(fav, atr, 2.0)
    return recs

def stat(vals):
    n=len(vals); net=sum(vals); w=100*sum(1 for v in vals if v>0)/n if n else 0
    return f"n={n:3} net={net:+8.1f} $/tr={net/n:+7.1f} w={w:4.0f}%" if n else "n=0"

def main():
    recs = enrich(load())
    def base2(r): return 2*net_usd(r["chand"])
    def tr1(r): return net_usd(r["tr"])
    def chand1(r): return net_usd(r["chand"])
    def scale2(r): return net_usd(r["scalp2"]) + net_usd(r["chand"])
    def scale2_tr(r): return net_usd(r["scalp2"]) + net_usd(r["tr"])

    print("="*100)
    print("RUNNER LOCATION — where do the rMFE>=3R runners live? (fake-filter guard)")
    print("="*100)
    runners = [r for r in recs if r["rm_r"]>=3.0]
    print(f"total runners rMFE>=3R: {len(runners)} of {len(recs)}")
    print("by regime:", dict(collections.Counter(r["regime"] for r in runners)))
    print("by ER>=0.3:", sum(1 for r in runners if (r['er'] or 0)>=0.3), "of", len(runners))
    print("runner details (ts, regime, er, atr, rm_r):")
    for r in sorted(runners,key=lambda x:-x["rm_r"]):
        print(f"   {r['ts'][:16]} {r['regime']:20} er={r['er']:.2f} atr={r['atr']:.1f} rm={r['rm_r']:.1f}R  chand={net_usd(r['chand']):+.0f} tr={net_usd(r['tr']):+.0f}")

    print("\n" + "="*100)
    print("TWO-RATCHET SAFETY VALVE — on big runners does TR clip vs CHAND? (disarm_r=4.5)")
    print("="*100)
    print("  rm_r>=4R runners: TR should ~match CHAND (disarm lets it ride the wide trail)")
    for r in sorted([r for r in recs if r['rm_r']>=4.0],key=lambda x:-x['rm_r']):
        d = net_usd(r['tr'])-net_usd(r['chand'])
        flag = "CLIP!" if d<-20 else ("gain" if d>20 else "~same")
        print(f"   {r['ts'][:16]} rm={r['rm_r']:.1f}R chand={net_usd(r['chand']):+.0f} tr={net_usd(r['tr']):+.0f} d={d:+.0f} {flag}")

    print("\n" + "="*100)
    print("ENTRY FILTER SWEEP — the REAL lever: regime-gate the SIGNAL (not the exit)")
    print("  Test: keep winners? A filter that drops runners is a FAKE win.")
    print("="*100)
    for name, pred in [
        ("NO FILTER (all)", lambda r: True),
        ("ER>=0.2", lambda r: (r['er'] or 0)>=0.2),
        ("ER>=0.3 (building+)", lambda r: (r['er'] or 0)>=0.3),
        ("ER>=0.4", lambda r: (r['er'] or 0)>=0.4),
        ("ATR<=28 (drop violent)", lambda r: r['atr']<=28),
        ("ATR 20-32 band", lambda r: 20<=r['atr']<=32),
        ("ER>=0.3 & ATR<=32", lambda r: (r['er'] or 0)>=0.3 and r['atr']<=32),
        ("ER>=0.25 & ATR<=30", lambda r: (r['er'] or 0)>=0.25 and r['atr']<=30),
    ]:
        sub=[r for r in recs if pred(r)]
        kept_runners=sum(1 for r in sub if r['rm_r']>=3.0)
        print(f"\n  [{name}]  kept {len(sub)}/{len(recs)} signals, {kept_runners}/{len(runners)} runners")
        print(f"      BASE2   {stat([base2(r) for r in sub])}")
        print(f"      CHAND1  {stat([chand1(r) for r in sub])}")
        print(f"      TR1     {stat([tr1(r) for r in sub])}")
        print(f"      SCALE2  {stat([scale2(r) for r in sub])}")
        print(f"      SCALE2+TR {stat([scale2_tr(r) for r in sub])}")

    print("\n" + "="*100)
    print("BEST POLICY under the regime-gate (ER>=0.3): per-day robustness")
    print("="*100)
    sub=[r for r in recs if (r['er'] or 0)>=0.3]
    for d in sorted(set(r['day'] for r in sub)):
        dd=[r for r in sub if r['day']==d]
        print(f"  {d} n={len(dd):2} tr1={sum(tr1(r) for r in dd):+8.1f} scale2_tr={sum(scale2_tr(r) for r in dd):+8.1f} base2={sum(base2(r) for r in dd):+8.1f}")

    print("\n" + "="*100)
    print("MALFUNCTION NORMALIZATION")
    print("="*100)
    for r in recs:
        for g,q,raw,reason in zip(r['gates'],r['live_qty'],r['live_raw_pnl'],r['live_reasons']):
            if abs(raw)>120:
                perlot = raw/q
                normstop = -r['atr']*net_usd.__defaults__[0] if False else -(r['atr']*2+1.5)
                print(f"  {r['ts'][:19]} {g} qty={q} raw={raw:+.1f} exit={reason}")
                print(f"     -> per-lot {perlot:+.1f}; base_size=1 -1R stop would be {-(r['atr']*2+1.5):+.1f} (atr={r['atr']:.1f})")
                print(f"     -> conviction-sizing x{q:.0f} amplified a normal -1R stop; NORMALIZED loss = {perlot:+.1f}")

if __name__=="__main__":
    main()
