#!/usr/bin/env python3
"""PROJECT ROBOT — the recursive self-improvement driver. Scope: docs/PROJECT_ROBOT.md.

  --init            check the start condition (S3), stamp PROJECT.json + R000 + pool + 22 CONFIRMATION_DAYS; refuses if S3 fails unless --waive-start
  --phase0          champion twice on one L and one V day -> the single-day noise band (recorded; A3 itself needs V net >= 0)
  --run [--cycles N]  --exam checkpoint|final (informational only)  --confirm (ONCE: frozen R_final vs S3 on the confirmation days)
  --status  --check-start (exit 0 only if the start condition holds)

Sonnet for every call (operator). READ-ONLY on the desk: simulated fills only; no order path, no commit, no restart.
"""
from __future__ import annotations

import argparse
import datetime as dt
import statistics
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
import robot_core as RC                                    # noqa: E402
from robot_core import P, GB, sha                          # noqa: E402

MAX_CYCLES = 12
NO_ACCEPT_STOP = 6
STANDING_BURN_DEFAULT = 30_000_000          # tokens/day the rest of the desk burns when the meter cannot say
CYCLE_ESTIMATE_TOKENS = 22_000_000          # a tested cycle: 4 day-runs (ops audit)
EXAM_ESTIMATE_PER_DAY = 5_500_000           # one day-run
WORKERS = 1
UNINFORMATIVE = ("UNINFORMATIVE: %d consecutive cycles without an accept. The accept probability per cycle is only ~15-30%% "
                 "under noise, so this is NOT evidence that the rule set cannot be improved.")
HALT_RC = 6
S3_TAG, S1B_TAG = "sline_s3", "sline_s1b"
FROZEN = {"brief_v2_sha": RC.BRIEF_V2_SHA}


class Halt(Exception):
    pass


# ---------------------------------------------------------------- environment / pre-gates
def sw():
    os.environ["ANTHROPIC_MODEL"] = RC.MODEL            # every claude -p inherits this; no --model flag exists in the harness
    os.environ["ROBOT_NO_TOOLS"] = "1"                  # sim_week_recursive.ask/ask_text then pass --tools= (no tools at all)
    import sim_week_recursive as SW
    return SW


def brief_sha() -> str:
    SW = sw()
    return sha(SW.BRIEF_V2)


_MODEL_VERIFIED = False


def verify_model_live() -> list[str]:
    """Ask a real call which model answered (modelUsage in the JSON result). Checks what calls actually use."""
    global _MODEL_VERIFIED
    if _MODEL_VERIFIED:
        return []
    SW = sw()
    try:
        p = subprocess.run([SW.CLAUDE, "--tools=", "--output-format", "json", "-p", "Reply with exactly: OK"],
                           cwd=SW.OUT, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "HOME": "/root", **SW._api_env()})
        mu = json.loads(p.stdout).get("modelUsage") or {}
    except Exception as e:
        return [f"could not verify the model a live call uses: {type(e).__name__}: {str(e)[:80]}"]
    if not mu or any(not k.startswith(RC.MODEL) for k in mu):
        return [f"live call answered by {sorted(mu)} — ROBOT is Sonnet-only ({RC.MODEL})"]
    _MODEL_VERIFIED = True
    return []


def budget_summary() -> dict:
    import claude_usage as CU
    bf = os.environ.get("ROBOT_BUDGET_FILE")
    if bf:
        CU.BUDGET = bf
    return CU.summary()


def standing_burn_per_day() -> int:
    """Tokens/day burned by everything that is not ROBOT or the sim harness (by-project meter), else the default."""
    try:
        import claude_usage as CU
        agg = json.load(open(CU.OUT))
        days = max(1, len(agg.get("days") or {}))
        non = sum(CU.billable(v) for k, v in (agg.get("by_project") or {}).items()
                  if not any(t in k for t in ("sim-week", "recursive-loop", "robot")))
        return int(non / days) if non > 0 else STANDING_BURN_DEFAULT
    except Exception:
        return STANDING_BURN_DEFAULT


def budget_gate(need_tokens: int) -> list[str]:
    """remaining must cover: what the rest of the desk will burn until the reset + one cycle of margin + the work asked for."""
    try:
        s_ = budget_summary()
        rem = s_.get("remaining_tokens")
        if rem is None:
            return ["no budget configured — cannot verify the work is covered"]
        days_left = float(s_.get("hours_left", 168.0)) / 24.0
        burn = standing_burn_per_day()
        reserve = int(burn * days_left) + CYCLE_ESTIMATE_TOKENS
        if rem < reserve + need_tokens:
            return [f"budget: {rem/1e6:.0f}M remaining < reserve {reserve/1e6:.0f}M ({burn/1e6:.0f}M/day x {days_left:.1f}d to reset + one cycle) "
                    f"+ need {need_tokens/1e6:.0f}M"]
        return []
    except Exception as e:
        return [f"budget meter failed: {e}"]


