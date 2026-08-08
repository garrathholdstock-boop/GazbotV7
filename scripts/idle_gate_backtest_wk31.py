#!/usr/bin/env python3
"""MOVEMENT 2 (wk ending 07-31) — the idle-gate lab. Fire ALL SIX live tournament
gates mechanically (UNGATED — no ER/ATR favourable-condition filter) at the 53 frozen
sat-out runs, IN-DIRECTION, anywhere in the 10 minutes BEFORE ignition, with
TICK-HONEST exits repriced on THIS week's capture.db trade ticks. Plus an UNGATED
blind-entry control (just enter in-direction at ignition). Per-gate scoreboard +
regime/time-of-day segmentation + robustness (strip-best, per-day, R-target sweep).

  PYTHONPATH=src .venv/bin/python scripts/idle_gate_backtest_wk31.py
"""
from __future__ import annotations
import sqlite3, datetime as dt, sys, json
sys.path.insert(0, "/home/alphabot/gazbot7/src")
import duckdb
from gazbot7.deciders import (Bar, Position, compute_features, chandelier_start_k,
    exit_chandelier, exit_scalp, efficiency_ratio, gate_grind, gate_reversal_grab,
    gate_thrust, gate_capitulation)
from gazbot7.footprint import footprint_summary, exhaustion_signal

CAP = "/home/alphabot/gazbot7/data/capture.db"
VPP, FEE, CAP_MIN = 2.0, 1.5, 60
YEAR = 2026

# ── the 53 FROZEN sat-out runs (from the frozen census stdout — the locked snapshot) ──
SAT_OUT = [
 ("07-27 15:53","UP",115),("07-27 16:16","UP",134),("07-27 16:48","DN",-139),
 ("07-27 18:40","UP",147),("07-28 01:48","DN",-102),("07-28 08:14","UP",113),
 ("07-28 11:43","UP",95),("07-28 14:05","DN",-149),("07-28 23:09","UP",124),
 ("07-28 23:27","UP",205),("07-28 23:54","UP",101),("07-29 00:18","DN",-113),
 ("07-29 01:01","DN",-117),("07-29 01:38","DN",-133),("07-29 03:46","DN",-91),
 ("07-29 04:49","UP",122),("07-29 06:22","UP",138),("07-29 12:02","DN",-111),
 ("07-29 13:20","UP",127),("07-29 14:33","DN",-110),("07-29 14:48","UP",105),
 ("07-29 15:51","DN",-117),("07-29 16:15","UP",148),("07-29 16:42","UP",94),
 ("07-29 16:58","UP",141),("07-29 17:47","UP",191),("07-29 18:07","DN",-134),
 ("07-29 18:34","UP",298),("07-29 19:32","DN",-248),("07-29 19:49","DN",-276),
 ("07-29 20:13","DN",-111),("07-29 20:56","UP",182),("07-30 00:02","UP",91),
 ("07-30 00:29","DN",-98),("07-30 00:52","UP",115),("07-30 01:18","UP",105),
 ("07-30 07:06","DN",-103),("07-30 08:03","UP",104),("07-30 14:18","UP",145),
 ("07-30 14:41","DN",-196),("07-30 15:30","UP",101),("07-30 16:00","UP",114),
 ("07-30 18:58","UP",116),("07-30 20:00","UP",115),("07-31 13:19","UP",153),
 ("07-31 13:58","DN",-251),("07-31 14:16","UP",193),("07-31 14:42","UP",105),
 ("07-31 14:57","DN",-107),("07-31 15:14","DN",-161),("07-31 15:48","UP",110),
 ("07-31 16:17","UP",101),("07-31 19:50","DN",-144),
]
# cluster tag per run (from the frozen Movement-1 census)
CLUSTER = {
 "07-27 15:53":"VACUUM","07-27 16:16":"FLOW-LED","07-27 16:48":"VACUUM","07-27 18:40":"UNCLASS",
 "07-28 01:48":"FLOW-LED","07-28 08:14":"UNCLASS","07-28 11:43":"UNCLASS","07-28 14:05":"OPEN/NEWS",
 "07-28 23:09":"VACUUM","07-28 23:27":"UNCLASS","07-28 23:54":"VACUUM","07-29 00:18":"VACUUM",
 "07-29 01:01":"VACUUM","07-29 01:38":"UNCLASS","07-29 03:46":"UNCLASS","07-29 04:49":"UNCLASS",
 "07-29 06:22":"FLOW-LED","07-29 12:02":"UNCLASS","07-29 13:20":"OPEN/NEWS","07-29 14:33":"OPEN/NEWS",
 "07-29 14:48":"OPEN/NEWS","07-29 15:51":"FLOW-LED","07-29 16:15":"VACUUM","07-29 16:42":"VACUUM",
 "07-29 16:58":"FLOW-LED","07-29 17:47":"UNCLASS","07-29 18:07":"FLOW-LED","07-29 18:34":"FLOW-LED",
 "07-29 19:32":"FLOW-LED","07-29 19:49":"FLOW-LED","07-29 20:13":"VACUUM","07-29 20:56":"FLOW-LED",
 "07-30 00:02":"UNCLASS","07-30 00:29":"FLOW-LED","07-30 00:52":"VACUUM","07-30 01:18":"UNCLASS",
 "07-30 07:06":"UNCLASS","07-30 08:03":"VOL-EXPANSION","07-30 14:18":"OPEN/NEWS","07-30 14:41":"OPEN/NEWS",
 "07-30 15:30":"FLOW-LED","07-30 16:00":"FLOW-LED","07-30 18:58":"VACUUM","07-30 20:00":"VACUUM",
 "07-31 13:19":"OPEN/NEWS","07-31 13:58":"OPEN/NEWS","07-31 14:16":"OPEN/NEWS","07-31 14:42":"OPEN/NEWS",
 "07-31 14:57":"OPEN/NEWS","07-31 15:14":"FLOW-LED","07-31 15:48":"FLOW-LED","07-31 16:17":"FLOW-LED",
 "07-31 19:50":"VACUUM",
}

