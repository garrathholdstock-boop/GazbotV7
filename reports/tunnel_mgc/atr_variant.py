"""WHERE DOES 1.75x COME FROM? Same breaks, three ways of normalising the excursion.

The live tunnel_watch message tells the operator "expect ~1.75x normal 60m excursion". Under a
matched-hour control with ATR taken AT the break, this pipeline gets 0.99x for MNQ. Before saying
the live number is wrong, find out what definition produces it.
"""
import sys, math, json, random, datetime, collections; sys.path.insert(0,'scripts')
import numpy as np
from tunnel_fit_mgc import (front_month_minutes, true_range, observations, normalised,
                            filter_quiet, tunnels_and_breaks, race, _atr14, session_key)
SYM = sys.argv[1]
VPP = 10.0 if SYM == "MGC" else 2.0
random.seed(7)
F = json.load(open(f'reports/tunnel_mgc/fit_norm_train_{SYM}.json'))
mu, sd, A = F["mu"], F["sd"], F["A"]
b, rolls = front_month_minutes(verbose=False, symbol=SYM)
trs = true_range(b, rolls)
z = normalised(observations(trs))
sess = sorted({session_key(v["m"]) for v in b}); n = len(sess)
test = sorted(sess[2*n//3:])
by = collections.defaultdict(list)
for i, v in enumerate(b): by[session_key(v["m"])].append(i)
HOR = 60
rows_b, rows_c = [], []
for s in test:
    idx = by[s]; zz = z[idx]
    if np.isnan(zz).all(): continue
    post = filter_quiet(zz, mu, sd, A)
    bb = [b[i] for i in idx]; tt = [trs[i] for i in idx]
    tun, brks = tunnels_and_breaks(bb, tt, post)
    for k in brks:
        i = k["i"]
        if i + HOR >= len(bb) or k["side"] == "BOTH": continue
        d = 1 if k["side"] == "UP" else -1
        atr_at = k["atr"]                      # includes the break bar — what the alert prints
        atr_pre = _atr14(tt, i - 1)            # the tunnel's own ATR, before the break bar
        r = race(bb, i, atr_at, horizon=HOR, direction=d)
        if r is None or not atr_pre or atr_pre != atr_pre: continue
        rows_b.append({"hr": datetime.datetime.fromtimestamp(bb[i]["m"], datetime.UTC).hour,
                       "mfe_pt": r["mfe"] * atr_at, "mae_pt": r["mae"] * atr_at,
                       "atr_at": atr_at, "atr_pre": atr_pre})
    hours = collections.Counter(r["hr"] for r in rows_b[-len(brks):]) if brks else {}
    for hr, cnt in hours.items():
        cands = [j for j in range(20, len(bb) - HOR - 1)
                 if datetime.datetime.fromtimestamp(bb[j]["m"], datetime.UTC).hour == hr]
        random.shuffle(cands)
        for j in cands[:cnt * 6]:
            atr = _atr14(tt, j)
            if not atr or atr != atr: continue
            for d in (1, -1):
                r = race(bb, j, atr, horizon=HOR, direction=d)
                if r is None: continue
                rows_c.append({"hr": hr, "mfe_pt": r["mfe"] * atr, "mae_pt": r["mae"] * atr, "atr_at": atr})
mb = np.mean([r["mfe_pt"] for r in rows_b]); mc = np.mean([r["mfe_pt"] for r in rows_c])
print(f"\n=== {SYM} · n_break={len(rows_b)} n_ctl={len(rows_c)} ===")
print(f"  A) POINTS                       break {mb:7.2f} vs control {mc:7.2f}  = {mb/mc:.2f}x")
a1 = np.mean([r["mfe_pt"]/r["atr_at"] for r in rows_b]); c1 = np.mean([r["mfe_pt"]/r["atr_at"] for r in rows_c])
print(f"  B) ATR measured AT the break    break {a1:7.2f} vs control {c1:7.2f}  = {a1/c1:.2f}x")
a2 = np.mean([r["mfe_pt"]/r["atr_pre"] for r in rows_b])
print(f"  C) ATR measured BEFORE it       break {a2:7.2f} vs control {c1:7.2f}  = {a2/c1:.2f}x   <- mixes two ATRs")
print(f"     ATR inflation across the break bar: median {np.median([r['atr_at']/r['atr_pre'] for r in rows_b]):.2f}x")
# D) no hour matching at all — control = every minute, unconditioned
print(f"  hours covered by breaks: {sorted(set(r['hr'] for r in rows_b))}")