def baseline_problems(days: list[str], tags=((S3_TAG, "S3"), (S1B_TAG, "S1b"))) -> list[str]:
    out = []
    for tag, name in tags:
        for d in days:
            p = f"{sw().OUT}/{tag}_{d}.json"
            if not os.path.exists(p):
                out.append(f"{name} record for {d} is missing")
                continue
            try:
                if RC.poisoned(json.load(open(p))):
                    out.append(f"{name} record for {d} is poisoned")
            except Exception as e:
                out.append(f"{name} record for {d} unreadable: {e}")
    return out


def pre_gates(day_pair: tuple[str, str] | None, need_tokens: int, offline: bool = False) -> list[str]:
    """Deterministic, fail closed. Returns the list of failures (empty = go)."""
    bad = []
    env_model = os.environ.get("ANTHROPIC_MODEL")
    if env_model != RC.MODEL:
        bad.append(f"model env is {env_model!r}, ROBOT is Sonnet-only ({RC.MODEL})")
    if os.environ.get("ROBOT_NO_TOOLS") != "1":
        bad.append("ROBOT_NO_TOOLS is not set — headless calls would have tools")
    import sim_week_recursive as SW
    if brief_sha() != FROZEN["brief_v2_sha"]:
        bad.append("BRIEF_V2 sha moved — frozen hash mismatch")
    import hashlib
    if hashlib.sha256(SW.BRIEF.encode()).hexdigest()[:12] != "b314ac3c6cb7":
        bad.append("BRIEF v1 sha moved")
    try:
        ok, why = RC.ledger_verify()
        if not ok:
            bad.append(why)
    except RC.LedgerError as e:
        bad.append(str(e))
    if day_pair:
        for d in day_pair:
            if d in RC.EXAM or d in RC.HOLDOUT_DAYS:
                bad.append(f"{d} is an exam or holdout day")
            try:
                bars, _ = SW.load_day(d)
                if len(bars) < 600:
                    bad.append(f"tape for {d} has {len(bars)} bars")
            except Exception as e:
                bad.append(f"tape for {d}: {e}")
    if not offline:
        if not os.path.exists(SW.CLAUDE):
            bad.append(f"claude binary missing: {SW.CLAUDE}")
        else:
            r = SW.ask_text("Reply with exactly one word: OK", timeout=90)
            if "OK" not in r.upper() or r.startswith("["):
                bad.append(f"live call did not answer: {r[:80]!r}")
            else:
                bad += verify_model_live()
        bad += budget_gate(need_tokens)
    return bad


# ---------------------------------------------------------------- the real trading step
def tag_for(rules_text: str, rep: str = "") -> str:
    return f"rb{rep}_{sha(rules_text)[:10]}"


def clean(rec: dict) -> bool:
    return not RC.poisoned(rec)


def real_trade_day(rules_text: str, day: str, rep: str = "") -> dict:
    """One day under a rule set. Poisoned days are re-run (L7) up to twice, never scored."""
    import paired_arm as PA
    SW = sw()
    for attempt in range(3):
        while PA.avail_mb() < PA.MEM_FLOOR_MB:
            print(f"  [memory] {PA.avail_mb()}MB < floor, waiting", flush=True)
            time.sleep(60)
        rec = SW.run_day(day, rules_text, tag_for(rules_text, rep), resume=True, self_aware=True, line="v2", mil=False)
        if clean(rec):
            return rec
        print(f"  poisoned day {day} (attempt {attempt+1}) — re-running", flush=True)
    raise Halt(f"{day} stayed poisoned after 3 attempts under {tag_for(rules_text, rep)}")


# ---------------------------------------------------------------- reviewer prompt + proposal parsing
ROLE = """You are the trader who traded the day below, reading your own record. Your job is to improve YOUR OWN RULE SET by at most ONE rule.

Compass (Law 0e): the strategy is to enter a little EARLIER into a leg that has already proven itself, to exit a little LATER but while still IN PROFIT, and to keep exits in profit.
There are NO stops, NO loss-cuts and NO trade caps. A rule must serve one of those three things or it is not allowed.

Discipline:
- NO_CHANGE is always legal and is the right answer whenever the recorded trades below do not support a specific change. It is never penalised.
- You may change exactly ONE rule: ADD one, EDIT one, or REMOVE one. Never two.
- Cite at least three REAL trades from the day below by their open time (HH:MM, as printed) and entry price. A citation that does not match a recorded trade invalidates the proposal.
- The rule's trigger must be something printed on the tape page a look would see. No clock times, dates, price levels or weekdays in the rule text.
- Declare, BEFORE it is tested, which measured metric the rule should move, in which direction, and by at least how much. Declare what it is expected to make worse.
- Do not re-propose a change that the history below shows was rejected unless you cite new evidence.
- The history below was written by code from earlier cycles; trust it over your impression.

Metric menu (choose one id): {menu}

Return ONLY one JSON object, nothing else.
For no change:  {{"decision":"NO_CHANGE","reason":"..."}}
For a change:   {{"decision":"PROPOSE","change":"ADD|EDIT|REMOVE","rule_no":<int, required for EDIT/REMOVE>,"new_text":"<the full rule text; omit for REMOVE>",
 "serves":"EARLIER_ENTRY|LATER_EXIT_IN_PROFIT|EXITS_IN_PROFIT",
 "cited_trades":[{{"opened":"HH:MM","entry":<price>,"why_it_matters":"..."}}, ...at least 3],
 "trigger_on_page":"the exact thing on the page that makes this rule fire","metric":"<menu id>","direction":"up|down","min_move":<number>,
 "expected_cost":"what gets worse","not_a_stop_not_a_cap":true}}
"""


