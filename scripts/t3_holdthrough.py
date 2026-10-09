#!/usr/bin/env python
"""T3 - HOLD-THROUGH TRIAL (declared in reports/recursive_loop/T3_change.txt).

T1 engine unchanged (same hindsight lab entries, $150 first alert / +$50 steps, a look EVERY completed minute from the
first alert, decision at a completed bar's close, fill at the NEXT bar's close, 4 lots, same costs, no re-entry).
What changes is what the exit SEES and is TOLD: a move-so-far block (size, age, pullbacks inside the trade and whether
each was recovered, 5-min structure, day context) and a hold-through brief. Arm A = structure only. Arm B = A + one
descriptive base-rate sentence. Controls = mechanical trailing rules (stops - controls only, never for the line).
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, sys, threading
GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts"); sys.path.insert(0, f"{GB}/src")
import t1_profit_take as T
import sim_week_recursive as S

OUT = f"{GB}/reports/recursive_loop/t3"
LOTS, PT_USD = T.LOTS, T.PT_USD

HEAD = f"""You are managing ONE open MNQ position for a discretionary trader. The ENTRY HAS ALREADY BEEN MADE and it was a good one: roughly half way up (or down) a major intraday leg. You have exactly one job: THE EXIT, and in this trial one skill matters: SITTING THROUGH PULLBACKS INSIDE A BIG RUN WITHOUT SELLING THE MIDDLE OF IT.

HIS TECHNIQUE: he is messaged when a trade first reaches $150 open profit and at every further $50. From the first message he watches every minute. You are only called once the trade has reached $150, then every minute.

WHAT HE WANTS: leave near the top of the move, in profit. A quick $200 on a run that then carries 200 more points is the failure he is trying to fix; a trade that was $400 up and finishes at $50 or red is the other failure. There is no stop and no target: you are the exit.

HOW HE HOLDS A BIG RUN: a pullback inside a trending move is normal, and the tolerance scales with the size of the move: a run that is already 80 points deep can give back far more than one that is 20 points deep without being over. A one-minute wobble, or a dip that finds support above the last 5-minute low (or below the last 5-minute high for a short) and then makes a new best, is not an exit. He leaves when the STRUCTURE breaks: price takes out the last meaningful 5-/15-minute swing against the position and fails to recover it, the pushes in his direction shrink while the pushes against grow, and the page shows it is not just noise. Pullbacks that were recovered earlier in THIS trade are evidence the tape is still trending. When he does decide the run is over he leaves promptly and in profit; he does not wait for the money to evaporate.

Money: {LOTS} lots, ${PT_USD:.0f} per point, so $50 = {50/PT_USD:.2f} pt. Fees are not shown. Each look is a fresh call; your last few looks are printed. If you say EXIT the position is closed at the close of the NEXT minute."""

PRIOR = """

For scale only (descriptive, not a forecast): in this tape the median major move runs about 2 hours 45 minutes and about 245 points, and a move that has already run an hour or more has historically had longer left than one that just started. Nothing tells you where THIS move ends."""

TAIL = """

