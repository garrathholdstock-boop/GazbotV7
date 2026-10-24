"""E106 scorer (SEPARATE process from e106_run.py: the E6 import patches S.WIN_END_MIN). Reuses e88.py's harness by exec of its definitions only."""
import sys, io, os, json, contextlib, statistics as st, datetime as dt
GB = "/home/alphabot/gazbot7"
src = open(GB + "/reports/recursive_loop/E78_code/e88.py").read().split("\nout = {}")[0]
exec(compile(src, "e88_defs", "exec"))
_full = open(GB + "/reports/recursive_loop/E78_code/e88.py").read()
exec(compile("def claude_set" + _full.split("def claude_set", 1)[1].split("\nif have:")[0], "e88_claude_set", "exec"))
sys.path.insert(0, GB + "/reports/recursive_loop/E78_code")
import sqlite3
_five_parquet = five
def five(day):
    # the lake mirror exports a day late (10-23 is not there until 21:05Z 10-24): fall back to the hot capture.db 5s bars, same source the replay read
    if day in _five: return _five[day]
    r = _five_parquet(day) if day < '2026-10-23' else []
    if r: return r
    d0 = d0_of(day); c = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
    rows = c.execute("SELECT bar_ts, high, low, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>=? AND bar_ts<? ORDER BY bar_ts", (d0 - 7200, d0 + 21 * 3600)).fetchall()
    _five[day] = [(int(t), float(h), float(l), float(cl)) for t, h, l, cl in rows]; return _five[day]
