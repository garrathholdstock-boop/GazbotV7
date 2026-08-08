#!/usr/bin/env python3
"""MOVEMENT 2 — the idle-gate lab. Fire ALL SIX live tournament gates mechanically
(UNGATED — no ER/ATR favourable-condition filter) at the 43 frozen sat-out runs,
IN-DIRECTION, anywhere in the 10 minutes BEFORE ignition, with TICK-HONEST exits
repriced on THIS week's capture.db trade ticks. Per-gate scoreboard.

  PYTHONPATH=src .venv/bin/python scripts/idle_gate_backtest.py
"""
from __future__ import annotations
import sqlite3, datetime as dt, sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")
import duckdb
from gazbot7.deciders import (Bar, Position, compute_features, chandelier_start_k,
    exit_chandelier, exit_scalp, gate_grind, gate_reversal_grab, gate_thrust,
    gate_capitulation)
from gazbot7.footprint import footprint_summary

CAP = "/home/alphabot/gazbot7/data/capture.db"
VPP, FEE, CAP_MIN = 2.0, 1.5, 60
YEAR = 2026

# ── the 43 FROZEN sat-out runs (from the census stdout — the locked snapshot) ──
SAT_OUT = [
 ("07-19 22:29","UP",80),("07-20 01:54","UP",100),("07-20 02:09","DN",-75),
 ("07-20 02:29","UP",89),("07-20 04:18","UP",74),("07-20 04:57","DN",-84),
 ("07-20 07:19","UP",109),("07-20 14:40","DN",-105),("07-20 15:06","UP",87),
 ("07-20 15:50","UP",104),("07-20 16:49","DN",-87),("07-20 18:28","DN",-86),
 ("07-20 19:41","DN",-103),("07-20 23:47","DN",-87),("07-21 00:16","UP",112),
 ("07-21 14:00","DN",-97),("07-22 07:27","DN",-80),("07-22 13:18","UP",87),
 ("07-22 14:55","UP",110),("07-22 19:50","DN",-79),("07-22 20:52","DN",-139),
 ("07-23 00:13","UP",98),("07-23 06:58","DN",-119),("07-23 07:27","DN",-83),
 ("07-23 08:02","UP",84),("07-23 08:48","UP",79),("07-23 11:22","DN",-106),
 ("07-23 13:02","DN",-86),("07-23 13:28","UP",166),("07-23 14:40","DN",-178),
 ("07-23 14:59","DN",-118),("07-23 16:14","UP",80),("07-23 16:39","DN",-117),
 ("07-23 17:26","DN",-91),("07-23 19:31","DN",-84),("07-23 19:49","UP",217),
 ("07-23 20:59","DN",-104),("07-24 00:01","DN",-88),("07-24 06:57","UP",107),
 ("07-24 13:38","DN",-194),("07-24 13:59","UP",99),("07-24 18:17","DN",-104),
 ("07-24 19:01","DN",-102),
]

def to_epoch(s):
    return int(dt.datetime.strptime(f"{YEAR}-{s}", "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())

# gate spec: tag, kind, side, exit_kind (live params baked in _fires_gate)
GATES = [
 ("rgv_long","reversal_grab","LONG","scalp"),
 ("grind_long","grind","LONG","chandelier"),
 ("capitulation_long","capitulation","LONG","scalp"),
 ("thrust_short","thrust","SHORT","chandelier"),
 ("rgv_short","reversal_grab","SHORT","scalp"),
 ("exhaustion_short","exhaustion","SHORT","scalp"),
]
_RGV = dict(ext_min=2.0, turn_atr=0.15, fast_slope=True, fast_turn=True, atr_min=13.0)

def features_fires(kind, side, f):
    if kind == "grind":
        e = gate_grind(f, tape_net=0.0, slope_min=0.4, fast_slope=True)
    elif kind == "reversal_grab":
        e = gate_reversal_grab(f, side=side, tape_net=0.0, in_rth=True, **_RGV)
    elif kind == "thrust":
        e = gate_thrust(f, thr=1.5, amp_floor=0.0004)
    else:
        return False
    return e is not None and e.side == side

def replay_exit(exit_kind, side, entry_px, atr, ticks):
    peak = 0.0; k = chandelier_start_k(atr)
    for ts, px in ticks:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak: peak = fav
        pos = Position(side, entry_px, atr, peak)
        if exit_kind == "chandelier":
            r = (exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75)
                 or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))
        else:
            r = exit_scalp(pos, px, target_r=2.0, stop_atr_mult=1.0)
        if r: return px, ts, r
    return ticks[-1][1], ticks[-1][0], "TIMEOUT"

