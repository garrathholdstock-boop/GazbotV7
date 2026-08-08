#!/usr/bin/env python3
"""RGV_SHORT full-rehab engine — regime-segmented, tick-honest.

Runs the REAL gate_reversal_grab (SHORT) over ALL tick-covered MNQ tape (capture.db),
tags every fire with its ENTRY regime (ATR, ER30, atr_pct, RTH, aligned/counter to the
session lean) and time-of-day, then reprices the exit on REAL ticks for a SWEEP of exit
configs. Reports PER-SEGMENT (never a blanket cross-tape number), sweeps the R-targets
(operator: the cheat-sheet Rs are GUESSES — prove them), and runs robustness (per-day,
leave-one-day-out, strip-the-best).

VPP 2.0, fee 1.5/RT. Entry = first tick after the 1-min signal bar closes (how the live
gate fires). Exit = first-touch on real ticks, 60-min hold cap.

  PYTHONPATH=src .venv/bin/python scripts/rehab_rgv_short.py
"""
from __future__ import annotations
import sys, math, itertools, json
from collections import defaultdict
import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import (  # noqa: E402
    Bar, Position, compute_features, efficiency_ratio,
    gate_reversal_grab, exit_scalp, exit_fixed, exit_chandelier_lock,
)

CAP = "/home/alphabot/gazbot7/data/capture.db"
VPP, FEE, CAP_MIN = 2.0, 1.5, 60

# CURRENT LIVE rgv_short base config (slot_strategy._RGV_SHORT)
LIVE_BASE = dict(ext_min=1.5, turn_atr=0.25, flow_min=None, atr_min=20.0,
                 fast_slope=False, fast_turn=False)

con = duckdb.connect()
con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")

# ---- 1-min bars from 5s, per calendar day (session anchor for VWAP/ATR) ----
rows = con.execute("""
    WITH b AS (SELECT (bar_ts-bar_ts%60) m, arg_min(open,bar_ts) o, max(high) h, min(low) l,
                      arg_max(close,bar_ts) cl, SUM(volume) v
               FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1)
    SELECT m, o, h, l, cl, v, strftime(to_timestamp(m),'%m-%d') d,
           CAST(strftime(to_timestamp(m),'%w') AS INT) dow
    FROM b ORDER BY m""").fetchall()

# per-minute net aggressor flow (tape_net for flow_min confirm)
flowrows = con.execute("""
    SELECT (ts_ms//60000)*60 m,
           COALESCE(SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END),0) net
    FROM c.ticks WHERE symbol='MNQ' GROUP BY 1""").fetchall()
tape_net = {m: n for m, n in flowrows}

days = defaultdict(list)
for m, o, h, lo, cl, v, d, dow in rows:
    days[d].append((m, Bar(m, o, h, lo, cl, v)))

# per-day session lean (close-open, pts) -> regime direction context
lean = {}
for d, bl in days.items():
    closes = [b.close for _m, b in bl]
    lean[d] = closes[-1] - closes[0]

