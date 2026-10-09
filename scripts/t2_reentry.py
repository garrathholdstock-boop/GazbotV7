#!/usr/bin/env python
"""T2 - THE RE-ENTRY TRIAL (declared in reports/recursive_loop/T2_change.txt).

T1 showed Claude banks profit well but leaves the giant legs early. T2 asks: after it exits, can it BUY BACK
the same direction to take the next part of the same leg?

Design = a paired increment on T1. The FIRST trade of every leg REPLAYS Claude's own T1 exit decisions (read
from T1_<day>_claude.json), so the only new thing is what happens after the exit. Lab entries, timing (decision
at a completed bar's close, fill at the NEXT bar's close), costs and the 150/+50 alert ladder are T1's.
After an exit the lab watches for WATCH_MIN minutes; a re-entry is the same direction only; a re-entered trade is
watched EVERY minute from its entry (no $150 gate). Re-entries are capped at 8 - (lab entries that day).
The next lab entry cancels the watch and flips as in T1.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, sys, threading
GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts"); sys.path.insert(0, f"{GB}/src")
import t1_profit_take as T
import sim_week_recursive as S

OUT = f"{GB}/reports/recursive_loop/t2"
WATCH_MIN = 60
DAY_CAP = 8
PT_USD, FEE, LOTS = T.PT_USD, T.FEE, T.LOTS

T2_RE_BRIEF = f"""You manage a discretionary trader's MNQ position in a big intraday move. You have JUST CLOSED a trade in profit, on a wobble, while the move might still have further to run. You are now FLAT, and your only question each minute is: has the move you just left RESUMED, so that getting back in the SAME direction is worth it? Or has it really ended, in which case you WAIT.

Facts: {LOTS} lots, ${PT_USD:.0f} per point. A round trip costs about $14 (spread and fees), i.e. under 2 pt, so a wrong buy-back is cheap IF you get out in profit or near flat, but a buy-back on a move that has really ended is an expensive trade that can finish red. Waiting is free: you are called every minute for up to {WATCH_MIN} minutes after your exit, then the watch ends.

HOW HE DOES IT: he does not guess a bottom. He lets the pullback happen, sees price turn and take out the recent high (or low) again, and only then jumps back in to take the next part. A pullback that keeps going, or a tape that has gone flat and tired, is a move that has ended, and then you WAIT. If you buy back, the position has no stop and no target: you will be called every minute from the moment you are in, with the same job as before (leave near the top, in profit).

The page tells you where you left, what you banked, where the high of the move is, how deep the pullback has been, and the tape since. It does not tell you where the move ends: nobody knows that.

ANSWER WITH ONE JSON OBJECT AND NOTHING ELSE:
{{"action":"WAIT|REENTER","reason":"<one sentence, name the evidence>"}}"""

T2_EXIT_ADDENDUM = """

