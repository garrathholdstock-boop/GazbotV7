"""Is a gold break worth anything? Held-out third only, matched-hour control."""
import sys, math, json, random, datetime, collections; sys.path.insert(0,'scripts')
import numpy as np
from tunnel_fit_mgc import (front_month_minutes, true_range, observations, normalised,
                            filter_quiet, tunnels_and_breaks, race, _atr14, session_key, MGC_VPP)

SYM = sys.argv[1] if len(sys.argv) > 1 else "MGC"
VPP = 10.0 if SYM == "MGC" else 2.0
random.seed(7)
FIT = json.load(open(f'reports/tunnel_mgc/fit_norm_train_{SYM}.json'))
mu, sd, A = FIT["mu"], FIT["sd"], FIT["A"]

b, rolls = front_month_minutes(verbose=False, symbol=SYM)
trs = true_range(b, rolls)
z = normalised(observations(trs))
sess = sorted({session_key(v["m"]) for v in b}); n = len(sess)
test = sorted(sess[2*n//3:])
by_s = collections.defaultdict(list)
for i, v in enumerate(b):
    by_s[session_key(v["m"])].append(i)

HOR = 60
brk_rows, ctl_rows = [], []
for s in test:
    idx = by_s[s]
    zz = z[idx]
    if np.isnan(zz).all():
        continue
    post = filter_quiet(zz, mu, sd, A)
    bb = [b[i] for i in idx]
    tt = [trs[i] for i in idx]
    _, brks = tunnels_and_breaks(bb, tt, post)
    for k in brks:
        i = k["i"]
        if i + HOR >= len(bb) or k["side"] == "BOTH":
            continue
        d = 1 if k["side"] == "UP" else -1
        r = race(bb, i, k["atr"], horizon=HOR, direction=d)
        if r is None:
            continue
        hr = datetime.datetime.fromtimestamp(bb[i]["m"], datetime.UTC).hour
        brk_rows.append({"s": s, "hr": hr, "side": k["side"], "atr": k["atr"],
                         "tunnel_n": k["tunnel_n"], "width": k["width"],
                         "volx": None, **{f"p{m}": r["passage"][m] for m in (1.0, 1.5, 2.0)},
                         "mfe": r["mfe"], "mae": r["mae"]})
    # ── matched-hour control: same session set, same UTC hour, 6 draws per hour present
    hours = collections.Counter(r["hr"] for r in brk_rows if r["s"] == s)
    for hr, cnt in hours.items():
        cands = [j for j in range(20, len(bb) - HOR - 1)
                 if datetime.datetime.fromtimestamp(bb[j]["m"], datetime.UTC).hour == hr]
        random.shuffle(cands)
        for j in cands[:cnt * 6]:
            atr = _atr14(tt, j)
            if not atr or atr != atr:
                continue
            for d in (1, -1):                       # both directions = the true coin-flip baseline
                r = race(bb, j, atr, horizon=HOR, direction=d)
                if r is None:
                    continue
                ctl_rows.append({"s": s, "hr": hr, "atr": atr,
                                 **{f"p{m}": r["passage"][m] for m in (1.0, 1.5, 2.0)},
                                 "mfe": r["mfe"], "mae": r["mae"]})

def summarise(rows, label):
    n = len(rows)
    print(f"\n{label} (n={n:,})")
    print(f"  60m MFE {np.mean([r['mfe'] for r in rows]):.2f} ATR · "
          f"MAE {np.mean([r['mae'] for r in rows]):.2f} ATR · "
          f"ratio {np.mean([r['mfe'] for r in rows])/np.mean([r['mae'] for r in rows]):.2f}")
    for m in (1.0, 1.5, 2.0):
        v = [r[f"p{m}"] for r in rows]
        res = [x for x in v if x != 0]
        p = sum(1 for x in res if x > 0) / len(res) if res else float("nan")
        se = math.sqrt(p * (1 - p) / len(res)) if res else float("nan")
        print(f"  +/-{m} ATR: P(favourable first) {p:.3f} +/- {se:.3f}  "
              f"(resolved {len(res):,}/{n:,})")
    return rows

print(f"\n=== {SYM} ===")
summarise(brk_rows, "BREAKS")
summarise(ctl_rows, "MATCHED-HOUR CONTROL (both directions)")
json.dump({"brk": brk_rows, "ctl": ctl_rows},
          open(f'reports/tunnel_mgc/race_{SYM}.json', 'w'))
print("\nmedian ATR at a break: %.2fpt ($%.0f) | median tunnel width %.1fpt ($%.0f)" % (
    np.median([r["atr"] for r in brk_rows]), np.median([r["atr"] for r in brk_rows])*VPP,
    np.median([r["width"] for r in brk_rows]), np.median([r["width"] for r in brk_rows])*VPP))
