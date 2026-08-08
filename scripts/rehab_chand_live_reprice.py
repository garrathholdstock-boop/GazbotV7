"""CHANDELIER rehab — STAGE 3: reprice the ACTUAL LIVE chandelier/giveback trades under the
candidate exit configs (apples-to-apples on trades the desk really took). Confirms the fix banks
more of the tail on the real leaking trades, segmented by regime. $1.50/RT, $2/pt, 1 lot basis.
PYTHONPATH=src .venv/bin/python scripts/rehab_chand_live_reprice.py"""
from __future__ import annotations
import sqlite3, datetime as dt
from collections import defaultdict
import duckdb, numpy as np

VPP, FEE = 2.0, 1.5
con = duckdb.connect()
con.execute("ATTACH 'data/gazbot7.db' AS g (TYPE sqlite, READ_ONLY)")
z = np.load("scratchpad/tape5s.npz")
bts = np.asarray(z["ts"]); bh = np.asarray(z["h"]); bl = np.asarray(z["l"]); bc = np.asarray(z["c"])

# 1-min close/hi/lo for atr+er
mk = {}
for i in range(len(bts)):
    m = int(bts[i]) // 60
    r = mk.get(m)
    if r is None:
        mk[m] = [bh[i], bl[i], bc[i]]
    else:
        r[0] = max(r[0], bh[i]); r[1] = min(r[1], bl[i]); r[2] = bc[i]
mins = sorted(mk)
mhi = np.array([mk[m][0] for m in mins]); mlo = np.array([mk[m][1] for m in mins]); mcl = np.array([mk[m][2] for m in mins])
mm = np.array(mins)

def atr_er(t0):
    m0 = int(t0) // 60
    j = int(np.searchsorted(mm, m0))
    if j < 31:
        return 0.0, 0.0
    cl = mcl[j - 30:j + 1]; hi = mhi[j - 30:j + 1]; lo = mlo[j - 30:j + 1]
    tr = np.maximum(hi[1:] - lo[1:], np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
    atr = float(tr[-14:].mean())
    path = float(np.abs(np.diff(cl)).sum()) or 1.0
    return atr, abs(cl[-1] - cl[0]) / path

def regime(er):
    return "trend" if er >= 0.50 else "build" if er >= 0.30 else "chop"

def fwd(side, ep, atr, t0):
    i0 = int(np.searchsorted(bts, t0))
    j1 = min(i0 + 90 * 12, len(bts))
    h, l, c = bh[i0:j1], bl[i0:j1], bc[i0:j1]
    if len(h) < 12 or atr <= 0:
        return None
    if side == "LONG":
        return (h - ep) / atr, (ep - l) / atr, (c - ep) / atr
    return (ep - l) / atr, (h - ep) / atr, (ep - c) / atr

def r_lock(fav, adv, cf, sk, lr, lk, gb=None):
    stop_i = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else len(fav)
    peak = 0.0
    for i in range(len(fav)):
        if i >= stop_i:
            return -1.0
        peak = max(peak, fav[i])
        if peak > 0:
            k = sk if peak < lr else lk
            if gb is not None:
                k = min(k, gb)
            if cf[i] > 0 and cf[i] <= peak - k:
                return float(cf[i])
    return max(min(float(cf[-1]), peak), -1.0)

def r_fixed(fav, adv, cf, t):
    fc = np.maximum.accumulate(fav)
    hit = int(np.argmax(fc >= t)) if (fc >= t).any() else len(fav)
    stop_i = int(np.argmax(adv >= 1.0)) if (adv >= 1.0).any() else len(fav)
    if hit < stop_i:
        return t
    if stop_i < len(fav):
        return -1.0
    return max(min(float(cf[-1]), t), -1.0)

CFG = {
    "INCUMBENT L3.5/6.0/0.5": ("lock", 3.5, 6.0, 0.5, None),
    "regime-fix (see below)": None,  # applied specially
    "L3.5/3.0/0.5": ("lock", 3.5, 3.0, 0.5, None),
    "L3.0/6.0/0.5+gb1.0": ("lock", 3.0, 6.0, 0.5, 1.0),
    "fix2.5": ("fixed", 2.5),
}

rows = con.execute("""SELECT epoch(opened_at::TIMESTAMPTZ), gate, side, entry_price, pnl_usd, exit_reason
    FROM g.trades WHERE symbol='MNQ' AND exit_reason IN ('CHANDELIER','GIVEBACK')
    AND (gate LIKE 'grind%' OR gate LIKE 'thrust%' OR gate LIKE 'abs_veto%') ORDER BY opened_at""").fetchall()

def score(spec, fav, adv, cf):
    if spec[0] == "fixed":
        return r_fixed(fav, adv, cf, spec[1])
    return r_lock(fav, adv, cf, spec[1], spec[2], spec[3], spec[4])

# regime-conditional POLICY: trend->wide incumbent, build->lock3.0, chop->lock3.0 (tighten)
def policy_spec(reg):
    if reg == "trend":
        return ("lock", 3.5, 6.0, 0.5, None)
    return ("lock", 3.5, 3.0, 0.5, None)   # build+chop: lower lock

agg = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))  # regime -> cfg -> [n, sum]
tot = defaultdict(float)
n_by_reg = defaultdict(int)
for t0, gate, side, ep, pnl, reason in rows:
    atr, er = atr_er(t0)
    reg = regime(er)
    p = fwd(side, ep, atr, t0)
    if p is None:
        continue
    fav, adv, cf = p
    n_by_reg[reg] += 1
    usd = lambda rr: rr * atr * VPP - FEE
    vals = {"ACTUAL(live)": pnl}
    for name, spec in CFG.items():
        if spec is None:
            vals["POLICY(regime)"] = usd(score(policy_spec(reg), fav, adv, cf))
        else:
            vals[name] = usd(score(spec, fav, adv, cf))
    for name, v in vals.items():
        agg[reg][name][0] += 1; agg[reg][name][1] += v
        tot[name] += v

names = ["ACTUAL(live)", "INCUMBENT L3.5/6.0/0.5", "POLICY(regime)", "L3.5/3.0/0.5", "L3.0/6.0/0.5+gb1.0", "fix2.5"]
print("LIVE chandelier/giveback trades repriced (grind+thrust+absveto), by regime\n")
print(f"{'config':26}" + "".join(f"{r:>16}" for r in ("chop", "build", "trend", "TOTAL")))
for name in names:
    line = f"{name:26}"
    for reg in ("chop", "build", "trend"):
        n, s = agg[reg][name]
        line += f"{s:>+11.0f}(n{n:>2})" if n else f"{'-':>16}"
    line += f"{tot[name]:>+16.0f}"
    print(line)
print(f"\nregime mix of these live trades: " + "  ".join(f"{r}={n_by_reg[r]}" for r in ("chop", "build", "trend")))