def build_review_prompt(rules_text: str, rec: dict, hist_digest: str, lessons: str, hours: str = "") -> str:
    from gazbot7.bible import laws
    SW = sw()
    t = rec["trades"]
    L = [f"DAY RESULT: net ${rec['net_usd']:+,.2f} over {len(t)} trade(s)"]
    for x in t:
        L.append(f"  {x['side']:5} opened {x['opened'][11:16]}Z entry {x['entry']:.2f} -> closed {x['closed'][11:16]}Z exit {x['exit']:.2f} "
                 f"{x['held_min']:>4.0f}min {x['points']:+7.1f}pt ${x['pnl_usd']:+8.2f} peak {x['peak_pt']:+.0f}pt [{x['why']}]  entry reason: {x['entry_reason'][:110]}")
    L += ["", "YOUR CALLS (time, price, action, holding, your reason):"]
    for c in rec["calls"]:
        if c["action"] == "WAIT" and not c["holding"]:
            continue
        L.append(f"  {c['ts'][11:16]}Z {c['px']:.2f} {c['action']:11} {'IN ' if c['holding'] else 'out'} {(c.get('reason') or '')[:150]}")
    pm = ""
    try:
        import trade_review as TR
        pm = "\n\n=== THE MEASURED POST-MORTEM (computed by code; it outranks your impression) ===\n" + \
             TR.render(TR.analyse(rec["day"], rec["trades"], rec.get("calls") or []))
    except Exception as e:
        pm = f"\n\n[post-mortem unavailable: {type(e).__name__}: {e}]"
    try:
        import importlib.util as _il
        s = _il.spec_from_file_location("snake", f"{GB}/scripts/snake_page.py")
        m = _il.module_from_spec(s)
        s.loader.exec_module(m)
        bars, _ = SW.load_day(rec["day"])
        snake = m.page(bars, rec["trades"], rec["day"])
    except Exception as e:
        snake = f"[snake page failed: {type(e).__name__}: {e}]"
    return (ROLE.format(menu="; ".join(f"{k} ({v})" for k, v in RC.MENU.items()))
            + "\n" + laws()
            + "\n\n=== YOUR CURRENT RULE SET (numbered) ===\n" + (rules_text or "(empty — you have no rules yet)")
            + "\n\n=== HISTORY OF EARLIER CYCLES (written by code) ===\n" + hist_digest
            + "\n\n=== LESSONS YOU WROTE EARLIER ===\n" + lessons
            + ("\n\n=== WHEN YOUR TRADES OPENED (code-computed, earlier learning days only) ===\n" + hours if hours else "")
            + "\n\n=== THE DAY, AS A PICTURE. READ THIS FIRST ===\n" + snake
            + "\n\n=== WHAT YOU DID ===\n" + "\n".join(L) + pm)


def extract_json(raw: str) -> dict | None:
    for i, ch in enumerate(raw):
        if ch != "{":
            continue
        depth, in_str, esc = 0, False, False
        for k in range(i, len(raw)):
            c = raw[k]
            if in_str:
                esc = (c == "\\") if not esc else False
                if c == '"' and not esc:
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        o = json.loads(raw[i:k + 1])
                    except Exception:
                        break
                    if isinstance(o, dict) and ("decision" in o or "change" in o):
                        return o
                    break
    return None


_LIMIT_RX = re.compile(r"usage limit|rate limit|hit your .{0,20}limit|limit reached|credit balance|quota|overloaded|resets? (?:at|on|in) ", re.I)


def unusable(raw: str) -> bool:
    r = (raw or "").strip()
    return (not r) or r.startswith("[") or bool(_LIMIT_RX.search(r[:400]))


def real_reviewer(prompt: str) -> str:
    return sw().ask_text(prompt, timeout=420)


CRITIC = """In two or three sentences, as one lesson for your future self: you proposed the change below, predicted what it would do, and this is what the code measured.
What did you expect, what happened, and what does that teach you about proposing rules? Be specific. Reply with the lesson only.

PROPOSAL: {prop}
RESULT (computed by code): {res}
"""


def real_critic(prompt: str) -> str:
    return sw().ask_text(prompt, timeout=180)


# ---------------------------------------------------------------- state
def champion() -> dict:
    p = P("champion.json")
    if not os.path.exists(p):
        raise Halt("no champion.json — run --init first")
    return json.load(open(p))[-1]


