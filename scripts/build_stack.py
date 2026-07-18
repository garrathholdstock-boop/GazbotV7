#!/usr/bin/env python3
"""Build + report the risk-weighted ALWAYS-ON stack (thrust trend + rgv chop).

Always-on gates, each capped by a per-day max-loss circuit breaker, inverse-vol risk-weighted,
leaning on the anti-correlation. No on/off timing governor (killed by the autocorrelation test).

  PYTHONPATH=src python scripts/build_stack.py
"""
import sqlite3

from gazbot7.deciders import (Bar, compute_features, gate_thrust, gate_reversal_grab,
                              chandelier_start_k, exit_chandelier, exit_scalp, Position)
from gazbot7.stack import (day_circuit_breaker, inverse_vol_weights, combine, sharpe,
                           max_drawdown, diversification_multiplier, _corr)

DB = "/home/alphabot/alphabot2/data/alphabot.db"
CB = 400.0   # per-gate per-day max-loss circuit breaker ($), fixed (not re-tuned)


def _trades(bars, fn, momentum):
    out = []; op = None
    for i in range(len(bars)):
        w = bars[max(0, i - 59):i + 1]
        if len(w) < 6:
            continue
        f = compute_features(w); px = f.price
        if op:
            if momentum:
                fav = (px - op['e']) if op['s'] == 'LONG' else (op['e'] - px); op['peak'] = max(op['peak'], fav)
                pos = Position(op['s'], op['e'], op['atr'], op['peak'])
                r = exit_chandelier(pos, px, start_k=op['k'], min_k=0.5, tighten=0.75) or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0)
            else:
                pos = Position(op['s'], op['e'], op['atr'], 0.0); r = exit_scalp(pos, px, target_r=2.0, stop_atr_mult=1.0)
            if r:
                g = (px - op['e']) if op['s'] == 'LONG' else (op['e'] - px); out.append(g * 2 - 1.5); op = None
        if op is None:
            e = fn(f)
            if e:
                op = {'s': e.side, 'e': px, 'atr': f.atr, 'peak': 0.0, 'k': chandelier_start_k(f.atr)}
    return out


thrust = (lambda f: gate_thrust(f, thr=1.5, amp_floor=0.0004), True)
rgv = (lambda f: gate_reversal_grab(f, side="LONG", ext_min=2.0, turn_atr=0.15, fast_slope=True,
                                    fast_turn=True, atr_min=13.0, tape_net=0.0, in_rth=True), False)

c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c.row_factory = sqlite3.Row
daily = {"thrust": [], "rgv": []}
for day in [r[0] for r in c.execute("SELECT DISTINCT date(bar_ts,'unixepoch') d FROM bar_history WHERE symbol='MNQ' AND timeframe='1m' ORDER BY 1")]:
    br = c.execute("SELECT bar_ts,open,high,low,close,volume FROM bar_history WHERE symbol='MNQ' AND timeframe='1m' AND date(bar_ts,'unixepoch')=? ORDER BY bar_ts", (day,)).fetchall()
    bars = [Bar(r['bar_ts'], r['open'], r['high'], r['low'], r['close'], r['volume'] or 0) for r in br]
    if len(bars) < 600:
        continue
    daily["thrust"].append(day_circuit_breaker(_trades(bars, *thrust), CB))
    daily["rgv"].append(day_circuit_breaker(_trades(bars, *rgv), CB))

n = len(daily["thrust"])
print(f"RISK-WEIGHTED ALWAYS-ON STACK · {n} days · always-on + per-day −${int(CB)} circuit breaker\n")


def line(name, s):
    import statistics
    print(f"  {name:>18}  total {round(sum(s)):>6}   dailyσ {round(statistics.pstdev(s)):>4}   "
          f"Sharpe {sharpe(s):>5.2f}   maxDD {round(max_drawdown(s)):>6}")


line("thrust (trend)", daily["thrust"])
line("rgv (chop)", daily["rgv"])
print(f"\n  correlation thrust~rgv: {_corr(daily['thrust'], daily['rgv']):+.2f}")

wv = inverse_vol_weights(daily)
ew = {"thrust": 0.5, "rgv": 0.5}
print(f"\n  inverse-vol weights: thrust {wv['thrust']:.2f} / rgv {wv['rgv']:.2f}   "
      f"(equal-weight is the 0.50/0.50 baseline)")
idm = diversification_multiplier(daily, wv)
print(f"  diversification multiplier (IDM): {idm:.2f}  → the anti-correlation lets you run "
      f"~{idm:.1f}× the risk at the same portfolio vol\n")

line("equal-weight", combine(daily, ew))
line("risk-weighted", combine(daily, wv))
line("risk-wt × IDM", [x * idm for x in combine(daily, wv)])
print("\n(unit-gross weights sum to 1; 'risk-wt × IDM' scales to the same vol a single gate ran at.\n"
      " optimistic 1m basis — real fills ~60-70%. In-sample; incubate 100+ trades before arming.)")
