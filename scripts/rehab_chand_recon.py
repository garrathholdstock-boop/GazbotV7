"""CHANDELIER (runner give-back) rehab — STAGE 1: LIVE-trade reconstruction & normalization.

For every LIVE managed-profit exit (CHANDELIER / GIVEBACK) and the STOP_UNFILLED malfunctions,
reconstruct the TRUE tick path over the hold (ticks where captured >=07-23, else 5s-bar hi/lo),
measure entry-ATR (from 5s->1m bars), peak-favorable (R and $), what we banked, the give-back
(peak$ - bank$) and capture%. Segment by ATR band / regime(ER) / time-of-day. Corrected cost
$1.50/RT, $2/pt. Read-only.  PYTHONPATH=src .venv/bin/python scripts/rehab_chand_recon.py
"""
from __future__ import annotations
import sqlite3, datetime as dt
from collections import defaultdict
import duckdb, numpy as np

VPP, FEE = 2.0, 1.5
con = duckdb.connect()
con.execute("ATTACH 'data/capture.db' AS c (TYPE sqlite, READ_ONLY)")
con.execute("ATTACH 'data/gazbot7.db' AS g (TYPE sqlite, READ_ONLY)")

# tick coverage
tk_min = con.execute("SELECT min(ts_ms) FROM c.ticks").fetchone()[0] / 1000.0

rows = con.execute("""SELECT id, epoch(opened_at::TIMESTAMPTZ) t0, epoch(closed_at::TIMESTAMPTZ) t1,
    gate, side, qty, entry_price, exit_price, pnl_usd, exit_reason FROM g.trades
    WHERE symbol='MNQ' AND closed_at IS NOT NULL AND exit_reason IN ('CHANDELIER','GIVEBACK','STOP_UNFILLED')
    ORDER BY opened_at""").fetchall()

# preload 5s bars once
allbars = con.execute("SELECT bar_ts, high, low, close FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' ORDER BY bar_ts").fetchall()
bt = np.array([r[0] for r in allbars], float); bh = np.array([r[1] for r in allbars], float)
bl = np.array([r[2] for r in allbars], float); bc = np.array([r[3] for r in allbars], float)

# 1-min bars for ATR/ER context
mk = {}
for i in range(len(bt)):
    m = int(bt[i]) // 60
    r = mk.get(m)
    if r is None:
        mk[m] = [bh[i], bl[i], bc[i]]
    else:
        r[0] = max(r[0], bh[i]); r[1] = min(r[1], bl[i]); r[2] = bc[i]
mins = sorted(mk)
mhi = {m: mk[m][0] for m in mins}; mlo = {m: mk[m][1] for m in mins}; mcl = {m: mk[m][2] for m in mins}

