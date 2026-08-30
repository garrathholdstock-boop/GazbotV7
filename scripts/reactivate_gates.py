#!/usr/bin/env python3
"""Paris-midnight auto-reactivation — a gate turned off is off FOR THE DAY only.

The intraday off-switch (data/gate_switches.env) stops a gate's new entries, but nothing expired
it: a gate set off just stayed off until someone flipped it back (rgv_short sat off ~2 days,
2026-07-21→23). Operator rule (2026-07-23): an off lasts 1 day and auto-reactivates at Paris
midnight (the desk's trading-day boundary — daily P&L rolls there too). Run by a systemd timer at
00:00 Europe/Paris (DST-handled by systemd). Idempotent: nothing off → no write, no noise. A
LONGER hold (e.g. a relegation candidate) is the Saturday roster action, not this switch.

  python scripts/reactivate_gates.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/alphabot/gazbot7/src")
import re  # noqa: E402

from gazbot7.telegram_bot import apply_gate_switch as _apply  # noqa: E402
from gazbot7.telegram_bot import reactivate_all  # noqa: E402
from gazbot7.session import is_open as _session_is_open  # noqa: E402

SWITCH = "/home/alphabot/gazbot7/data/gate_switches.env"

# ★2026-08-01 (audit FIX): gates this nightly job must NEVER auto-arm. The 1-day-expiry rule
# assumes an "off" is an intraday ROUTER bench of a gate that has already earned its place. It is
# WRONG for a gate that has never been accepted: nipc_* shipped BENCHED because its acceptance
# replay (scripts/nipc_replay.py) failed to reproduce the lab (+$264/n=159 vs +$2,676/n=171), and
# gate_switches.env says in plain text "SHIPS BENCHED — the operator arms it after reviewing".
# Without this, the 00:00 Europe/Paris timer (22:00 UTC — i.e. the Sunday reopen minute) silently
# flips them to on and a never-validated construct trades live. The Telegram /on command and
# telegram_bot.reactivate_all are untouched, so the operator can still arm them by hand.
# Revert: HOLD = frozenset().
#
# ★2026-08-01 (operator, explicit): "every gate we have should re-enable for the midnight open. then
# the router manages." So HOLD is EMPTY by policy — no gate is exempt from the 1-day rule. rgv_short was
# briefly held here and has been released: its week-long bench now lives in the ROUTER's standing
# guidance (scripts/router_tick_durable.py) instead, which is the right home for it — the router re-reads
# the regime every 5 min and can bench it again straight after the midnight re-arm.
# Rationale for the policy: the midnight re-arm is the SESSION reopen on quiet overnight tape, ~15h
# before the 13:30 UTC cash open. We have no regime read at 22:00, so starting armed and letting the
# router bench on evidence beats starting benched on yesterday's opinion. The "arm veto-gates only"
# lesson applies to the VIOLENT CASH OPEN, not to the midnight reopen — different tape, different call.
# NOTE this job is genuinely dangerous for a NEVER-VALIDATED gate: it flips every =off to =on with no
# idea why the gate was off. If a future gate ships benched pending review, hold it HERE, not in a
# comment — nothing reads comments. (nipc_* was held here until the operator armed it on 08-01.)
# ★2026-08-03 — nipc_* held. This is the documented EXCEPTION to the operator's "every gate re-enables
# at midnight" policy: that rule assumes an "off" is an intraday ROUTER bench of a gate that has earned
# its place. nipc is benched for DIAGNOSIS — its live signals diverge from the shipped decider by $655
# in the opposite direction, so every further session adds data that cannot count toward its n>=40
# review. The 22:00 job re-armed it once already tonight because the warning was written as a COMMENT
# in gate_switches.env and nothing reads comments. Holding it here is the only mechanism that works.
# Remove once the divergence is diagnosed and the replay reproduces live within a stated tolerance.
# ★2026-08-15 nipc dropped from HOLD — it is retired from the roster entirely now, so there is no
# switch to re-arm and nothing to hold back. rgv_short stays: it is still a live spec.
# ★★★2026-08-20 OPERATOR DECISION — THE TOURNAMENT IS STOOD DOWN. THE DAY RIDER IS THE ONLY DESK.
# "the only thing that trades is day rider ... turn all other gates off."
# ALL SIX tournament gates are held OFF at the Paris-midnight reopen. This is the whole roster, so
# the reopen now arms nothing at all.
# ⚠ WHY HERE AND NOT JUST IN gate_switches.env: this job re-arms every `=off` gate at 22:00Z and it
#   writes the file DIRECTLY. A comment in gate_switches.env does not stop it — nothing reads
#   comments, which is the exact failure documented above for rgv_short. HOLD is the only mechanism
#   that works. The router is separately PINNED off the whole roster in router_tick_durable.py.
# REVERT (restores the previous policy exactly): HOLD = frozenset({"rgv_short"})
# ★2026-08-26 RESTORED to the pre-standdown roster. The full-roster HOLD was the mechanical half
# of the 08-20 tournament stand-down; with it in place the 22:00Z reopen arms NOTHING, so lifting
# TOURNAMENT_STOOD_DOWN alone would leave the router able to bench but never arm.
# rgv_short stays held for the 2026-08-09 churn reason documented immediately below — that is a
# separate, still-valid decision and is NOT part of the stand-down.
HOLD: frozenset = frozenset({"rgv_short"})

# ★★2026-08-09 — rgv_short ADDED TO HOLD. This reverses the 08-01 release noted above, which moved
# its bench from here into the router's standing guidance. That was the right call at the time and
# it has been running as designed; the problem is that the design produces pure churn:
#   · reactivate_gates arms it at every 22:00 reopen (it was the ONLY gate tonight would have armed)
#   · the router's standing rule (a) benches it again within a tick or two, every single night
#   · rule (a)'s own re-look date — "on/after 2026-08-08" — passed with no new evidence for it
# and underneath that, its two filters are COMPLEMENTS. direction_router.py:78 puts it in UP_OFF
# (benched in TREND_UP), but measured over 40 days of tape it fires 72.5% in TREND_UP, 0.0% in
# TREND_DOWN and 27.5% in chop; the signal journal agrees independently at 9 of 9 fires in TREND_UP.
# So the router removes ~three-quarters of its signal population by construction and it never fires
# in the regime where it would be kept armed. Live since the 07-29 cutover: ONE signal, -$107.
# Its 07-31 verdict was SHADOW (11 fires, -$142, negative at EVERY exit rung, strip-best-1 -$242),
# so arming it nightly to re-bench it by hand buys nothing and costs a switch change every night.
# ⚠ HOLD is the honest mechanism for "benched pending a decision" — it is NOT a retirement, and it
# does not fix the pairing. Reviving this gate means fixing the UP_OFF contradiction FIRST, because
# a revival that leaves it benched in the only regime it fires in is not a revival.
# Revert: drop "rgv_short" from HOLD.

# ★★2026-08-09 — MONDAY #2 (fix-midnight-reopen-reversion-only-0808), operator-picked LIVE 08-08.
# The 22:00 reopen no longer arms the whole roster. It arms the REVERSION gates only; MOMENTUM gates
# start BENCHED and the router must ARM them on evidence (structure break + ER climbing + vol
# expanding — and per MONDAY #4, vol expansion alone is not enough).
#
# WHY this supersedes the 08-01 "every gate re-enables at midnight" policy quoted above: that policy
# was argued from "we have no regime read at 22:00, so starting armed beats starting benched on
# yesterday's opinion." The report's biggest single number says the opposite for MOMENTUM — chop
# avoidance — and a momentum gate armed into 15h of overnight chop is precisely the wrongly-armed
# error the standing asymmetry calls expensive. Reversion gates are the ones that earn through chop,
# so they keep the old behaviour. Nothing here is irreversible: the router can arm any of these on
# the very next 5-minute tick.
#
# ★ abs_veto_short is a THRUST gate (momentum by mechanism) but is listed as REVERSION-side here
# DELIBERATELY, because SATURDAY #1 (absveto-short-arm-by-default-er035-0808) arms it BY DEFAULT and
# explicitly includes "fix the 22:00 auto re-arm" — it is positive in all five regimes including
# chop, and a reopen that benched it would silently undo the arm-by-default it is being reviewed on.
# If SATURDAY #1's 15-fire review ends AGAINST the gate, move it to MOMENTUM_START_BENCHED.
#
# Revert (restores the 08-01 all-on policy exactly): MOMENTUM_START_BENCHED = frozenset().
MOMENTUM_START_BENCHED: frozenset = frozenset({"grind_long", "abs_veto_long"})


def run() -> int:
    # ★★★2026-08-20 THE CROSS-DESK KILL MUST SURVIVE THE REOPEN.
    # deskrecon stops BOTH desks when `venue != tournament + rider` and writes desk_kill.json;
    # CLAUDE.md says it "never re-arms — --release is a human act". That was TRUE for the rider
    # (single writer, off-only) and FALSE for the tournament: this job re-armed its gates at the
    # next 22:00Z whether or not a human had released the kill. Failure: reconcile confirms a breach
    # at 20:00Z on an unreconciled shared account, and two hours later the tournament trades again
    # while the rider stays correctly frozen.
    try:
        import json as _json
        _k = _json.load(open("/home/alphabot/gazbot7/data/desk_kill.json"))
        if _k.get("active"):
            print("reactivate_gates: REFUSED — desk_kill.json is ACTIVE. Release it by hand; "
                  "a kill is not lifted by a clock.")
            return 0
    except FileNotFoundError:
        pass                      # no kill file = no kill, the normal case
    except Exception as _e:
        print(f"reactivate_gates: REFUSED — desk_kill.json unreadable ({_e}). Failing CLOSED: "
              f"an unreadable kill file is not evidence that there is no kill.")
        return 0

    try:
        with open(SWITCH) as f:
            text = f.read()
    except OSError as e:
        print(f"reactivate_gates: no switch file ({e}) — nothing to do")
        return 0

    # ★★★2026-08-29 WEEKENDS ARE OFF. Operator: "everything should be off on weekends."
    # This job runs at 00:00 Europe/Paris EVERY day, which is 22:00Z — and on Friday that is one
    # hour AFTER the CME halt. On 2026-08-28 it armed three gates into a venue that was shut until
    # Sunday; the router benched two as "housekeeping, not evidence" and capitulation_long sat
    # armed for the whole weekend.
    # session.is_open() already draws the line exactly where it is needed, so no new clock is
    # invented here:  Fri 22:00Z -> False (weekend) · Sat 22:00Z -> False · Sun 22:00Z -> TRUE,
    # because that instant IS the reopen. So the same timer arms on Sunday and disarms on Friday
    # and Saturday, with no extra unit and no second definition of "the weekend" to drift.
    _now = datetime.now(timezone.utc)
    if not _session_is_open(_now):
        off = re.sub(r"^(\w+)=on\s*$", r"\1=off", text, flags=re.M)
        changed = sorted(m.group(1) for m in re.finditer(r"^(\w+)=on\s*$", text, flags=re.M))
        if changed:
            tmp = SWITCH + ".tmp"          # same atomic write the arm path uses
            with open(tmp, "w") as fh:
                fh.write(off)
            os.replace(tmp, SWITCH)
            print(f"reactivate_gates: VENUE SHUT ({_now:%a %H:%M}Z) — benched {', '.join(changed)}. "
                  f"Nothing arms until the Sunday reopen.")
        else:
            print(f"reactivate_gates: VENUE SHUT ({_now:%a %H:%M}Z) — already all off, nothing to do.")
        return 0

    new, reactivated = reactivate_all(text)
    # ★ HOLD and MOMENTUM_START_BENCHED are NOT applied the same way, and the difference is the
    # whole point of MONDAY #2:
    #   HOLD                   — "never AUTO-ARM this gate". It only has to undo an arm, so it acts
    #                            on `reactivated` (the gates that were off and just got flipped on).
    #   MOMENTUM_START_BENCHED — "this gate STARTS THE SESSION BENCHED". That is a START STATE, so
    #                            it must be applied UNCONDITIONALLY, including to a gate that was
    #                            already ARMED going into the reopen.
    # ⚠2026-08-09 BUG FIXED HERE, found by audit before it ever ran: the first version filtered
    # BOTH sets through `reactivated`, which made MOMENTUM_START_BENCHED vacuous for any momentum
    # gate already on at 22:00. `abs_veto_long` was on, so it would have sailed through the reopen
    # armed while gate_switches.env told the router it had been benched — the file documenting a
    # behaviour that does not happen. A re-bench filter is not a start state.
    held = sorted(HOLD & set(reactivated))
    benched = sorted(MOMENTUM_START_BENCHED)          # ← unconditional, not filtered by reactivated
    for g in held + benched:
        new = _apply(new, g, "off")
    reactivated = [g for g in reactivated if g not in (HOLD | MOMENTUM_START_BENCHED)]
    if held:
        print(f"reactivate_gates: HELD (not auto-armed): {', '.join(held)}")
    if benched:
        print(f"reactivate_gates: MOMENTUM start-benched (MONDAY #2 — router arms on "
              f"evidence): {', '.join(benched)}")
    # ★ The write test is now "did the FILE change", not "did we arm anything". Those differ: a run
    # that arms nothing but has to bench an already-armed momentum gate MUST still write.
    if new == text:
        print("reactivate_gates: nothing to change — file already in the target state")
        return 0
    tmp = SWITCH + ".tmp"
    with open(tmp, "w") as f:
        f.write(new)
    os.replace(tmp, SWITCH)  # atomic; the tournament re-reads live (no restart)
    _bench_note = ""
    if MOMENTUM_START_BENCHED:
        _bench_note = (f" | momentum start-benched per MONDAY #2 "
                       f"({', '.join(sorted(MOMENTUM_START_BENCHED))}) — router arms on evidence")
    _armed = ", ".join(reactivated) if reactivated else "none"
    msg = (f"gates auto-reactivated at Paris midnight (1-day off expired): {_armed}{_bench_note}")
    print(f"reactivate_gates: {msg}")
    try:
        from gazbot7.notify import notify
        notify(f"V7 — {msg}. Re-off any you want held (a longer hold is the Saturday roster call).",
               critical=False)
    except Exception as e:
        print(f"reactivate_gates: notify skipped ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
