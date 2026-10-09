#!/usr/bin/env python
"""T1 - THE PROFIT-TAKING TRIAL (declared in reports/recursive_loop/T1_change.txt).

ONE technique in isolation: the EXIT. Entries are not Claude's: they are LAB entries placed half way up
each major intraday leg (MIL, 7xATR give-back) from the finished tape - a HINDSIGHT label, disclosed, used
only to take entry skill out of the experiment. Result is a measure of exit skill, never a tradeable P&L.

Mechanic = the operator's own: no looks until the trade first shows +ALERT_FIRST_USD open profit, an alert at
that level and at every +ALERT_STEP_USD above, and from the first alert Claude looks at EVERY completed minute.

Timing is strict and the same for Claude and every baseline: a decision is made at the CLOSE of a completed
1-min bar and FILLED at the close of the NEXT bar (one bar of latency). bar_ts is the minute START, so a bar
is complete only when bar_ts + 60 <= now. Nothing in sim_week_recursive is edited.

  python scripts/t1_profit_take.py --days 2026-03-05 2026-04-30 --baselines        # zero model cost
  python scripts/t1_profit_take.py --days 2026-03-05 --dry                         # mechanics, stub model
  python scripts/t1_profit_take.py --days 2026-03-05 2026-04-30 --model claude-sonnet-5 --workers 2
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, statistics as st, sys, threading

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts"); sys.path.insert(0, f"{GB}/src")
import sim_week_recursive as S

OUT = f"{GB}/reports/recursive_loop/t1"
LOTS, VPP, FEE = S.LOTS, S.VPP, S.FEE_RT
PT_USD = LOTS * VPP                       # $8 per point at 4 lots
ALERT_FIRST_USD, ALERT_STEP_USD = 150.0, 50.0
MAX_TRADES = 8                            # lab constraint (Law 0e forbids a cap in the real line)
MIN_LEG_PT = 60.0                         # a leg smaller than this leaves < $240 of room after the 50% point
MAX_CALLS_DAY = 900
POISON = S.POISON_RATE

T1_BRIEF = f"""You are managing ONE open MNQ position for a discretionary trader. The ENTRY HAS ALREADY BEEN MADE and it was a good one: roughly half way up (or down) a major intraday leg. You have exactly one job: THE EXIT.

HIS TECHNIQUE, which you are copying: he is messaged when a trade first reaches $150 open profit and again at every further $50. From the first message he stops doing anything else and WATCHES, every minute, until he takes the money. You are only called once the trade has reached $150, and then every minute.

WHAT HE WANTS: leave near the top of the move, in profit. Not early (a leg that is still running pays far more than a quick $200), and not late (a trade that was $400 up and finishes at $50, or red, is the failure this trial exists to measure). There is no stop and no target: you are the exit. The page gives you the money, the best so far, the give-back from the best, and the tape since entry. Judge, as he does, whether the move you are in is still driving or has turned.

Money: {LOTS} lots, ${PT_USD:.0f} per point, so $50 = {50/PT_USD:.2f} pt and $150 = {150/PT_USD:.2f} pt. Fees are not shown.

Each look is a fresh call: your last few looks and reasons are printed so you keep the thread. If you say EXIT the position is closed at the close of the NEXT minute.