def set_champion(n: int, text: str, cycle: int, why: str) -> None:
    RC.save_rules(n, text)
    h = json.load(open(P("champion.json"))) if os.path.exists(P("champion.json")) else []
    h.append({"version": n, "sha": sha(text), "since_cycle": cycle, "why": why, "ts": RC.now()})
    json.dump(h, open(P("champion.json"), "w"), indent=1)


def project() -> dict:
    return json.load(open(P("PROJECT.json")))


def noise_band() -> float:
    p = P("noise", "noise.json")
    if os.path.exists(p):
        return max(RC.NOISE_FLOOR_USD, float(json.load(open(p))["band_usd"]))
    return RC.NOISE_FLOOR_USD


def used_days() -> list[str]:
    u = []
    for r in RC.ledger_read():
        if r.get("kind") == "cycle":
            u += [r["L"], r["V"]]
        if r.get("kind") == "phase0":
            u += r.get("days", [])
    return u


def save_cycle_file(n: int, name: str, content) -> str:
    d = P("cycles", f"c{n:04d}")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "w") as f:
        f.write(content if isinstance(content, str) else json.dumps(content, indent=1, default=str))
    return p


def bars_for(day: str):
    return sw().load_day(day)[0]


# ---------------------------------------------------------------- one cycle (stubbable)
def hour_recs(rows: list[dict], recL: dict) -> list[dict]:
    """Champion records of EARLIER learning (L) days + this one. Never an exam day, never a validation day (R11)."""
    out = []
    for r in rows:
        if r.get("kind") != "cycle" or r.get("L") in RC.EXAM:
            continue
        if not isinstance(r.get("champion_version"), int):
            continue
        pth = P("rules", f"R{int(r['champion_version']):03d}.txt")
        if not os.path.exists(pth):
            continue
        f = f"{sw().OUT}/{tag_for(open(pth).read())}_{r['L']}.json"
        if os.path.exists(f):
            try:
                rec = json.load(open(f))
            except Exception:
                continue
            if clean(rec):
                out.append(rec)
    return out + [recL]


def run_cycle(n: int, pair: tuple[str, str], trade_day, reviewer, critic, bars_fn=bars_for) -> dict:
    L, V = pair
    ch = champion()
    rules = open(P("rules", f"R{ch['version']:03d}.txt")).read()
    hist = RC.ledger_read()
    rec_id = {"kind": "cycle", "cycle": n, "L": L, "V": V, "champion_version": ch["version"],
              "champion_sha": sha(rules), "model": RC.MODEL, "brief_sha": FROZEN["brief_v2_sha"][:16]}

    recL = trade_day(rules, L)                                  # 1 champion record on L
    mL = RC.metrics(recL, bars_fn(L))

    prompt = build_review_prompt(rules, recL, RC.digest(hist), RC.lessons_text(), RC.hour_block(hour_recs(hist, recL)))   # 2 review: sees L only
    prev_p, prev_o = P("cycles", f"c{n:04d}", "review_prompt.txt"), P("cycles", f"c{n:04d}", "review_output.raw")
    raw = None
    if os.path.exists(prev_p) and os.path.exists(prev_o) and open(prev_p).read() == prompt:      # resume after a halt: same question, same answer
        old = open(prev_o).read()
        if not unusable(old) and extract_json(old) is not None:
            raw = old
    save_cycle_file(n, "review_prompt.txt", prompt)
    if raw is None:
        raw = reviewer(prompt)
        save_cycle_file(n, "review_output.raw", raw)
    rec_id["prompt_sha"] = sha(prompt)[:16]
    out = extract_json(raw)

    if out is None:                                              # an unreadable reviewer is an outage, not a verdict
        raise Halt(f"cycle {n}: reviewer reply unusable ({'limit/error text' if unusable(raw) else 'no parseable JSON'}): "
                   f"{(raw or '').strip()[:120]!r}")
    if str(out.get("decision", "")).upper() == "NO_CHANGE":
        return _finish(n, rec_id, None, "NO_CHANGE", "reviewer: " + str(out.get("reason", ""))[:300], {}, critic)
    prop = {k: v for k, v in out.items() if k != "decision"}
    save_cycle_file(n, "proposal.json", prop)

    valid = RC.validate_proposal(prop, rules, hist_rejects(hist), recL["trades"], L)       # 3 validate (never raises)
    new_rules = None
    if valid[0]:
        new_rules = RC.apply_proposal(rules, prop)
        if not RC.diff_is_one_rule(rules, new_rules):
            valid = (False, "diff is not exactly one rule")
    if not valid[0]:
        d = RC.decide(prop, valid, mL, {}, None, None, noise_band())
        return _finish(n, rec_id, prop, "REJECT", d["reason"], {"A1": d["A1"]}, critic, public=d["reason_public"])
    save_cycle_file(n, "diff.txt", f"--- R{ch['version']:03d}\n{rules}\n+++ proposed\n{new_rules}")
    rec_id["challenger_sha"] = sha(new_rules)

    recL2 = trade_day(new_rules, L)                              # 4 mechanism rerun (in-sample)
    mL2 = RC.metrics(recL2, bars_fn(L))
    recV = trade_day(rules, V)                                   # 5 transfer: champion and challenger on V
    mV = RC.metrics(recV, bars_fn(V))
    recV2 = trade_day(new_rules, V)
    mV2 = RC.metrics(recV2, bars_fn(V))
    d = RC.decide(prop, valid, mL, mL2, mV, mV2, noise_band())   # 6 decide (code)
    ev = {"mL": mL, "mL2": mL2, "mV": mV, "mV2": mV2, **{k: d[k] for k in ("A1", "A2", "A3", "A4") if k in d}}
    save_cycle_file(n, "decision.json", {"decision": d, "metrics": ev})
    if d["decision"] == "ACCEPT":
        rec_id["new_version"] = RC.next_version()
        return _finish(n, rec_id, prop, "ACCEPT", d["reason"], ev, critic, public=d["reason_public"], new_rules=new_rules)
    return _finish(n, rec_id, prop, d["decision"], d["reason"], ev, critic, public=d["reason_public"])