DAYS = ["2026-10-21","2026-10-22","2026-10-23"]
def E(day, hh, mm, ss=0): return int(dt.datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:{ss:02d}+00:00").timestamp())
CUT = {"2026-10-21": E("2026-10-21", 8, 50), "2026-10-22": E("2026-10-22", 5, 25), "2026-10-23": E("2026-10-23", 13, 30)}
CUTLBL = {"2026-10-21": "lock 08:50Z", "2026-10-22": "first lock 05:25Z", "2026-10-23": "no lock; live window ended 13:30Z"}
# sqlite: actual live ledger, flagged lots excluded, grouped by entry (opened_at)
con = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
rows = con.execute("SELECT opened_at, closed_at, pnl_usd, data_quality FROM trades WHERE gate='day_rider' AND opened_at >= '2026-10-21' AND opened_at < '2026-10-24'").fetchall()
def iso(x): return int(dt.datetime.fromisoformat(x).timestamp())
live = {d: {} for d in DAYS}
for o, c, p, q in rows:
    if (q or "").startswith(("EXCLUDE", "BADFILL")): continue
    d = o[:10]
    if d not in live: continue
    e = live[d].setdefault(o, dict(open=iso(o), last=0, usd=0.0, lots=0)); e["last"] = max(e["last"], iso(c)); e["usd"] += p; e["lots"] += 1
H4 = [P.FIX(37.5)] * 4
FLOOR = 20 * 60 + 40
for d in DAYS:
    if d not in TURNS:
        with contextlib.redirect_stdout(io.StringIO()):
            TURNS[d] = E6.confirmed_turns(E6.series_for(d)); DET[d] = P.paths(d)
recs, bad = {}, {}
for d in DAYS:
    f = f"{GB}/reports/sim_week_recursive/e106_post_{d}.json"
    if not os.path.exists(f): bad[d] = "missing"; continue
    r = json.load(open(f)); cl = r.get("calls") or []; e_ = sum(1 for x in cl if x.get("error"))
    r["n_calls"], r["n_errors"] = len(cl), e_
    if not cl or e_ / len(cl) > 0.10: bad[d] = f"poisoned {e_}/{len(cl)}"
    else: recs[d] = r
def hm(ts): return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%H:%M")
out = dict(arm="v1.02-LIVE+POSTLOCK-sim", days=DAYS, bad=bad, per_day={})
L = []; P_ = L.append
P_("E106 v1.02-LIVE+POSTLOCK-sim - ACTUAL live entries up to the cut, then only the slots the live robot did not call are simulated (Claude S1b hybrid, 4 lots all out at +37.5pt, no stop, flat 20:40Z, engine F, IDEAL fills on the sim side). REPLAY after the cut, not forward.")
P_(f"days scored {len(recs)}/{len(DAYS)}; unscored: {bad or 'none'}")
P_("")
P_(f"{'day':11s} {'cut':32s} | LIVE to cut: {'ent':>3s} {'$':>8s} | SIM after: {'calls':>5s} {'claudeE':>7s} {'withleg':>7s} {'blocked':>7s} {'ent':>3s} {'win':>3s} {'$':>8s} | COMBINED {'ent':>3s} {'$':>8s} | LIVE as it ran {'ent':>3s} {'$':>8s}")
tot = dict(cut=0.0, sim=0.0, comb=0.0, ran=0.0)
for d in DAYS:
    le = sorted(live[d].values(), key=lambda x: x["open"])
    pre = [x for x in le if x["open"] < CUT[d]]; allr = le
    pre_usd = sum(x["usd"] for x in pre); ran_usd = sum(x["usd"] for x in allr)
    free = max([x["last"] for x in pre] + [CUT[d]])
    if d not in recs:
        P_(f"{d:11s} {CUTLBL[d]:32s} | {len(pre):>3d} {pre_usd:>8,.0f} | sim: {bad.get(d)}"); continue
    ss = claude_set(d, recs[d]["trades"], "withleg_veto"); kept = [s for s in ss if s["ct"] >= free]
    arr = arrs(d, kept, FLOOR, "F")
    total, n, o = P.run_day_paths(arr, H4, False)
    wins = sum(1 for x in o if x[1] > 0)
    P_(f"{d:11s} {CUTLBL[d]:32s} | {'':13s}{len(pre):>3d} {pre_usd:>8,.0f} | {'':11s}{recs[d]['n_calls']:>5} {len(recs[d]['trades']):>7} {len(ss):>7} {len(ss) - len(kept):>7} {n:>3} {wins:>3} {total:>8,.0f} | {'':9s}{len(pre) + n:>3} {pre_usd + total:>8,.0f} | {'':15s}{len(allr):>3d} {ran_usd:>8,.0f}")
    out["per_day"][d] = dict(cut=CUTLBL[d], live_to_cut=dict(entries=len(pre), usd=round(pre_usd, 2), free_after=hm(free)),
        live_as_ran=dict(entries=len(allr), usd=round(ran_usd, 2), after_cut=[dict(t=hm(x["open"]), usd=round(x["usd"], 2)) for x in allr if x["open"] >= CUT[d]]),
        sim=dict(calls=recs[d]["n_calls"], errors=recs[d]["n_errors"], claude_entries=len(recs[d]["trades"]), with_leg=len(ss), blocked_by_live_pos=len(ss) - len(kept), entries=n, wins=wins, total=round(total),
                 list=[dict(t=hm(x[0]), usd=round(x[1]), lots_hit=sum(x[2])) for x in o]),
        combined=dict(entries=len(pre) + n, usd=round(pre_usd + total, 2)))
    tot["cut"] += pre_usd; tot["sim"] += total; tot["comb"] += pre_usd + total; tot["ran"] += ran_usd
P_(f"{'TOTAL':11s} {'':32s} | live to cut ${tot['cut']:,.0f} | sim after ${tot['sim']:,.0f} | COMBINED ${tot['comb']:,.0f} | live as it ran ${tot['ran']:,.2f}")
P_("")
P_("LIVE ENTRIES (actual): day time lots $ ; * = at/after the cut")
for d in DAYS:
    P_("  " + d + ": " + "; ".join(f"{hm(x['open'])}Z{'*' if x['open'] >= CUT[d] else ''} {x['lots']}lots ${x['usd']:,.0f}" for x in sorted(live[d].values(), key=lambda x: x["open"])))
P_("SIM ENTRIES (after the cut): day time $ lots-on-target")
for d, v in out["per_day"].items():
    P_("  " + d + ": " + ("; ".join(f"{e['t']}Z ${e['usd']:,} ({e['lots_hit']}/4)" for e in v["sim"]["list"]) or "none"))
P_("")
P_("CAVEATS: n=3 days = a story, not a result. Sim side starts FLAT at the cut and Claude is non-deterministic; ideal fills flatter the sim side only (the live side is actual paper fills). Sim entries before the last live lot was out are dropped (rider busy). Thu 22: the live lock leaked (06:25 and 10:40 entries after the 05:25 lock) - 'live to cut' excludes them, 'live as it ran' includes them. Fri 23 never locked: its sim is the PM after the live window. Open positions at 20:40Z flat are marked at the flat. Nothing tuned or applied.")
open(GB + "/reports/recursive_loop/E106_result.json", "w").write(json.dumps(out, indent=1, default=str))
open(GB + "/reports/recursive_loop/E106_result.txt", "w").write("\n".join(L) + "\n")
print("\n".join(L))
