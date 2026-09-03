"""Which CONTROL produces 1.75x? Same breaks, three different comparison sets."""
import sys, math, json, random, datetime, collections; sys.path.insert(0,'scripts')
import numpy as np
from tunnel_fit_mgc import (front_month_minutes, true_range, observations, normalised,
                            filter_quiet, tunnels_and_breaks, race, _atr14, session_key)
SYM = sys.argv[1]
random.seed(11)
F = json.load(open(f'reports/tunnel_mgc/fit_norm_train_{SYM}.json'))
mu, sd, A = F["mu"], F["sd"], F["A"]
b, rolls = front_month_minutes(verbose=False, symbol=SYM)
trs = true_range(b, rolls); z = normalised(observations(trs))
sess = sorted({session_key(v["m"]) for v in b}); n = len(sess)
test = sorted(sess[2*n//3:])
by = collections.defaultdict(list)
for i, v in enumerate(b): by[session_key(v["m"])].append(i)
HOR = 60
brk, ctl_any, ctl_quiet, ctl_active = [], [], [], []
for s in test:
    idx = by[s]; zz = z[idx]
    if np.isnan(zz).all(): continue
    post = filter_quiet(zz, mu, sd, A)
    bb = [b[i] for i in idx]; tt = [trs[i] for i in idx]
    _, brks = tunnels_and_breaks(bb, tt, post)
    hrs = collections.Counter()
    for k in brks:
        i = k["i"]
        if i + HOR >= len(bb) or k["side"] == "BOTH": continue
        d = 1 if k["side"] == "UP" else -1
        r = race(bb, i, k["atr"], horizon=HOR, direction=d)
        if r is None: continue
        brk.append((r["mfe"], r["mfe"]*k["atr"]))
        hrs[datetime.datetime.fromtimestamp(bb[i]["m"], datetime.UTC).hour] += 1
    for hr, cnt in hrs.items():
        pool = [j for j in range(20, len(bb) - HOR - 1)
                if datetime.datetime.fromtimestamp(bb[j]["m"], datetime.UTC).hour == hr]
        pools = {"any": pool,
                 "quiet": [j for j in pool if post[j] >= 0.5],
                 "active": [j for j in pool if post[j] < 0.5]}
        for name, P in pools.items():
            random.shuffle(P)
            got = 0
            for j in P:
                if got >= cnt * 6: break
                atr = _atr14(tt, j)
                if not atr or atr != atr: continue
                for d in (1, -1):
                    r = race(bb, j, atr, horizon=HOR, direction=d)
                    if r is None: continue
                    {"any": ctl_any, "quiet": ctl_quiet, "active": ctl_active}[name].append((r["mfe"], r["mfe"]*atr))
                got += 1
mb_a = np.mean([v[0] for v in brk]); mb_p = np.mean([v[1] for v in brk])
print(f"\n=== {SYM} · breaks n={len(brk)} · 60m MFE {mb_a:.2f} ATR / {mb_p:.1f} pt ===")
for name, arr in (("ANY minute, hour-matched", ctl_any),
                  ("QUIET minutes only (inside a tunnel)", ctl_quiet),
                  ("ACTIVE minutes only", ctl_active)):
    a = np.mean([v[0] for v in arr]); pp = np.mean([v[1] for v in arr])
    print(f"  control {name:38} {a:5.2f} ATR -> {mb_a/a:.2f}x | {pp:6.1f} pt -> {mb_p/pp:.2f}x   (n={len(arr):,})")
