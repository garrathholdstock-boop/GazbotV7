"""S3 PATIENCE measurements for ONE tag, read-only, from the day records and the 1-min tape.
A 'spike exit' is an exit whose last 5 minutes moved SPIKE_PT or more against the position (closes).
The one-look-delay figure is the in-sample DELETION counterfactual (exit one 5-min look later at that
bar's close, fee $6/4 lots); it ignores the path the model would take and is an upper bound, not a forecast.
S3_change.txt P1 is read from this. Run on sline_s1b for the stamped baseline, sline_s3 after the run."""
from __future__ import annotations
import argparse, datetime as dt, glob, json, os, statistics as st, sys
GB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, f"{GB}/scripts"); sys.path.insert(0, f"{GB}/src")
import sim_week_recursive as SW            # noqa: E402

EP = lambda s: int(dt.datetime.fromisoformat(s).timestamp())
SPIKE_PT = 15.0       # a measurement convention only; the rule text names no number
LOOK_S = 300
USD_PT = 8.0          # 4 lots x $2
RT_COST = 4 * 1.50   # 4 lots x $1.50 per round trip


def sgn(side: str) -> int:
    return 1 if side == "LONG" else -1


def last5_move_against(bars, side: str, exit_px: float, closed_ep: int) -> float:
    """Points lost over the final 5 minutes: close at closed-300s minus the exit price, signed to the side."""
    c0 = [b for b in bars if b[0] <= closed_ep - LOOK_S]
    return sgn(side) * (c0[-1][3] - exit_px) if c0 else 0.0


def delayed_pnl(bars, side: str, entry: float, closed_ep: int, looks: int = 1) -> float | None:
    tg = [b for b in bars if b[0] <= closed_ep + looks * LOOK_S]
    return None if not tg else sgn(side) * (tg[-1][3] - entry) * USD_PT - RT_COST


def measure(tag: str, spike_pt: float = SPIKE_PT) -> dict:
    recs = [json.load(open(f)) for f in sorted(glob.glob(f"{SW.OUT}/{tag}_20*.json"))]
    rows = []
    for r in recs:
        bars, _ = SW.load_day(r["day"])
        for t in r["trades"]:
            ce = EP(t["closed"])
            rows.append({"day": r["day"], "t": t, "drop": last5_move_against(bars, t["side"], t["exit"], ce),
                         "d1": delayed_pnl(bars, t["side"], t["entry"], ce)})
    n = len(rows) or 1
    sp = [x for x in rows if x["drop"] >= spike_pt]
    red = [x for x in sp if x["t"]["pnl_usd"] < 0]
    grn = [x for x in sp if x["t"]["pnl_usd"] > 0]
    def delta(g):
        return round(sum(x["d1"] - x["t"]["pnl_usd"] for x in g if x["d1"] is not None))
    by_day = {r["day"]: [sum(1 for x in red if x["day"] == r["day"]),
                         sum(1 for x in rows if x["day"] == r["day"])] for r in recs}
    return {"tag": tag, "spike_pt": spike_pt, "exits": len(rows), "red_spike_exits_by_day": by_day,
            "spike_exits": [len(sp), len(rows)], "spike_exit_share": round(len(sp) / n, 3),
            "spike_exits_red": [len(red), len(sp)], "spike_exits_green": [len(grn), len(sp)],
            "red_spike_exit_share": round(len(red) / n, 3),
            "spike_actual_usd": round(sum(x["t"]["pnl_usd"] for x in sp)),
            "one_look_delay_delta_usd": {"all": delta(sp), "red": delta(red), "green": delta(grn)},
            "hold_median_min": st.median([x["t"]["held_min"] for x in rows]) if rows else None}


def trigger_looks(bars, calls, trades, spike_pt: float = SPIKE_PT, later: bool = False, look_s: int = LOOK_S, min_gap_s: int = 0):
    """FIRST look per trade (later=True: every look AFTER the first within the same trade) where the position is red and >= spike_pt against over the last 5 min.
    Returns [(day-less) dict(action, ts)] - the rule's trigger; HOLD there is obedience, EXIT is not."""
    out = []
    for t in trades:
        oe, ce = EP(t["opened"]), EP(t["closed"])
        seen = 0
        for c in calls:
            if not c.get("holding") or c.get("error"):
                continue
            ce_ = EP(c["ts"])
            if not (oe < ce_ <= ce):
                continue
            red = sgn(t["side"]) * (c["px"] - t["entry"]) < 0
            c0 = [b for b in bars if b[0] <= ce_ - look_s]
            move = sgn(t["side"]) * (c0[-1][3] - c["px"]) if c0 else 0.0
            if red and move >= spike_pt:
                seen += 1
                if seen == 1:
                    first_ep = ce_
                if (seen > 1) == later and (not later or ce_ - first_ep >= min_gap_s):
                    out.append({"ts": c["ts"], "action": c["action"], "side": t["side"], "px": c["px"], "entry": t["entry"], "final": t.get("pnl_usd", 0.0), "reason": (c.get("reason") or "")[:300]})
                if not later:
                    break
    return out


