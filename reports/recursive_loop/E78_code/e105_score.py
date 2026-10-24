"""E105 scorer (SEPARATE process from e105_run.py: the E6 import patches S.WIN_END_MIN). Reuses e88.py's harness by exec of its definitions only."""
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
LIVE = {"2026-10-21": dict(entries=4, net=1178.98, lock="08:46Z", note="locked; 56 slots uncalled; one press never filled"),
        "2026-10-22": dict(entries=5, net=1424.48, lock="05:24Z", note="locked; 53 slots uncalled; one entry opened 8 lots (4 BADFILL)"),
        "2026-10-23": dict(entries=3, net=904.00, lock=None, note="never locked; 138/138 slots, window to 13:25Z")}
for d in DAYS:
    if d not in TURNS:
        with contextlib.redirect_stdout(io.StringIO()):
            TURNS[d] = E6.confirmed_turns(E6.series_for(d)); DET[d] = P.paths(d)
H4 = [P.FIX(37.5)] * 4
FLOOR = 20 * 60 + 40
recs, bad = {}, {}
for d in DAYS:
    f = f"{GB}/reports/sim_week_recursive/e105_full_{d}.json"
    if not os.path.exists(f): bad[d] = "missing"; continue
    r = json.load(open(f)); cl = r.get("calls") or []; e = sum(1 for x in cl if x.get("error"))
    r["n_calls"], r["n_errors"] = len(cl), e
    if not cl or e / len(cl) > 0.10: bad[d] = f"poisoned {e}/{len(cl)}"
    else: recs[d] = r
def cset(day, mode): return claude_set(day, recs[day]["trades"], mode)
def hm(ts): return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%H:%M")
AMEND = 13 * 3600 + 30 * 60
out = dict(arm="v1.02-NOLOCK-replay", days=DAYS, bad=bad, per_day={})
L = []; P_ = L.append
P_("E105 v1.02-NOLOCK-replay - the hybrid over the WHOLE session 02:00Z-19:55Z, 4 lots all out at +37.5pt, no stop, flat 20:40Z, engine F, IDEAL fills. Each day starts FLAT. REPLAY, not forward.")
P_(f"days scored {len(recs)}/{len(DAYS)}; unscored: {bad or 'none'}")
P_("")
P_(f"{'day':11s} {'calls':>5s} {'err':>3s} {'claudeE':>7s} {'withleg':>7s} | NO-LOCK: {'ent':>3s} {'win':>3s} {'AM$':>7s} {'PM$':>7s} {'total$':>8s} | WITH-LOCK(replay): {'lock@':>6s} {'ent':>3s} {'$':>7s} | LIVE: {'ent':>3s} {'$':>8s}")
tot = dict(nolock=0, lock=0, live=0)
for d in DAYS:
    if d not in recs: P_(f"{d}  {bad.get(d)}"); continue
    ss = cset(d, "withleg_veto"); allc = cset(d, "all")
    arr = arrs(d, ss, FLOOR, "F")
    total, n, o = P.run_day_paths(arr, H4, False)
    d0 = d0_of(d)
    am = sum(x[1] for x in o if x[0] < d0 + AMEND); pm = total - am
    wins = sum(1 for x in o if x[1] > 0)
    # lock replay: equity = realised + open marks (5s path), first touch of +1000
    base, lock_ts = 0.0, None
    for ct, pnl, hit, e, a in o:
        for i in range(0, e + 1):
            mark = base + 4 * ((a["pts"][i] - HALF) * P.VPP) - 4 * P.FEE1 if i < e else base + pnl
            if mark >= 1000.0: lock_ts = int(a["ts"][i]); break
        if lock_ts: break
        base += pnl
    kept = [x for x in o if lock_ts is None or x[0] <= lock_ts]
    ltot = sum(x[1] for x in kept)
    lv = LIVE[d]
    P_(f"{d:11s} {recs[d]['n_calls']:>5} {recs[d]['n_errors']:>3} {len(recs[d]['trades']):>7} {len(ss):>7} | NO-LOCK: {n:>3} {wins:>3} {am:>7,.0f} {pm:>7,.0f} {total:>8,.0f} | WITH-LOCK(replay): {hm(lock_ts) + 'Z' if lock_ts else 'none':>6s} {len(kept):>3} {ltot:>7,.0f} | LIVE: {lv['entries']:>3} {lv['net']:>8,.2f}")
    out["per_day"][d] = dict(calls=recs[d]["n_calls"], errors=recs[d]["n_errors"], claude_entries=len(recs[d]["trades"]), with_leg=len(ss), nolock=dict(entries=n, wins=wins, am=round(am), pm=round(pm), total=round(total)),
        lock_replay=dict(lock_at=hm(lock_ts) if lock_ts else None, entries=len(kept), total=round(ltot)), live=lv,
        entries=[dict(t=hm(x[0]), usd=round(x[1]), lots_hit=sum(x[2]), exit_idx=int(x[3])) for x in o])
    tot["nolock"] += total; tot["lock"] += ltot; tot["live"] += lv["net"]
P_(f"{'TOTAL':11s} {'':>5s} {'':>3s} {'':>7s} {'':>7s} | NO-LOCK total ${tot['nolock']:,.0f} | WITH-LOCK(replay) total ${tot['lock']:,.0f} | LIVE total ${tot['live']:,.2f}")
P_("")
P_("ENTRY LIST (no-lock replay): day time $ lots-on-target")
for d, v in out["per_day"].items():
    P_("  " + d + ": " + "; ".join(f"{e['t']}Z ${e['usd']:,} ({e['lots_hit']}/4)" for e in v["entries"]))
P_("")
P_("CAVEATS: n=3 days = a story, not a result. Replay != live: Claude's replay calls differ from the live ones (replay page, sampling) so the replay's entries are NOT the live entries; ideal fills (paper fabricates 0.1% on lots 2-4); flat start 02:00Z; nothing tuned; arms never pooled; lock in the replay is approximated from 5s marks (realised + open 4-lot mark, spread and fee included), and is NOT the live robot's own lock clock. Live column = ledger from reports/hybrid_nightly (includes paper fills and the 10-21 never-filled press / 10-22 8-lot FAULT).")
open(GB + "/reports/recursive_loop/E105_result.json", "w").write(json.dumps(out, indent=1, default=str))
open(GB + "/reports/recursive_loop/E105_result.txt", "w").write("\n".join(L) + "\n")
print("\n".join(L))