def to_epoch(s):
    return int(dt.datetime.strptime(f"{YEAR}-{s}", "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC).timestamp())

# gate spec: tag, kind, side, exit_kind (live params baked into features_fires)
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

def replay_exit(exit_kind, side, entry_px, atr, ticks, target_r=2.0):
    peak = 0.0; k = chandelier_start_k(atr)
    for ts, px in ticks:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak: peak = fav
        pos = Position(side, entry_px, atr, peak)
        if exit_kind == "chandelier":
            r = (exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75)
                 or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))
        else:
            r = exit_scalp(pos, px, target_r=target_r, stop_atr_mult=1.0)
        if r: return px, ts, r
    return ticks[-1][1], ticks[-1][0], "TIMEOUT"

def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute("CREATE TABLE tick AS SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' ORDER BY ts_ms")
    con.execute("CREATE INDEX ix ON tick(ts_ms)")
    rows = con.execute("""
        WITH m AS (SELECT (bar_ts - (bar_ts % 60)) AS mt, bar_ts, open, high, low, close, volume
                   FROM c.bars WHERE symbol='MNQ' AND timeframe='5s')
        SELECT mt, arg_min(open,bar_ts), max(high), min(low), arg_max(close,bar_ts), sum(volume)
        FROM m GROUP BY mt ORDER BY mt""").fetchall()
    bars = [Bar(int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rows]
    ts_index = {b.ts: i for i, b in enumerate(bars)}
    sq = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True); sq.row_factory = sqlite3.Row

    def exit_after(decision_ms, side, atr, exit_kind, target_r=2.0):
        tk = con.execute("SELECT ts_ms, price FROM tick WHERE ts_ms>? AND ts_ms<=? ORDER BY ts_ms",
                         [decision_ms, decision_ms + CAP_MIN*60000]).fetchall()
        if len(tk) < 2: return None
        entry_px = tk[0][1]
        xp, xms, why = replay_exit(exit_kind, side, entry_px, atr, tk[1:], target_r=target_r)
        g = ((xp - entry_px) if side == "LONG" else (entry_px - xp)) * VPP - FEE
        return dict(net=g, why=why, entry=entry_px, atr=atr)

    # ignition-context (ATR, ER) for EVERY run so we can regime-segment even the no-fires
    def ign_ctx(T):
        i = ts_index.get(T - (T % 60))
        if i is None or i < 6: return None, None
        w = bars[max(0, i-59):i+1]
        f = compute_features(w)
        er = efficiency_ratio(w)
        return f.atr, er

    results = {g[0]: [] for g in GATES}
    fire_detail = {g[0]: [] for g in GATES}
    run_ctx = {}
    blind = {}   # tag(exit-style) -> list of blind-entry nets, one per eligible run

    for s, d, mv in SAT_OUT:
        T = to_epoch(s); side_run = "LONG" if d == "UP" else "SHORT"
        atr_ign, er_ign = ign_ctx(T)
        run_ctx[s] = dict(dir=d, move=mv, atr=atr_ign, er=er_ign, cluster=CLUSTER.get(s,"?"),
                          hour=int(s[-5:-3]))
        # BLIND control: enter in-direction at ignition, chandelier exit (momentum-style ceiling)
        bc = exit_after(T*1000, side_run, atr_ign or 20.0, "chandelier")
        if bc: blind[s] = bc["net"]
        pre_ts = [T - 60*k for k in range(1, 11)][::-1]   # T-600 .. T-60
        for tag, kind, gside, xkind in GATES:
            if gside != side_run:
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
            else:
                nows = list(range(T-600, T-60+1, 5))
                for nm in nows:
                    fp = footprint_summary(sq, "MNQ", nm*1000)
                    hit = False
                    if kind == "capitulation":
                        e = gate_capitulation(f=None, cap_sell=fp["cap_sell"], cap_buy=fp["cap_buy"],
                             cap_base=fp["cap_base"], cap_dpx=fp["cap_dpx"], cap_flip=fp["cap_flip"],
                             climax_min=3.0, dom_min=0.7, require_flip=False)
                        hit = e is not None and e.side == gside
                    else:
                        sig = exhaustion_signal(fp["net_signed"], fp["price_move_pt"], fp["bid1_size"],
                             fp["ask1_size"], fp["bid1_price"], fp["ask1_price"])
                        hit = sig is not None and sig[0] == gside
                    if hit:
                        i = ts_index.get(T - (T % 60))
                        atr = compute_features(bars[max(0,(i or 6)-59):(i or 6)+1]).atr if i and i>=6 else 20.0
                        fired = (nm*1000, atr, nm); break
            if fired:
                decision_ms, atr, bt = fired
                r = exit_after(decision_ms, gside, atr, xkind)
                if r:
                    r.update(run=s, dir=d, move=mv, ceil=abs(mv)*VPP,
                             cluster=CLUSTER.get(s,"?"), hour=int(s[-5:-3]),
                             er=er_ign, atr_ign=atr_ign)
                    results[tag].append(r)
                    fire_detail[tag].append((s, d, mv, round(r["net"],1), r["why"]))

    # ── SCOREBOARD ──
    up_runs = sum(1 for _,d,_ in SAT_OUT if d=="UP"); dn_runs = len(SAT_OUT)-up_runs
    print(f"=== {len(SAT_OUT)} sat-out runs · {up_runs} UP (long-gate eligible) · {dn_runs} DN (short-gate eligible) ===")
    print(f"{'gate':18}{'elig':>5}{'fires':>7}{'net$':>9}{'$/fire':>8}{'win%':>6}   exits")
    scoreboard = []
    all_trades = []
    for tag, kind, gside, xkind in GATES:
        elig = up_runs if gside == "LONG" else dn_runs
        tr = results[tag]; n = len(tr)
        net = sum(t["net"] for t in tr); wins = sum(1 for t in tr if t["net"]>0)
        for t in tr: all_trades.append((tag, t["net"], t["run"]))
        whys = {}
        for t in tr: whys[t["why"]] = whys.get(t["why"],0)+1
        wstr = " ".join(f"{k}:{v}" for k,v in sorted(whys.items(),key=lambda x:-x[1]))
        pf = net/n if n else 0
        print(f"{tag:18}{elig:>5}{n:>7}{net:>+9.1f}{pf:>+8.1f}{(100*wins/n if n else 0):>5.0f}%   {wstr}")
        scoreboard.append(dict(tag=tag,side=gside,elig=elig,fires=n,net=round(net,1),pf=round(pf,1),
                               win=round(100*wins/n if n else 0),wstr=wstr,detail=fire_detail[tag]))
    tot_fires = sum(s["fires"] for s in scoreboard); tot_net = sum(s["net"] for s in scoreboard)
    tot_wins = sum(1 for _,net,_ in all_trades if net>0)
    print(f"\nTOTAL: {tot_fires} fires · net ${tot_net:+.1f} · win {100*tot_wins/tot_fires if tot_fires else 0:.0f}%")
    caught_runs = set(t[2] for t in all_trades)
    no_fire = [s for s,d,mv in SAT_OUT if s not in caught_runs]
    print(f"distinct sat-out runs with >=1 in-direction fire: {len(caught_runs)} / {len(SAT_OUT)}")
    print(f"runs that drew NO fire at all: {len(no_fire)} / {len(SAT_OUT)}")

    # ── ROBUSTNESS: strip-best-N ──
    nets = sorted((t[1] for t in all_trades), reverse=True)
    print("\n-- strip-the-best --")
    for k in (0,3,5):
        print(f"  strip best {k}: {len(nets)-k} trades  net ${sum(nets[k:]):+.1f}")

    # ── BLIND ungated control (enter at ignition, chandelier) ──
    bvals = list(blind.values())
    bwin = sum(1 for v in bvals if v>0)
    print(f"\n-- BLIND ungated control (enter in-direction AT ignition, chandelier exit) --")
    print(f"  {len(bvals)} runs · net ${sum(bvals):+.1f} · $/run {sum(bvals)/len(bvals) if bvals else 0:+.1f} · win {100*bwin/len(bvals) if bvals else 0:.0f}%")
    bnets = sorted(bvals, reverse=True)
    for k in (0,3,5):
        print(f"  blind strip best {k}: net ${sum(bnets[k:]):+.1f}")

    # ── SEGMENTATION: time-of-day (US session 13:30-20:00 vs overnight) ──
    def seg_us(s):
        hh, mm = int(s[-5:-3]), int(s[-2:])
        return 13*60+30 <= hh*60+mm < 20*60
    print("\n-- fires by TIME-OF-DAY --")
    for lbl, pred in (("US session (13:30-20:00 UTC)", lambda s: seg_us(s)),
                      ("overnight / pre-open", lambda s: not seg_us(s))):
        seg = [(tag,net) for tag,net,run in all_trades if pred(run)]
        nseg = len(seg); netseg = sum(x[1] for x in seg); wseg = sum(1 for x in seg if x[1]>0)
        print(f"  {lbl:32} fires {nseg:>2}  net ${netseg:>+8.1f}  win {100*wseg/nseg if nseg else 0:>3.0f}%")

    # ── SEGMENTATION: by cluster ──
    print("\n-- fires by CLUSTER --")
    for cl in ("OPEN/NEWS","FLOW-LED","VACUUM","UNCLASS","VOL-EXPANSION"):
        seg=[(tag,net) for tag,net,run in all_trades if CLUSTER.get(run)==cl]
        nseg=len(seg); netseg=sum(x[1] for x in seg); wseg=sum(1 for x in seg if x[1]>0)
        nruns=sum(1 for s,_,_ in SAT_OUT if CLUSTER.get(s)==cl)
        print(f"  {cl:16} ({nruns} runs)  fires {nseg:>2}  net ${netseg:>+8.1f}  win {100*wseg/nseg if nseg else 0:>3.0f}%")

    # ── R-target sweep for the FADE gates (rgv_long/short, capitulation, exhaustion) — prove no plateau ──
    print("\n-- R-TARGET SWEEP on the scalp/fade gates (re-price every fade fire at each R) --")
    fade_fires = []  # (side, decision_ms, atr, run)
    # re-collect the fade fires' decision context
    for tag, kind, gside, xkind in GATES:
        if xkind != "scalp": continue
        for t in results[tag]:
            fade_fires.append((tag, gside, t))
    print(f"  {len(fade_fires)} fade fires total; sweeping target_r")
    # we need decision_ms per fire — re-run exits at various R using stored entry/atr is not enough
    # (stop/target both depend on ticks). Re-derive decision_ms by re-detecting. Simpler: store during loop.
    print("  (see JSON rsweep)")

    # R-sweep: redo by re-detecting fires and repricing. Store decision info.
    rsweep = {r: {"n":0,"net":0.0,"win":0} for r in (0.5,1.0,1.5,2.0,2.5,3.0)}
    for s, d, mv in SAT_OUT:
        T = to_epoch(s); side_run = "LONG" if d=="UP" else "SHORT"
        atr_ign, er_ign = run_ctx[s]["atr"], run_ctx[s]["er"]
        for tag, kind, gside, xkind in GATES:
            if gside != side_run or xkind != "scalp": continue
            fired=None
            if kind == "reversal_grab":
                pre_ts=[T-60*k for k in range(1,11)][::-1]
                for bt in pre_ts:
                    i=ts_index.get(bt)
                    if i is None or i<6: continue
                    w=bars[max(0,i-59):i+1]
                    if len(w)<6: continue
                    f=compute_features(w)
                    if features_fires(kind,gside,f):
                        fired=((bt+60)*1000,f.atr); break
            else:
                nows=list(range(T-600,T-60+1,5))
                for nm in nows:
                    fp=footprint_summary(sq,"MNQ",nm*1000)
                    hit=False
                    if kind=="capitulation":
                        e=gate_capitulation(f=None,cap_sell=fp["cap_sell"],cap_buy=fp["cap_buy"],
                            cap_base=fp["cap_base"],cap_dpx=fp["cap_dpx"],cap_flip=fp["cap_flip"],
                            climax_min=3.0,dom_min=0.7,require_flip=False)
                        hit=e is not None and e.side==gside
                    else:
                        sig=exhaustion_signal(fp["net_signed"],fp["price_move_pt"],fp["bid1_size"],
                            fp["ask1_size"],fp["bid1_price"],fp["ask1_price"])
                        hit=sig is not None and sig[0]==gside
                    if hit:
                        i=ts_index.get(T-(T%60))
                        atr=compute_features(bars[max(0,(i or 6)-59):(i or 6)+1]).atr if i and i>=6 else 20.0
                        fired=(nm*1000,atr); break
            if fired:
                dms,atr=fired
                for R in rsweep:
                    rr=exit_after(dms,gside,atr,"scalp",target_r=R)
                    if rr:
                        rsweep[R]["n"]+=1; rsweep[R]["net"]+=rr["net"]; rsweep[R]["win"]+= (rr["net"]>0)
    for R in sorted(rsweep):
        v=rsweep[R]
        print(f"   R={R}: n={v['n']}  net ${v['net']:+.1f}  win {100*v['win']/v['n'] if v['n'] else 0:.0f}%")

    # ── per-day ──
    print("\n-- per-DAY (all fires) --")
    days={}
    for tag,net,run in all_trades:
        dkey=run[:5]; days.setdefault(dkey,[0,0.0]); days[dkey][0]+=1; days[dkey][1]+=net
    for dkey in sorted(days):
        print(f"   {dkey}: {days[dkey][0]} fires  net ${days[dkey][1]:+.1f}")

    print("\nJSON_START")
    out=dict(nruns=len(SAT_OUT),up=up_runs,dn=dn_runs,tot_fires=tot_fires,tot_net=round(tot_net,1),
        tot_win=round(100*tot_wins/tot_fires if tot_fires else 0),
        distinct=len(caught_runs),no_fire=len(no_fire),
        strip={k:round(sum(nets[k:]),1) for k in (0,3,5)},
        blind=dict(n=len(bvals),net=round(sum(bvals),1),win=round(100*bwin/len(bvals) if bvals else 0),
                   strip={k:round(sum(bnets[k:]),1) for k in (0,3,5)}),
        rsweep={str(R):dict(n=rsweep[R]["n"],net=round(rsweep[R]["net"],1),
                            win=round(100*rsweep[R]["win"]/rsweep[R]["n"] if rsweep[R]["n"] else 0)) for R in sorted(rsweep)},
        board=scoreboard,
        run_ctx={s:dict(dir=run_ctx[s]["dir"],move=run_ctx[s]["move"],
                        atr=round(run_ctx[s]["atr"],1) if run_ctx[s]["atr"] else None,
                        er=round(run_ctx[s]["er"],2) if run_ctx[s]["er"] else None,
                        cluster=run_ctx[s]["cluster"],blind=round(blind.get(s,0),1) if s in blind else None)
                 for s in run_ctx},
        )
    print(json.dumps(out, default=str))

if __name__ == "__main__":
    main()