ANSWER WITH ONE JSON OBJECT AND NOTHING ELSE:
{{"action":"HOLD|EXIT","reason":"<one sentence, name the evidence>"}}"""


# ---------------------------------------------------------------- hindsight legs and lab entries
def hind_legs(bars, K=S.MIL_K):
    n = len(bars); cl = [b[3] for b in bars]; trs = [0.25]
    for i in range(1, n):
        h, lo, pc = bars[i][1], bars[i][2], bars[i - 1][3]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc), 0.25))
    dirn = 1 if cl[10] > cl[0] else -1
    ext, ext_i, start_i, out = cl[10], 10, 0, []
    for i in range(11, n):
        atr = sum(trs[max(1, i - 13):i + 1]) / min(14, i)
        if dirn * (cl[i] - ext) > 0:
            ext, ext_i = cl[i], i
        elif dirn * (ext - cl[i]) >= K * atr:
            out.append([dirn, start_i, ext_i]); start_i = ext_i; dirn = -dirn; ext, ext_i = cl[i], i
    out.append([dirn, start_i, ext_i])
    return out


def lab_entries(day):
    bars, _ = S.load_day(day)
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    ws, we = d0 + S.WIN_START_MIN * 60, d0 + S.WIN_END_MIN * 60
    bw = [b for b in bars if b[0] + 60 <= we]
    ents = []
    for dirn, s, e in hind_legs(bw):
        tot = dirn * (bw[e][3] - bw[s][3])
        if tot < MIN_LEG_PT:
            continue
        half = next(i for i in range(s, e + 1) if dirn * (bw[i][3] - bw[s][3]) >= 0.5 * tot)
        if bw[half][0] < ws or half >= e or half + 1 >= len(bw):
            continue
        ents.append({"dir": dirn, "sig_i": half, "start_i": s, "ext_i": e, "leg_total_pt": round(tot, 1),
                     "ext_px": bw[e][3], "leg_start": bw[s][0], "leg_end": bw[e][0]})
    return bw, ents[:MAX_TRADES], d0


# ---------------------------------------------------------------- the engine (Claude and baselines share it)
def hhmm(ep): return dt.datetime.fromtimestamp(ep, dt.UTC).strftime("%H:%M")


def simulate(bw, ents, policy, day):
    n = len(bw); trades, calls = [], []
    pos = None; pend = []                       # pending actions to fill at the close of bar j
    sig = {e["sig_i"]: e for e in ents}
    for j in range(n):
        px = bw[j][3]
        # 1. fills decided on the previous bar's close, executed at THIS bar's close
        for kind, payload in pend:
            if kind == "EXIT" and pos:
                trades.append(close(pos, px, bw[j][0] + 60, payload))
                pos = None
            elif kind == "ENTER" and pos is None:
                d = payload["dir"]
                pos = {"dir": d, "entry": px + d * S.HALF_SPREAD_PT, "entry_bar": j, "opened": bw[j][0] + 60,
                       "best": 0.0, "best_t": bw[j][0] + 60, "mfe_hl": 0.0, "alerts": [], "alerted": False,
                       "ext_px": payload["ext_px"], "leg_total": payload["leg_total_pt"], "looks": [],
                       "stall_ref": 0.0}
        pend = []
        # 2. mark the position on the completed bar j
        if pos and j > pos["entry_bar"]:
            d = pos["dir"]; pts = d * (px - pos["entry"]); usd = pts * PT_USD
            hl = d * ((bw[j][1] if d > 0 else bw[j][2]) - pos["entry"])
            pos["mfe_hl"] = max(pos["mfe_hl"], hl)
            if pts > pos["best"]:
                pos["best"], pos["best_t"] = pts, bw[j][0] + 60
            lvl = -1 if usd < ALERT_FIRST_USD else int((usd - ALERT_FIRST_USD) // ALERT_STEP_USD)
            while len(pos["alerts"]) <= lvl:
                pos["alerts"].append((ALERT_FIRST_USD + ALERT_STEP_USD * len(pos["alerts"]), bw[j][0] + 60))
                pos["alerted"] = True
            if pos["alerted"]:
                v = policy(bw, j, pos, day, calls)
                if v == "EXIT":
                    pend.append(("EXIT", "CLAUDE_EXIT" if policy.__name__ == "model_policy" else "RULE_EXIT"))
        # 3. a new lab entry: the signal is the close of bar sig_i; the previous trade is closed by the flip
        e = sig.get(j)
        if e and len(trades) + (1 if pos else 0) < MAX_TRADES:
            if pos and not any(k == "EXIT" for k, _ in pend):
                pend.append(("EXIT", "FLIP_NEXT_ENTRY"))
            pend.append(("ENTER", e))
        if j == n - 1:
            if pos:
                trades.append(close(pos, px, bw[j][0] + 60, "WINDOW_CLOSE_1330Z")); pos = None
    return trades, calls


def close(pos, px, t, why):
    d = pos["dir"]; ex = px - d * S.HALF_SPREAD_PT
    pts = d * (ex - pos["entry"])
    avail = d * (pos["ext_px"] - pos["entry"])
    return {"side": "LONG" if d > 0 else "SHORT", "entry": round(pos["entry"], 2), "exit": round(ex, 2),
            "opened": dt.datetime.fromtimestamp(pos["opened"], dt.UTC).isoformat(),
            "closed": dt.datetime.fromtimestamp(t, dt.UTC).isoformat(),
            "held_min": round((t - pos["opened"]) / 60, 1), "points": round(pts, 2),
            "pnl_usd": round(pts * PT_USD - FEE * LOTS, 2), "why": why,
            "alerted": pos["alerted"], "alerts": [(a, hhmm(x)) for a, x in pos["alerts"]],
            "best_pt": round(pos["best"], 2), "mfe_hl_pt": round(pos["mfe_hl"], 2),
            "giveback_pt": round(pos["best"] - pts, 2),
            "avail_pt": round(avail, 2), "leg_total_pt": pos["leg_total"],
            "share_of_leg_remainder": round(pts / avail, 3) if avail > 0 else None,
            "share_of_best": round(pts / pos["best"], 3) if pos["best"] > 0 else None}


# ---------------------------------------------------------------- baselines (zero model cost, same engine)
def _usd(pos, bw, j): return pos["dir"] * (bw[j][3] - pos["entry"]) * PT_USD

def b_hold(bw, j, pos, day, calls): return "HOLD"
def b_first_alert(bw, j, pos, day, calls): return "EXIT"                       # exit at the first alert
def b_take300(bw, j, pos, day, calls): return "EXIT" if _usd(pos, bw, j) >= 300 else "HOLD"
def b_give75(bw, j, pos, day, calls): return "EXIT" if pos["best"] * PT_USD - _usd(pos, bw, j) >= 75 else "HOLD"
def b_stall3(bw, j, pos, day, calls): return "EXIT" if (bw[j][0] + 60 - pos["best_t"]) >= 180 else "HOLD"
def b_oracle(bw, j, pos, day, calls): return "EXIT" if abs(bw[j][3] - pos["ext_px"]) < 1e-9 else "HOLD"
BASELINES = {"B0_hold_to_flip": b_hold, "B1_exit_at_first_alert": b_first_alert, "B2_take_300": b_take300,
             "B3_giveback_75": b_give75, "B4_stall_3min": b_stall3, "B5_oracle_leg_top": b_oracle}


# ---------------------------------------------------------------- the model's page
def page(bw, j, pos, day, calls):
    d = pos["dir"]; px = bw[j][3]; now = bw[j][0] + 60
    pts = d * (px - pos["entry"]); usd = pts * PT_USD
    atr = S.atr14(bw[:j + 1]) or 1.0
    gb = pos["best"] - pts
    L = [f"=== YOUR POSITION  ({day}) ===",
         f"{'LONG' if d > 0 else 'SHORT'} {LOTS} lots, in at {pos['entry']:.2f} at {hhmm(pos['opened'])}Z ({(now - pos['opened'])/60:.0f} min ago)",
         f"NOW {hhmm(now)}Z  price {px:.2f}  (close of the minute that just finished)",
         f"OPEN PROFIT  {pts:+.1f} pt = ${usd:+,.0f}",
         f"BEST SO FAR  {pos['best']:+.1f} pt = ${pos['best']*PT_USD:+,.0f}  at {hhmm(pos['best_t'])}Z ({(now - pos['best_t'])/60:.0f} min ago)",
         f"GIVE-BACK FROM THE BEST  {gb:.1f} pt = ${gb*PT_USD:,.0f}  = {gb/atr:.1f} x ATR   (ATR14 on 1-min = {atr:.1f} pt)",
         "ALERTS you have received: " + ", ".join(f"${int(a)} at {hhmm(t)}Z" for a, t in pos["alerts"]),
         f"next alert at ${int(ALERT_FIRST_USD + ALERT_STEP_USD * len(pos['alerts']))}",
         "", "=== SINCE ENTRY, every 5 min, points from your entry (your direction positive) ==="]
    since = [(bw[k][0] + 60, d * (bw[k][3] - pos["entry"])) for k in range(pos["entry_bar"], j + 1)]
    L.append(" ".join(f"{p:+.0f}" for t, p in since[::5][-40:]))
    L += ["", "=== LAST 15 MINUTES, 1-min bars: time close (high/low), points from your entry ==="]
    for k in range(max(pos["entry_bar"], j - 14), j + 1):
        L.append(f"{hhmm(bw[k][0] + 60)} {d*(bw[k][3]-pos['entry']):+.1f} ({d*(bw[k][1]-pos['entry']):+.1f}/{d*(bw[k][2]-pos['entry']):+.1f})")
    L += ["", "=== THE LAST 4 HOURS, 15-min closes, points relative to NOW (your direction positive) ==="]
    L.append(" ".join(f"{d*(bw[k][3]-px):+.0f}" for k in range(max(0, j - 240), j + 1, 15)))
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    L += ["", f"{(d0 + S.WIN_END_MIN*60 - now)//60} minutes to the 13:30Z flat, when you are closed whatever you say."]
    if pos["looks"]:
        L += ["", "=== YOUR LAST LOOKS IN THIS TRADE ==="] + pos["looks"][-4:]
    return "\n".join(L)


_lock = threading.Lock()
def model_policy(bw, j, pos, day, calls):
    if len([c for c in calls if c.get("day") == day]) >= MAX_CALLS_DAY:
        return "HOLD"
    pg = page(bw, j, pos, day, calls)
    r = S.ask(T1_BRIEF + "\n\n" + pg, timeout=180) if not os.environ.get("T1_DRY") else _stub(pos, bw, j)
    act = "EXIT" if r.get("action") == "EXIT" else "HOLD"
    pos["looks"].append(f"{hhmm(bw[j][0]+60)}Z {act}: {(r.get('reason') or r.get('error') or '')[:160]}")
    calls.append({"day": day, "ts": dt.datetime.fromtimestamp(bw[j][0] + 60, dt.UTC).isoformat(), "px": bw[j][3],
                  "action": act, "error": r.get("error"), "reason": (r.get("reason") or "")[:300]})
    return act


def _stub(pos, bw, j):   # --dry only: exits on a 75$ give-back; proves the plumbing, says nothing about Claude
    return {"action": "EXIT" if pos["best"] * PT_USD - pos["dir"] * (bw[j][3] - pos["entry"]) * PT_USD >= 75 else "HOLD",
            "reason": "stub"}


# ---------------------------------------------------------------- scoring
def score(trades):
    al = [t for t in trades if t["alerted"]]
    avail = sum(t["avail_pt"] for t in trades if t["avail_pt"] > 0)
    best = sum(t["best_pt"] for t in trades)
    return {"n_trades": len(trades), "n_alerted": len(al), "usd": round(sum(t["pnl_usd"] for t in trades), 2),
            "pts": round(sum(t["points"] for t in trades), 1),
            "M1_share_of_leg_remainder": round(sum(t["points"] for t in trades) / avail, 3) if avail else None,
            "M1b_share_of_best": round(sum(t["points"] for t in trades) / best, 3) if best > 0 else None,
            "M2_alerted_closed_in_profit": f"{sum(1 for t in al if t['pnl_usd'] > 0)}/{len(al)}",
            "M3_mean_giveback_pt": round(st.mean(t["giveback_pt"] for t in al), 1) if al else None,
            "M4_alerted_ended_red": sum(1 for t in al if t["pnl_usd"] <= 0),
            "never_alerted": len(trades) - len(al)}


def run_day(day, who, model_mode):
    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/T1_{day}_{who}.json"
    bw, ents, d0 = lab_entries(day)
    policy = model_policy if who == "claude" else BASELINES[who]
    trades, calls = simulate(bw, ents, policy, day)
    errs = sum(1 for c in calls if c.get("error"))
    rec = {"day": day, "who": who, "entries": ents, "trades": trades, "calls": calls, "n_calls": len(calls),
           "error_rate": round(errs / len(calls), 3) if calls else 0.0,
           "poisoned": bool(calls) and errs / len(calls) > POISON,
           "brief_sha": hashlib.sha256(T1_BRIEF.encode()).hexdigest()[:16], "score": score(trades),
           "model": os.environ.get("ANTHROPIC_MODEL"), "dry": bool(os.environ.get("T1_DRY"))}
    json.dump(rec, open(path, "w"), indent=1, default=str)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--baselines", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    if a.baselines:
        for d in a.days:
            for b in BASELINES:
                r = run_day(d, b, False); print(d, b, json.dumps(r["score"]))
        return
    if a.dry:
        os.environ["T1_DRY"] = "1"
    else:
        os.environ["ANTHROPIC_MODEL"] = a.model
        os.environ["ROBOT_NO_TOOLS"] = "1"
    ths = []
    def go(d):
        r = run_day(d, "claude", True); print(d, "claude", json.dumps(r["score"]), "calls", r["n_calls"], "err", r["error_rate"], flush=True)
    for d in a.days:
        t = threading.Thread(target=go, args=(d,)); t.start(); ths.append(t)
        while sum(x.is_alive() for x in ths) >= a.workers:
            ths[0].join(5)
    for t in ths: t.join()

if __name__ == "__main__":
    main()
