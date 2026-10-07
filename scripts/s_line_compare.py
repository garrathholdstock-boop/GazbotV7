"""S-line comparison metrics for ONE tag: score_week terms, hold/exit-timing stats, and the S2 rule
violations (against-MIL entries, early repeat entries) recomputed CAUSALLY from the day's bars.
Read-only. S2_change.txt P1-P5 are read from this. Run on sline_s1b for the baseline, sline_s2 after the run."""
from __future__ import annotations
import argparse, datetime as dt, glob, json, os, statistics as st, sys
GB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, f"{GB}/scripts"); sys.path.insert(0, f"{GB}/src")
import sim_week_recursive as SW            # noqa: E402
import recursive_loop as RL                # noqa: E402

EP = lambda s: int(dt.datetime.fromisoformat(s).timestamp())


def measure(tag: str) -> dict:
    recs = [json.load(open(f)) for f in sorted(glob.glob(f"{SW.OUT}/{tag}_20*.json"))]
    recs = [r for r in recs if not (r.get("calls") and sum(1 for c in r["calls"] if c.get("error")) / len(r["calls"]) > 0.10)]
    sc = RL.score_week(recs)
    tr_all, n_ag, n_r4, per_day = [], 0, 0, []
    for r in recs:
        bars, _ = SW.load_day(r["day"])
        tr = sorted(r["trades"], key=lambda t: t["opened"])
        ag = r4 = 0
        for i, t in enumerate(tr):
            m = SW.mil_state([b for b in bars if b[0] <= EP(t["opened"])], tr[:i])
            a = t["side"] == m["against"]
            ag += a
            r4 += (not a) and m["taken"][t["side"]] >= 1 and m["age"] < SW.MIL_T
        n_ag += ag; n_r4 += r4; tr_all += tr
        per_day.append([r["day"], len(tr), round(r["net_usd"]), ag, r4])
    held = [t["held_min"] for t in tr_all]
    n = len(tr_all) or 1
    return {"tag": tag, **sc, "entries": len(tr_all),
            "against_mil": [n_ag, len(tr_all)], "repeat_in_mil_lt_T": [n_r4, len(tr_all)],
            "exits_in_profit": [sum(1 for t in tr_all if t["points"] > 0), len(tr_all)],
            "hold_median_min": st.median(held) if held else None,
            "hold_mean_min": round(st.mean(held), 1) if held else None,
            "exit_within_5min": [sum(1 for h in held if h <= 5), len(held)],
            "exit_within_20min": [sum(1 for h in held if h <= 20), len(held)],
            "worst_trade_usd": min((t["pnl_usd"] for t in tr_all), default=None),
            "per_day[day,entries,net,against,repeat]": per_day}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", required=True); ap.add_argument("--write", default="")
    a = ap.parse_args(); out = measure(a.tag)
    print(json.dumps(out, indent=1))
    if a.write:
        out["stamped"] = dt.datetime.now(dt.UTC).isoformat(); json.dump(out, open(a.write, "w"), indent=1)
