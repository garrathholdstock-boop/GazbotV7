"""THE TRADE POLICY — the small, declarative set of numbers the nightly lab is allowed to move.

★★★ docs/SCOPE_RECURSIVE_TRADING_LOOP.md. Operator: *"the nightly lab should just be fine tuning
entries and exits. thats it. metrics changed sloghrly for the next day."*

That sentence is the whole design, and the two halves of it are both load-bearing:

  "ENTRIES AND EXITS, THATS IT"   — the policy is a FIXED, human-reviewed vocabulary of numbers.
                                    The lab may change their VALUES. It may not add a parameter,
                                    invent a feature, or write code. Extending the vocabulary is a
                                    human change, deliberately.
  "CHANGED SLIGHTLY"              — at most ONE parameter moves per night, by at most ONE STEP.

★★ THE STEP LIMIT IS NOT TIMIDITY, IT IS THE ANTI-OVERFITTING DEVICE. An unconstrained nightly
optimiser on 616 sessions will find a pathology — this desk has measured that 5,026 specs reproduce
a published t=5.83 from pure noise 13% of the time, and that 6 of 6 NULL worlds cleared all three
naive bars. A one-step-per-night walk cannot leap to an overfit optimum: it has to survive forward
evidence at every intermediate point, and `degraded()` reverses it when it does not. Slow is the
mechanism, not a compromise.

⚠⚠⚠ THE LOOP WRITES DATA, NEVER CODE. This file defines the shape; the lab writes values; the rider
would READ them. So the worst an experimental failure can produce is a bad NUMBER inside a declared
range — never a crash, a naked position, or a runaway. An invalid file falls back to BASELINE and
says so loudly.

⚠ WHAT IS OUTSIDE THIS POLICY AND CANNOT BE TOUCHED BY IT: the 20:40Z hard flat, `eod_flatten`,
`desk_reconcile`, the daily loss limit, and the catastrophe stop. Those are the floor; a research
loop may not reach them. A test asserts none of their names appear here.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

POLICY_PATH = os.environ.get("GAZBOT7_POLICY", "/home/alphabot/gazbot7/data/trade_policy_active.json")
SHADOW_PATH = os.environ.get("GAZBOT7_POLICY_SHADOW",
                             "/home/alphabot/gazbot7/data/trade_policy_shadow.json")


@dataclass(frozen=True)
class Param:
    """One tunable number: its range, its step, and WHY it is allowed to move."""
    name: str
    default: float
    lo: float
    hi: float
    step: float
    unit: str
    why: str


# ── THE VOCABULARY. Adding a row here is a HUMAN decision, never the lab's. ─────────────────────
PARAMS: tuple[Param, ...] = (
    # ENTRY — deliberately few. Every automated entry rule tested so far is inside the noise of a
    # random entry, so the entry side starts as a SHADOW reading and these exist to be tuned once
    # the greenfield study names a signal worth tuning.
    Param("entry_min_leg_atr", 6.0, 3.0, 12.0, 0.5, "ATR",
          "how extended the old move must be before a turn is worth acting on. The operator's "
          "phrase is 'once its run a lot'; leg_watch already uses 6.0 as its size gate."),
    Param("entry_confirm_min", 15.0, 0.0, 60.0, 5.0, "minutes",
          "how long the new direction must HOLD before entering. This is the 'and then for a "
          "period it changes' half — the only thing separating a turn from a wobble. Measured: at "
          "zero confirmation, net-direction flips fire 42-87 times a session."),
    # ★★★2026-10-02 THE QUIET-TURN PARAMETER, and it is now the central one. Operator: "the turns
    # are not violent. they often just change direction... more often than not it can just start
    # grinding in that direction." Every signal this desk had tested was a MAGNITUDE detector —
    # retrace from the extreme, net-direction flips, EMA crossovers, CVD climax, volume spikes — and
    # none of them can see a leg that merely stops rising. A stall measured in TIME needs no
    # magnitude event at all, which is why it is the one feature that matches his description.
    Param("entry_stall_min", 20.0, 5.0, 60.0, 5.0, "minutes",
          "minutes with no new extreme before the old leg is treated as over. The quiet-turn "
          "trigger. ⚠ UNMEASURED at the time of writing — the greenfield study of 2026-10-02 is "
          "what populates its evidence, and until then this parameter must not be acted on."),
    Param("entry_max_per_session", 5.0, 3.0, 6.0, 1.0, "trades",
          "the trade-count band. Legs run 3.1/day, so 3-6 is the tradeable window; 23 entries on "
          "2026-09-28 lost $1,882.50 while 19 of them aligned with the line made +$1,010."),

    # EXIT — where the measured edge actually is.
    Param("exit_min_hold_min", 15.0, 0.0, 45.0, 5.0, "minutes",
          "do not bank before this. MEASURED on clean fills at entry level: under-15min holds are "
          "-$47.89/entry, 15-60min are +$33.21, 1-4h are +$88.28. The single clearest gradient in "
          "the book and the reason the exit is the loop's first subject."),
    Param("exit_max_hold_min", 240.0, 120.0, 480.0, 30.0, "minutes",
          "bank by this. Over-4h entries are -$705.00/entry (n=7) and the five worst trades in the "
          "book are 48% of all losses — all LONG, all held 3h+."),
    Param("exit_lot1_target_pt", 50.0, 40.0, 120.0, 10.0, "points",
          "the first lot's profit target. Reach rates over 231 lake sessions: 50pt 77.5%, 100pt "
          "58.0%, 200pt 29.4%. Banking at 50 on a 298pt median leg is the ladder's most "
          "front-loaded choice and has never been compared to an alternative."),
    Param("exit_giveback_atr", 2.0, 1.0, 5.0, 0.5, "ATR",
          "give-back from the peak that raises the exit question. EXIT_ASK uses 2.0 today and it "
          "has never been validated."),
)

BY_NAME = {p.name: p for p in PARAMS}
BASELINE = {p.name: p.default for p in PARAMS}

# names the loop may never write, because they are the floor rather than a parameter
FORBIDDEN = ("hard_flat", "flat_utc", "eod_flatten", "desk_reconcile", "daily_loss",
             "kill", "venue_stop", "catastrophe", "lots", "qty", "account")


def validate(d: dict) -> tuple[bool, str]:
    """A policy is valid only if every key is declared and every value is in range and on-step.

    ⚠ FAIL CLOSED AND SAY WHY. A silently-coerced value is a policy nobody can audit, and the whole
    promise of this layer is that every number is traceable to an experiment.
    """
    if not isinstance(d, dict):
        return False, "policy is not an object"
    unknown = set(d) - set(BY_NAME) - {"_meta"}
    if unknown:
        return False, f"undeclared parameter(s): {sorted(unknown)}"
    for bad in FORBIDDEN:
        if any(bad in k.lower() for k in d):
            return False, f"policy may not contain '{bad}' — that is the floor, not a parameter"
    for k, v in d.items():
        if k == "_meta":
            continue
        p = BY_NAME[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return False, f"{k} is not a number"
        if not (p.lo <= v <= p.hi):
            return False, f"{k}={v} outside [{p.lo}, {p.hi}]"
        steps = (v - p.lo) / p.step
        if abs(steps - round(steps)) > 1e-6:
            return False, f"{k}={v} is not on the {p.step}{p.unit} step grid"
    return True, "ok"


def load(path: str = POLICY_PATH) -> tuple[dict, str]:
    """Return (policy, note). An unreadable or invalid file yields BASELINE and a loud note."""
    try:
        with open(path) as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return dict(BASELINE), "no policy file — running BASELINE"
    except Exception as e:
        return dict(BASELINE), f"policy unreadable ({type(e).__name__}) — running BASELINE"
    ok, why = validate(d)
    if not ok:
        return dict(BASELINE), f"policy INVALID ({why}) — running BASELINE"
    merged = dict(BASELINE)
    merged.update({k: float(v) for k, v in d.items() if k != "_meta"})
    return merged, "ok"


def save(policy: dict, path: str, meta: dict | None = None) -> None:
    ok, why = validate({k: v for k, v in policy.items() if k != "_meta"})
    if not ok:
        raise ValueError(f"refusing to write an invalid policy: {why}")
    out = {k: v for k, v in policy.items() if k != "_meta"}
    out["_meta"] = meta or {}
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)          # atomic: a reader never sees half a policy


def neighbours(policy: dict) -> list[tuple[str, float, dict]]:
    """Every policy ONE STEP away on exactly ONE parameter.

    ★★ THIS IS THE "changed slightly" CONSTRAINT MADE MECHANICAL. The candidate set each night is
    at most 2 x len(PARAMS) — 14 — and never a grid. A grid search over seven parameters is how a
    nightly loop becomes a noise-mining machine; a one-step walk has to earn every step forward.
    """
    out = []
    for p in PARAMS:
        cur = float(policy.get(p.name, p.default))
        for delta in (-p.step, +p.step):
            v = round(cur + delta, 6)
            if p.lo <= v <= p.hi:
                cand = dict(policy)
                cand[p.name] = v
                out.append((p.name, v, cand))
    return out


def describe(policy: dict, other: dict | None = None) -> str:
    """Human-readable, with the delta against another policy when given."""
    lines = []
    for p in PARAMS:
        v = policy.get(p.name, p.default)
        if other is not None and other.get(p.name, p.default) != v:
            lines.append(f"  {p.name:<24} {v:>7g} {p.unit:<8} "
                         f"(was {other.get(p.name, p.default):g})  ← CHANGED")
        else:
            lines.append(f"  {p.name:<24} {v:>7g} {p.unit}")
    return "\n".join(lines)