ANSWER WITH ONE JSON OBJECT AND NOTHING ELSE:
{"action":"HOLD|EXIT","reason":"<one sentence, name the structure evidence>"}"""

BRIEF = {"A": HEAD + TAIL, "B": HEAD + PRIOR + TAIL}


def block(bw, j, pos, day):
    d = pos["dir"]; px = bw[j][3]; now = bw[j][0] + 60
    atr = S.atr14(bw[:j + 1]) or 1.0
    i0 = pos["entry_bar"]; ent = pos["entry"]
    L = ["", "=== THE MOVE SO FAR (your direction positive, points from your entry) ==="]
    L.append(f"best close {pos['best']:+.1f} pt at {T.hhmm(pos['best_t'])}Z; open {d*(px-ent):+.1f}; in the trade {(now-pos['opened'])/60:.0f} min "
             f"= average {pos['best']/max(1,(pos['best_t']-pos['opened'])/60):.2f} pt/min to the best")
    # pullback episodes inside this trade (threshold 1 x current ATR)
    best, best_i, eps, cur = None, None, [], None
    for k in range(i0, j + 1):
        c = d * (bw[k][3] - ent)
        if best is None or c > best:
            if cur: cur["recovered"] = True; eps.append(cur); cur = None
            best, best_i = c, k
        else:
            dd = best - c
            if dd >= atr and cur is None: cur = {"from": best, "depth": dd, "t": bw[k][0] + 60, "recovered": False}
            elif cur: cur["depth"] = max(cur["depth"], dd)
    if cur: eps.append(cur)
    L.append(f"pullbacks of >= 1 x ATR inside this trade: {len(eps)}"
             + (": " + "; ".join(f"{T.hhmm(e['t'])}Z depth {e['depth']:.1f} pt = {e['depth']/atr:.1f}xATR from +{e['from']:.0f} "
                                 f"{'RECOVERED to a new best' if e['recovered'] else 'NOT YET recovered'}" for e in eps[-4:]) if eps else ""))
    gb = pos["best"] - d * (px - ent)
    L.append(f"current give-back from best {gb:.1f} pt = {gb/atr:.1f} x ATR = {100*gb/max(pos['best'],1e-9):.0f}% of the move so far (ATR14 1-min {atr:.1f} pt)")
    L += ["", "=== 5-MIN BARS since entry, last 14 completed: time  close (high/low), points from entry ==="]
    bk = {}
    for k in range(i0, j + 1):
        if (bw[k][0] // 300) not in bk or True:
            bk.setdefault(bw[k][0] // 300, []).append(k)
    rows = []
    for key in sorted(bk):
        ks = bk[key]
        if bw[ks[-1]][0] + 60 > now or (bw[ks[-1]][0] // 60) % 5 != 4 and ks[-1] != j:
            continue
        hi = max(d * (bw[k][1 if d > 0 else 2] - ent) for k in ks); lo = min(d * (bw[k][2 if d > 0 else 1] - ent) for k in ks)
        rows.append(f"{T.hhmm(bw[ks[-1]][0] + 60)} {d*(bw[ks[-1]][3]-ent):+.0f} ({hi:+.0f}/{lo:+.0f})")
    L.append("  ".join(rows[-14:]))
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    day_bars = [b for b in bw[:j + 1] if b[0] >= d0 + 0]
    dh, dl = max(b[1] for b in day_bars), min(b[2] for b in day_bars)
    L += ["", f"=== DAY CONTEXT ===  day high {dh:.2f}, day low {dl:.2f}, range {dh-dl:.0f} pt; price is {(px-dl)/(dh-dl+1e-9)*100:.0f}% of the way up it"]
    return "\n".join(L)


def make_policy(arm):
    def model_policy(bw, j, pos, day, calls):
        if len([c for c in calls if c.get("day") == day]) >= T.MAX_CALLS_DAY: return "HOLD"
        pg = T.page(bw, j, pos, day, calls) + block(bw, j, pos, day)
        if os.environ.get("T1_DRY"):
            r = T._stub(pos, bw, j)
        else:
            r = S.ask(BRIEF[arm] + "\n\n" + pg, timeout=180)
        act = "EXIT" if r.get("action") == "EXIT" else "HOLD"
        pos["looks"].append(f"{T.hhmm(bw[j][0]+60)}Z {act}: {(r.get('reason') or r.get('error') or '')[:160]}")
        calls.append({"day": day, "ts": dt.datetime.fromtimestamp(bw[j][0] + 60, dt.UTC).isoformat(), "px": bw[j][3],
                      "action": act, "error": r.get("error"), "reason": (r.get("reason") or "")[:300]})
        return act
    return model_policy


def atr_trail(k):
    def f(bw, j, pos, day, calls):
        atr = S.atr14(bw[:j + 1]) or 1.0
        return "EXIT" if pos["best"] - pos["dir"] * (bw[j][3] - pos["entry"]) >= k * atr else "HOLD"
    f.__name__ = f"atr{k}"; return f

def frac_trail(fr):
    def f(bw, j, pos, day, calls):
        return "EXIT" if pos["best"] - pos["dir"] * (bw[j][3] - pos["entry"]) >= fr * pos["best"] else "HOLD"
    f.__name__ = f"frac{fr}"; return f

def scaled_trail(k, fr):
    def f(bw, j, pos, day, calls):
        atr = S.atr14(bw[:j + 1]) or 1.0
        gb = pos["best"] - pos["dir"] * (bw[j][3] - pos["entry"])
        return "EXIT" if gb >= max(k * atr, fr * pos["best"]) else "HOLD"
    f.__name__ = f"scaled{k}_{fr}"; return f

CONTROLS = {"K3_trail_3xATR": atr_trail(3), "K4_trail_5xATR": atr_trail(5), "K5_trail_7xATR": atr_trail(7),
            "K6_trail_30pct_of_best": frac_trail(0.30),
            "K7_max3ATR_40pct": scaled_trail(3, 0.40), "K8_max3ATR_50pct": scaled_trail(3, 0.50)}


def run_day(day, who):
    os.makedirs(OUT, exist_ok=True)
    bw, ents, d0 = T.lab_entries(day)
    pol = make_policy(who[-1]) if who.startswith("claude") else CONTROLS[who]
    if who.startswith("claude"): pol.__name__ = "model_policy"
    trades, calls = T.simulate(bw, ents, pol, day)
    errs = sum(1 for c in calls if c.get("error"))
    rec = {"day": day, "who": who, "trades": trades, "calls": calls, "n_calls": len(calls),
           "error_rate": round(errs / len(calls), 3) if calls else 0.0,
           "poisoned": bool(calls) and errs / len(calls) > T.POISON,
           "brief_sha": {k: hashlib.sha256(v.encode()).hexdigest()[:16] for k, v in BRIEF.items()},
           "score": T.score(trades), "dry": bool(os.environ.get("T1_DRY")), "model": os.environ.get("ANTHROPIC_MODEL")}
    json.dump(rec, open(f"{OUT}/T3_{day}_{who}{'_dry' if rec['dry'] else ''}.json", "w"), indent=1, default=str)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--controls", action="store_true")
    ap.add_argument("--arms", nargs="+", default=["A", "B"])
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    if a.controls:
        for d in a.days:
            for w in CONTROLS: print(d, w, json.dumps(run_day(d, w)["score"]))
        return
    if a.dry: os.environ["T1_DRY"] = "1"
    else: os.environ["ANTHROPIC_MODEL"] = a.model; os.environ["ROBOT_NO_TOOLS"] = "1"
    jobs = [(d, "claude_" + arm) for d in a.days for arm in a.arms]
    ths = []
    def go(d, w):
        r = run_day(d, w); print(d, w, json.dumps(r["score"]), "calls", r["n_calls"], "err", r["error_rate"], flush=True)
    for d, w in jobs:
        t = threading.Thread(target=go, args=(d, w)); t.start(); ths.append(t)
        while sum(x.is_alive() for x in ths) >= a.workers: ths[0].join(5)
    for t in ths: t.join()

if __name__ == "__main__":
    main()
