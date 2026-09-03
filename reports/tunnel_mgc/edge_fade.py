"""THE OPERATOR'S ACTUAL IDEA: trade INSIDE the tunnel, not the break.

"we will trade between the tunnels" has two readings and the break study only answers one. This
answers the other: while the tape is compressed, is a touch of the tunnel's edge worth fading back
to its middle?

CAUSAL BY CONSTRUCTION. The tunnel is only ever "what has happened so far" — its high, low, mid and
width are computed from the minutes up to t and nothing after. Using the tunnel's FINAL bounds
would be reading the answer off the back of the page: the edges are, by definition, where price
turned around.

The trade scored: at a touch of the edge, target = the tunnel's mid so far, stop = 1 ATR beyond the
edge. First passage, from the END of the touch bar. Costs carried at the end.
"""
import sys, json, random, collections, datetime; sys.path.insert(0,'scripts')
import numpy as np
from tunnel_fit_mgc import (front_month_minutes, true_range, observations, normalised,
                            filter_quiet, _atr14, session_key)
SYM = sys.argv[1]
VPP = 10.0 if SYM == "MGC" else 2.0
FEE = 4.50 if SYM == "MGC" else 1.50
MIN_TUNNEL = 25
random.seed(17)
F = json.load(open(f'reports/tunnel_mgc/fit_norm_train_{SYM}.json'))
mu, sd, A = F["mu"], F["sd"], F["A"]
b, rolls = front_month_minutes(verbose=False, symbol=SYM)
trs = true_range(b, rolls); z = normalised(observations(trs))
sess = sorted({session_key(v["m"]) for v in b}); n = len(sess)
test = sorted(sess[2*n//3:])                     # held out from the fit
by = collections.defaultdict(list)
for i, v in enumerate(b): by[session_key(v["m"])].append(i)

HOR = 120
rows, ctl = [], []
for s in test:
    idx = by[s]; zz = z[idx]
    if np.isnan(zz).all(): continue
    post = filter_quiet(zz, mu, sd, A)
    bb = [b[i] for i in idx]; tt = [trs[i] for i in idx]
    run0 = None
    busy_until = -1
    for t in range(len(bb)):
        if post[t] < 0.5:
            run0 = None; continue
        if run0 is None:
            run0 = t; continue
        age = t - run0 + 1
        if age < MIN_TUNNEL or t <= busy_until:
            continue
        seg = bb[run0:t + 1]                     # CAUSAL: up to and including now
        hi = max(x["hi"] for x in seg); lo = min(x["lo"] for x in seg)
        w = hi - lo
        if w <= 0: continue
        mid = (hi + lo) / 2.0
        atr = _atr14(tt, t)
        if not atr or atr != atr or atr <= 0: continue
        bar = bb[t]
        near_lo = bar["low"] if "low" in bar else bar["lo"]
        touch_lo = near_lo <= lo + 0.10 * w
        touch_hi = bar["hi"] >= hi - 0.10 * w
        if touch_lo == touch_hi:                 # neither, or both (an inside-out bar) — skip
            continue
        d = 1 if touch_lo else -1                # fade: long the low, short the high
        entry = bar["close"]
        target = mid
        stop = (lo - atr) if touch_lo else (hi + atr)
        if (d > 0 and target <= entry) or (d < 0 and target >= entry):
            continue                             # already through the mid — no trade to take
        out = 0
        end = t
        for f in bb[t + 1:t + 1 + HOR]:
            end += 1
            hit_t = f["hi"] >= target if d > 0 else f["lo"] <= target
            hit_s = f["lo"] <= stop if d > 0 else f["hi"] >= stop
            if hit_t and hit_s: out = -1; break   # both in one bar -> scored a LOSS, never a win
            if hit_t: out = 1; break
            if hit_s: out = -1; break
        if out == 0: continue
        busy_until = end
        rows.append({"s": s, "out": out, "win_pt": abs(target - entry), "loss_pt": abs(entry - stop),
                     "age": age, "w": w, "atr": atr,
                     "hr": datetime.datetime.fromtimestamp(bar["m"], datetime.UTC).hour})

n_t = len(rows)
wins = [r for r in rows if r["out"] > 0]
p = len(wins) / n_t
se = (p * (1 - p) / n_t) ** 0.5
avg_w = np.mean([r["win_pt"] for r in wins]) if wins else 0
avg_l = np.mean([r["loss_pt"] for r in rows if r["out"] < 0])
exp_pt = p * avg_w - (1 - p) * avg_l
print(f"\n=== {SYM} · EDGE FADE INSIDE THE TUNNEL · held-out {len(test)} sessions ===")
print(f"  trades {n_t:,} = {n_t/len(test):.1f}/session · win rate {p:.3f} +/- {se:.3f}")
print(f"  avg win {avg_w:.2f}pt (${avg_w*VPP:.0f}) · avg loss {avg_l:.2f}pt (${avg_l*VPP:.0f})")
print(f"  expectancy {exp_pt:+.3f}pt = ${exp_pt*VPP:+.2f} gross · ${exp_pt*VPP - FEE:+.2f} NET of ${FEE:.2f}/RT")
print(f"  median tunnel age at entry {np.median([r['age'] for r in rows]):.0f}m · width {np.median([r['w'] for r in rows]):.1f}pt")
tot = (exp_pt*VPP - FEE) * n_t
print(f"  total over the held-out sample: ${tot:+,.0f} across {n_t:,} trades")
