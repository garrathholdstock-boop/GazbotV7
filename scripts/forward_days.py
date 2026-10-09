#!/usr/bin/env python3
"""PAIRED RUN OF FROZEN RULE SETS OVER A LIST OF PRE-CHOSEN DAYS — NO REVIEW, NO REWRITE.

Each arm is `label=rules_path[@v1|@v2]`; days are chosen mechanically by the caller (never holdout, L7).
All arms run on the SAME model, same harness, same `self_aware=True`. Days are scheduled
arm-interleaved so a partial result is always paired. A day is paired only if it is clean
(<=10% errored calls, L7) for EVERY arm. READ-ONLY on the desk: simulated fills, no order path.
`--name` is required so a run can never be filed under another experiment's label.

The model is set with ANTHROPIC_MODEL for this process; sim_week_recursive spawns `claude -p` with the
inherited environment and no --model flag, so every call uses it. The model and rule shas are stamped
into the output, because a Sonnet number is not an Opus number.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
import time

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import sim_week_recursive as SW          # noqa: E402
import paired_arm as PA                  # noqa: E402
from gazbot7.bible import gate           # noqa: E402
from gazbot7.notify import notify, in_quiet_hours   # noqa: E402

POISON = 0.10
OUT = f"{GB}/reports/forward_days"
HOLDOUT = {"2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
           "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"}
CLAIM_RX = re.compile(r"claim|\bbank(ed|ing)?\b|decent profit|best open profit|banks? (it|the|this)", re.I)
_lock = threading.Lock()


def _load(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def is_clean(tag: str, day: str, line: str = "v1", mil: bool = False) -> bool:
    p = f"{SW.OUT}/{tag}_{day}.json"
    if not os.path.exists(p):
        return False
    rec = json.load(open(p))
    if rec.get("line", "v1") != line:          # made under the other brief: not this arm's day
        return False
    if line in ("v2", "v3") and rec.get("peak_def") != "1m":   # old-page S-line record: no page stamp
        return False
    if line == "v3" and rec.get("page_rev") != SW.PAGE_REV_V3:   # v3 page was revised since this record
        return False
    if bool(rec.get("mil_ctx", False)) != mil:         # made on the other page (S2's MIL line)
        return False
    c = rec.get("calls") or []
    return bool(c) and sum(1 for x in c if x.get("error")) / len(c) <= POISON


def say(msg: str) -> None:
    if not in_quiet_hours(dt.datetime.now(dt.UTC)):
        notify(msg, critical=False, mark=False, weekend_ok=True)


def billing_mode() -> str:
    return "api_credits" if SW._api_env().get("ANTHROPIC_API_KEY") else "subscription"


def recheck_key() -> None:
    """If the API key file appears mid-run, the next call re-probes it once and bills credits."""
    with _lock:
        if billing_mode() == "subscription" and os.path.exists(SW.API_KEY_FILE):
            SW._API_ENV = None
            print(f"  [billing] key file appeared — now {billing_mode()}", flush=True)


def claim_exits(rec: dict) -> list[dict]:
    """Trades whose closing call cites a claim/bank/retrace reason (obedience check)."""
    out = []
    calls = rec.get("calls") or []
    for t in rec["trades"]:
        if t.get("why") != "CLAUDE_EXIT":
            continue
        c = [x for x in calls if x.get("ts", "") >= t["closed"][:19]
             and (x.get("action") or "").upper().startswith(("EXIT", "CLOSE", "CLAIM"))]
        txt = (c[0].get("reason") or "") if c else ""
        if CLAIM_RX.search(txt):
            out.append(t)
    return out


REENTRY_WINDOW_MIN = 60   # rule 6's one-hour clock; IT5's guard window


def _is_cited_claim(p: dict, rec: dict) -> bool:
    return p["points"] > 0 and (p.get("peak_pt") or 0) >= 30 and any(
        p["opened"] == x["opened"] for x in claim_exits(rec))


def _is_proxy_claim(p: dict, rec: dict) -> bool:
    g = (p.get("peak_pt") or 0) - p["points"]
    return p["points"] > 0 and (p.get("peak_pt") or 0) >= 30 and g >= 15 and g >= p["peak_pt"] / 3


def reentries_after_claim(day: str, rec: dict, is_claim) -> list[dict]:
    """P1 (IT5_change.txt): same-side entries inside REENTRY_WINDOW_MIN of a profit-claim with no new
    extreme beyond that trade's best price since it closed. Each entry is judged against the most
    recent prior claim on its side. Reads the 1-min tape; entry minute is included in the scan."""
    bars, _ = SW.load_day(day)
    ep = lambda x: int(dt.datetime.fromisoformat(x).timestamp())
    T, out = rec["trades"], []
    for j, t in enumerate(T):
        prior = [q for q in T[:j] if q["side"][0] == t["side"][0] and is_claim(q, rec)]
        if not prior:
            continue
        q = prior[-1]
        short = q["side"][0] == "S"
        best = q["entry"] - q["peak_pt"] if short else q["entry"] + q["peak_pt"]
        tc, te = ep(q["closed"]), ep(t["opened"])
        gap = (te - tc) / 60
        made = any((b[2] < best - 0.01) if short else (b[1] > best + 0.01) for b in bars if tc <= b[0] <= te)
        if not made and gap <= REENTRY_WINDOW_MIN:
            out.append({"day": day, "side": t["side"], "opened": t["opened"], "gap_min": round(gap),
                        "pnl_usd": t["pnl_usd"], "points": t["points"]})
    return out


def arm_stats(tag: str, days: list[str], rl) -> dict:
    recs = [json.load(open(f"{SW.OUT}/{tag}_{d}.json")) for d in days]
    for r, d in zip(recs, days):
        r["day"] = d
    s = rl.score_week(recs)
    pm = PA.metrics(tag, days) or {}
    s["premature_pct"] = pm.get("premature_pct")
    s["median_hold_min"] = pm.get("median_hold_min")
    peaks = [t for r in recs for t in r["trades"] if (t.get("peak_pt") or 0) >= 30]
    s["trades_peak30"] = len(peaks)
    s["peak30_finishing_le0"] = sum(1 for t in peaks if t["points"] <= 0)
    s["peak30_giveback_pt"] = round(sum(t["peak_pt"] - t["points"] for t in peaks), 1)
    s["claim_exits"] = sum(len(claim_exits(r)) for r in recs)
    s["nets"] = {d: round(r["net_usd"], 2) for d, r in zip(days, recs)}
    for key, fn in (("reentry_cited", _is_cited_claim), ("reentry_proxy", _is_proxy_claim)):
        hits = [h for d, r in zip(days, recs) for h in reentries_after_claim(d, r, fn)]
        s[key] = {"n": len(hits), "usd": round(sum(h["pnl_usd"] for h in hits), 1),
                  "worst_usd": round(min((h["pnl_usd"] for h in hits), default=0), 1), "entries": hits}
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", required=True, help="comma-separated YYYY-MM-DD")
    ap.add_argument("--arm", action="append", required=True,
                    help="label=rules_path[@v1|@v2|@v2+mil] (repeat); @v2+mil adds the S2 MIL line; @v2 selects the strategy-line brief "
                         "(Law 0e), default v1 is the frozen BRIEF")
    ap.add_argument("--prefix", default="snt")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--name", required=True, help="output label for this experiment (no default)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    assert a.workers <= 2, "memory: the box is 7.5GB, workers must be <=2"
    days = sorted(a.days.split(","))
    bad = sorted(set(days) & HOLDOUT)
    assert not bad, f"holdout days in the list: {bad}"
    if a.model != "default":
        os.environ["ANTHROPIC_MODEL"] = a.model
    os.makedirs(OUT, exist_ok=True)
    arms = {}
    for spec in a.arm:
        lab, path = spec.split("=", 1)
        line, mil = "v1", False
        if "@" in path and path.rsplit("@", 1)[1] in ("v1", "v2", "v2+mil", "v3"):
            path, line = path.rsplit("@", 1)
            if line == "v2+mil":
                line, mil = "v2", True
        txt = open(path).read()
        arms[lab] = {"tag": f"{a.prefix}_{lab}", "rules": txt, "path": path, "line": line, "mil": mil,
                     "sha": hashlib.sha256(txt.encode()).hexdigest()[:12]}
    mode = billing_mode()
    print(f"{a.name}: model {a.model}, billing {mode}, {len(days)} days, arms "
          + ", ".join(f"{k}={v['sha']}/{v['line']}{'+mil' if v['mil'] else ''}" for k, v in arms.items()), flush=True)

    def one(d: str, lab: str):
        if PA.avail_mb() < PA.MEM_FLOOR_MB:
            time.sleep(60)
            if PA.avail_mb() < PA.MEM_FLOOR_MB:
                print(f"  {lab} {d} DEFERRED (memory)", flush=True)
                return
        recheck_key()
        r = SW.run_day(d, arms[lab]["rules"], arms[lab]["tag"], resume=True, self_aware=True,
                       line=arms[lab]["line"], mil=arms[lab]["mil"])
        e = sum(1 for c in r["calls"] if c.get("error"))
        print(f"  {lab} {d}  ${r['net_usd']:>+9,.2f}  {len(r['trades'])} tr  {e}/{len(r['calls'])} err",
              flush=True)

    if not a.report_only:
        half_sent = False
        for pass_no in (1, 2, 3):
            todo = [(d, lab) for d in days for lab in arms if not is_clean(arms[lab]["tag"], d, arms[lab]["line"], arms[lab]["mil"])]
            if not todo:
                break
            print(f"pass {pass_no}: {len(todo)} day-run(s)", flush=True)
            with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
                futs = [ex.submit(one, d, lab) for d, lab in todo]
                for fut in cf.as_completed(futs):
                    try:
                        fut.result()
                    except Exception as e:
                        print(f"  worker error {type(e).__name__}: {e}", flush=True)
                    done = sum(1 for d in days if all(is_clean(v["tag"], d, v["line"], v["mil"]) for v in arms.values()))
                    if not half_sent and done >= len(days) // 2:
                        half_sent = True
                        say(f"{a.name} ({a.model}): {done}/{len(days)} days done on every arm. "
                            f"No result yet — an interim is never a result.")

    paired = [d for d in days if all(is_clean(v["tag"], d, v["line"], v["mil"]) for v in arms.values())]
    dropped = [d for d in days if d not in paired]
    if not paired:
        print("no paired clean days")
        return 1
    rl = _load(f"{GB}/scripts/recursive_loop.py", "rl")
    stats = {lab: arm_stats(v["tag"], paired, rl) for lab, v in arms.items()}
    rep = {"name": a.name, "model": a.model, "billing": billing_mode(),
           "arms": {k: {"sha": v["sha"], "tag": v["tag"], "rules": v["path"], "line": v["line"], "mil": v["mil"]}
                    for k, v in arms.items()},
           "days_planned": days, "days_paired": paired, "dropped_poisoned_or_missing": dropped,
           "stats": stats, "generated": dt.datetime.now(dt.UTC).isoformat()}
    ch = next((l for l in arms if l != "it2"), None)
    if ch and "it2" in stats:
        ok, why = gate(stats[ch], stats["it2"])
        rep["gate"] = {"passes": ok, "why": why}
        # points given up on runners: challenger claim exits vs IT2's same-side trade opened within 10 min
        given, matched, claimed = 0.0, 0, 0
        for d in paired:
            rc = json.load(open(f"{SW.OUT}/{arms[ch]['tag']}_{d}.json"))
            r2 = json.load(open(f"{SW.OUT}/{arms['it2']['tag']}_{d}.json"))
            for t in claim_exits(rc):
                claimed += 1
                t4 = dt.datetime.fromisoformat(t["opened"])
                for u in r2["trades"]:
                    if u["side"] == t["side"] and abs((dt.datetime.fromisoformat(u["opened"]) - t4).total_seconds()) <= 600:
                        matched += 1
                        given += max(0.0, u["points"] - t["points"])
                        break
        rep["runner_giveup"] = {f"{ch}_claim_exits": claimed, "matched_to_it2_trade": matched,
                                "points_it2_kept_beyond_challenger": round(given, 1)}
        worst = {}
        for lab in (ch, "it2"):
            n = stats[lab]["nets"]
            wd = min(n, key=n.get)
            r = json.load(open(f"{SW.OUT}/{arms[lab]['tag']}_{wd}.json"))
            wt = min(r["trades"], key=lambda t: t["pnl_usd"]) if r["trades"] else None
            worst[lab] = {"day": wd, "net": n[wd], "worst_trade": wt and {k: wt[k] for k in
                          ("side", "opened", "closed", "points", "pnl_usd", "why")}}
        rep["worst_day_detail"] = worst
    json.dump(rep, open(f"{OUT}/{a.name}.json", "w"), indent=1)

    print(f"\n=== RESULT ({a.model}, {rep['billing']}) paired on {len(paired)} day(s) ===")
    for lab, s in stats.items():
        print(f"{lab}: ${s['usd_per_day']:+,.0f}/day · {s['days_positive']}/{s['days']} positive · worst ${s['worst_day']:+,.0f} · "
              f"SD ${s['daily_sd']:,.0f} · {s['trades_per_day']} tr/day · capture {s['capture']} · side {s['side_accuracy']} · "
              f"peak>=30pt trades {s['trades_peak30']} (finished <=0: {s['peak30_finishing_le0']}) · claim-exits {s['claim_exits']} · "
              f"P1 re-entries in window: cited {s['reentry_cited']['n']} (${s['reentry_cited']['usd']:+,.0f}), proxy {s['reentry_proxy']['n']} (${s['reentry_proxy']['usd']:+,.0f})")
    if "gate" in rep:
        print(f"GATE ({ch.upper()} vs IT2): {'PASS' if rep['gate']['passes'] else 'FAIL'} — {rep['gate']['why']}")
        print(f"runner give-up: {rep['runner_giveup']}")
        print(f"worst day: {json.dumps(rep['worst_day_detail'])}")
    if dropped:
        print(f"⚠ excluded (poisoned/missing on at least one arm): {', '.join(dropped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
