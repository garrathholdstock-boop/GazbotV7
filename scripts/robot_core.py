#!/usr/bin/env python3
"""PROJECT ROBOT — pure, testable core: ledger, rule versions, proposal validator, metrics, accept function, pool.

Scope and law: docs/PROJECT_ROBOT.md. Nothing here calls Claude or touches the desk; the driver (robot_loop.py) does.
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import os
import random
import re
import statistics as st
import sys
import fcntl

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")

MODEL = "claude-sonnet-5"
ROBOT_DIR = os.environ.get("ROBOT_DIR", f"{GB}/reports/robot")
BRIEF_V2_SHA = "e24645d20fa76e8be15f4a38cc150192a93377bc8ee568271960170ef6125ed9"

EXAM = ["2026-02-05", "2026-02-19", "2026-03-05", "2026-03-19", "2026-04-02",
        "2026-04-16", "2026-04-30", "2026-05-14", "2026-05-28"]
CHECKPOINT_EXAM = ["2026-02-19", "2026-04-16", "2026-05-14"]
EXAM_LABEL = ("the nine S-line days are SELECTED-ON (the S3 seed was written from them) — "
              "NOT out-of-sample; only the frozen CONFIRMATION_DAYS are")
CONFIRMATION_N = 22
CONFIRMATION_SEED = 20261009
HOLDOUT_DAYS = {"2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
                "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"}
MAX_RULES = 10
MAX_RULE_CHARS = 600
MAX_LESSONS = 20
NOISE_FLOOR_USD = 324.0         # the S-line's measured single-run noise floor; the measured band may only raise it
GUARD_EXIT_SHARE_PP = 0.10
GUARD_WORST_TRADE_USD = 300.0
SERVES = {"EARLIER_ENTRY", "LATER_EXIT_IN_PROFIT", "EXITS_IN_PROFIT"}
POISON_RATE = 0.10

# metric id -> (description). Claude picks an id; code computes it (R12).
MENU = {
    "net_usd": "the day's net dollars after fees",
    "gross_points": "sum of trade points, before fees and size",
    "exits_in_profit_share": "share of trades that closed with pnl > 0",
    "giveback_count": "trades that were >= 2x ATR green at a look and finished below half of that mark",
    "target_obedience": "share of first 2x-ATR-profit looks at which the model EXITED",
    "same_side_rebuy_15": "same-side re-entries within 15 min of a profitable exit",
    "never_green_share": "share of trades whose peak was never above 0",
    "hold_median": "median hold in minutes",
    "worst_trade": "the single worst trade in dollars",
}
# A pure trade-count metric as the declared primary would be a trade cap by the back door (Law 0e).
BARRED_PRIMARY = {"trades_per_day"}
# Per-metric floor on the declared min_move (the model may raise it, never lower it).
# Dollar metrics: the pooled arm-to-arm SD of a day, $474 (statistics audit) — a single day cannot show less.
# gross_points: the same $474 at $8/pt = 59.25 pt. Counts: one whole trade. Shares: 10 percentage points
# (one trade in a 5-10 trade day moves a share by 10-20 pp). hold_median: 5 minutes.
DOLLAR_FLOOR = 474.0
MIN_MOVE_FLOOR = {
    "net_usd": DOLLAR_FLOOR, "worst_trade": DOLLAR_FLOOR, "gross_points": DOLLAR_FLOOR / 8.0,
    "giveback_count": 1.0, "same_side_rebuy_15": 1.0,
    "exits_in_profit_share": 0.10, "never_green_share": 0.10, "target_obedience": 0.10,
    "hold_median": 5.0,
}

_FORBID = [
    (r"\b\d{1,2}:\d{2}\b", "a clock time"),
    (r"\b\d{1,2}\s?(?:am|pm|utc|gmt)\b|\b\d{2}:?\d{2}\s?z\b", "a clock time"),
    (r"\b20\d{2}-\d{2}-\d{2}\b", "a date"),
    (r"\b(?:mon|tues?|wednes|thurs?|fri|satur|sun)day\b", "a day of week"),
    (r"\b\d{4,5}(?:\.\d+)?\b", "a price level"),
    (r"stop[- ]?loss|stopped out|stop out|hard stop|\bcut (?:the |your )?(?:loss|losses|losers)\b|loss limit|daily limit|"
     r"max(?:imum)?(?: of)? \d+ trades|no more than \d+ trades|at most \d+ trades|\btrade cap\b|limit(?:ed)? to \d+ trades",
     "a stop, loss-cut, cap or daily limit (Law 0e)"),
    (r"\bcut\b.{0,40}\b(?:loss|losing|red|down|underwater)\b|\bat a loss\b|\bloss of \$?\d|\b(?:down|below|under) \$?\d+ ?(?:points?|pts?|usd|dollars|\$)|"
     r"\bstop(?:s|ped)?\b.{0,30}\b(?:points?|pts?|below|under|above|loss|\$\d+|atr)\b|\b(?:exit|close|sell|flatten)\b.{0,30}\b(?:if|when)\b.{0,25}\b(?:down|red|losing|negative|underwater)\b",
     "a loss exit / stop in other words (Law 0e)"),
]


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def P(*a) -> str:
    return os.path.join(ROBOT_DIR, *a)


# ---------------------------------------------------------------- ledger (append-only, hash-chained)
class LedgerError(RuntimeError):
    pass


def ledger_read() -> list[dict]:
    """Fails CLOSED: a line that does not parse (a torn final write included) is an error, never skipped."""
    p = P("ledger.jsonl")
    if not os.path.exists(p):
        return []
    lines = [x for x in open(p).read().split("\n") if x.strip()]
    out = []
    for i, x in enumerate(lines, 1):
        try:
            out.append(json.loads(x))
        except ValueError as e:
            where = "the FINAL line (a truncated write?)" if i == len(lines) else f"line {i}"
            raise LedgerError(f"ledger.jsonl is corrupt at {where}: {e}. Not guessing — repair by hand "
                              "from a backup and re-run; ROBOT will not append over a damaged chain") from e
    return out


def ledger_append(rec: dict) -> dict:
    os.makedirs(ROBOT_DIR, exist_ok=True)
    rows = ledger_read()
    prev = rows[-1]["entry_sha"] if rows else "GENESIS"
    body = {**rec, "seq": len(rows) + 1, "ts": now(), "prev_sha": prev}
    body["entry_sha"] = sha(json.dumps(body, sort_keys=True, default=str))
    new = not os.path.exists(P("ledger.jsonl"))
    with open(P("ledger.jsonl"), "a") as f:
        f.write(json.dumps(body, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())
    if new:
        fd = os.open(ROBOT_DIR, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return body


def ledger_verify() -> tuple[bool, str]:
    prev = "GENESIS"
    for i, r in enumerate(ledger_read(), 1):
        d = {k: v for k, v in r.items() if k != "entry_sha"}
        if d.get("prev_sha") != prev or r.get("entry_sha") != sha(json.dumps(d, sort_keys=True, default=str)):
            return False, f"ledger broken at seq {i}"
        prev = r["entry_sha"]
    return True, "ok"


_LOCK_FH = None


def acquire_lock() -> tuple[bool, str]:
    """One mutating ROBOT process at a time. Non-blocking: a second one fails fast, loudly."""
    global _LOCK_FH
    os.makedirs(ROBOT_DIR, exist_ok=True)
    fh = open(P(".lock"), "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False, f"another ROBOT process holds {P('.lock')} — refusing to run two at once"
    fh.seek(0)
    fh.truncate()
    fh.write(f"pid {os.getpid()} since {now()}\n")
    fh.flush()
    _LOCK_FH = fh
    return True, "locked"


def release_lock() -> None:
    global _LOCK_FH
    if _LOCK_FH is not None:
        try:
            fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_UN)
        finally:
            _LOCK_FH.close()
            _LOCK_FH = None


# ---------------------------------------------------------------- rule versions (immutable)
def next_version() -> int:
    """max(existing R*.txt, any version the ledger or champion history mentions) + 1 — a rollback must never reuse a number."""
    seen = [0]
    for f in (os.listdir(P("rules")) if os.path.isdir(P("rules")) else []):
        m = re.fullmatch(r"R(\d+)\.txt", f)
        if m:
            seen.append(int(m.group(1)))
    for r in ledger_read():
        for k in ("new_version", "champion_version"):
            if isinstance(r.get(k), int):
                seen.append(r[k])
    if os.path.exists(P("champion.json")):
        seen += [int(x["version"]) for x in json.load(open(P("champion.json")))]
    return max(seen) + 1


def save_rules(n: int, text: str) -> str:
    os.makedirs(P("rules"), exist_ok=True)
    p = P("rules", f"R{n:03d}.txt")
    if os.path.exists(p):
        if open(p).read() != text:
            raise RuntimeError(f"{p} exists with different text — rule versions are immutable")
        return p
    open(p, "w").write(text)
    return p


def parse_rules(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\.\s+(.*)", line)
        if m:
            out.append(m.group(2).strip())
        elif line.strip() and out:
            out[-1] += " " + line.strip()
    return out


def render_rules(rules: list[str]) -> str:
    return "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)) + ("\n" if rules else "")


# ---------------------------------------------------------------- proposal: validate + apply
def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


_NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUMALT = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)"
_LEVEL_RX = re.compile(r"\b(" + _NUMALT + r")\s*(?:x|×|\*|times|multiples? of)\s*(?:the\s+)?ATR"
                       r"|\b(" + _NUMALT + r")\s*(?:ATRs?|average true ranges?)\b"
                       r"|\b(?:double|twice|triple|treble)\s+(?:the\s+)?(?:ATR|average true range)", re.I)
_CLAIMWORD = r"(?:claim|bank|exit|take[- ]profit|take (?:the )?profit)"


def claim_levels(text: str) -> list[float]:
    out = []
    for m in _LEVEL_RX.finditer(text):
        g = (m.group(1) or m.group(2) or "").lower()
        if not g:
            out.append(2.0 if re.match(r"(?:double|twice)", m.group(0), re.I) else 3.0)
            continue
        out.append(float(_NUMWORD.get(g, g)))
    return sorted(out)


def _restates_claim_level(text: str) -> bool:
    for m in _LEVEL_RX.finditer(text):
        a, b = max(0, m.start() - 60), m.end() + 60
        if re.search(r"\b" + _CLAIMWORD + r"\b", text[a:b], re.I):
            return True
    return False


def validate_proposal(prop, rules_text: str, history: list[dict], ltrades: list[dict], lday: str) -> tuple[bool, str]:
    """Never raises: a malformed proposal is a rejection with a reason, not a crash."""
    try:
        return _validate(prop, rules_text, history, ltrades, lday)
    except Exception as e:                                  # noqa: BLE001 — by design, the validator is the boundary
        return False, f"proposal could not be validated ({type(e).__name__}: {str(e)[:100]})"


def _validate(prop: dict, rules_text: str, history: list[dict], ltrades: list[dict], lday: str) -> tuple[bool, str]:
    """Hard rejections (docs §5). `ltrades` = the recorded trades of the learning day; `history` = ledger rows."""
    if not isinstance(prop, dict):
        return False, "not an object"
    ch = str(prop.get("change", "")).upper()
    if ch not in ("ADD", "EDIT", "REMOVE"):
        return False, f"change must be ADD|EDIT|REMOVE, got {ch!r}"
    rules = parse_rules(rules_text)
    no = prop.get("rule_no")
    if ch in ("EDIT", "REMOVE") and not (isinstance(no, int) and 1 <= no <= len(rules)):
        return False, f"rule_no {no!r} is not an existing rule (1..{len(rules)})"
    if ch == "ADD" and len(rules) >= MAX_RULES:
        return False, f"rule set already at MAX_RULES={MAX_RULES}"
    lv1 = claim_levels(rules[0]) if rules else []
    if lv1 and ch in ("EDIT", "REMOVE") and no == 1:
        if ch == "REMOVE":
            return False, "rule 1 carries the claim level and is not removable (119 claim calibrations failed; do not re-tune it)"
        if claim_levels(str(prop.get("new_text", ""))) != lv1:
            return False, f"rule 1's claim level {lv1} may not be changed (119 claim calibrations failed; do not re-tune it)"
    if lv1 and ch in ("ADD", "EDIT") and no != 1 and _restates_claim_level(str(prop.get("new_text", ""))):
        return False, "the claim level belongs to rule 1 and is not tunable; do not restate it in another rule"
    if ch in ("ADD", "EDIT"):
        txt = str(prop.get("new_text", "")).strip()
        if not txt:
            return False, "new_text empty"
        if len(txt) > MAX_RULE_CHARS:
            return False, f"new_text {len(txt)} chars > {MAX_RULE_CHARS}"
        for rx, what in _FORBID:
            if re.search(rx, txt, re.I):
                return False, f"new_text contains {what}"
        if prop.get("not_a_stop_not_a_cap") is not True:
            return False, "not_a_stop_not_a_cap must be true"
    if prop.get("serves") not in SERVES:
        return False, f"serves must be one of {sorted(SERVES)}"
    if prop.get("metric") in BARRED_PRIMARY:
        return False, f"metric {prop.get('metric')!r} cannot be the declared primary (a trade count is a trade cap by the back door, Law 0e)"
    if prop.get("metric") not in MENU:
        return False, f"metric {prop.get('metric')!r} is not on the menu"
    if prop.get("direction") not in ("up", "down"):
        return False, "direction must be up|down"
    try:
        if float(prop.get("min_move")) <= 0:
            return False, "min_move must be > 0"
    except (TypeError, ValueError):
        return False, "min_move must be a number"
    for k in ("trigger_on_page", "expected_cost"):
        if not str(prop.get(k, "")).strip():
            return False, f"{k} is empty"
    cites = prop.get("cited_trades") or []
    if len(cites) < 3:
        return False, f"needs >= 3 cited trades, got {len(cites)}"
    pool = {(t["opened"][11:16], round(float(t["entry"]), 2)): t for t in ltrades}
    new_cites = 0
    for i, c in enumerate(cites, 1):
        if str(c.get("day", lday)) != lday:
            return False, f"citation {i} is not from the learning day"
        key = (str(c.get("opened", ""))[:5], round(float(c.get("entry", -1)), 2))
        hit = [t for (o, e), t in pool.items() if o == key[0] and abs(e - key[1]) <= 0.5]
        if not hit:
            return False, f"citation {i} ({c.get('opened')} @ {c.get('entry')}) matches no recorded trade on {lday}"
        if not str(c.get("why_it_matters", "")).strip():
            return False, f"citation {i} has no why_it_matters"
        new_cites += 1
    if ch in ("ADD", "EDIT"):
        for r in history:
            if r.get("decision") == "ACCEPT" or not r.get("proposal"):
                continue
            old = _norm((r["proposal"] or {}).get("new_text", ""))
            if old and difflib.SequenceMatcher(None, old, _norm(txt)).ratio() >= 0.8:
                return False, (f"near-duplicate of a rule REJECTED in cycle {r.get('cycle')} "
                               f"({r.get('reason', '')[:80]}) — new evidence needed (R7); citations from a different "
                               "day do not count as new for a verbatim retry")
    return True, "valid"


def apply_proposal(rules_text: str, prop: dict) -> str:
    rules = parse_rules(rules_text)
    ch, no = prop["change"].upper(), prop.get("rule_no")
    if ch == "ADD":
        rules.append(prop["new_text"].strip())
    elif ch == "EDIT":
        rules[no - 1] = prop["new_text"].strip()
    else:
        del rules[no - 1]
    return render_rules(rules)


def diff_is_one_rule(old: str, new: str) -> bool:
    a, b = parse_rules(old), parse_rules(new)
    if len(b) == len(a) + 1:
        return b[:len(a)] == a or any(a == b[:i] + b[i + 1:] for i in range(len(b)))
    if len(b) == len(a) - 1:
        return any(b == a[:i] + a[i + 1:] for i in range(len(a)))
    if len(b) == len(a):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    return False


# ---------------------------------------------------------------- metrics (code, never the model)
def poisoned(rec: dict) -> bool:
    c = rec.get("calls") or []
    return (not c) or sum(1 for x in c if x.get("error")) / len(c) > POISON_RATE


def metrics(rec: dict, bars=None) -> dict:
    """Every number is recomputed from the day record (R12). Bar-dependent ones are None when bars are absent."""
    t = rec["trades"]
    n = len(t)
    m = {
        "net_usd": round(sum(x["pnl_usd"] for x in t), 2),
        "gross_points": round(sum(x.get("points", 0.0) for x in t), 2),
        "trades_per_day": float(n),
        "exits_in_profit_share": (sum(1 for x in t if x["pnl_usd"] > 0) / n) if n else None,
        "never_green_share": (sum(1 for x in t if x.get("peak_pt", 0) <= 0) / n) if n else None,
        "hold_median": st.median([x["held_min"] for x in t]) if n else None,
        "worst_trade": min((x["pnl_usd"] for x in t), default=None),
        "giveback_count": None, "target_obedience": None, "same_side_rebuy_15": None,
    }
    try:
        import s_line_claim as SC
        m["same_side_rebuy_15"] = float(SC.rebuys(t, 15)[0])
        if bars is not None:
            tl = SC.target_looks(bars, rec.get("calls") or [], t)
            m["target_obedience"] = (sum(1 for x in tl if x["action"] == "EXIT") / len(tl)) if tl else None
            m["giveback_count"] = float(sum(1 for x in tl if x["final"] < 0.5 * x["mark"]))
    except Exception:
        pass
    return m


def moved(metric_name: str, direction: str, old: dict, new: dict) -> float | None:
    a, b = old.get(metric_name), new.get(metric_name)
    if a is None or b is None:
        return None
    return (b - a) * (1.0 if direction == "up" else -1.0)


# ---------------------------------------------------------------- the accept function (docs §6)
def decide(prop: dict, valid: tuple[bool, str], mL: dict, mL2: dict, mV: dict | None, mV2: dict | None,
           noise_band: float) -> dict:
    """A1 valid · A2 mechanism on L >= max(min_move, floor) · A3 guards on V (V net >= champion's, L+V net not worse)
    · A4 transfer on V. Doubts -> REJECT. `reason_public` is the direction-only text later cycles may see (R11)."""
    out = {"A1": {"ok": bool(valid[0]), "note": valid[1]}, "decision": "REJECT", "reason": "", "reason_public": ""}
    if not valid[0]:
        out["reason"] = f"A1 invalid proposal: {valid[1]}"
        out["reason_public"] = f"A1 the proposal was invalid: {valid[1]}"
        return out
    mv = moved(prop["metric"], prop["direction"], mL, mL2)
    need = max(float(prop["min_move"]), MIN_MOVE_FLOOR.get(prop["metric"], 0.0))
    out["A2"] = {"ok": mv is not None and mv >= need, "moved": mv, "needed": need, "declared": float(prop["min_move"]),
                 "in_sample": True}
    if not out["A2"]["ok"]:
        out["reason"] = (f"A2 mechanism: {prop['metric']} moved {mv} in the predicted direction, needed >= {need} "
                         "(rule not obeyed on its own learning day)")
        out["reason_public"] = "A2 mechanism: the rule did not move its declared metric far enough on its own learning day"
        return out
    if mV is None or mV2 is None:
        out["reason"] = out["reason_public"] = "validation day not run"
        return out
    g, gp = [], []
    d_share = None if None in (mV.get("exits_in_profit_share"), mV2.get("exits_in_profit_share")) else \
        mV2["exits_in_profit_share"] - mV["exits_in_profit_share"]
    if d_share is not None and d_share < -GUARD_EXIT_SHARE_PP:
        g.append(f"exits-in-profit share fell {d_share:+.2f}")
        gp.append("exits-in-profit share fell")
    d_worst = None if None in (mV.get("worst_trade"), mV2.get("worst_trade")) else mV2["worst_trade"] - mV["worst_trade"]
    if d_worst is not None and d_worst < -GUARD_WORST_TRADE_USD:
        g.append(f"worst trade worse by ${-d_worst:,.0f}")
        gp.append("the worst trade got worse")
    d_net = mV2["net_usd"] - mV["net_usd"]
    l_net = mL2["net_usd"] - mL["net_usd"]
    if d_net < 0:
        g.append(f"validation-day net below the champion's by ${-d_net:,.0f}")
        gp.append("the validation day finished worse than the champion on the same day")
    if l_net + d_net < 0:
        g.append(f"learning + validation net below the champion's by ${-(l_net + d_net):,.0f}")
        gp.append("the two days combined finished worse than the champion")
    out["A3"] = {"ok": not g, "failed": g, "d_exit_share": d_share, "d_worst": d_worst, "d_net": d_net,
                 "l_net": l_net, "lv_net": l_net + d_net, "noise_band": noise_band}
    tv = moved(prop["metric"], prop["direction"], mV, mV2)
    out["A4"] = {"ok": tv is not None and tv > 0, "moved": tv}
    if not out["A3"]["ok"]:
        out["reason"] = "A3 guard failed on the validation day: " + "; ".join(g)
        out["reason_public"] = "A3 guard failed: " + "; ".join(gp)
    elif not out["A4"]["ok"]:
        out["reason"] = f"A4 transfer: {prop['metric']} did not move the predicted way on the validation day ({tv})"
        out["reason_public"] = "A4 transfer: the declared metric did not move the predicted way on the validation day"
    else:
        out["decision"] = "ACCEPT"
        out["reason"] = (f"mechanism {mv:+.2f} on L (in-sample), transfer {tv:+.2f} on V, guards clear "
                         f"(V net diff {d_net:+,.0f}, L+V {l_net + d_net:+,.0f})")
        out["reason_public"] = "ACCEPT: the metric moved as declared on its learning day and again on the validation day, guards clear"
    return out


# ---------------------------------------------------------------- stats shared with the exam
def stats(nets: list[float]) -> dict:
    return {"days_positive": sum(1 for x in nets if x > 0), "worst_day": min(nets),
            "daily_sd": st.pstdev(nets) if len(nets) > 1 else 0.0,
            "usd_per_day": sum(nets) / len(nets), "n": len(nets), "total": sum(nets)}


_T90 = {1: 3.078, 2: 1.886, 3: 1.638, 4: 1.533, 5: 1.476, 6: 1.440, 7: 1.415, 8: 1.397, 9: 1.383, 10: 1.372,
        11: 1.363, 12: 1.356, 13: 1.350, 14: 1.345, 15: 1.341, 16: 1.337, 17: 1.333, 18: 1.330, 19: 1.328,
        20: 1.325, 21: 1.323, 22: 1.321, 23: 1.319, 24: 1.318, 25: 1.316, 26: 1.315, 27: 1.314, 28: 1.313,
        29: 1.311, 30: 1.310}


def paired_summary(a: list[float], b: list[float]) -> dict:
    """a = frozen R_final, b = S3, same days. One-sided 90% lower bound on the mean paired difference (t)."""
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    mean = sum(d) / n
    sd = st.stdev(d) if n > 1 else 0.0
    t = _T90.get(n - 1, 1.2816)
    se = sd / (n ** 0.5) if n else 0.0
    return {"n": n, "mean_diff": mean, "sd_diff": sd, "se": se, "t90": t, "lower90": mean - t * se,
            "days_positive_diff": sum(1 for x in d if x > 0), "final_days_positive": sum(1 for x in a if x > 0),
            "s3_days_positive": sum(1 for x in b if x > 0), "final_per_day": sum(a) / n, "s3_per_day": sum(b) / n}


def touched_days(sim_dir: str, doc_dirs: list[str]) -> set[str]:
    """Days that already have a sim record or are named in an S-line document: not fresh out-of-sample."""
    import glob
    rx = re.compile(r"\d{4}-\d{2}-\d{2}")
    out: set[str] = set()
    for f in glob.glob(os.path.join(sim_dir, "*.json")):
        out.update(rx.findall(os.path.basename(f)))
    for d in doc_dirs:
        for f in glob.glob(os.path.join(d, "*.txt")) + glob.glob(os.path.join(d, "*.md")):
            try:
                out.update(rx.findall(open(f, errors="replace").read()))
            except OSError:
                pass
    return out


def pick_confirmation(seed: int, candidates: list[str], char_fn, k: int = CONFIRMATION_N) -> list[str]:
    """k untouched days, stratified round-robin over the same three character buckets build_pool makes."""
    bp = build_pool(seed, candidates, char_fn)
    b = [list(x) for x in bp["buckets"]]
    out, i = [], 0
    while len(out) < k and any(b):
        if b[i % 3]:
            out.append(b[i % 3].pop(0))
        i += 1
    return sorted(out)


def hour_block(recs: list[dict], fee_per_trade: float = 6.0) -> str:
    """Code-computed aggregate of trades by UTC hour OPENED, over the records passed (learning-pool days only)."""
    agg: dict[int, list] = {}
    for r in recs:
        for t in r.get("trades") or []:
            h = int(str(t["opened"])[11:13])
            a = agg.setdefault(h, [0, 0.0])
            a[0] += 1
            a[1] += t["pnl_usd"]
    if not agg:
        return "(no earlier learning days yet)"
    L = [f"Trades by UTC hour opened, pooled over {len(recs)} earlier learning day(s) (computed by code; counts are small, treat as context only):"]
    for h in sorted(agg):
        n, net = agg[h]
        L.append(f"  {h:02d}:00-{h:02d}:59  n={n:>3}  gross ${net + fee_per_trade * n:+9,.0f}  net ${net:+9,.0f}")
    return "\n".join(L)


# ---------------------------------------------------------------- pool (seeded, stratified, consumed without replacement)
def day_character(day: str) -> float | None:
    """Session-window range in ATRs (the stratifier). None when the lake lacks a full session."""
    import sim_week_recursive as SW
    bars, _ = SW.load_day(day)
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    w = [b for b in bars if d0 + SW.WIN_START_MIN * 60 <= b[0] <= d0 + SW.WIN_END_MIN * 60]
    if len(w) < 500:
        return None
    a = SW.atr14(w)
    return ((max(b[1] for b in w) - min(b[2] for b in w)) / a) if a else None


def build_pool(seed: int, candidates: list[str], char_fn) -> dict:
    ch = {}
    for d in candidates:
        if d in EXAM or d in HOLDOUT_DAYS:
            continue
        c = char_fn(d)
        if c is not None:
            ch[d] = c
    ds = sorted(ch, key=lambda d: ch[d])
    k = len(ds) // 3
    buckets = [ds[:k], ds[k:2 * k], ds[2 * k:]]
    rng = random.Random(seed)
    for b in buckets:
        rng.shuffle(b)
    return {"seed": seed, "buckets": buckets, "character": {d: round(ch[d], 2) for d in ds}}


def next_pair(pool: dict, used: list[str], n: int) -> tuple[str, str] | None:
    left = [[d for d in b if d not in used] for b in pool["buckets"]]
    order = [n % 3, (n + 1) % 3, (n + 2) % 3]
    l = next((left[i][0] for i in order if left[i]), None)
    if l is None:
        return None
    left = [[d for d in b if d != l] for b in left]
    lb = next(i for i, b in enumerate(pool["buckets"]) if l in b)
    other = [i for i in order if i != lb] + [lb]
    v = next((left[i][0] for i in other if left[i]), None)
    return (l, v) if v else None


# ---------------------------------------------------------------- digest + lessons + status + changelog
_NUM_RX = re.compile(r"(?<![A-Za-z0-9_.])[-+]?(?:\$\s?)?\d[\d,]*(?:\.\d+)?")
_USD_RX = re.compile(r"[-+]?\$\s?\d[\d,]*(?:\.\d+)?")


def scrub_numbers(text: str) -> str:
    """No figures at all: later cycles may read direction words, never a validation-day number (R11)."""
    return _NUM_RX.sub("#", text or "")


def scrub_dollars(text: str) -> str:
    return _USD_RX.sub("$#", text or "")


def digest(rows: list[dict]) -> str:
    out = []
    for r in rows:
        if r.get("kind") != "cycle":
            continue
        p = r.get("proposal") or {}
        what = (f"{p.get('change', '?')} {('rule ' + str(p.get('rule_no'))) if p.get('rule_no') else ''}: "
                f"\"{(p.get('new_text') or '')[:160]}\"" if p else "NO_CHANGE")
        why = r.get("reason_public") or scrub_numbers(r.get("reason", ""))
        out.append(f"cycle {r['cycle']}: tried {what} | predicted {p.get('metric', '-')} {p.get('direction', '')} "
                   f"| {r.get('decision')}: {why[:200]}")
    return "\n".join(out) if out else "(no earlier cycles — this is the first)"


def lessons_read() -> list[dict]:
    p = P("lessons.json")
    return json.load(open(p)) if os.path.exists(p) else []


def lessons_add(cycle: int, text: str) -> list[dict]:
    ls = lessons_read()
    ls.append({"cycle": cycle, "text": scrub_dollars(text.strip())[:600], "superseded": False})
    live = [x for x in ls if not x["superseded"]]
    while len(live) > MAX_LESSONS:                 # oldest live lesson is retired (marked, never deleted)
        live[0]["superseded"] = True
        live[0]["note"] = f"retired at cycle {cycle} (cap {MAX_LESSONS})"
        live = [x for x in ls if not x["superseded"]]
    json.dump(ls, open(P("lessons.json"), "w"), indent=1)
    open(P("lessons.md"), "w").write("\n".join(
        f"- [c{x['cycle']}]{' (SUPERSEDED)' if x['superseded'] else ''} {x['text']}" for x in ls) + "\n")
    return ls


def lessons_text() -> str:
    return "\n".join(f"- (cycle {x['cycle']}) {x['text']}" for x in lessons_read() if not x["superseded"]) or "(none yet)"


def write_status(extra: dict) -> None:
    try:
        rows = [r for r in ledger_read() if r.get("kind") == "cycle"]
    except LedgerError as e:                    # a damaged ledger must still be able to say HALTED
        rows = []
        extra = {**extra, "ledger": f"UNREADABLE — {str(e)[:160]}"}
    acc = [r for r in rows if r["decision"] == "ACCEPT"]
    s = ["# PROJECT ROBOT — STATUS (regenerated every cycle)", "", f"updated: {now()}", "",
         f"cycles: {len(rows)}   accepted: {len(acc)}   rejected: "
         f"{sum(1 for r in rows if r['decision'] == 'REJECT')}   no-change: {sum(1 for r in rows if r['decision'] == 'NO_CHANGE')}",
         "", f"NOTE: {EXAM_LABEL}.", ""]
    for k, v in extra.items():
        s.append(f"- {k}: {v}")
    s += ["", "## last 5 cycles"]
    for r in rows[-5:]:
        s.append(f"- c{r['cycle']} L={r.get('L')} V={r.get('V')} {r['decision']} — {r.get('reason', '')[:160]}")
    os.makedirs(ROBOT_DIR, exist_ok=True)
    open(P("STATUS.md"), "w").write("\n".join(s) + "\n")


def write_changelog() -> None:
    L = ["# CHANGELOG — generated from ledger.jsonl, never hand-written", ""]
    for r in ledger_read():
        if r.get("kind") != "cycle":
            continue
        p = r.get("proposal") or {}
        L.append(f"## cycle {r['cycle']} — {r['decision']}  ({r['ts']})")
        L.append(f"- learn day {r.get('L')}, validate day {r.get('V')}; champion {str(r.get('champion_sha'))[:8]}"
                 + (f" -> {str(r.get('challenger_sha'))[:8]}" if r.get("challenger_sha") else ""))
        if p:
            L.append(f"- change: {p.get('change')} rule {p.get('rule_no')}: {p.get('new_text')}")
            L.append(f"- why (cited trades): " + "; ".join(
                f"{c.get('opened')} @ {c.get('entry')}: {c.get('why_it_matters')}" for c in (p.get('cited_trades') or [])))
            L.append(f"- predicted: {p.get('metric')} {p.get('direction')} >= {p.get('min_move')}; cost: {p.get('expected_cost')}")
        L.append(f"- result: {r.get('reason')}")
        L.append("")
    open(P("CHANGELOG.md"), "w").write("\n".join(L) + "\n")
