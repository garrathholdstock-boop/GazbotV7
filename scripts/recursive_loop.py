#!/usr/bin/env python3
"""RE-RUN THE WEEK UNTIL IT LEARNS IT — with a held-out week so "learning" means something.

★★★ Operator: *"you need to keep re-doing the week over and over until it learns to do it properly.
we have all weekend. recursive learning claudio. set it up to keep improving until it nails it."*

    iteration N:  run the TRAIN week with the accumulated rules
                  review the WHOLE WEEK, and REWRITE the rules (not append)
                  run the HOLDOUT week with the same rules and NO review
                  stop when the HOLDOUT meets the bar, else iterate

⚠⚠⚠ WHY THE HOLDOUT IS NOT OPTIONAL. Re-running one week with lessons that accumulate IS
OVERFITTING BY CONSTRUCTION. After a few passes the rules can encode "the low prints at 09:11 on
Monday" and the training week will look magnificent while the system has learned nothing
transferable. This desk has measured the shape before: 5,026 specs reproduced a published t=5.83
from pure noise 13% of the time, and 6 of 6 NULL worlds cleared all three naive bars.
→ TRAIN draws a DIFFERENT week each iteration from a pool of EIGHT. HOLDOUT is TWO weeks that are
  never trained on and never reviewed — 14-18 Sep (which holds his two best days, +$1,478 and
  +$1,546) and 17-21 Aug — run with exactly the rules the training pass produced.
  ★ Operator: "will it do random weeks to train itself?" It did not, as first written; he spotted
    that a single fixed training week lets memorisation happen regardless of the rewrite rule,
    because every pass sees the same five days. Varying the week makes a week-specific rule
    actively costly, which is the only thing that really prevents it.
→ **"IT NAILS IT" MEANS THE HOLDOUT NAILS IT.** A rising training curve with a flat holdout is
  memorisation, and the loop says so in its own log rather than celebrating.

⚠⚠ AND THE RULES ARE REWRITTEN, NOT APPENDED. The first design appended ~6 lessons a night: 12 by
Wednesday, 24 by Friday, undifferentiated. That is the leading suspect for why the arm CARRYING the
lessons underperformed the one with none (-$1,960 against +$522 over four days) — advice crowding
out the picture it was supposed to sharpen. So each review returns a CONSOLIDATED set of at most
MAX_RULES.

★★★2026-10-06 THE LAW CHANGED HERE AND THIS LINE IS WHY. It used to end "...and must drop
what has stopped earning its place" — an instruction to rewrite everything, every night. The
loop obeyed it: three iterations each replaced up to ten rules at once, scored $509 / $620 /
$406, and nothing accumulated. Iteration 2's set was the best by every measure and iteration
3 discarded it wholesale. Operator: *"All fine tuning needs to try as best we can to preserve
the configuration of the best iteration and improve it. We can't be trying things and getting
worse."* The full reasoning and the evidence for each law is in docs/FINE_TUNING_BIBLE.md;
these are the ones that bind you.

⚠⚠⚠ L1 — START FROM THE CHAMPION, NEVER A BLANK PAGE. You will be shown THE CHAMPION'S RULE
SET and its score. Reproduce it VERBATIM and change at most ONE rule. You are editing a
working configuration, not writing a new one. Rules you are not changing must come back
word-for-word; rewording a rule you did not mean to change destroys the only record of what
actually changed.

⚠⚠⚠ L2 — ONE RULE PER ITERATION. Exactly one. Not "one theme", not "a few related clauses".
Iteration 1 to 2 changed all ten and moved $111/day, which is inside the ±$324 standard error
of a ten-day mean — so not one dollar of it is attributable to anything. One change a night
accumulates; ten changes a night is a random walk.

⚠⚠⚠ L5 — NEVER REVERSE A RULE ON ONE WEEK'S IMPRESSION. Reversing needs evidence that THAT
RULE failed, not that the week went badly. Iteration 1 said "Target 8-15 entries per session"
and "a session with no trade is a failure"; iteration 2 replaced both with "there is no quota
and a flat session is not a failure". Trades/day fell 6.4 to 4.1 and $/day fell $620 to $406.
If you believe a rule must be reversed, say so explicitly in the CHANGELOG using the word
REVERSE, and name the number that justifies it.

⚠⚠ L9 — DO NOT RE-DERIVE WHAT IS SETTLED. Entries are a coin on a symmetric race (+0.2pp
side-matched, n=174). Turn entries are a coin at every multiple, timeframe and target tested.
A bare stall is a coin. The money is in the asymmetric payoff — 4 lots, no stop, hold to
structure — not in entry timing. A rule aimed at picking better entry moments is aimed at
something already measured as noise.

⚠⚠ L10 — COUNTS BEFORE DOLLARS. One week cannot resolve $/day: the daily spread is ~$1,000.
Median hold, premature-exit rate, leg capture, side accuracy and trades/day are counts and
move well outside their own noise. Aim your change at a COUNT you can name, and say in the
CHANGELOG which count should move and in which direction.
⚠ This is NOT a claim that a few hundred dollars a day is immaterial — it is tens of
thousands a year. It means five days cannot MEASURE it.

⚠ If the week gives you no evidence that any single rule failed, the correct output is the
champion's set returned UNCHANGED with "CHANGELOG: no change — the week gave no reason to
alter the rules." A null iteration is a legitimate and cheap outcome. Churn is not.

⚠ THE BAR IS HIS METHOD, NOT P&L ALONE. His own two best days: 7 of 8 and 13 of 15 trades on the
dominant leg, 41% and 23% of the available points captured, 8 and 15 entries. P&L alone would reward
one lucky trade; this rewards doing it his way.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import statistics as st
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/recursive_loop"
# ★★★2026-10-06 ONE SOURCE OF TRUTH FOR THE LAWS. Operator: *"how do we make the AI always
# abide. Just like Claude code does. If it sits outside CLAUDE.md you don't do it."* So the
# laws are NOT written out in this prompt — they are imported from gazbot7.bible, and
# tests/test_bible_is_enforced.py FAILS if this prompt does not contain every one of them.
# ⚠ Writing them inline here is how they drift: an earlier attempt put them in this module's
# DOCSTRING, which no model reads, and the diff looked correct.
sys.path.insert(0, f"{GB}/src")
from gazbot7.bible import laws as _laws        # noqa: E402

_BIBLE = _laws()
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")

# ★★★2026-10-03 RANDOM TRAINING WEEKS. Operator: "will it do random weeks to train itself?"
# No, as first written — it trained on ONE fixed week, which is the weakness he spotted. Ten full
# weeks of dense 5s tape exist in capture.db (2026-07-27 to 2026-10-02, 50 dense weekdays), so each
# iteration now draws a DIFFERENT training week and the rules have to survive eight of them.
# ⚠ A rule that only works on one week dies on the next draw. That is the point: with a single
#   fixed training week the rewrite constraint slows memorisation but cannot stop it, because every
#   pass sees the same five days. Varying the week makes week-specific rules actively costly.
ALL_WEEKS = [
    ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"],
    ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"],
    ["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"],
    ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"],
    ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"],
    ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"],
    ["2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"],
    ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"],
    ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"],
    ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"],
]
# ⚠⚠ TWO WEEKS PERMANENTLY HELD OUT AND NEVER TRAINED ON, NEVER REVIEWED.
#    14-18 Sept is deliberately one of them: it contains his two best days (+$1,478 and +$1,546),
#    so if the rules learn his method they should show it there — and we will know it was not
#    learned BY looking at those days.
HOLDOUT_WEEKS = [ALL_WEEKS[7], ALL_WEEKS[3]]              # 14-18 Sep, 17-21 Aug
TRAIN_POOL = [w for w in ALL_WEEKS if w not in HOLDOUT_WEEKS]
HOLDOUT = HOLDOUT_WEEKS[0] + HOLDOUT_WEEKS[1]             # both, scored together

MAX_RULES = 10
MAX_ITERS = 12

# ── THE BAR. All four must hold on the HOLDOUT week. ────────────────────────────────────────────
BAR = {"net_usd": 0.0,          # the week must make money
       "trades_per_day": (3.0, 6.0),
       "side_accuracy": 0.75,   # share of trades on the dominant leg — he runs 85-88%
       "capture": 0.15}         # share of the day's leg points taken — he runs 23-41%


def _mod(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


SW = _mod(f"{GB}/scripts/sim_week_recursive.py", "sw")
SP = _mod(f"{GB}/scripts/snake_page.py", "sp")


def log(m: str) -> None:
    line = f"{dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%M:%SZ} {m}"
    print(line, flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/loop.log", "a") as fh:
        fh.write(line + "\n")


def score_week(recs: list) -> dict:
    """His method, measured: side accuracy and leg capture, not just P&L."""
    sides, caps, trades, net = [], [], 0, 0.0
    for rec in recs:
        net += rec["net_usd"]
        trades += len(rec["trades"])
        bars, _ = SW.load_day(rec["day"])
        d0 = int(dt.datetime.fromisoformat(rec["day"] + "T00:00:00+00:00").timestamp())
        vis = [b for b in bars if d0 + 2 * 3600 <= b[0] <= d0 + 13 * 3600 + 1800]
        legs = SP._legs(vis) if len(vis) > 30 else []
        offered = sum(abs(l["pts"]) for l in legs) or 1.0
        got = sum(t["points"] for t in rec["trades"])
        caps.append(max(0.0, got) / offered)
        for t in rec["trades"]:
            ts = int(dt.datetime.fromisoformat(t["opened"]).timestamp())
            for lg in legs:
                if vis[lg["si"]][0] <= ts <= vis[lg["ei"]][0]:
                    sides.append(1 if (t["side"] == "LONG") == (lg["dir"] > 0) else 0)
                    break
    # ★★2026-10-06 CONSISTENCY IS NOW MEASURED, because the operator says it is the point:
    # *"the most important thing is consistency"*. None of the four bar metrics measured it —
    # a $620/day average built from one +$2,022 day and four losses is a different animal
    # from the same average spread evenly, and the bar could not tell them apart.
    # ⚠ `daily_sd` also explains the so-called noise floor: individual days run -$1,180 to
    # +$2,022, an SD near $1,000, so the standard error of a 10-day mean is ~$324 — the
    # figure quoted all weekend as "run-to-run variance" is really just THIS, the sampling
    # error of a short average. Recording it per iteration makes that visible instead of
    # folklore.
    dailies = [r["net_usd"] for r in recs]
    mean = sum(dailies) / max(1, len(dailies))
    sd = (sum((x - mean) ** 2 for x in dailies) / max(1, len(dailies) - 1)) ** 0.5 \
        if len(dailies) > 1 else 0.0
    return {"net_usd": round(net, 2), "trades": trades,
            "trades_per_day": round(trades / max(len(recs), 1), 2),
            "days": len(recs),
            "usd_per_day": round(mean, 2),
            "days_positive": sum(1 for x in dailies if x > 0),
            "daily_sd": round(sd, 2),
            "worst_day": round(min(dailies), 2) if dailies else 0.0,
            "stderr_of_mean": round(sd / (len(dailies) ** 0.5), 2) if dailies else 0.0,
            "side_accuracy": round(sum(sides) / len(sides), 3) if sides else None,
            "capture": round(st.mean(caps), 3) if caps else None}


def meets_bar(s: dict) -> tuple[bool, str]:
    why = []
    if s["net_usd"] <= BAR["net_usd"]:
        why.append(f"net ${s['net_usd']:+,.0f} not positive")
    lo, hi = BAR["trades_per_day"]
    if not (lo <= s["trades_per_day"] <= hi):
        why.append(f"{s['trades_per_day']}/day outside {lo}-{hi}")
    if (s["side_accuracy"] or 0) < BAR["side_accuracy"]:
        why.append(f"side {s['side_accuracy']} < {BAR['side_accuracy']}")
    if (s["capture"] or 0) < BAR["capture"]:
        why.append(f"capture {s['capture']} < {BAR['capture']}")
    return (not why), ("ALL FOUR MET" if not why else "; ".join(why))


CONSOLIDATE = f"""You have just traded a week of MNQ. Below is every day of it: the day drawn as a
picture with your entries and exits on it, the leg table, and your trades.

