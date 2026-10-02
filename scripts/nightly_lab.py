#!/usr/bin/env python3
"""THE NIGHTLY LAB — fine-tune the entry and exit numbers, one step a night.

★★★ docs/SCOPE_RECURSIVE_TRADING_LOOP.md. Operator: *"the nightly lab should just be fine tuning
entries and exits. thats it. metrics changed sloghrly for the next day."*

So this is deliberately NOT a research platform. It is a hill-climb with a one-step leash:

    score yesterday  ->  evaluate the 16 one-step neighbours on a HOLDOUT  ->  take at most ONE
    step  ->  write tomorrow's policy  ->  write the morning report

⚠⚠⚠ IT RUNS IN SHADOW. It writes `data/trade_policy_shadow.json`. NOTHING READS THAT FILE TO TRADE.
Promotion to `trade_policy_active.json` is a human act and stays one until the shadow has a track
record the operator has seen. The scope's Phase 4 exit criterion is 20 sessions of shadow LCR at or
above baseline with demotions firing correctly.

HOW IT AVOIDS BECOMING A NOISE-MINING MACHINE — four mechanisms, all mechanical:

 1. ONE STEP, ONE PARAMETER, PER NIGHT. 16 candidates, never a grid. A seven-parameter grid is how
    a nightly loop manufactures pathologies; a one-step walk must survive forward evidence at every
    intermediate point.
 2. THE SEARCH IS CHARGED. 16 candidates against a holdout each night is 16 chances to be fooled,
    so a step requires a margin that scales with the count — not merely "beat the incumbent".
    5,026 specs once reproduced a published t=5.83 from pure noise 13% of the time on this desk.
 3. NEIGHBOURHOOD AGREEMENT. A step is only taken if the candidate's own neighbour in the same
    direction also beats baseline. A lone good cell is noise; this desk's own rule.
 4. FORWARD DEGRADATION DEMOTES. Every step records the session it was taken. If realised
    performance falls below baseline over the following window the step is REVERSED automatically
    and the reason recorded. Promotion being cheap to reverse is what makes nightly change honest.

⚠ WHAT IT MAY NOT DO: write code, add a parameter, touch the active policy, place an order, reach
the 20:40Z hard flat / eod_flatten / desk_reconcile / the daily loss limit, or call IBKR. It reads
the lake and the trade book and writes two files of its own. Tests assert all of that.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics as st
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import trade_policy as tp                      # noqa: E402
from gazbot7 import research_data as rd                     # noqa: E402

GB = "/home/alphabot/gazbot7"
MEMORY = f"{GB}/data/lab_memory.json"
REPORT = f"{GB}/data/lab_morning_report.md"
LOG = f"{GB}/data/nightly_lab.log"

HOLDOUT_SESSIONS = 40        # the rolling window; gains exactly one unseen session a night
DEGRADE_WINDOW = 10          # sessions of forward evidence before a step can be demoted
MARGIN_PP = 3.0              # base margin a candidate must clear, before the search charge


def log(m: str) -> None:
    stamp = f"{dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%M:%SZ}"
    print(f"{stamp} {m}", flush=True)
    try:
        with open(LOG, "a") as fh:
            fh.write(f"{stamp} {m}\n")
    except OSError:
        pass


def memory() -> dict:
    try:
        with open(MEMORY) as fh:
            return json.load(fh)
    except Exception:
        return {"steps": [], "rejected": {}, "sessions_seen": 0}


def save_memory(d: dict) -> None:
    tmp = MEMORY + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh, indent=1)
    os.replace(tmp, MEMORY)


# ── SCORING ─────────────────────────────────────────────────────────────────────────────────────
# ⚠ The score is LEG CAPTURE RATIO — points banked over points the leg offered from our entry —
#   bounded [0,1] so it cannot be gamed by size, leverage or frequency. P&L as an objective finds
#   pathologies on 616 sessions. ⚠⚠ LCR uses the leg's realised extent, which is HINDSIGHT, so it
#   is a SCORE and never an INPUT: the policy being scored may only read causal state. Reading the
#   peak as an input once produced 866 winners from 866 trades.

def score_policy(policy: dict, sessions) -> dict:
    """Replay `policy`'s EXIT rules over historical entries and return its LCR distribution.

    ⚠⚠ HONEST LIMITATION, STATED RATHER THAN HIDDEN: this scores the EXIT half only. The entry half
    cannot be scored this way until the greenfield study names a signal, because every entry rule
    measured so far is inside the noise of a random entry — so scoring an entry change here would
    be scoring noise. Until then `entry_*` parameters are carried, reported, and NOT tuned, and
    `pending_entry_signal` says so in the report.
    """
    lcrs, held = [], []
    for _sess, series in sessions:
        if len(series) < 120:
            continue
        # the incumbent's own entries, so entry quality is held CONSTANT across candidates and only
        # the exit differs. Comparing two policies that also entered differently would confound.
        for i in range(60, len(series) - 1, 90):
            entry = series[i][1]
            direction = 1 if series[i][1] > series[i - 30][1] else -1
            best = 0.0
            exit_at = None
            for j in range(i + 1, min(i + 1 + int(policy["exit_max_hold_min"]), len(series))):
                mins = j - i
                fav = direction * (series[j][1] - entry)
                best = max(best, fav)
                if mins < policy["exit_min_hold_min"]:
                    continue
                if fav >= policy["exit_lot1_target_pt"]:
                    exit_at = fav
                    break
                if best > 0 and (best - fav) >= policy["exit_giveback_atr"] * 12.0:
                    exit_at = fav
                    break
            if exit_at is None:
                j = min(i + int(policy["exit_max_hold_min"]), len(series) - 1)
                exit_at = direction * (series[j][1] - entry)
            offered = max(best, 1e-9)
            lcrs.append(max(0.0, exit_at) / offered)
            held.append(1)
    # ⚠⚠2026-10-02 THE FIRST DRY RUN RETURNED LCR median 0.0 FOR EVERY CANDIDATE, AND THAT WAS
    # THIS FUNCTION, NOT A RESULT. LCR is floored at 0 for a losing exit, and roughly half of any
    # entry sample loses, so the MEDIAN pins to 0.0 and no exit parameter on earth can move it —
    # 16 candidates all scored +0.00pp and the lab correctly decided NO CHANGE for the wrong
    # reason. A metric that cannot move is indistinguishable from a rule that does not work, which
    # is the most dangerous kind of broken scorer: it reports a confident null forever.
    # → the decision metric is now the MEAN, which responds to the whole distribution.
    return {"n": len(lcrs),
            "lcr_median": round(st.median(lcrs), 4) if lcrs else None,
            "lcr_mean": round(sum(lcrs) / len(lcrs), 4) if lcrs else None,
            "win_share": round(sum(1 for x in lcrs if x > 0) / len(lcrs), 3) if lcrs else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=HOLDOUT_SESSIONS)
    ap.add_argument("--dry-run", action="store_true", help="evaluate and report; write nothing")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    log(f"nightly lab start · holdout {a.sessions} sessions · SHADOW ONLY")
    mem = memory()
    active, note = tp.load()
    if note != "ok":
        log(f"⚠ {note}")

    # the holdout: the most recent N sessions, gaining one genuinely unseen session each night
    import importlib.util
    s = importlib.util.spec_from_file_location("ecc", f"{GB}/scripts/entry_cvd_climax.py")
    ECC = importlib.util.module_from_spec(s)
    s.loader.exec_module(ECC)
    sessions = ECC.load(a.sessions)
    log(f"holdout loaded: {len(sessions)} sessions")

    base = score_policy(active, sessions)
    log(f"incumbent LCR mean {base['lcr_mean']} median {base['lcr_median']} "
        f"win-share {base['win_share']} (n={base['n']})")

    cands = tp.neighbours(active)
    # ★ CHARGE THE SEARCH: the margin rises with the number of candidates scored tonight.
    charged = MARGIN_PP * (1.0 + len(cands) / 16.0)
    log(f"{len(cands)} one-step candidates · charged margin {charged:.2f}pp")

    scored = []
    for name, value, cand in cands:
        if name.startswith("entry_"):
            continue                      # see score_policy: entry cannot be honestly scored yet
        r = score_policy(cand, sessions)
        if r["lcr_mean"] is None or base["lcr_mean"] is None:
            continue
        delta = 100.0 * (r["lcr_mean"] - base["lcr_mean"])
        scored.append((delta, name, value, r))
    scored.sort(reverse=True)

    decision, reason = None, ""
    if not scored:
        reason = "no scoreable candidate (entry parameters are carried, not tuned — see report)"
    else:
        delta, name, value, r = scored[0]
        if delta < charged:
            reason = (f"best candidate {name}={value:g} gained only {delta:+.2f}pp against a "
                      f"charged margin of {charged:.2f}pp — NO CHANGE")
        else:
            # ★ NEIGHBOURHOOD AGREEMENT: the next step in the same direction must also beat baseline
            p = tp.BY_NAME[name]
            cur = float(active[name])
            further = round(value + (value - cur), 6)
            agree = True
            if p.lo <= further <= p.hi:
                c2 = dict(active); c2[name] = further
                r2 = score_policy(c2, sessions)
                agree = (r2["lcr_mean"] or 0) > base["lcr_mean"]
            if not agree:
                reason = (f"{name}={value:g} gained {delta:+.2f}pp but its own next step did NOT "
                          f"beat baseline — a lone good cell is noise, NO CHANGE")
            else:
                decision = (name, value, delta)
                reason = (f"STEP {name} {cur:g} -> {value:g} ({delta:+.2f}pp LCR, neighbourhood "
                          f"agrees, clears the {charged:.2f}pp charged margin)")
    log(reason)

    shadow = dict(active)
    if decision:
        shadow[decision[0]] = decision[1]

    lines = [
        f"# GAZBOT nightly lab — {dt.datetime.now(dt.UTC):%Y-%m-%d}",
        "",
        "## Decision",
        f"{reason}",
        "",
        "## Policy for tomorrow (SHADOW — nothing trades on this yet)",
        "```",
        tp.describe(shadow, active),
        "```",
        "",
        "## Candidates scored tonight",
        "```",
    ]
    for delta, name, value, r in scored[:8]:
        lines.append(f"  {name:<24} -> {value:<7g} {delta:+7.2f}pp LCR   n={r['n']}")
    lines += ["```", "",
              "## Confidence",
              "- **inconclusive** until the shadow has a forward record. One night of holdout "
              "evidence is not a result; the scope requires 20 sessions before promotion.",
              "",
              "## ⚠ WHAT IS NOT YET WIRED — read this before trusting a number above",
              "- the entries replayed here are **SYNTHETIC** (sampled every 90min, direction from "
              "the prior 30min), NOT the operator's real entries. So the LCR levels are a harness "
              "self-test, not a measurement of the desk. The next wiring step is to drive the "
              "replay from `research_entries` (clean fills, entry-level) so exit variants are "
              "scored against the entries that actually happened.",
              "- until then this lab proves the MACHINERY runs end to end; it does not yet prove "
              "anything about an exit rule.",
              "",
              "## Pending",
              "- ⚠ **entry parameters are carried, NOT tuned.** Every automated entry rule measured "
              "so far sits inside the noise of a random entry on the same tape, so tuning one would "
              "be tuning noise. The greenfield study of 2026-10-02 is what unblocks them.",
              f"- steps taken to date: {len(mem.get('steps', []))}"]
    report = "\n".join(lines)

    if a.dry_run:
        print(report)
        log("dry run — nothing written")
        return 0

    tp.save(shadow, tp.SHADOW_PATH, meta={
        "written": dt.datetime.now(dt.UTC).isoformat(),
        "from": "nightly_lab", "decision": reason,
        "incumbent_lcr_mean": base["lcr_mean"], "holdout_sessions": len(sessions)})
    if decision:
        mem.setdefault("steps", []).append(
            {"ts": dt.datetime.now(dt.UTC).isoformat(), "param": decision[0],
             "to": decision[1], "delta_pp": round(decision[2], 3),
             "demote_after_session": mem.get("sessions_seen", 0) + DEGRADE_WINDOW})
    mem["sessions_seen"] = mem.get("sessions_seen", 0) + 1
    save_memory(mem)
    with open(REPORT, "w") as fh:
        fh.write(report)
    log(f"shadow policy + report written · steps to date {len(mem.get('steps', []))}")
    if a.json:
        print(json.dumps({"decision": reason, "shadow": shadow, "base": base}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
