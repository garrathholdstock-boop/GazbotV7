"""S3 measurement: the claim-while-green rule. Reads day records; no credits.
Target = open profit >= K x ATR14(1m) at a look (both numbers are on the page). Rule obeyed = EXIT at that look."""
from __future__ import annotations
import argparse, glob, json, statistics as st, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import sim_week_recursive as SW            # noqa: E402
import s_line_patience as P                # noqa: E402

K = 2.0
PT, RT_COST = 8.0, 4 * 1.50
EP = P.EP


def sgn(side: str) -> int:
    return 1 if side == "LONG" else -1


def trade_looks(bars, calls, t):
    oe, ce = EP(t["opened"]), EP(t["closed"])
    out = []
    for c in calls:
        if not c.get("holding") or c.get("error"):
            continue
        e = EP(c["ts"])
        if oe < e <= ce:
            b = [x for x in bars if x[0] <= e]
            out.append({"ts": c["ts"], "ep": e, "px": c["px"], "action": c["action"],
                        "ahead": sgn(t["side"]) * (c["px"] - t["entry"]),
                        "atr": SW.atr14(b) if len(b) > 15 else 0.0, "reason": (c.get("reason") or "")[:300]})
    return out


def target_looks(bars, calls, trades, k: float = K):
    """FIRST look per trade with ahead >= k*ATR. HOLD there = the claim was not taken."""
    res = []
    for t in trades:
        for lk in trade_looks(bars, calls, t):
            if lk["atr"] and lk["ahead"] >= k * lk["atr"]:
                res.append({**lk, "side": t["side"], "entry": t["entry"], "final": t["pnl_usd"], "held_min": t["held_min"],
                            "peak_pt": t["peak_pt"], "closed": t["closed"], "mark": lk["ahead"] * PT - RT_COST})
                break
    return res


def rebuys(trades, window_min: int):
    """Entries on the SAME side within window_min of an exit that closed in profit."""
    ts = sorted(trades, key=lambda t: t["opened"])
    n, net = 0, 0.0
    for a, b in zip(ts, ts[1:]):
        if a["pnl_usd"] > 0 and b["side"] == a["side"] and (EP(b["opened"]) - EP(a["closed"])) / 60 <= window_min:
            n += 1
            net += b["pnl_usd"]
    return n, net


def claim_rebuys(trades, claims, window_min: int):
    """Entries on the SAME side within window_min after a trade closed by a claim at its target look (the P2 guard)."""
    closed = {c["closed"] for c in claims if c["action"] == "EXIT"}
    ts = sorted(trades, key=lambda t: t["opened"])
    out = []
    for a, b in zip(ts, ts[1:]):
        if a["closed"] in closed and b["side"] == a["side"] and (EP(b["opened"]) - EP(a["closed"])) / 60 <= window_min:
            out.append(b["pnl_usd"])
    return out


def post_exit_extension(bars, t, minutes: int = 30):
    """How much further the market ran in the trade's direction in the `minutes` after its exit (pt, from the exit price)."""
    ce = EP(t["closed"])
    seg = [b for b in bars if ce < b[0] <= ce + minutes * 60]
    if not seg:
        return None
    return max(0.0, (max(b[1] for b in seg) - t["exit"]) if t["side"] == "LONG" else (t["exit"] - min(b[2] for b in seg)))