def hist_rejects(hist: list[dict]) -> list[dict]:
    return [r for r in hist if r.get("kind") == "cycle" and r.get("decision") == "REJECT"]


def _finish(n, rec_id, prop, decision, reason, ev, critic, public=None, new_rules=None) -> dict:
    """Order matters (crash safety): critic (may Halt, nothing persisted) -> immutable rules file -> LEDGER ROW ->
    champion pointer -> lessons -> changelog. A crash after the ledger row is reconciled on resume (reconcile())."""
    public = public or RC.scrub_numbers(reason)
    lesson = None
    if prop and decision in ("ACCEPT", "REJECT") and ev.get("A2"):          # 7 self-critique (only when something was tested)
        raw = critic(CRITIC.format(prop=json.dumps({k: prop.get(k) for k in ('change', 'rule_no', 'new_text', 'metric', 'direction', 'min_move', 'expected_cost')}),
                                   res=f"{decision}: {public}"))
        if unusable(raw):
            raise Halt(f"cycle {n}: critic reply unusable: {(raw or '').strip()[:120]!r}")
        lesson = RC.scrub_dollars(raw.strip())[:600]
    row = {**rec_id, "proposal": prop, "decision": decision, "reason": reason, "reason_public": public, "evidence": ev}
    if lesson:
        row["lesson"] = lesson
    if decision == "NO_CHANGE" and prop is None:
        row["note"] = "NO_CHANGE is a first-class record"
    if decision == "ACCEPT":
        RC.save_rules(rec_id["new_version"], new_rules)          # immutable and orphan-safe: a crash here wastes a number, nothing else
    led = RC.ledger_append(row)                                  # 8 ledger FIRST
    if decision == "ACCEPT":
        set_champion(rec_id["new_version"], new_rules, n, reason)
    if lesson:
        RC.lessons_add(n, f"(cycle {n}) {lesson}")
    RC.write_changelog()
    return led


def reconcile() -> list[str]:
    """After a crash between the ledger row and the champion/lessons writes: make them agree, or Halt."""
    notes = []
    rows = RC.ledger_read()
    acc = [r for r in rows if r.get("kind") == "cycle" and r.get("decision") == "ACCEPT" and isinstance(r.get("new_version"), int)]
    expected = acc[-1]["new_version"] if acc else 0
    ch = champion()
    if ch["version"] > expected:
        raise Halt(f"champion.json is at v{ch['version']} but the ledger's last ACCEPT is v{expected} — they disagree; not guessing")
    if ch["version"] < expected and expected not in {int(x["version"]) for x in json.load(open(P("champion.json")))}:
        pth = P("rules", f"R{expected:03d}.txt")
        if not os.path.exists(pth):
            raise Halt(f"ledger ACCEPTed v{expected} but {pth} is missing")
        text = open(pth).read()
        if sha(text) != acc[-1].get("challenger_sha"):
            raise Halt(f"{pth} does not match the ledger's challenger_sha")
        set_champion(expected, text, acc[-1]["cycle"], "reconciled on resume: ledger ACCEPT had no champion update")
        notes.append(f"champion reconciled to v{expected}")
    have = {x["cycle"] for x in RC.lessons_read()}
    for r in rows:
        if r.get("kind") == "cycle" and r.get("lesson") and r["cycle"] not in have:
            RC.lessons_add(r["cycle"], f"(cycle {r['cycle']}) {r['lesson']}")
            notes.append(f"lesson for cycle {r['cycle']} restored")
    return notes


# ---------------------------------------------------------------- exams
def nets_for(tag: str, days: list[str]) -> dict[str, float] | None:
    out = {}
    for d in days:
        p = f"{sw().OUT}/{tag}_{d}.json"
        if not os.path.exists(p):
            return None
        r = json.load(open(p))
        if RC.poisoned(r):
            return None
        out[d] = r["net_usd"]
    return out