# ---- exit reprice cache: key (m, target_r rounded, atr rounded) ----
tick_cache = {}
def get_ticks(m):
    if m in tick_cache:
        return tick_cache[m]
    t = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
        AND ts_ms>={(m+60)*1000} AND ts_ms<{(m+60+CAP_MIN*60)*1000} ORDER BY ts_ms""").fetchall()
    tick_cache[m] = t
    return t

def reprice_scalp(m, atr, target_r, stop_atr_mult=1.0):
    ticks = get_ticks(m)
    if len(ticks) < 3:
        return None
    entry = ticks[0][1]
    peak = 0.0
    exit_px = ticks[-1][1]
    reason = "MAXHOLD"
    for ts, px in ticks[1:]:
        fav = entry - px  # SHORT
        peak = max(peak, fav)
        r = exit_scalp(Position("SHORT", entry, atr, peak), px, target_r=target_r, stop_atr_mult=stop_atr_mult)
        if r:
            exit_px = px; reason = r; break
    pnl = (entry - exit_px) * VPP - FEE
    return entry, pnl, reason

def reprice_chand_lock(m, atr, start_k=3.5, lock_r=6.0, lock_k=0.5):
    ticks = get_ticks(m)
    if len(ticks) < 3:
        return None
    entry = ticks[0][1]; peak = 0.0; exit_px = ticks[-1][1]; reason = "MAXHOLD"
    for ts, px in ticks[1:]:
        fav = entry - px; peak = max(peak, fav)
        pos = Position("SHORT", entry, atr, peak)
        # native 1-ATR stop first
        if px >= entry + atr:
            exit_px = px; reason = "STOP"; break
        r = exit_chandelier_lock(pos, px, start_k=start_k, lock_r=lock_r, lock_k=lock_k)
        if r:
            exit_px = px; reason = r; break
    pnl = (entry - exit_px) * VPP - FEE
    return entry, pnl, reason

# ---- build the fire list for a given base config ----
def fires(base):
    out = []
    for d, bl in days.items():
        bars = [b for _m, b in bl]
        busy = -1
        for i in range(len(bars)):
            w = bars[max(0, i-59):i+1]
            if len(w) < 6:
                continue
            m = bl[i][0]
            if m < busy:
                continue
            f = compute_features(w)
            tn = tape_net.get(m - m % 60, 0.0)
            e = gate_reversal_grab(f, side="SHORT", tape_net=tn, in_rth=True, **base)
            if e is None:
                continue
            er = efficiency_ratio(w)
            # session progress at fire (pts from day open) -> aligned/counter
            day_net_sofar = bars[i].close - bars[0].close
            hh = int(((m % 86400)) // 3600)
            mm = int(((m % 86400) % 3600) // 60)
            utc_min = hh*60+mm
            rth = utc_min >= 13*60+30 and utc_min < 20*60  # 13:30-20:00 UTC US cash
            out.append(dict(d=d, m=m, atr=f.atr, atr_pct=f.atr_pct, er=er,
                            ext=f.ext_atr, turn=f.net_atr_5, day_net=day_net_sofar,
                            lean=lean[d], rth=rth, utc_min=utc_min))
            busy = m + 60
    return out

# ---- regime bucketing ----
def regime(fr):
    atr, er = fr["atr"], fr["er"]
    if atr >= 38:
        return "violent"          # US-open ATR-52/62 chop
    if er >= 0.45:
        return "clean-trend"
    if er >= 0.30:
        return "building"
    if atr < 14 or er < 0.10:
        return "dead-chop"
    return "normal-chop"

def align(fr):
    # SHORT fade: aligned if the session is leaning DOWN, counter if leaning UP
    if fr["lean"] <= -30:
        return "aligned(DOWN)"
    if fr["lean"] >= 30:
        return "counter(UP)"
    return "flat"

def tod(fr):
    return "US" if fr["rth"] else "ON"

def summ(pnls):
    n = len(pnls)
    if n == 0:
        return (0,0,0,0)
    net = sum(pnls); wins = sum(1 for p in pnls if p > 0)
    return (n, round(net,1), round(net/n,1), round(100*wins/n))

# ============ RUN ============
report = []
def P(*a):
    line = " ".join(str(x) for x in a)
    report.append(line); print(line)

P("="*90)
P("RGV_SHORT REHAB — regime-segmented tick-honest backtest")
P("tape:", min(days), "->", max(days), "| VPP", VPP, "fee", FEE, "| entry=1st tick post signal-bar; 60m cap")
P("LIVE base:", LIVE_BASE)
P("="*90)

live_fires = fires(LIVE_BASE)
P(f"\nLIVE-config SHORT fires over tick tape: {len(live_fires)}")
P("per-day lean (session close-open pts):", " ".join(f"{d}:{lean[d]:+.0f}" for d in sorted(lean)))

# attach live-exit (adaptive: chop tight k1.5 scalp / counter k2.0 / trend wide) — but operator
# says PROVE the Rs. First reprice each fire under a grid of scalp target_r + chand_lock.
GRID_R = [1.0, 1.5, 2.0, 2.5, 3.0]
for fr in live_fires:
    fr["seg"] = regime(fr); fr["al"] = align(fr); fr["tod"] = tod(fr)
    fr["scalp"] = {}
    for tr in GRID_R:
        rp = reprice_scalp(fr["m"], fr["atr"], tr)
        fr["scalp"][tr] = rp[1] if rp else None
    rp = reprice_chand_lock(fr["m"], fr["atr"])
    fr["chand"] = rp[1] if rp else None

valid = [fr for fr in live_fires if fr["scalp"].get(2.0) is not None]
P(f"repriceable (have ticks): {len(valid)}")

# ---------- SEGMENT TABLES ----------
def seg_table(key_fn, title, target_r=2.0):
    P(f"\n---- {title} (exit=scalp {target_r}R/1-ATR) ----")
    P(f"  {'segment':<20} {'n':>3} {'net$':>8} {'$/tr':>7} {'win%':>5}")
    buckets = defaultdict(list)
    for fr in valid:
        buckets[key_fn(fr)].append(fr["scalp"][target_r])
    tot = []
    for k in sorted(buckets):
        n, net, ev, w = summ(buckets[k])
        tot += buckets[k]
        P(f"  {k:<20} {n:>3} {net:>+8.0f} {ev:>+7.1f} {w:>4}%")
    n, net, ev, w = summ(tot)
    P(f"  {'ALL(blanket-BUG)':<20} {n:>3} {net:>+8.0f} {ev:>+7.1f} {w:>4}%")

seg_table(lambda f: f["seg"], "BY REGIME")
seg_table(lambda f: f["al"], "BY ALIGNMENT (short fade vs session lean)")
seg_table(lambda f: f["tod"], "BY TIME-OF-DAY")
seg_table(lambda f: f"{f['seg']}/{f['al']}", "BY REGIME x ALIGNMENT")

# ---------- R-TARGET SWEEP PER REGIME (operator: prove the Rs) ----------
P("\n==== R-TARGET SWEEP per regime x alignment (scalp target_r, 1-ATR stop) ====")
P("  (cheat-sheet guess for a FADER: Lot-A 0.5R / Lot-B 1.5R — proving vs data)")
grp = defaultdict(list)
for fr in valid:
    grp[(fr["seg"], fr["al"])].append(fr)
P(f"  {'seg/align':<26} {'n':>3} " + " ".join(f"{('R'+str(r)):>7}" for r in GRID_R) + "  best")
for k in sorted(grp):
    frs = grp[k]
    row = []; best=None
    for tr in GRID_R:
        pnls=[f["scalp"][tr] for f in frs if f["scalp"].get(tr) is not None]
        net=sum(pnls)
        row.append(net)
        if best is None or net>best[1]: best=(tr,net)
    P(f"  {(k[0]+'/'+k[1]):<26} {len(frs):>3} " + " ".join(f"{r:>+7.0f}" for r in row) + f"  R{best[0]}")

# ---------- BASE-PARAM SWEEP (is the bleed the SIGNAL/base config?) ----------
P("\n==== BASE-PARAM SWEEP (ext_min x turn_atr x flow_min), exit=scalp 2R, per regime-home ====")
P("  home = normal-chop + dead-chop + building (fader habitat); EXCL clean-trend/violent (bench-regime)")
EXT=[1.0,1.5,2.0,2.5]; TURN=[0.15,0.25,0.5]; FLOW=[None,25,50]
P(f"  {'ext':>4} {'turn':>5} {'flow':>5} {'n_all':>5} {'net_all':>8} {'n_home':>6} {'net_home':>9} {'$/tr_home':>9} {'w%':>4}")
for ext,turn,fl in itertools.product(EXT,TURN,FLOW):
    b=dict(LIVE_BASE); b.update(ext_min=ext, turn_atr=turn, flow_min=fl)
    frs=fires(b)
    all_p=[]; home_p=[]
    for fr in frs:
        rp=reprice_scalp(fr["m"], fr["atr"], 2.0)
        if rp is None: continue
        fr["er"]=fr["er"]; seg=regime(fr)
        all_p.append(rp[1])
        if seg in ("normal-chop","dead-chop","building"):
            home_p.append(rp[1])
    na,neta=len(all_p),sum(all_p)
    nh,neth=len(home_p),sum(home_p)
    evh = neth/nh if nh else 0
    wh = 100*sum(1 for p in home_p if p>0)/nh if nh else 0
    fls="none" if fl is None else str(fl)
    P(f"  {ext:>4} {turn:>5} {fls:>5} {na:>5} {neta:>+8.0f} {nh:>6} {neth:>+9.0f} {evh:>+9.1f} {wh:>3.0f}%")

# ---------- ROBUSTNESS: per-day + LODO + strip-best (best home config, 2R) ----------
P("\n==== ROBUSTNESS (LIVE base, scalp 2R, HOME regimes only) ====")
home=[fr for fr in valid if fr["seg"] in ("normal-chop","dead-chop","building")]
byday=defaultdict(list)
for fr in home: byday[fr["d"]].append(fr["scalp"][2.0])
P("  per-day (home only):")
for d in sorted(byday):
    n,net,ev,w=summ(byday[d]); P(f"    {d}: n={n} net={net:+.0f} $/tr={ev:+.1f} w={w}%")
allhome=[fr["scalp"][2.0] for fr in home]
n,net,ev,w=summ(allhome); P(f"  TOTAL home: n={n} net={net:+.0f} $/tr={ev:+.1f} w={w}%")
# strip best trade / best day
if allhome:
    sp=sorted(allhome)
    P(f"  strip best 1 trade: net={sum(sp[:-1]):+.0f} (was {net:+.0f})")
    P(f"  strip best 3 trades: net={sum(sp[:-3]):+.0f}")
    # LODO
    P("  leave-one-day-out (net with that day removed):")
    for d in sorted(byday):
        rem=[p for dd in byday if dd!=d for p in byday[dd]]
        P(f"    -{d}: net={sum(rem):+.0f}")

# ---------- ALIGNED (DOWN-day) subset: the true edge? ----------
P("\n==== ALIGNED-ONLY (session leaning DOWN, i.e. router would NOT bench) ====")
al=[fr for fr in valid if fr["al"]=="aligned(DOWN)"]
for tr in GRID_R:
    pnls=[f["scalp"][tr] for f in al if f["scalp"].get(tr) is not None]
    n,net,ev,w=summ(pnls); P(f"  scalp {tr}R: n={n} net={net:+.0f} $/tr={ev:+.1f} w={w}%")
pnls=[f["chand"] for f in al if f["chand"] is not None]
n,net,ev,w=summ(pnls); P(f"  chand_lock: n={n} net={net:+.0f} $/tr={ev:+.1f} w={w}%")

P("\nDONE")
con.close()

# dump fire detail for the report
with open("/home/alphabot/gazbot7/scratchpad/rgv_fires.json","w") as fh:
    json.dump([{k:(round(v,2) if isinstance(v,float) else v) for k,v in fr.items() if k!="scalp"}
               | {"scalp2R": fr["scalp"].get(2.0)} for fr in valid], fh, indent=0)
