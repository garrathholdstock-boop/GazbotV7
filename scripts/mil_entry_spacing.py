"""Read-only MIL entry-spacing study. Pre-registered in reports/recursive_loop/MIL_SPACING_PREREG.md."""
import datetime as dt, glob, json, sqlite3, statistics as st, sys, importlib.util
GB = "/home/alphabot/gazbot7"
spec = importlib.util.spec_from_file_location("SW", f"{GB}/scripts/sim_week_recursive.py")
SW = importlib.util.module_from_spec(spec); sys.modules["SW"] = SW; spec.loader.exec_module(SW)
HOLD = {f"2026-09-{d}" for d in (14, 15, 16, 17, 18)} | {f"2026-08-{d}" for d in (17, 18, 19, 20, 21)}

def tracker(bars, k):
    """causal legs: returns list of (dir, start_epoch, ext_epoch) with the last one open; plus leg-at-index."""
    cl = [b[3] for b in bars]; trs = [0.25]
    for i in range(1, len(bars)):
        h, lo, pc = bars[i][1], bars[i][2], bars[i - 1][3]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc), 0.25))
    dirn = 1 if cl[10] > cl[0] else -1
    ext, ext_i = cl[10], 10
    legs = [[dirn, bars[0][0], None]]; leg_at = [0] * len(bars)
    for i in range(11, len(bars)):
        atr = sum(trs[max(1, i - 13):i + 1]) / min(14, i)
        if dirn * (cl[i] - ext) > 0: ext, ext_i = cl[i], i
        elif dirn * (ext - cl[i]) >= k * atr:
            legs[-1][2] = bars[ext_i][0]; dirn = -dirn
            legs.append([dirn, bars[ext_i][0], None]); ext, ext_i = cl[i], i
        leg_at[i] = len(legs) - 1
    return legs, leg_at

def epoch(s): return int(dt.datetime.fromisoformat(s).timestamp())
def q(v, p): v = sorted(v); return round(v[min(len(v) - 1, int(p * len(v)))], 1) if v else None

def operator_days():
    con = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    rows = con.execute("select opened_at,closed_at,side,qty,pnl_usd,coalesce(data_quality,'') from trades "
                       "where entry_source='manual' and symbol='MNQ' order by opened_at").fetchall()
    bad = {r[0][:10] for r in rows if r[5]}
    ent = {}
    for o, c, s, qy, p, _ in rows:
        e = ent.setdefault(o, {"side": s, "opened": o, "qty": 0, "pnl": 0.0, "closed": c})
        e["qty"] += qy; e["pnl"] += p; e["closed"] = max(e["closed"], c)
    days = {}
    for e in ent.values():
        d = e["opened"][:10]
        if d in HOLD or d in bad: continue
        t = epoch(e["opened"]); h = dt.datetime.fromtimestamp(t, dt.UTC)
        if not (2 <= h.hour + h.minute / 60 < 13.5): continue
        days.setdefault(d, []).append({"side": e["side"], "t_open": t, "t_close": epoch(e["closed"]),
                                       "pt": e["pnl"] / (2 * e["qty"])})
    return days

def s1b_days():
    out = {}
    for f in sorted(glob.glob(f"{GB}/reports/sim_week_recursive/sline_s1b_*.json")):
        d = json.load(open(f))
        out[d["day"]] = [{"side": t["side"], "t_open": epoch(t["opened"]), "t_close": epoch(t["closed"]),
                          "pt": t["points"]} for t in d["trades"]]
    return out

def analyse(book, mil_of):
    gaps, per_day, firsts, later, later_after_loss, later_after_win = [], [], [], [], [], []
    blocks = {"R1": [], "R2": [], "R3": []}
    for day, es in book.items():
        es = sorted(es, key=lambda e: e["t_open"]); per_day.append(len(es))
        gaps += [(b["t_open"] - a["t_open"]) / 60 for a, b in zip(es, es[1:])]
        seen = {}
        for e in es:
            m = mil_of(day, e)
            key = (day, m["idx"], e["side"]); prev = seen.get(key)
            if prev is None: firsts.append(e["pt"])
            else:
                later.append(e["pt"]); (later_after_loss if prev["pt"] <= 0 else later_after_win).append(e["pt"])
                blocks["R1"].append(e["pt"])
                if prev["pt"] <= 0:
                    blocks["R2"].append(e["pt"])
                    if (e["t_open"] - prev["t_close"]) / 60 < m["G"]: blocks["R3"].append(e["pt"])
            seen[key] = e
    n = sum(per_day); f = lambda v: {"n": len(v), "sum_pt_lot": round(sum(v), 1), "mean": round(st.mean(v), 1) if v else None}
    return {"days": len(per_day), "entries": n, "entries_per_day": {"mean": round(n / len(per_day), 1), "p25": q(per_day, .25), "median": q(per_day, .5), "p75": q(per_day, .75), "max": max(per_day)},
            "gap_min": {"p25": q(gaps, .25), "median": q(gaps, .5), "p75": q(gaps, .75), "share_lt30": round(sum(g < 30 for g in gaps) / len(gaps), 2) if gaps else None},
            "first_in_mil_side": f(firsts), "second_plus": f(later), "second_plus_after_loss": f(later_after_loss),
            "second_plus_after_win": f(later_after_win), "share_second_plus": round(len(later) / n, 2),
            "rule_blocks": {k: f(v) for k, v in blocks.items()}}

def main():
    op, mo = operator_days(), s1b_days()
    daylist = sorted(set(op) | set(mo)); cache = {}
    mil_stats = {k: {"per_day": [], "gap_h": [], "dur_min": []} for k in (4, 7, 10, 15)}
    for d in daylist:
        bars, _ = SW.load_day(d)
        if len(bars) < 600: print("skip", d, len(bars)); continue
        base = dt.datetime.fromisoformat(d + "T00:00:00+00:00").timestamp()
        lo, hi = base + 2 * 3600, base + 13.5 * 3600
        for k in mil_stats:
            legs, leg_at = tracker(bars, k)
            starts = [l[1] for l in legs[1:] if lo <= l[1] < hi]
            mil_stats[k]["per_day"].append(len(starts))
            mil_stats[k]["gap_h"] += [(b - a) / 3600 for a, b in zip(starts, starts[1:])]
            if k == 7:
                cache[d] = (legs, leg_at, bars)
                mil_stats[k]["dur_min"] += [(l[2] - l[1]) / 60 for l in legs[1:-1] if l[2] and lo <= l[1] < hi]
    med_dur = st.median(mil_stats[7]["dur_min"]); G = med_dur / 4
    def mil_of(day, e):
        legs, leg_at, bars = cache[day]
        i = max(0, min(len(bars) - 1, (e["t_open"] - bars[0][0]) // 60))
        return {"idx": leg_at[i], "G": G}
    ms = {f"{k}xATR": {"mil_per_day_mean": round(st.mean(v["per_day"]), 1), "mil_per_day_median": q(v["per_day"], .5),
                       "gap_hours_p25/med/p75": [q(v["gap_h"], .25), q(v["gap_h"], .5), q(v["gap_h"], .75)]} for k, v in mil_stats.items()}
    keep = lambda b: {d: e for d, e in b.items() if d in cache}
    res = {"days_measured": sorted(cache), "market": ms, "mil7_median_duration_min": round(med_dur), "G_min": round(G),
           "operator_book": analyse(keep(op), mil_of), "s1b_model": analyse(keep(mo), mil_of)}
    json.dump(res, open(f"{GB}/reports/recursive_loop/MIL_SPACING.json", "w"), indent=1)
    print(json.dumps(res, indent=1))
main()