def exam(kind: str, trade_day=real_trade_day) -> dict:
    """INFORMATIONAL. The nine days are selected-on (the S3 seed was written from them): an exam here never rolls the
    champion back and never selects a version. Only --confirm, on the untouched confirmation days, can support a claim."""
    ch = champion()
    rules = open(P("rules", f"R{ch['version']:03d}.txt")).read()
    days = RC.CHECKPOINT_EXAM if kind == "checkpoint" else RC.EXAM
    prob = baseline_problems(days, ((S3_TAG, "S3"), (S1B_TAG, "S1b")) if kind == "final" else ((S3_TAG, "S3"),))
    if prob:
        raise Halt("exam needs clean baselines first (fail closed): " + "; ".join(prob[:4]))
    nets = {d: trade_day(rules, d, "x")["net_usd"] for d in days}
    res = {"kind": "exam", "exam": kind, "informational": True, "label": RC.EXAM_LABEL, "champion_version": ch["version"],
           "champion_sha": sha(rules), "days": days, "nets": nets, "stats": RC.stats(list(nets.values()))}
    if kind == "final":
        from gazbot7.bible import gate
        for name, tag in (("S3", S3_TAG), ("S1b", S1B_TAG)):
            b = nets_for(tag, days)
            ok, why = gate(res["stats"], RC.stats(list(b.values())))
            res[f"gate_vs_{name}"] = {"passes": ok, "why": why, "baseline": RC.stats(list(b.values())), "baseline_nets": b}
        res["caveat"] = ("INFORMATIONAL ONLY — " + RC.EXAM_LABEL + ". Passed/unresolved is never a promotion (L6); "
                         "SE of a 9-day mean ~ $350/day")
    else:
        b = nets_for(S3_TAG, days)
        res["vs_s3"] = {"s3_nets": b, "s3_usd_per_day": RC.stats(list(b.values()))["usd_per_day"]}
        res["usd_per_day_below_s3"] = res["stats"]["usd_per_day"] < res["vs_s3"]["s3_usd_per_day"]
        res["rollback"] = False
        res["note"] = "informational only: never rolls back, never selects (the nine days are selected-on)"
    os.makedirs(P("exams"), exist_ok=True)
    json.dump(res, open(P("exams", f"{kind}_{RC.now().replace(':','')}.json"), "w"), indent=1)
    RC.ledger_append(res)
    return res


def confirm(trade_day=real_trade_day) -> dict:
    """Frozen R_final vs S3, paired, on the 22 untouched CONFIRMATION_DAYS. ONCE: a ledger stamp refuses a second run."""
    pr = project()
    days = pr.get("confirmation_days") or []
    if len(days) != RC.CONFIRMATION_N:
        raise Halt(f"PROJECT.json carries {len(days)} confirmation days, expected {RC.CONFIRMATION_N} (init predates this fix?)")
    rows = RC.ledger_read()
    if any(r.get("kind") == "confirm" for r in rows):
        raise Halt("the confirmation has already been run once — it is never repeated (it would stop being untouched)")
    ch = champion()
    final = open(P("rules", f"R{ch['version']:03d}.txt")).read()
    s3 = open(P("rules", "R000.txt")).read()
    started = [r for r in rows if r.get("kind") == "confirm_started"]
    if started:
        if started[-1]["champion_sha"] != sha(final):
            raise Halt("a confirmation was started under a different champion — refusing to restart it")
    else:
        RC.ledger_append({"kind": "confirm_started", "champion_version": ch["version"], "champion_sha": sha(final),
                          "s3_sha": sha(s3), "days": days})
    nf = {d: trade_day(final, d, "cf")["net_usd"] for d in days}
    ns = {d: trade_day(s3, d, "cf")["net_usd"] for d in days}
    ps = RC.paired_summary([nf[d] for d in days], [ns[d] for d in days])
    res = {"kind": "confirm", "champion_version": ch["version"], "champion_sha": sha(final), "days": days,
           "final_nets": nf, "s3_nets": ns, "paired": ps,
           "lower90_above_zero": ps["lower90"] > 0, "lower90_above_noise_floor": ps["lower90"] > RC.NOISE_FLOOR_USD,
           "caveat": "one run, never repeated; the 90% lower bound is the claim, the mean is not (L6)"}
    os.makedirs(P("exams"), exist_ok=True)
    json.dump(res, open(P("exams", f"confirm_{RC.now().replace(':','')}.json"), "w"), indent=1)
    RC.ledger_append(res)
    return res