Write the CONSOLIDATED RULE SET you will trade with next time — at most {MAX_RULES} rules.

{_BIBLE}

⚠ The list must not simply GROW either: the version carrying accumulated lessons LOST $1,960 over
four days while the version carrying NONE made $522 on the identical tape. At most {MAX_RULES}
rules, and a rule you replace is replaced, not appended to.

⚠⚠⚠ EVERY RULE MUST APPLY TO A DAY YOU HAVE NEVER SEEN. You will be tested on a different week and
you will not be told how it went. So:
  · NO prices. "Do not short below 30535" is memorising one Monday.
  · NO clock times unless the rule is genuinely about the session (the open, the US open).
  · NO day names.
  · Each rule must be checkable from what you are actually shown: the picture, the leg list, your
    own trade count and P&L so far, and the clock.
★ The method you are trying to reproduce, measured on the operator's own two best days: 7 of 8 and
13 of 15 trades ON THE DOMINANT LEG, 41% and 23% of the day's available points captured, 8 and 15
entries. He identifies which way the day is going and keeps taking that side. He does not call
turns.

Answer with the numbered rules and nothing else."""


def consolidate(recs: list, prev_rules: str) -> str:
    L = []
    for rec in recs:
        bars, _ = SW.load_day(rec["day"])
        L.append(SP.page(bars, rec["trades"], rec["day"]))
        L.append(f"  your P&L that day: ${rec['net_usd']:+,.2f} over {len(rec['trades'])} trades")
        L.append("")
    # ★2026-10-06 L1 NEEDS THE CHAMPION ON THE PAGE, NOT JUST IN THE PROMPT'S PROSE.
    # Telling the reviewer "start from the champion" while handing it only the CURRENT set is
    # the same mistake as filing a law in a document: it cannot comply with text it cannot
    # see. The champion is the best-scoring iteration by $/day, read from history.json.
    champ_txt, champ_note = "", ""
    try:
        hp_ = f"{OUT}/history.json"
        if os.path.exists(hp_):
            hist = json.load(open(hp_))
            cands = [h for h in hist if (h.get("holdout") or {}).get("usd_per_day") is not None]
            if cands:
                c = max(cands, key=lambda h: h["holdout"]["usd_per_day"])
                cp = f"{OUT}/rules_iter{c['iter']}.txt"
                o = c["holdout"]
                champ_note = (f"THE CHAMPION IS ITERATION {c['iter']}'s SET: "
                              f"${o['usd_per_day']:+,.0f}/day, "
                              f"{o.get('days_positive','?')}/{o.get('days','?')} positive days, "
                              f"daily SD ${o.get('daily_sd',0):,.0f}, "
                              f"worst day ${o.get('worst_day',0):+,.0f}, "
                              f"{o.get('trades_per_day','?')} trades/day. "
                              f"THIS IS THE NUMBER YOU MUST BEAT, and you beat it by editing "
                              f"ONE rule of the set below — not by writing a new set.")
                if os.path.exists(cp):
                    champ_txt = open(cp).read()
    except Exception as e:
        champ_note = f"[champion lookup failed: {type(e).__name__}]"
    if champ_note:
        L += ["=== THE CHAMPION ===", champ_note, ""]
    if champ_txt:
        L += ["THE CHAMPION'S RULE SET — reproduce this VERBATIM with ONE rule changed:",
              champ_txt, ""]
    if prev_rules:
        L += ["THE RULES YOU WERE CARRYING INTO THIS WEEK "
              "(these may NOT be the champion's — if they differ, the champion wins):",
              prev_rules, ""]
        # ★★★2026-10-06 MAKE IT DECLARE THE DELTA. Operator: *"how do you know what is
        # changing in the logic between iterations? that is important? we need to know what
        # is changing between strategies no? or do we just leave it to claude"*.
        # He was right, and until now the answer was that nobody knew: three iterations in,
        # the rule TEXT was versioned and had never been diffed, so iteration 1 → 2 had
        # silently REVERSED its own position on trade count (iter 1 ordered "Target 8-15
        # entries per session" and "a session with no trade is a FAILURE"; iter 2 replaced
        # both with "there is no quota and a flat session is not a failure") and neither of
        # us had noticed. `scripts/rule_diff.py` now reconstructs the change after the fact,
        # but a reconstruction from prose is not the same as the author stating its intent.
        # ⚠ The CHANGELOG is a statement of INTENT, never evidence that the change worked —
        # the rules are rewritten from ONE training week, and one week cannot establish that
        # a rule earned its place.
        L += ["★ BEFORE YOUR RULE LIST, WRITE A SECTION HEADED 'CHANGELOG:' — at most six "
              "short lines, each naming ONE change you are making to the rules above and "
              "the single observation from THIS WEEK that caused it. If you are dropping a "
              "rule, say which and why it failed to earn its place. If you are reversing a "
              "rule, say so in those words. If you are changing nothing, write "
              "'CHANGELOG: no change — the week gave no reason to alter the rules.' "
              "Then write the numbered rule list as instructed.", ""]
    try:
        p = subprocess.run([CLAUDE, "-p", CONSOLIDATE + "\n\n=== THE WEEK ===\n" + "\n".join(L)],
                           cwd=OUT, capture_output=True, text=True, timeout=600,
                           env={**os.environ, "HOME": "/root"})
        txt = (p.stdout or "").strip()
    except Exception as e:
        return prev_rules or f"[consolidation failed: {type(e).__name__}]"
    return txt if len(txt) > 150 else (prev_rules or txt)


def run_week(days: list, rules: str, tag: str, fresh: bool = False) -> list:
    recs = []
    for day in days:
        # ⚠ one arm name per ITERATION so a later pass never silently resumes an earlier one's day
        rec = SW.run_day(day, rules, tag, resume=not fresh, self_aware=True)
        recs.append(rec)
        log(f"    {tag} {day} ${rec['net_usd']:+9,.2f} {len(rec['trades'])} trades")
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=MAX_ITERS)
    ap.add_argument("--start", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    rules = ""
    rp = f"{OUT}/rules.txt"
    if os.path.exists(rp):
        rules = open(rp).read()
        log(f"resuming with {len(rules)} chars of rules")

    history = []
    hp = f"{OUT}/history.json"
    if os.path.exists(hp):
        history = json.load(open(hp))

    for it in range(a.start, a.start + a.iters):
        # ★★★2026-10-06 THE PRE-ITERATION AUDIT GATE. Operator: *"so we are not forgetting
        # things and needing to rerun things, can you put an audit agent out each time
        # before each iteration to make sure whats about to be done is thorough and aimed at
        # improving the numbers?"*
        # Deterministic gates FAIL CLOSED (binary resolvable, a live call answers, budget
        # covers the WHOLE plan, tape present for every day, no poisoned artefact `resume`
        # would inherit, no holdout day in the training week). Each one is a failure that
        # already cost this project a day or a week. Then a headless audit judges the one
        # thing a gate cannot: is this iteration aimed at the metric that is actually
        # failing, and will its result be distinguishable from the $324/day noise floor.
        # ⚠ A gate cannot be forced; the audit's STOP can, with GAZBOT_PREFLIGHT_FORCE=1.
        # ⚠ On its FIRST run it caught a real confound in a 127M-token A/B that had already
        #   launched — rule 1 carries a second stop-after-losses clause present in every arm.
        # ★ the training week is chosen HERE, before the gate, because the gate has to check
        #   the tape and the holdout-leak of the ACTUAL days about to run. The first cut of
        #   this block referenced a `train_days` variable that did not exist at this point —
        #   it would have raised NameError on iteration 4 and killed the loop at the gate
        #   meant to protect it.
        import random as _r
        wk = TRAIN_POOL[(it - 1) % len(TRAIN_POOL)] if it <= len(TRAIN_POOL) \
            else _r.Random(it).choice(TRAIN_POOL)
        if os.environ.get("GAZBOT_PREFLIGHT", "1") != "0":
            cmd = [sys.executable, f"{GB}/scripts/preflight_iteration.py",
                   "--iter", str(it), "--train", ",".join(wk)]
            if os.environ.get("GAZBOT_PREFLIGHT_FORCE") == "1":
                cmd.append("--force")
            pf = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                                env={**os.environ, "HOME": "/root",
                                     "PYTHONPATH": f"{GB}/src"})
            for line in (pf.stdout or "").splitlines():
                log(f"  PREFLIGHT {line}")
            if pf.returncode not in (0,):
                log(f"  ⛔ PREFLIGHT BLOCKED iteration {it} (rc={pf.returncode}) — stopping. "
                    f"Fix what it named, or set GAZBOT_PREFLIGHT_FORCE=1 for an audit STOP.")
                break
        log(f"=== ITERATION {it} ===")
        log(f"  TRAIN week {wk[0]}..{wk[-1]} with {len(rules)} chars of rules")
        tr = run_week(wk, rules, f"loop{it}_train")
        s_tr = score_week(tr)
        log(f"  TRAIN  {s_tr}")

        log("  HOLDOUT — 14-18 Sep + 17-21 Aug, never trained on, never reviewed")
        ho = run_week(HOLDOUT, rules, f"loop{it}_hold")
        s_ho = score_week(ho)
        ok, why = meets_bar(s_ho)
        log(f"  HOLDOUT {s_ho}")
        log(f"  BAR: {why}")

        history.append({"iter": it, "train": s_tr, "holdout": s_ho, "met": ok,
                        "rules_chars": len(rules)})
        json.dump(history, open(hp, "w"), indent=1)

        # ★ the honest diagnostic: is the training curve rising while the holdout is not?
        if len(history) >= 3:
            t = [h["train"]["net_usd"] for h in history[-3:]]
            h_ = [h["holdout"]["net_usd"] for h in history[-3:]]
            if t[-1] > t[0] and h_[-1] <= h_[0]:
                log("  ⚠⚠ TRAINING IMPROVING WHILE HOLDOUT IS NOT — that is MEMORISATION, not "
                    "learning. The rules are encoding this particular week.")

        if ok:
            log(f"★★★ HOLDOUT MET THE BAR ON ITERATION {it}. Stopping.")
            # ⚠ PING THE MOMENT IT NAILS IT, not at the end of the twelve. He asked to be told when
            #   it nails it, and waiting for the loop to exhaust its iterations would mean sitting
            #   on the one result he actually wants for hours.
            try:
                subprocess.run([sys.executable, f"{GB}/scripts/ping_loop.py"], cwd=GB,
                               env={**os.environ, "PYTHONPATH": "src"}, timeout=1200)
            except Exception as e:
                log(f"  ping failed: {type(e).__name__}: {e}")
            break

        # ★★★2026-10-06 KEEP THE CHAMPION. THIS WAS A RANDOM WALK, NOT HILL-CLIMBING.
        # `rules = consolidate(...)` ran unconditionally, so the loop always carried forward
        # the MOST RECENT rule set regardless of how it scored. Iteration 3 discarded the
        # $620/day set, produced a weaker one, and iteration 4 would then have been built on
        # the worse rules — three iterations with no selection pressure anywhere in the loop,
        # which on its own could explain three flat results. The operator asked the right
        # question: *"Shouldn't we be improving?"*
        # ⚠ THE CHALLENGER MUST BEAT THE CHAMPION ON BOTH AXES — $/day AND days-positive —
        # because he is explicit that *"the most important thing is consistency"*, and a
        # challenger that buys a higher average with more losing days is not an improvement.
        # ⚠ A REJECTED CHALLENGER IS RECORDED, NEVER DISCARDED SILENTLY: its rules are kept
        # as rules_iter<N>_rejected.txt so the search path stays auditable.
        # ⚠ The margin is deliberately ZERO rather than the ~$324 standard error. Requiring a
        # challenger to clear the sampling error of a 10-day mean would reject every real
        # $100/day gain, and $100/day is $25k a year — "cannot measure it in ten days" is not
        # "it does not matter". The guard against drifting on noise is the ratchet itself:
        # the champion is never replaced by something that scored worse.
        champ = None
        for h in history:
            if h.get("holdout", {}).get("usd_per_day") is not None:
                if champ is None or h["holdout"]["usd_per_day"] > champ["holdout"]["usd_per_day"]:
                    champ = h
        this_pd = s_ho.get("usd_per_day")
        this_pos = s_ho.get("days_positive", 0)
        if champ and champ["iter"] != it and this_pd is not None:
            cpd = champ["holdout"]["usd_per_day"]
            cpos = champ["holdout"].get("days_positive", 0)
            # ★★★2026-10-06 LAW 0 DECIDES, NOT $/day. Operator: *"consistency is more
            # important"*. The first ratchet compared $/day and days-positive; `bible.gate()`
            # adds the worst day and the spread-to-mean ratio, so a challenger that buys a
            # bigger average with deeper holes is refused — his exact objection, *"If we
            # maximise one day to $2000 but then have 3 negatives or $200 days it's no good."*
            from gazbot7.bible import gate as _gate
            _ok, _why = _gate(s_ho, champ["holdout"])
            log(f"  CONSISTENCY GATE: {_why}")
            if not _ok:
                log(f"  ✗ CHALLENGER REJECTED: iter {it} scored ${this_pd:+,.0f}/day with "
                    f"{this_pos} positive days vs champion iter {champ['iter']} at "
                    f"${cpd:+,.0f}/day with {cpos}. REVERTING to the champion's rules.")
                open(f"{OUT}/rules_iter{it}_rejected.txt", "w").write(rules)
                champ_rules = f"{OUT}/rules_iter{champ['iter']}.txt"
                if os.path.exists(champ_rules):
                    rules = open(champ_rules).read()
                    open(rp, "w").write(rules)
                log(f"  → iteration {it + 1} will start from iteration "
                    f"{champ['iter']}'s rules, not this one's")
                history[-1]["rejected"] = True
                history[-1]["champion_iter"] = champ["iter"]
                json.dump(history, open(hp, "w"), indent=1)
                continue
            log(f"  ✓ CHALLENGER ACCEPTED: ${this_pd:+,.0f}/day · {this_pos} positive days "
                f"beats iter {champ['iter']} (${cpd:+,.0f} · {cpos})")

        log("  consolidating the week into a rewritten rule set")
        rules = consolidate(tr, rules)
        open(rp, "w").write(rules)
        open(f"{OUT}/rules_iter{it}.txt", "w").write(rules)
        # ★ split the declared CHANGELOG out to its own file so it is readable without
        # wading through the rule set, and so a missing one is obvious rather than implied.
        cl = ""
        if "CHANGELOG:" in rules:
            cl = rules.split("CHANGELOG:", 1)[1]
            cl = cl.split("\n1.", 1)[0].strip()
        open(f"{OUT}/rules_iter{it}_changelog.txt", "w").write(
            cl or "[no CHANGELOG section was produced]")
        log(f"  new rules: {len(rules)} chars")
        for line in (cl or "[no CHANGELOG declared]").splitlines():
            if line.strip():
                log(f"    CHANGE: {line.strip()[:160]}")

    json.dump(history, open(hp, "w"), indent=1)
    log("=== LOOP DONE ===")
    for h in history:
        log(f"  iter {h['iter']:>2}  train ${h['train']['net_usd']:>+9,.0f}  "
            f"holdout ${h['holdout']['net_usd']:>+9,.0f}  "
            f"side {h['holdout']['side_accuracy']}  cap {h['holdout']['capture']}  "
            f"{'MET' if h['met'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