def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute("CREATE TABLE tick AS SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' ORDER BY ts_ms")
    con.execute("CREATE INDEX ix ON tick(ts_ms)")
    # resample 5s -> 1m
    rows = con.execute("""
        WITH m AS (SELECT (bar_ts - (bar_ts % 60)) AS mt, bar_ts, open, high, low, close, volume
                   FROM c.bars WHERE symbol='MNQ' AND timeframe='5s')
        SELECT mt, arg_min(open,bar_ts), max(high), min(low), arg_max(close,bar_ts), sum(volume)
        FROM m GROUP BY mt ORDER BY mt""").fetchall()
    bars = [Bar(int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rows]
    ts_index = {b.ts: i for i, b in enumerate(bars)}
    # sqlite conn (Row) for the footprint gate evals — reuse the LIVE footprint code
    sq = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True); sq.row_factory = sqlite3.Row

    def exit_after(decision_ms, side, atr, exit_kind):
        tk = con.execute("SELECT ts_ms, price FROM tick WHERE ts_ms>? AND ts_ms<=? ORDER BY ts_ms",
                         [decision_ms, decision_ms + CAP_MIN*60000]).fetchall()
        if len(tk) < 2: return None
        entry_px = tk[0][1]
        xp, xms, why = replay_exit(exit_kind, side, entry_px, atr, tk[1:])
        g = ((xp - entry_px) if side == "LONG" else (entry_px - xp)) * VPP - FEE
        return dict(net=g, why=why, entry=entry_px, atr=atr)

    results = {g[0]: [] for g in GATES}          # tag -> list of trade dicts (one per run it fired)
    fire_detail = {g[0]: [] for g in GATES}
    for s, d, mv in SAT_OUT:
        T = to_epoch(s); side_run = "LONG" if d == "UP" else "SHORT"
        # pre-ignition 1-min bars: close between T-540 and T  -> bar_ts in [T-600, T-60]
        pre_ts = [T - 60*k for k in range(1, 11)][::-1]   # T-600 .. T-60
        for tag, kind, gside, xkind in GATES:
            if gside != side_run:   # in-direction only
                continue
            fired = None
            if kind in ("grind","reversal_grab","thrust"):
                for bt in pre_ts:
                    i = ts_index.get(bt)
                    if i is None or i < 6: continue
                    w = bars[max(0, i-59):i+1]
                    if len(w) < 6: continue
                    f = compute_features(w)
                    if features_fires(kind, gside, f):
                        fired = ((bt + 60)*1000, f.atr, bt); break
            else:  # footprint gates — eval on the tape/book each 5s across the window
                nows = list(range(T-600, T-60+1, 5))
                for nm in nows:
                    fp = footprint_summary(sq, "MNQ", nm*1000)
                    hit = False
                    if kind == "capitulation":
                        e = gate_capitulation(f=None, cap_sell=fp["cap_sell"], cap_buy=fp["cap_buy"],
                             cap_base=fp["cap_base"], cap_dpx=fp["cap_dpx"], cap_flip=fp["cap_flip"],
                             climax_min=3.0, dom_min=0.7, require_flip=False)
                        hit = e is not None and e.side == gside
                    else:  # exhaustion
                        from gazbot7.footprint import exhaustion_signal
                        sig = exhaustion_signal(fp["net_signed"], fp["price_move_pt"], fp["bid1_size"],
                             fp["ask1_size"], fp["bid1_price"], fp["ask1_price"])
                        hit = sig is not None and sig[0] == gside
                    if hit:
                        # atr proxy from bars for the scalp stop
                        i = ts_index.get(T - (T % 60))
                        atr = compute_features(bars[max(0,(i or 6)-59):(i or 6)+1]).atr if i and i>=6 else 20.0
                        fired = (nm*1000, atr, nm); break
            if fired:
                decision_ms, atr, bt = fired
                r = exit_after(decision_ms, gside, atr, xkind)
                if r:
                    r.update(run=s, dir=d, move=mv, ceil=abs(mv)*VPP)
                    results[tag].append(r)
                    fire_detail[tag].append((s, d, mv, round(r["net"],1), r["why"]))

    # ── SCOREBOARD ──
    up_runs = sum(1 for _,d,_ in SAT_OUT if d=="UP"); dn_runs = len(SAT_OUT)-up_runs
    print(f"43 sat-out runs · {up_runs} UP (long-gate eligible) · {dn_runs} DN (short-gate eligible)")
    print(f"{'gate':18}{'elig':>5}{'fires':>7}{'net$':>9}{'$/fire':>8}{'win%':>6}   exits")
    scoreboard = []
    for tag, kind, gside, xkind in GATES:
        elig = up_runs if gside == "LONG" else dn_runs
        tr = results[tag]; n = len(tr)
        net = sum(t["net"] for t in tr); wins = sum(1 for t in tr if t["net"]>0)
        whys = {}
        for t in tr: whys[t["why"]] = whys.get(t["why"],0)+1
        wstr = " ".join(f"{k}:{v}" for k,v in sorted(whys.items(),key=lambda x:-x[1]))
        pf = net/n if n else 0
        print(f"{tag:18}{elig:>5}{n:>7}{net:>+9.1f}{pf:>+8.1f}{(100*wins/n if n else 0):>5.0f}%   {wstr}")
        scoreboard.append(dict(tag=tag,side=gside,elig=elig,fires=n,net=net,pf=pf,
                               win=(100*wins/n if n else 0),wstr=wstr,detail=fire_detail[tag]))
    tot_fires = sum(s["fires"] for s in scoreboard); tot_net = sum(s["net"] for s in scoreboard)
    print(f"\nTOTAL: {tot_fires} fires across the 43 sat-out runs · net ${tot_net:+.1f}")
    # how many DISTINCT sat-out runs got at least one in-direction fire
    caught_runs = set()
    for tag in results:
        for t in results[tag]: caught_runs.add(t["run"])
    print(f"distinct sat-out runs with >=1 in-direction fire: {len(caught_runs)} / 43")
    import json
    print("JSON_START")
    print(json.dumps(dict(up=up_runs,dn=dn_runs,tot_fires=tot_fires,tot_net=round(tot_net,1),
        distinct=len(caught_runs),board=[{k:v for k,v in s.items()} for s in scoreboard]), default=str))

if __name__ == "__main__":
    main()