def measure(tag: str, k: float = K) -> dict:
    recs = [json.load(open(f)) for f in sorted(glob.glob(f"{SW.OUT}/{tag}_20*.json"))]
    ext_profit, ext_claim = [], []
    tl, allt, rb15, rb30, per_day = [], [], [0, 0.0], [0, 0.0], {}
    exits_profit = 0
    crb = []
    for r in recs:
        bars, _ = SW.load_day(r["day"])
        x = target_looks(bars, r["calls"], r["trades"], k)
        tl += x
        allt += r["trades"]
        crb += claim_rebuys(r["trades"], x, 15)
        cl_ts = {y["ts"] for y in x if y["action"] == "EXIT"}
        for t in r["trades"]:
            if t["pnl_usd"] > 0:
                e = post_exit_extension(bars, t)
                if e is not None:
                    ext_profit.append(e)
                    if any(y["side"] == t["side"] and abs(EP(y["ts"]) - EP(t["closed"])) <= 330 for y in x if y["ts"] in cl_ts):
                        ext_claim.append(e)
        per_day[r["day"]] = {"trades": len(r["trades"]), "target_looks": len(x), "claimed": sum(1 for y in x if y["action"] == "EXIT")}
        for w, acc in ((15, rb15), (30, rb30)):
            n, net = rebuys(r["trades"], w)
            acc[0] += n
            acc[1] += net
    n = len(tl)
    claimed = [x for x in tl if x["action"] == "EXIT"]
    held = [x for x in tl if x["action"] != "EXIT"]
    wins = sum(1 for t in allt if t["pnl_usd"] > 0)
    out = {"tag": tag, "k_atr": k, "trades": len(allt), "exits_in_profit": wins,
           "exits_in_profit_share": round(wins / len(allt), 3) if allt else None,
           "trades_reaching_target": n, "reach_share": round(n / len(allt), 3) if allt else None,
           "claimed_at_target": len(claimed), "claim_share": round(len(claimed) / n, 3) if n else None,
           "held_past_target": len(held),
           "held_finished_red": sum(1 for x in held if x["final"] <= 0),
           "held_net_vs_mark": round(sum(x["final"] - x["mark"] for x in held), 0) if held else 0,
           "held_median_delta": round(st.median(x["final"] - x["mark"] for x in held), 0) if held else None,
           "held_deeper_count": sum(1 for x in held if x["final"] < x["mark"]),
           "claimed_net_delta_vs_actual": round(sum(x["mark"] - x["final"] for x in claimed), 0),
           "rebuy_same_side_15min": {"n": rb15[0], "net_usd": round(rb15[1], 0)},
           "rebuy_same_side_30min": {"n": rb30[0], "net_usd": round(rb30[1], 0)},
           "claim_rebuy_15min": {"n": len(crb), "winners": sum(1 for v in crb if v > 0), "net_usd": round(sum(crb), 0)},
           "per_day": per_day}
    out["post_exit_30min_extension_pt"] = {"after_any_profit_exit_median": round(st.median(ext_profit), 1) if ext_profit else None,
                                           "after_any_profit_exit_n": len(ext_profit),
                                           "after_claim_at_target_median": round(st.median(ext_claim), 1) if ext_claim else None,
                                           "after_claim_at_target_n": len(ext_claim)}
    lo = [x for x in tl if x["atr"] < 8]
    hi = [x for x in tl if x["atr"] >= 12]
    out["target_pt_at_look"] = {"median": round(st.median(k * x["atr"] for x in tl), 1) if tl else None,
                                "low_atr_lt8_n": len(lo), "high_atr_ge12_n": len(hi),
                                "low_median_pt": round(st.median(x["ahead"] for x in lo), 1) if lo else None,
                                "high_median_pt": round(st.median(x["ahead"] for x in hi), 1) if hi else None}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sline_s1b")
    ap.add_argument("--k", type=float, default=K)
    ap.add_argument("--write")
    a = ap.parse_args()
    m = measure(a.tag, a.k)
    m["by_k"] = {str(k): {kk: measure(a.tag, k)[kk] for kk in ("trades_reaching_target", "claimed_at_target", "claim_share", "held_past_target", "held_finished_red", "held_net_vs_mark", "held_deeper_count", "claimed_net_delta_vs_actual")} for k in (1.5, 2.0, 3.0)}
    print(json.dumps(m, indent=1))
    if a.write:
        json.dump(m, open(a.write, "w"), indent=1)