# ---------------------------------------------------------------- init / phase0 / run
def start_condition() -> dict:
    SW = sw()
    import s_line_claim as SC
    days = RC.EXAM
    recs = []
    for d in days:
        p = f"{SW.OUT}/{S3_TAG}_{d}.json"
        if os.path.exists(p):
            recs.append(json.load(open(p)))
    out = {"days_present": len(recs), "need": len(days)}
    if len(recs) < len(days):
        out.update(ok=False, reasons=[f"S3 has {len(recs)} of {len(days)} days"])
        return out
    nets = [r["net_usd"] for r in recs]
    m = SC.measure(S3_TAG)
    reasons = []
    if any(RC.poisoned(r) for r in recs):
        reasons.append("a poisoned day among the nine")
    if sum(nets) <= 0:
        reasons.append(f"S3 net {sum(nets):+,.0f} is not > 0")
    if min(nets) < -2000:
        reasons.append(f"a day below -$2,000 ({min(nets):+,.0f})")
    if (m.get("claim_share") or 0) < 0.70:
        reasons.append(f"P1 obedience {m.get('claim_share')} < 0.70")
    reasons += baseline_problems(days)
    out.update(ok=not reasons, reasons=reasons, nets=dict(zip(days, nets)), total=sum(nets), claim_share=m.get("claim_share"))
    return out


def init(waive: bool, seed: str) -> int:
    if os.path.exists(P("PROJECT.json")):
        print("PROJECT.json exists — ROBOT is already initialised (immutable)")
        return 1
    sc = start_condition()
    print(json.dumps(sc, indent=1))
    if not sc["ok"] and not waive:
        print("START CONDITION FAILED — not initialised. Options: --waive-start --seed s3 (pure self-improvement test) or --waive-start --seed s1 (empty set).")
        return 2
    src = {"s3": f"{GB}/reports/recursive_loop/S3.txt", "s1": f"{GB}/reports/recursive_loop/S1.txt"}[seed]
    text = open(src).read()
    RC.save_rules(0, text)
    set_champion(0, text, 0, f"seed from {os.path.basename(src)} verbatim")
    cands = sorted({dt.datetime.fromtimestamp(t, dt.UTC).date().isoformat() for (t,) in
                    __import__("duckdb").connect().execute(
                        f"SELECT DISTINCT (bar_ts // 86400) * 86400 FROM read_parquet('{GB}/data/tape/bars/MNQ/backfill_1min.parquet')").fetchall()})
    cands = [d for d in cands if dt.date.fromisoformat(d).weekday() < 5]
    memo: dict = {}

    def char(d):
        if d not in memo:
            memo[d] = RC.day_character(d)
        return memo[d]
    touched = RC.touched_days(f"{GB}/reports/sim_week_recursive", [f"{GB}/reports/recursive_loop", f"{GB}/docs"])
    conf = RC.pick_confirmation(RC.CONFIRMATION_SEED, [c for c in cands if c not in touched], char)          # frozen first, so the learning pool cannot touch them
    pool = RC.build_pool(20261008, [c for c in cands if c not in conf], char)
    json.dump({"started": RC.now(), "model": RC.MODEL, "seed": seed, "seed_sha": sha(text), "start_condition": sc,
               "start_condition_waived": bool(waive and not sc["ok"]), "frozen": FROZEN,
               "exam": RC.EXAM, "exam_label": RC.EXAM_LABEL, "checkpoint_exam": RC.CHECKPOINT_EXAM,
               "holdout": sorted(RC.HOLDOUT_DAYS), "pool": pool,
               "confirmation_days": conf, "confirmation_seed": RC.CONFIRMATION_SEED,
               "thresholds": {"guard_exit_share_pp": RC.GUARD_EXIT_SHARE_PP, "guard_worst_trade_usd": RC.GUARD_WORST_TRADE_USD,
                              "noise_floor_usd": RC.NOISE_FLOOR_USD, "max_rules": RC.MAX_RULES, "max_cycles": MAX_CYCLES,
                              "no_accept_stop": NO_ACCEPT_STOP, "standing_burn_default": STANDING_BURN_DEFAULT,
                              "cycle_estimate_tokens": CYCLE_ESTIMATE_TOKENS}},
              open(P("PROJECT.json"), "w"), indent=1)
    print(f"initialised: R000 sha {sha(text)[:12]}; pool {sum(len(b) for b in pool['buckets'])} days; {len(conf)} confirmation days stamped")
    return 0


def phase0(trade_day=real_trade_day) -> int:
    pr = project()
    pair = RC.next_pair(pr["pool"], used_days(), 0)
    ch = champion()
    rules = open(P("rules", f"R{ch['version']:03d}.txt")).read()
    diffs, rows = [], {}
    for d in pair:
        a = trade_day(rules, d)["net_usd"]
        b = trade_day(rules, d, "n1")["net_usd"]
        rows[d] = {"run_a": a, "run_b": b}
        diffs.append(abs(a - b))
    os.makedirs(P("noise"), exist_ok=True)
    json.dump({"days": rows, "band_usd": max(diffs), "floor_usd": RC.NOISE_FLOOR_USD,
               "note": "A3 uses max(floor, band): the largest same-rules same-day replicate difference observed"},
              open(P("noise", "noise.json"), "w"), indent=1)
    RC.ledger_append({"kind": "phase0", "days": list(pair), "band_usd": max(diffs)})
    print(f"noise band ${max(diffs):,.0f} (floor ${RC.NOISE_FLOOR_USD:,.0f})")
    return 0


