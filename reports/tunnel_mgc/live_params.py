"""The decisive test: score MNQ with the LIVE watcher's OWN parameters and definition.

If 1.75x is real it should appear here — same model, same knobs, same tape family. Everything
else about the pipeline (matched-hour control, race from t+1, one break per tunnel) is held.
"""
import sys, math, json, random, datetime, collections; sys.path.insert(0,'scripts')
import numpy as np
import tunnel_watch as TW
from tunnel_fit_mgc import (front_month_minutes, true_range, tunnels_and_breaks, race,
                            _atr14, session_key)
random.seed(13)
b, rolls = front_month_minutes(verbose=False, symbol="MNQ")
trs = true_range(b, rolls)
sess = sorted({session_key(v["m"]) for v in b})
by = collections.defaultdict(list)
for i, v in enumerate(b): by[session_key(v["m"])].append(i)
HOR = 60
brk, ctl = [], []
n_tun = 0
for s in sess:                                  # ALL sessions: the live params were fitted on all
    idx = by[s]
    bb = [b[i] for i in idx]; tt = [trs[i] for i in idx]
    tr_ok = [t if t is not None else 1e-6 for t in tt]
    post = TW.filter_states(tr_ok)              # the LIVE forward filter, LIVE MU/SD/A
    tun, brks = tunnels_and_breaks(bb, tt, post, min_tunnel=TW.MIN_TUNNEL_MIN)
    n_tun += sum(1 for t in tun if t["n"] >= TW.MIN_TUNNEL_MIN)
    hrs = collections.Counter()
    for k in brks:
        i = k["i"]
        if i + HOR >= len(bb) or k["side"] == "BOTH": continue
        d = 1 if k["side"] == "UP" else -1
        r = race(bb, i, k["atr"], horizon=HOR, direction=d)
        if r is None: continue
        brk.append((r["mfe"], r["mfe"] * k["atr"], r["passage"]))
        hrs[datetime.datetime.fromtimestamp(bb[i]["m"], datetime.UTC).hour] += 1
    for hr, cnt in hrs.items():
        pool = [j for j in range(20, len(bb) - HOR - 1)
                if datetime.datetime.fromtimestamp(bb[j]["m"], datetime.UTC).hour == hr]
        random.shuffle(pool)
        got = 0
        for j in pool:
            if got >= cnt * 6: break
            atr = _atr14(tt, j)
            if not atr or atr != atr or atr < 0.25: continue   # a sub-tick ATR is a dead-tape artefact, not volatility
            for d in (1, -1):
                r = race(bb, j, atr, horizon=HOR, direction=d)
                if r is None: continue
                ctl.append((r["mfe"], r["mfe"] * atr, r["passage"]))
            got += 1
ba, bp = np.mean([v[0] for v in brk]), np.mean([v[1] for v in brk])
ca, cp = np.mean([v[0] for v in ctl]), np.mean([v[1] for v in ctl])
print(f"LIVE tunnel_watch params · MNQ · all {len(sess)} sessions")
print(f"  armed tunnels {n_tun:,} = {n_tun/len(sess):.1f}/session · breaks {len(brk):,} = {len(brk)/len(sess):.1f}/session")
print(f"  60m MFE break {ba:.2f} ATR / {bp:.1f} pt   control {ca:.2f} ATR / {cp:.1f} pt")
print(f"  ratio {ba/ca:.2f}x in ATR · {bp/cp:.2f}x in POINTS      <- the message claims 1.75x")
for m in (1.0, 1.5, 2.0):
    rb = [v[2][m] for v in brk if v[2][m] != 0]; rc = [v[2][m] for v in ctl if v[2][m] != 0]
    pb = sum(1 for x in rb if x > 0)/len(rb); pc = sum(1 for x in rc if x > 0)/len(rc)
    print(f"  +/-{m} ATR continuation: break {pb:.3f} (n={len(rb):,}) vs control {pc:.3f} "
          f"— message claims {({1.0:0.436,1.5:0.466,2.0:0.477})[m]:.3f} vs {({1.0:0.504,1.5:0.506,2.0:0.510})[m]:.3f}")
