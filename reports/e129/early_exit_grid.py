"""E129 EARLY-EXIT GRID (operator 2026-10-29: "If we buy long and it immediately goes short. We sell."). Zero Claude tokens, read-only.
Every recorded entry (E112-E118 Claude replays Oct-Nov 2025 + Oct 2026, the live robot's presses since 10-15, this week's shadow entries that
passed the vote), deduplicated by (minute, side). Rule (X, T): if price goes X points against the fill within the first T minutes, before
the +37.5 target, exit at X+0.25 (stop-first inside a 1-min bar: conservative). Otherwise hold exactly as the desk does (target or 20:40Z flat).
Not modelled: what the freed desk would do after an exit (it could re-enter - better or worse); the +$1,000 lock; overlap between entries.
"""
import glob, json, sys, datetime as dt
sys.path.insert(0, "/home/alphabot/gazbot7/scripts"); sys.path.insert(0, "/home/alphabot/gazbot7/reports/recursive_loop/E112_code")
import mil_labels as ML
_live_minute_bars = ML.minute_bars          # replay's import replaces ML.minute_bars with its backfill reader - keep the live-capture one
import replay as R
UTC = dt.timezone.utc
TGT, THRU, LOTS, PV, FEE = 37.5, 0.25, 4, 2.0, 6.0
ents = {}
for f in glob.glob("/home/alphabot/gazbot7/reports/e112/*_20*.json"):
    try:
        r = json.load(open(f))
    except Exception:
        continue
    for p in r.get("presses") or []:
        if p.get("fill") is None:
            continue
        k = (p["decision_ts"][:16], p["side"])
        ents.setdefault(k, {"src": "replay", "ts": p["decision_ts"], "dir": 1 if p["side"] == "BUY" else -1, "fill": float(p["fill"])})
for l in open("/home/alphabot/gazbot7/data/hybrid_robot.jsonl"):
    if '"PRESS_RESULT"' in l or '"PRESS_' not in l or '"DECISION"' not in l:
        continue
    r = json.loads(l)
    if r.get("dry") or not str(r.get("entry_action", "")).startswith("PRESS_"):
        continue
    k = (r["decision_ts"][:16], "BUY" if r["entry_action"] == "PRESS_BUY" else "SELL")
    ents[k] = {"src": "live", "ts": r["decision_ts"], "dir": 1 if k[1] == "BUY" else -1, "fill": None}
for l in open("/home/alphabot/gazbot7/data/hybrid_overnight_shadow.jsonl"):
    r = json.loads(l)
    if r.get("would_press"):
        k = (r["decision_ts"][:16], "BUY" if r["action"] == "ENTER_LONG" else "SELL")
        ents.setdefault(k, {"src": "shadow", "ts": r["decision_ts"], "dir": 1 if k[1] == "BUY" else -1, "fill": None})
cache = {}
def bars_for(key):
    if key not in cache:
        b = []
        try:
            b = R.day_bars(key)
        except Exception:
            b = []
        if len(b) < 600:
            b = _live_minute_bars(key)
        cache[key] = b
    return cache[key]
paths = []
for k, e in sorted(ents.items()):
    t = dt.datetime.fromisoformat(e["ts"]); op = int(t.timestamp())
    key = (t + dt.timedelta(hours=2)).date().isoformat()          # session key: 22:00Z belongs to the next day
    d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp()); flat = d0 + 20 * 3600 + 2400
    b = bars_for(key)
    prior = [x for x in b if x[0] + 60 <= op]
    if not prior:
        continue
    fill = e["fill"] if e["fill"] is not None else prior[-1][3] + e["dir"] * 0.125
    path = [(x[0], x[1], x[2], x[3]) for x in b if op <= x[0] < flat]
    if len(path) < 30:
        continue
    paths.append({**e, "key": key, "op": op, "fill": fill, "path": path})

def run(X, T):
    out = []
    for p in paths:
        d, fill = p["dir"], p["fill"]; res = None
        for ts, hi, lo, cl in p["path"]:
            adv = (fill - lo) if d > 0 else (hi - fill)
            fav = (hi - fill) if d > 0 else (fill - lo)
            if X is not None and (ts - p["op"]) < T * 60 and adv >= X:
                res = ("STOP", -(X + 0.25) * LOTS * PV - FEE); break
            if fav >= TGT + THRU:
                res = ("TARGET", TGT * LOTS * PV - FEE); break
        if res is None:
            last = p["path"][-1][3]
            res = ("FLAT", d * (last - fill) * LOTS * PV - FEE)
        out.append(res)
    return out

base = run(None, 0)
print(f"entries: {len(paths)} ({sum(1 for p in paths if p['src']=='replay')} replay, {sum(1 for p in paths if p['src']=='live')} live, {sum(1 for p in paths if p['src']=='shadow')} shadow)")
bt = sum(x[1] for x in base); dis = [i for i, x in enumerate(base) if x[1] <= -1000]
print(f"HOLD (the desk today): total ${bt:,.0f}, {sum(1 for x in base if x[0]=='TARGET')} hit target, {len(dis)} disasters (<= -$1,000) totalling ${sum(base[i][1] for i in dis):,.0f}, worst ${min(x[1] for x in base):,.0f}")
rows = []
for X in (20, 30, 40, 60, 80, 100, 150):
    for T in (15, 30, 60, 120, 240, 1440):
        r_ = run(X, T)
        cut = sum(1 for a, b in zip(base, r_) if a[0] == "TARGET" and b[0] == "STOP")
        saved = sum(1 for i in dis if r_[i][0] == "STOP")
        tot = sum(x[1] for x in r_)
        rows.append((tot - bt, X, T, tot, cut, saved, min(x[1] for x in r_)))
print(f"{'X pts':>5} {'T min':>5} {'total':>9} {'vs hold':>9} {'winners cut':>11} {'disasters saved':>15} {'worst trade':>11}")
for d_, X, T, tot, cut, saved, w in sorted(rows, key=lambda x: (x[1], x[2])):
    print(f"{X:>5} {('all day' if T==1440 else T):>5} {tot:>9,.0f} {d_:>+9,.0f} {cut:>11} {saved:>11}/{len(dis):<3} {w:>11,.0f}")