def run(max_cycles: int, trade_day=real_trade_day, reviewer=real_reviewer, critic=real_critic, offline=False,
        bars_fn=bars_for) -> int:
    try:
        return _run(max_cycles, trade_day, reviewer, critic, offline, bars_fn)
    except (Halt, RC.LedgerError) as e:
        RC.write_status({"HALTED": str(e)[:400]})
        print(f"HALTED: {e}", flush=True)
        return HALT_RC


def _run(max_cycles, trade_day, reviewer, critic, offline, bars_fn) -> int:
    pr = project()
    for note in reconcile():
        print("  [reconcile]", note, flush=True)
    done = len([r for r in RC.ledger_read() if r.get("kind") == "cycle"])
    todo = max(0, min(max_cycles, MAX_CYCLES - done))
    if todo and not offline:
        bad = budget_gate(todo * CYCLE_ESTIMATE_TOKENS)
        if bad:
            RC.write_status({"HALTED": "; ".join(bad)})
            print("BUDGET GATE (requested cycles not covered):\n  " + "\n  ".join(bad)); return 3
    for _ in range(max_cycles):
        rows = [r for r in RC.ledger_read() if r.get("kind") == "cycle"]
        n = len(rows) + 1
        tail = rows[-NO_ACCEPT_STOP:]
        if n > MAX_CYCLES:
            print("cycle cap reached — run the final exam (informational) and then --confirm"); break
        if len(tail) == NO_ACCEPT_STOP and all(r["decision"] != "ACCEPT" for r in tail):
            msg = UNINFORMATIVE % NO_ACCEPT_STOP
            RC.write_status({"STOPPED": msg})
            print(msg); break
        pair = RC.next_pair(pr["pool"], used_days(), n)
        if pair is None:
            print("pool exhausted"); break
        bad = pre_gates(pair, CYCLE_ESTIMATE_TOKENS, offline=offline)
        if bad:
            RC.write_status({"HALTED": "; ".join(bad)})
            print("PRE-GATE FAILURE:\n  " + "\n  ".join(bad)); return 3
        print(f"cycle {n}: L={pair[0]} V={pair[1]}", flush=True)
        row = run_cycle(n, pair, trade_day, reviewer, critic, bars_fn)
        acc = sum(1 for r in RC.ledger_read() if r.get("kind") == "cycle" and r["decision"] == "ACCEPT")
        RC.write_status({"champion": f"R{champion()['version']:03d}", "last": f"c{n} {row['decision']}", "noise_band": noise_band(),
                         "model": RC.MODEL})
        print(f"  -> {row['decision']}: {row['reason'][:160]}", flush=True)
        if row["decision"] == "ACCEPT" and acc % 4 == 0 and not offline:
            bad = pre_gates(None, 3 * EXAM_ESTIMATE_PER_DAY, offline=offline)
            if bad:
                print("checkpoint exam skipped:", bad); continue
            ex = exam("checkpoint", trade_day)
            print(f"  checkpoint exam (informational): {ex['stats']['usd_per_day']:+.0f}/day on selected-on days")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--waive-start", action="store_true")
    ap.add_argument("--seed", choices=["s3", "s1"], default="s3")
    ap.add_argument("--phase0", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--cycles", type=int, default=MAX_CYCLES)
    ap.add_argument("--exam", choices=["checkpoint", "final"])
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--check-start", action="store_true")
    a = ap.parse_args()
    sw()
    if a.check_start:
        sc = start_condition()
        print(json.dumps(sc, indent=1))
        return 0 if sc.get("ok") else 1
    if a.init:
        return init(a.waive_start, a.seed)
    if a.status:
        print(open(P("STATUS.md")).read() if os.path.exists(P("STATUS.md")) else "no status yet"); return 0
    if a.phase0 or a.run or a.exam or a.confirm:
        ok, why = RC.acquire_lock()
        if not ok:
            print(why); return 5
        try:
            if a.run:
                return run(a.cycles)
            if a.phase0:
                need = 4 * EXAM_ESTIMATE_PER_DAY
            elif a.exam:
                need = (3 if a.exam == "checkpoint" else 9) * EXAM_ESTIMATE_PER_DAY
            else:
                need = 2 * RC.CONFIRMATION_N * EXAM_ESTIMATE_PER_DAY
            bad = pre_gates(None, need)
            if bad:
                print("PRE-GATE FAILURE:", bad); return 3
            try:
                if a.phase0:
                    return phase0()
                if a.exam:
                    print(json.dumps(exam(a.exam), indent=1)); return 0
                print(json.dumps(confirm(), indent=1)); return 0
            except (Halt, RC.LedgerError) as e:
                RC.write_status({"HALTED": str(e)[:400]})
                print(f"HALTED: {e}"); return HALT_RC
        finally:
            RC.release_lock()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