def obedience(tag: str, spike_pt: float = SPIKE_PT, look_s: int = LOOK_S, min_gap_s: int = 0) -> dict:
    recs = [json.load(open(f)) for f in sorted(glob.glob(f"{SW.OUT}/{tag}_20*.json"))]
    looks, later = [], []
    for r in recs:
        bars, _ = SW.load_day(r["day"])
        looks += trigger_looks(bars, r["calls"], r["trades"], spike_pt, look_s=look_s)
        later += trigger_looks(bars, r["calls"], r["trades"], spike_pt, later=True, look_s=look_s, min_gap_s=min_gap_s)
    nl = len(later)
    lh = sum(1 for x in later if x["action"] != "EXIT")
    n = len(looks)
    hold = sum(1 for x in looks if x["action"] != "EXIT")
    return {"tag": tag, "spike_pt": spike_pt, "window_min": look_s // 60, "first_trigger_looks": n, "held": hold,
            "exited": n - hold, "hold_share": round(hold / n, 3) if n else None,
            "later_looks": nl, "later_held": lh, "later_hold_share": round(lh / nl, 3) if nl else None}


def wait_distribution(tag: str, spike_pt: float = 20.0, look_s: int = 900) -> dict:
    """For trades whose FIRST trigger look was a HOLD: minutes from that look to the trade's close, and the look's action."""
    recs = [json.load(open(f)) for f in sorted(glob.glob(f"{SW.OUT}/{tag}_20*.json"))]
    mins, per_day, green = [], {}, 0
    for r in recs:
        bars, _ = SW.load_day(r["day"])
        for t in r["trades"]:
            fl = trigger_looks(bars, r["calls"], [t], spike_pt, look_s=look_s)
            if not fl or fl[0]["action"] == "EXIT":
                continue
            m = (EP(t["closed"]) - EP(fl[0]["ts"])) / 60.0
            mins.append(m if m >= 15 or t.get('pnl_usd', 0.0) <= 0 else 15.0)
            if m < 15 and t.get('pnl_usd', 0.0) > 0:
                green += 1
            per_day.setdefault(r["day"], []).append(round(m))
    n = len(mins)
    out = {"spike_pt": spike_pt, "window_min": look_s // 60, "held_first_looks": n, "closed_green_under_15": green}
    if n:
        out.update(median_min=round(st.median(mins), 1), under_10min=sum(1 for m in mins if m < 10),
                   from_10_to_15=sum(1 for m in mins if 10 <= m < 15), at_least_15=sum(1 for m in mins if m >= 15),
                   minutes_sorted=sorted(round(m) for m in mins))
    return out


def held_cost(tag: str, spike_pt: float = SPIKE_PT, look_s: int = LOOK_S) -> dict:
    """P2: trades whose FIRST trigger look was a HOLD - final P&L minus the mark at that look (4 lots, fee)."""
    recs = [json.load(open(f)) for f in sorted(glob.glob(f"{SW.OUT}/{tag}_20*.json"))]
    d = []
    for r in recs:
        bars, _ = SW.load_day(r["day"])
        for x in trigger_looks(bars, r["calls"], r["trades"], spike_pt, look_s=look_s):
            if x["action"] != "EXIT":
                mark = sgn(x["side"]) * (x["px"] - x["entry"]) * USD_PT - RT_COST
                d.append(x["final"] - mark)
    n = len(d)
    return {"spike_pt": spike_pt, "held_trades": n, "net_vs_first_look_usd": round(sum(d)),
            "deeper": sum(1 for v in d if v < 0), "deeper_share": round(sum(1 for v in d if v < 0) / n, 3) if n else None}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", required=True); ap.add_argument("--write", default="")
    a = ap.parse_args()
    m = measure(a.tag)
    m["by_threshold"] = {str(pt): {**{k: measure(a.tag, pt)[k] for k in ("spike_exits", "red_spike_exit_share", "spike_exits_red")},
                                   "obedience": obedience(a.tag, pt), "held_cost": held_cost(a.tag, pt)} for pt in (15.0, 20.0, 25.0)}
    m["page_unit_15min"] = {str(pt): {"obedience": obedience(a.tag, pt, 900), "held_cost": held_cost(a.tag, pt, 900),
                                       "aged_out": obedience(a.tag, pt, 900, min_gap_s=900),
                                       "wait_distribution": wait_distribution(a.tag, pt, 900)}
                            for pt in (20.0, 30.0, 40.0)}
    print(json.dumps(m, indent=1))
    if a.write:
        json.dump(m, open(a.write, "w"), indent=1)