def atr_er_at(t0):
    m0 = int(t0) // 60
    ms = [m for m in mins if m0 - 30 <= m <= m0]
    if len(ms) < 15:
        return 0.0, 0.0
    cl = np.array([mcl[m] for m in ms]); hi = np.array([mhi[m] for m in ms]); lo = np.array([mlo[m] for m in ms])
    tr = np.maximum(hi[1:] - lo[1:], np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
    atr = float(tr[-14:].mean()) if len(tr) >= 14 else float(tr.mean())
    path = float(np.abs(np.diff(cl)).sum()) or 1.0
    er = abs(cl[-1] - cl[0]) / path
    return atr, er

def peak_path(t0, t1, side, ep):
    """(peak_fav_pt, adverse_pt) over the hold, from ticks if covered else 5s bars."""
    if t0 >= tk_min:
        r = con.execute(f"SELECT min(price), max(price) FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={int(t0*1000)} AND ts_ms<={int(t1*1000)}").fetchone()
        lo, hi = r if r else (None, None)
        src = "tick"
    else:
        lo = hi = None; src = "5s"
    if lo is None:
        sel = (bt >= t0) & (bt <= t1)
        if not sel.any():
            return None
        lo = float(bl[sel].min()); hi = float(bh[sel].max()); src = "5s"
    fav = (hi - ep) if side == "LONG" else (ep - lo)
    adv = (ep - lo) if side == "LONG" else (hi - ep)
    return fav, adv, src

def band(a):
    return "40+" if a >= 40 else "30-40" if a >= 30 else "20-30" if a >= 20 else "<20"
def regime(er):
    return "trend" if er >= 0.50 else "build" if er >= 0.30 else "chop"
def tod(t0):
    h = dt.datetime.fromtimestamp(t0, dt.UTC).hour
    return "US" if 13 <= h < 21 else "ON"

recs = []
for tid, t0, t1, gate, side, qty, ep, xp, pnl, reason in rows:
    pp = peak_path(t0, t1, side, ep)
    if pp is None:
        continue
    fav, adv, src = pp
    atr, er = atr_er_at(t0)
    peak_r = fav / atr if atr > 0 else 0.0
    peak_usd = fav * VPP * (qty or 1)
    recs.append(dict(tid=tid, t0=t0, gate=gate, side=side, qty=qty or 1, reason=reason,
                     pnl=pnl, peak_usd=peak_usd, peak_r=peak_r, atr=atr, er=er,
                     band=band(atr), regime=regime(er), tod=tod(t0), src=src,
                     giveback=peak_usd - pnl if reason != "STOP_UNFILLED" else None))

print(f"reconstructed {len(recs)} live trades (tick_cov>= {dt.datetime.fromtimestamp(tk_min,dt.UTC):%m-%d})\n")

# ---- give-back leak on the managed-profit exits ----
prof = [r for r in recs if r["reason"] in ("CHANDELIER", "GIVEBACK")]
print("=== MANAGED-PROFIT EXITS: give-back leak ===")
print(f"n={len(prof)}  banked=${sum(r['pnl'] for r in prof):+.0f}  peak(sum)=${sum(r['peak_usd'] for r in prof):+.0f}  "
      f"give-back=${sum(r['peak_usd']-r['pnl'] for r in prof):+.0f}  capture={100*sum(r['pnl'] for r in prof)/max(1,sum(r['peak_usd'] for r in prof)):.0f}%")

def tbl(recs, keyfn, label):
    d = defaultdict(lambda: [0, 0.0, 0.0, []])
    for r in recs:
        k = keyfn(r); d[k][0] += 1; d[k][1] += r["pnl"]; d[k][2] += r["peak_usd"]; d[k][3].append(r["peak_r"])
    print(f"\n-- by {label} --")
    print(f"{label:>10}{'n':>4}{'bank$':>8}{'peak$':>8}{'gvbk$':>8}{'capt%':>7}{'medPkR':>8}")
    for k in sorted(d):
        n, bk, pk, prs = d[k]
        print(f"{str(k):>10}{n:>4}{bk:>+8.0f}{pk:>+8.0f}{pk-bk:>+8.0f}{100*bk/max(1,pk):>6.0f}%{np.median(prs):>8.2f}")

tbl(prof, lambda r: r["reason"], "exit")
tbl(prof, lambda r: r["band"], "ATRband")
tbl(prof, lambda r: r["regime"], "regime")
tbl(prof, lambda r: r["tod"], "tod")
tbl([r for r in prof if r["gate"].startswith("grind")], lambda r: r["reason"], "grind-only")

# ---- biggest single give-backs (the target winners leaking the tail) ----
print("\n=== TOP-12 give-back leaks (peak - banked), managed-profit exits ===")
print(f"{'date':>12}{'gate':16}{'reason':11}{'atr':>5}{'pkR':>6}{'peak$':>8}{'bank$':>8}{'gvbk$':>8}{'reg':>6}{'tod':>4}")
for r in sorted(prof, key=lambda r: -(r["peak_usd"] - r["pnl"]))[:12]:
    d = dt.datetime.fromtimestamp(r["t0"], dt.UTC).strftime("%m-%d %H:%M")
    print(f"{d:>12}{r['gate']:16}{r['reason']:11}{r['atr']:>5.0f}{r['peak_r']:>6.2f}{r['peak_usd']:>+8.0f}{r['pnl']:>+8.0f}{r['peak_usd']-r['pnl']:>+8.0f}{r['regime']:>6}{r['tod']:>4}")

# ---- STOP_UNFILLED normalization: what if the 1-ATR stop had worked ----
unf = [r for r in recs if r["reason"] == "STOP_UNFILLED"]
print(f"\n=== STOP_UNFILLED normalization (n={len(unf)}) ===")
print(f"actual realised: ${sum(r['pnl'] for r in unf):+.0f}")
# if the native 1-ATR stop had filled, loss ~= -1 ATR * VPP * qty - FEE (plus small slippage). Report both.
norm = sum(-(r['atr']*VPP*r['qty']) - FEE for r in unf if r['atr'] > 0)
print(f"if 1-ATR stop had FILLED (-1ATR each): ${norm:+.0f}  (delta vs actual ${norm - sum(r['pnl'] for r in unf):+.0f})")
print(f"{'date':>12}{'gate':16}{'atr':>5}{'actual$':>9}{'if1ATR$':>9}")
for r in sorted(unf, key=lambda r: r["pnl"])[:12]:
    d = dt.datetime.fromtimestamp(r["t0"], dt.UTC).strftime("%m-%d %H:%M")
    ifstop = -(r['atr']*VPP*r['qty']) - FEE
    print(f"{d:>12}{r['gate']:16}{r['atr']:>5.0f}{r['pnl']:>+9.0f}{ifstop:>+9.0f}")

import pickle
pickle.dump(recs, open("scratchpad/rehab_chand_recs.pkl", "wb"))
print("\nwrote scratchpad/rehab_chand_recs.pkl")