NOTE: if the page begins "RE-ENTRY", this position is a buy-back after you banked an earlier profit in the same move. Same job, and it is watched every minute from its first minute. Leave near the top, in profit."""


# ------------------------------------------------------------------ policies
def make_replay(day):
    j = json.load(open(f"{GB}/reports/recursive_loop/t1/T1_{day}_claude.json"))
    acts = {c["ts"]: c["action"] for c in j["calls"]}
    def replay_first(bw, jx, pos, day_, calls):
        return acts.get(dt.datetime.fromtimestamp(bw[jx][0] + 60, dt.UTC).isoformat(), "HOLD")
    replay_first.__name__ = "replay_t1_claude"
    return replay_first

def re_never(bw, j, w, day, calls): return "WAIT"
def re_immediate(bw, j, w, day, calls): return "REENTER"
def re_oracle(bw, j, w, day, calls):
    return "REENTER" if (bw[j][0] + 120 < w["leg_end"] and w["dir"] * (w["ext_px"] - bw[j][3]) > 2.0) else "WAIT"
def re_RA(bw, j, w, day, calls): return "REENTER" if w["new_high"] else "WAIT"
def re_RB(bw, j, w, day, calls):
    atr = S.atr14(bw[:j + 1]) or 1.0
    return "REENTER" if w["new_high"] and w["pb_before_high"] >= atr else "WAIT"

def _asker(brief):
    def f(page):
        return S.ask(brief + "\n\n" + page, timeout=180)
    return f

def page_watch(bw, j, w, day):
    d = w["dir"]; px = bw[j][3]; now = bw[j][0] + 60
    atr = S.atr14(bw[:j + 1]) or 1.0
    since_exit = d * (px - w["exit_px"])
    L = [f"=== YOU ARE FLAT  ({day}) ===",
         f"You were {'LONG' if d > 0 else 'SHORT'} {LOTS} lots and left at {w['exit_px']:.2f} at {T.hhmm(w['exit_t'])}Z, banking ${w['trade_usd']:+,.0f} net",
         f"NOW {T.hhmm(now)}Z  price {px:.2f}  (close of the minute that just finished)",
         f"SINCE YOUR EXIT  price is {since_exit:+.1f} pt (${since_exit*PT_USD:+,.0f} on {LOTS} lots) in your old direction",
         f"HIGH OF THE MOVE (best close in your direction since your entry)  {w['leg_best']:.2f} = {d*(px-w['leg_best']):+.1f} pt from now ({T.hhmm(w['leg_best_t'])}Z)",
         f"DEEPEST PULLBACK SINCE THAT HIGH  {w['pb_cur']:.1f} pt = {w['pb_cur']/atr:.1f} x ATR   (ATR14 on 1-min = {atr:.1f} pt)",
         f"CURRENT PULLBACK FROM THE HIGH  {max(0.0, d*(w['leg_best']-px)):.1f} pt",
         f"watch ends in {max(0, WATCH_MIN - int((now - w['exit_t'])//60))} min; buy-backs left today: {w['left']}",
         "", "=== LAST 20 MINUTES, 1-min bars: time close (high/low), points from YOUR EXIT price (old direction positive) ==="]
    for k in range(max(0, j - 19), j + 1):
        L.append(f"{T.hhmm(bw[k][0]+60)} {d*(bw[k][3]-w['exit_px']):+.1f} ({d*(bw[k][1]-w['exit_px']):+.1f}/{d*(bw[k][2]-w['exit_px']):+.1f})")
    L += ["", "=== THE LAST 4 HOURS, 15-min closes, points relative to NOW (old direction positive) ==="]
    L.append(" ".join(f"{d*(bw[k][3]-px):+.0f}" for k in range(max(0, j - 240), j + 1, 15)))
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    L += ["", f"{(d0 + S.WIN_END_MIN*60 - now)//60} minutes to the 13:30Z flat."]
    if w["looks"]:
        L += ["", "=== YOUR LAST LOOKS ==="] + w["looks"][-4:]
    return "\n".join(L)

_dry = lambda: bool(os.environ.get("T1_DRY"))

def claude_re(bw, j, w, day, calls):
    if len(calls) >= T.MAX_CALLS_DAY: return "WAIT"
    pg = page_watch(bw, j, w, day)
    if _dry():
        r = {"action": "REENTER" if (w["new_high"] and w["pb_before_high"] > 5) else "WAIT", "reason": "stub"}
    else:
        r = S.ask(T2_RE_BRIEF + "\n\n" + pg, timeout=180)
    act = "REENTER" if r.get("action") == "REENTER" else "WAIT"
    w["looks"].append(f"{T.hhmm(bw[j][0]+60)}Z {act}: {(r.get('reason') or r.get('error') or '')[:150]}")
    calls.append({"day": day, "kind": "reentry_look", "ts": dt.datetime.fromtimestamp(bw[j][0] + 60, dt.UTC).isoformat(),
                  "px": bw[j][3], "action": act, "error": r.get("error"), "reason": (r.get("reason") or "")[:300]})
    return act

def claude_exit_re(bw, j, pos, day, calls):
    if len(calls) >= T.MAX_CALLS_DAY: return "HOLD"
    pg = "RE-ENTRY: this position is a buy-back after you banked an earlier profit in the same move.\n" + T.page(bw, j, pos, day, calls)
    if _dry():
        r = {"action": "EXIT" if pos["best"] * PT_USD - pos["dir"] * (bw[j][3] - pos["entry"]) * PT_USD >= 75 else "HOLD", "reason": "stub"}
    else:
        r = S.ask(T.T1_BRIEF + T2_EXIT_ADDENDUM + "\n\n" + pg, timeout=180)
    act = "EXIT" if r.get("action") == "EXIT" else "HOLD"
    pos["looks"].append(f"{T.hhmm(bw[j][0]+60)}Z {act}: {(r.get('reason') or r.get('error') or '')[:150]}")
    calls.append({"day": day, "kind": "reentry_trade_look", "ts": dt.datetime.fromtimestamp(bw[j][0] + 60, dt.UTC).isoformat(),
                  "px": bw[j][3], "action": act, "error": r.get("error"), "reason": (r.get("reason") or "")[:300]})
    return act


# ------------------------------------------------------------------ engine
def _scan(bw, d, i0, j):
    best, best_t, pb_cur, pb_before = None, None, 0.0, 0.0
    for k in range(i0, j + 1):
        c = bw[k][3]
        if best is None or d * c > d * best:
            best, best_t, pb_cur = c, bw[k][0] + 60, 0.0
        else:
            pb_cur = max(pb_cur, d * (best - c))
    return best, best_t, pb_cur

def simulate2(bw, ents, day, first_pol, re_pol, rexit_pol, calls):
    n = len(bw); trades = []; pos = None; pend = []; watch = None; n_re = 0
    max_re = DAY_CAP - len(ents)
    sig = {e["sig_i"]: e for e in ents}
    for j in range(n):
        px = bw[j][3]
        for kind, payload in pend:
            if kind == "EXIT" and pos:
                tr = T.close(pos, px, bw[j][0] + 60, payload); tr["kind"] = pos["kind"]; trades.append(tr)
                was = pos; pos = None
                if payload != "FLIP_NEXT_ENTRY":
                    d = was["dir"]
                    best, best_t, pb_cur = _scan(bw, d, was["entry_bar"], j)
                    watch = {"dir": d, "start": j, "exit_px": px, "exit_t": bw[j][0] + 60, "trade_usd": tr["pnl_usd"],
                             "ext_px": was["ext_px"], "leg_total": was["leg_total"], "leg_end": was["leg_end"], "leg_best": best, "leg_best_t": best_t,
                             "pb_cur": pb_cur, "pb_before_high": 0.0, "new_high": False, "looks": [], "left": max_re - n_re}
            elif kind == "ENTER" and pos is None:
                dd = payload["dir"]; re = bool(payload.get("re"))
                pos = {"dir": dd, "entry": px + dd * S.HALF_SPREAD_PT, "entry_bar": j, "opened": bw[j][0] + 60,
                       "best": 0.0, "best_t": bw[j][0] + 60, "mfe_hl": 0.0, "alerts": [], "alerted": re,
                       "ext_px": payload["ext_px"], "leg_total": payload["leg_total_pt"], "looks": [],
                       "stall_ref": 0.0, "kind": "re" if re else "first", "leg_end": payload["leg_end"]}
                if re: n_re += 1
                watch = None
        pend = []
        if pos and j > pos["entry_bar"]:
            d = pos["dir"]; pts = d * (px - pos["entry"]); usd = pts * PT_USD
            hl = d * ((bw[j][1] if d > 0 else bw[j][2]) - pos["entry"])
            pos["mfe_hl"] = max(pos["mfe_hl"], hl)
            if pts > pos["best"]:
                pos["best"], pos["best_t"] = pts, bw[j][0] + 60
            lvl = -1 if usd < T.ALERT_FIRST_USD else int((usd - T.ALERT_FIRST_USD) // T.ALERT_STEP_USD)
            while len(pos["alerts"]) <= lvl:
                pos["alerts"].append((T.ALERT_FIRST_USD + T.ALERT_STEP_USD * len(pos["alerts"]), bw[j][0] + 60))
                pos["alerted"] = True
            if pos["alerted"]:
                pol = first_pol if pos["kind"] == "first" else rexit_pol
                if pol(bw, j, pos, day, calls) == "EXIT":
                    pend.append(("EXIT", "POLICY_EXIT_" + pos["kind"]))
        if watch and pos is None and not pend:
            d = watch["dir"]
            if j > watch["start"]:
                c = px
                nh = d * c > d * watch["leg_best"]
                watch["new_high"] = nh
                watch["pb_before_high"] = watch["pb_cur"] if nh else 0.0
                if nh:
                    watch["leg_best"], watch["leg_best_t"] = c, bw[j][0] + 60
                    # pb_cur is kept in the dict for the page until after the decision, then reset
                else:
                    watch["pb_cur"] = max(watch["pb_cur"], d * (watch["leg_best"] - c))
            else:
                watch["new_high"] = False
            if (j - watch["start"]) > WATCH_MIN:
                watch = None
            elif n_re < max_re and j < n - 1:
                if re_pol(bw, j, watch, day, calls) == "REENTER":
                    pend.append(("ENTER", {"dir": d, "ext_px": watch["ext_px"], "leg_total_pt": watch["leg_total"], "leg_end": watch["leg_end"], "re": True}))
                elif watch["new_high"]:
                    watch["pb_cur"] = 0.0
        e = sig.get(j)
        if e:
            pend = [p for p in pend if not (p[0] == "ENTER" and p[1].get("re"))]
            watch = None
            if pos and not any(k == "EXIT" for k, _ in pend):
                pend.append(("EXIT", "FLIP_NEXT_ENTRY"))
            pend.append(("ENTER", e))
        if j == n - 1 and pos:
            tr = T.close(pos, px, bw[j][0] + 60, "WINDOW_CLOSE_1330Z"); tr["kind"] = pos["kind"]; trades.append(tr); pos = None
    return trades


# ------------------------------------------------------------------ arms and scoring
def b_first(name): return T.BASELINES[name]
ARMS = {
    "C0_replay_no_reentry": ("replay", re_never, T.b_hold),
    "C1_replay_RA_giveback75": ("replay", re_RA, T.b_give75),
    "C2_replay_RB_giveback75": ("replay", re_RB, T.b_give75),
    "C3_take300_RB_take300": ("B2_take_300", re_RB, T.b_take300),
    "C4_giveback75_RB_giveback75": ("B3_giveback_75", re_RB, T.b_give75),
    "C5_ORACLE_rebuy_while_top_ahead_exit_at_top": ("replay", re_oracle, T.b_oracle),
}

def score2(trades):
    first = [t for t in trades if t["kind"] == "first"]; re = [t for t in trades if t["kind"] == "re"]
    avail = sum(t["avail_pt"] for t in first if t["avail_pt"] > 0)
    pts = sum(t["points"] for t in trades)
    return {"n_trades": len(trades), "n_first": len(first), "n_reentries": len(re),
            "usd": round(sum(t["pnl_usd"] for t in trades), 2), "pts": round(pts, 1),
            "M1_share_of_leg_remainder": round(pts / avail, 3) if avail else None,
            "first_usd": round(sum(t["pnl_usd"] for t in first), 2),
            "reentry_usd": round(sum(t["pnl_usd"] for t in re), 2),
            "reentries_in_profit": f"{sum(1 for t in re if t['pnl_usd'] > 0)}/{len(re)}",
            "reentry_round_trip_cost_usd": round(len(re) * FEE * LOTS, 2),
            "all_trades_in_profit": f"{sum(1 for t in trades if t['pnl_usd'] > 0)}/{len(trades)}"}

def run_day(day, who):
    os.makedirs(OUT, exist_ok=True)
    bw, ents, d0 = T.lab_entries(day)
    calls = []
    if who == "claude":
        first, re_pol, rexit = make_replay(day), claude_re, claude_exit_re
    else:
        f, re_pol, rexit = ARMS[who]
        first = make_replay(day) if f == "replay" else T.BASELINES[f]
    trades = simulate2(bw, ents, day, first, re_pol, rexit, calls)
    errs = sum(1 for c in calls if c.get("error"))
    rec = {"day": day, "who": who, "trades": trades, "calls": calls, "n_calls": len(calls),
           "error_rate": round(errs / len(calls), 3) if calls else 0.0,
           "poisoned": bool(calls) and errs / len(calls) > T.POISON,
           "brief_sha": {"re": hashlib.sha256(T2_RE_BRIEF.encode()).hexdigest()[:16],
                         "exit": hashlib.sha256((T.T1_BRIEF + T2_EXIT_ADDENDUM).encode()).hexdigest()[:16]},
           "score": score2(trades), "dry": _dry(), "model": os.environ.get("ANTHROPIC_MODEL")}
    json.dump(rec, open(f"{OUT}/T2_{day}_{who}{'_dry' if _dry() else ''}.json", "w"), indent=1, default=str)
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--controls", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    if a.controls:
        for d in a.days:
            for w in ARMS:
                r = run_day(d, w); print(d, w, json.dumps(r["score"]))
        return
    if a.dry: os.environ["T1_DRY"] = "1"
    else: os.environ["ANTHROPIC_MODEL"] = a.model; os.environ["ROBOT_NO_TOOLS"] = "1"
    ths = []
    def go(d):
        r = run_day(d, "claude"); print(d, "claude", json.dumps(r["score"]), "calls", r["n_calls"], "err", r["error_rate"], flush=True)
    for d in a.days:
        t = threading.Thread(target=go, args=(d,)); t.start(); ths.append(t)
        while sum(x.is_alive() for x in ths) >= a.workers: ths[0].join(5)
    for t in ths: t.join()

if __name__ == "__main__":
    main()
