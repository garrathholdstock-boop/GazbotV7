#!/usr/bin/env python3
"""DURABLE ROUTER TICK — one router decision via HEADLESS Claude, no live session needed.

Invoked by systemd (gazbot7-router-tick.timer) every 5 min. This is the ROBUSTNESS layer:
the router keeps managing the desk even after a Claude *session* ends.

SAFE ARCHITECTURE: this trusted wrapper gathers the desk state as TEXT, asks headless
`claude -p` (NO tools — pure reasoning) for a JSON decision, then THIS script applies it.
Claude never runs commands. FAIL-SAFE: any error / non-parse / invalid decision => NO
switch change (gate_switches.env left untouched). Benching-only, PAPER; stops/safety untouched.
"""
import subprocess, json, os, re, time
from datetime import datetime, timezone

GB = "/home/alphabot/gazbot7"
SW = f"{GB}/data/gate_switches.env"
LOG = f"{GB}/data/router_trial_log.txt"
HLOG = f"{GB}/data/router_headless.log"
PY = f"{GB}/.venv/bin/python"
GATES = ["grind_long", "capitulation_long", "abs_veto_long", "exhaustion_short", "abs_veto_short", "rgv_short",
         "nipc_long", "nipc_short"]   # ★2026-08-01: + nipc (news-impulse pullback), ships BENCHED
# ★ 2026-08-01 (operator: "frozenset") — FULL ROUTER CONTROL RESTORED. No gate is pinned.
#
# History: the 07-31 "enable all gates, US OPEN" override pinned ALL SIX gates. Because apply-time
# filters on `g not in PINNED`, a full-roster pin makes `valid` permanently empty — the router became
# a SILENT NO-OP: 411 ticks across 07-31/08-01 logged "no change" and applied nothing, the last real
# switch change being 2026-07-30T22:15. "no change" reads as healthy, which is exactly what masked it,
# and it left the churner armed into the 07-31 violent open (grind −$370) with the meter unable to bench.
#
# Why frozenset() and not the comment's prescribed frozenset({"exhaustion_short"}): the 0.5R/1.5R
# fade-scalp trial that pin protected is superseded (exit re-cut to 0.75R/k1.5), and the weekend
# re-derivation found that for exhaustion the BENCH matters more than the R — no exit rescues a
# violent-whipsaw entry at any R. Pinning a fader ON disables the fader bench, which was the only
# router behaviour that survived every robustness test (+$810 non-overlap, n=25, stable under every
# independent regime tag). So the fader is exactly the gate that must stay benchable.
#
# To pin again: PINNED = frozenset({"<gate>"}) — and give it an expiry, because see above.
#
# ★2026-08-01 (audit FIX) — nipc_long/nipc_short are pinned (they are OFF, so this pins them OFF).
# gate_switches.env carries the operator instruction "SHIPS BENCHED … Router: do not arm them",
# but read_switches() strips comments, so the router NEVER SEES that sentence — the only thing
# standing between an LLM tick and arming a gate that FAILED its acceptance replay was a paragraph
# of prose in the prompt whose surrounding RULES ("re-arm momentum on a real range-break") actively
# argue the other way. PINNED is the mechanism built for exactly this. Two of eight gates cannot
# recreate the all-pinned no-op, and the PIN ALARM below now catches it behaviourally if it ever
# did. EXPIRY: remove the moment the operator accepts nipc (re-derived exit accounting) or retires
# it. Revert: PINNED = frozenset().
PINNED: frozenset = frozenset()
MAINT_HOUR_UTC = 21  # CME index-futures daily maintenance halt 21:00-22:00 UTC


def hlog(msg):
    try:
        with open(HLOG, "a") as f:
            f.write(f"{datetime.now(timezone.utc).strftime('%FT%TZ')} {msg}\n")
    except Exception:
        pass


def sh(cmd, timeout=60):
    env = os.environ.copy(); env["PYTHONPATH"] = "src"
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout, cwd=GB, env=env).stdout
    except Exception as e:
        return f"(error: {e})"


def read_switches():
    cur = {}
    try:
        for line in open(SW):
            s = line.strip()
            if "=" in s and not s.startswith("#"):
                k, v = s.split("=", 1)
                cur[k.strip()] = v.strip()
    except Exception:
        pass
    return cur


def apply_switches(valid):
    lines = open(SW).read().splitlines()
    out = []
    for line in lines:
        hit = False
        for g, v in valid.items():
            if line.strip().startswith(g + "="):
                out.append(f"{g}={v}"); hit = True; break
        if not hit:
            out.append(line)
    with open(SW, "w") as f:
        f.write("\n".join(out) + "\n")


def append_log(msg):
    ts = datetime.now(timezone.utc).strftime('%FT%TZ')
    try:
        with open(LOG, "a") as f:
            f.write(f"{ts} | tune | DURABLE | {msg}\n")
    except Exception:
        pass


def main():
    # skip during the maintenance halt (desk frozen; nothing to decide)
    if time.gmtime().tm_hour == MAINT_HOUR_UTC:
        hlog("skip: CME maintenance halt"); return

    desk = sh(f"{PY} scripts/desk_view.py")
    if "DAY BIAS" not in desk:
        hlog("ABORT: desk_view unreadable -> no change"); return
    recent = sh(f"{PY} scripts/recent_trades.py 6")
    logtail = sh(f"tail -6 {LOG}")
    cur = read_switches()

    # UNTRADEABLE-DAY METER — the stay-out evidence (guarded; never blocks the tick)
    try:
        import sys as _sys
        if f"{GB}/src" not in _sys.path:
            _sys.path.insert(0, f"{GB}/src")
        from gazbot7 import untradeable as _U, pnl as _pnl
        _s = _pnl.paris_day_start_utc(datetime.now(timezone.utc))
        _ds = int((datetime.fromisoformat(_s) if isinstance(_s, str) else _s).timestamp())
        _u = _U.compute(f"{GB}/data/capture.db", f"{GB}/data/gazbot7.db", _ds)
        untr_txt = f"score {_u['score']}/100 -> {_u['verdict']} | {_u['detail']}"
    except Exception as e:
        untr_txt = f"(unavailable: {e})"

    prompt = (
        "You are the GAZBOT V7 intelligent router making ONE 5-min bench/enable decision (PAPER, "
        "benching-only). Decide which of the 8 gates should be on/off on a HOLISTIC regime read "
        "(trend vs chop), not mechanical thresholds.\n\n"
        "RULES: chop (low ER, range-bound) -> bench ALL momentum (grind_long, abs_veto_long), keep "
        "reversion (capitulation_long). day-bias UP>=+40 -> bench shorts; DOWN<=-40 -> bench longs. "
        "Re-arm momentum only on a real range-break WITH ER climbing + vol expanding (not a delta-blip). "
        "abs_veto_long is veto-protected (≈0-cost armed in chop unless it's firing+stopping); grind_long "
        "is a churner (keep OFF unless ER>=0.35 strong trend). Some gates may be operator-PINNED (auto-excluded "
        "from your changes) — decide holistically regardless. "
        "★★★ ARMING IS HALF YOUR JOB — READ THIS BEFORE THE BENCH RULES BELOW. "
        "Operator, 2026-08-04: 'i dont want blanket benching all the time. it needs to be intelligent. if you "
        "can watch like i watch with the smarts you have and turn things back on when we want them we are gold.' "
        "This prompt used to carry 19 bench directives against 13 arm ones, and its ONLY arm clause began with "
        "the word 'only' — so it read as a benching machine with one grudging exception. That is why on 08-04 "
        "you correctly identified a real break at 13:35 and STILL declined, leaving the aligned trend-rider off "
        "for 17 minutes of the best move of the day. BEING FLAT THROUGH A WINDOW IS A COST, NOT SAFETY. "
        "Bench on EVIDENCE OF HARM; arm on EVIDENCE OF OPPORTUNITY. Neither is a default state — both are "
        "active decisions you must justify in your reason. "
        "ARM (without waiting to be asked, and without waiting for 'n') when ANY of these holds: "
        "(1) an ALIGNED momentum gate is off while a real break runs — ER climbing AND sustained, vol expanding, "
        "AND structure (new extreme / range break). All three together is a break; one alone is a blip. "
        "(2) the gate's own book is GREEN IN THE CURRENT SEGMENT even if its full-day aggregate is red — a "
        "chop-morning aggregate is not evidence about a trend afternoon, and treating it as such is the exact "
        "error that cost 08-04. SEGREGATE BY REGIME, ALWAYS. "
        "(3) the SHADOW board shows that gate's family green over the last hour while the live twin sits off — "
        "the shadow is the unbenched counterfactual and that is precisely what it is for. "
        "★ DO NOT require a green full-day aggregate before arming, and DO NOT make the tape prove itself twice. "
        "If you are unsure a break is real, say so in your reason and ARM THE ALIGNED gate while leaving "
        "counter-trend gates and no-veto churners off — that is the intelligent middle, and it is what 'watch "
        "like I watch' means. The asymmetry (wrongly-armed churns, wrongly-benched merely misses) still applies "
        "to CHURNERS and COUNTER-TREND gates; it is NOT a licence to sit out a confirmed aligned window. "
        "★ STANDING FROM THE 07-31 FRIDAY REPORT (operator-picked 08-01, hold unless the tape genuinely changes): "
        "(a) rgv_short should be BENCHED for the week — verdicted SHADOW (11 fires, -$142, negative at EVERY exit "
        "rung, strip-best-1 -$242). ★ IT RE-ARMS BY POLICY at every Paris-midnight reopen (every gate does — "
        "reactivate_gates.py holds nothing back), so YOU are the only thing keeping it off: when you see rgv_short=on, "
        "bench it again. That is expected housekeeping, NOT thrash. One good-looking read is not evidence to leave it "
        "armed — it needs n, not a tick. Re-look on/after 2026-08-08. "
        "(b) abs_veto_short: bench it in VIOLENT WHIPSAW (ATR>=19pt AND 30-min ER<0.25) — that segment is -$20 to "
        "-$33 per signal at every exit cell and no exit rescues it. "
        "★★ (b2) 2026-08-04 — the abs_veto_short operator-arming override is EXPIRED and abs_veto_short is BENCHED AGAIN. "
        "It was armed 13:30 on a churny-roundtrip argument (day-ER 0.06) with a written expiry on ER climbing into a "
        "real trend; that fired at 13:59 (last-hr ER 0.34-0.43, ATR 21->24, new day high, bias UP +559). The general "
        "rule applies again in full: day-bias UP>=+40 -> bench shorts. Do NOT re-arm it today. Historical note kept "
        "because the reasoning matters: judge the EXPIRY on the current SEGMENT, not the chop-diluted day aggregate — "
        "day-ER was still only 0.10 when the segment was plainly trending, and using the day figure to keep a "
        "counter-trend gate armed would have been the same aggregate error as benching grind_long on its red day book. "
        "★★ (b3) 2026-08-04 14:16 — grind_long is BENCHED ON OPERATOR INSTRUCTION. Do NOT re-arm it today, "
        "even though the trend is intact and ER is high — this is an operator decision, not a regime read. "
        "Context so you do not re-derive it: it was armed 13:52 on a fully confirmed break and in 24 minutes "
        "produced ZERO signals. Price ran to +6.06 ATR above VWAP on a one-way move, and grind is a "
        "CONTINUATION-ON-PULLBACK gate — a trend that never retraces offers it no setup (removing its ext_hi "
        "ceiling did not make it fire either, so the binding condition is the pullback geometry). grind is the "
        "gate for a trend that BREATHES, not for a one-way run. It re-arms by policy at the 22:00 UTC reopen; "
        "judge it fresh on that tape. The 13:35 lesson still stands for FUTURE breaks: do not bench an aligned "
        "trend-rider on a chop-diluted full-day aggregate — segregate by the break window. "
        "(c) abs_veto_long: do NOT bench it merely for being 'momentum in chop'. On the evidence it is an OVERNIGHT "
        "CHOP gate (13 blocked fires worth +$384; live and shadow both green in that cell). Bench it on VIOLENCE, "
        "not on chop. "
        "(d) The FADER BENCH is the one router behaviour that survived every robustness test this weekend "
        "(+$810 non-overlap, n=25, stable under every independent regime tag) — keep doing it. Conversely, do NOT "
        "widen into 'stop benching momentum in TREND_UP': that idea was re-derived and REFUTED (placebo-null under "
        "two independent regime tags), so leave TREND_UP benching exactly as it is. "
        # ★2026-08-01 (audit FIX): the shipped wording said 'leave it as the operator set it', which under
        # the general RULE 're-arm momentum on a real range-break with ER climbing' reads as permission to
        # arm nipc. It is not. nipc FAILED its acceptance replay and is PINNED OFF; asking for it on is a
        # wasted tick that now raises a critical PIN-BLOCKED alarm. Revert: restore the previous sentence.
        "★ NEW GATE — nipc_long / nipc_short (news-impulse pullback, added 08-01): both are OFF and "
        "operator-PINNED OFF. They FAILED their acceptance replay (the shipped decider reproduces the lab's "
        "entry population but only +$264/n=159 against the lab's +$2,676/n=171), so they stay off until the "
        "operator re-derives the exit accounting. NEVER put nipc_long or nipc_short in `changes` — not 'on', "
        "not 'off'. They are already off, the general momentum re-arm rule does NOT apply to them, and the "
        "pin means any request you make for them is discarded and pages the operator. Ignore them entirely. "
        "★ UNTRADEABLE-DAY RULE: if the UNTRADEABLE METER reads STAY-OUT (score>=65 — a big range but ~0 net "
        "roundtrip + the day's move given back + gates stopping across mechanisms), bench ALL gates and keep flat; "
        "do NOT hunt for a gate that works — a no-trade day is correct (chasing an untradeable chop cost -$900 on 07-31). "
        "Reversion stays through chop. DON'T THRASH — change a switch ONLY when evidence genuinely changed; "
        "most ticks are no-change.\n\n"
        f"CURRENT SWITCHES: {json.dumps(cur)}\n\n"
        f"=== UNTRADEABLE METER ===\n{untr_txt}\n\n"
        f"=== DESK VIEW ===\n{desk}\n=== RECENT TRADES ===\n{recent}\n=== RECENT ROUTER LOG ===\n{logtail}\n\n"
        "Output ONLY a JSON object, nothing else:\n"
        '{"changes": {"<gate>": "on"|"off"}, "reason": "<one tight line>", "notify": "<telegram text, or empty string if no change>"}\n'
        "changes = ONLY gates whose state should FLIP from CURRENT (empty {} if no change). Be conservative."
    )

    try:
        r = subprocess.run(["/root/.local/bin/claude", "-p", prompt, "--allowedTools", ""],
                           capture_output=True, text=True, timeout=200,
                           env={**os.environ, "HOME": "/root"})
        out = (r.stdout or "").strip()
    except Exception as e:
        hlog(f"ABORT: claude invocation failed {e} -> no change"); return

    m = re.search(r'\{.*\}', out, re.DOTALL)
    if not m:
        hlog(f"ABORT: no JSON in output -> no change | raw={out[:200]!r}"); return
    try:
        dec = json.loads(m.group(0))
    except Exception as e:
        hlog(f"ABORT: JSON parse fail {e} -> no change | raw={out[:200]!r}"); return

    changes = dec.get("changes") or {}
    reason = str(dec.get("reason", ""))[:300]
    notify = str(dec.get("notify", "")).strip()

    blocked = {g: v for g, v in changes.items()
               if g in GATES and g in PINNED and v in ("on", "off") and cur.get(g) != v}
    valid = {g: v for g, v in changes.items()
             if g in GATES and g not in PINNED and v in ("on", "off") and cur.get(g) != v}

    # ★ PIN ALARM (2026-08-01). A PINNED set covering every gate makes `valid` permanently empty, so
    # the router silently stops managing the desk while still logging the healthy-looking "no change"
    # every tick. That went unnoticed for 411 ticks / 36 hours. A dead router and an idle one must
    # never log the same line again.
    # ★2026-08-01 (audit FIX): the shipped test was `PINNED >= set(GATES)` ALONE — roster-shape
    # dependent, and it would NOT have caught the incident it was written for: that pin was the SIX
    # gates of the old roster and GATES now holds EIGHT, so frozenset(6) >= set(8) is False → silent,
    # while the six real gates stay frozen. The load-bearing invariant is behavioural: the router
    # NAMED changes and every one was pin-suppressed. Test that too (needs blocked/valid, so those
    # move above). Revert: drop the `or (blocked and not valid)` clause and move this block back up.
    if PINNED >= set(GATES) or (blocked and not valid):
        msg = (f"ROUTER PIN-BLOCKED: the router asked for {blocked or 'changes'} but every gate it "
               f"named is PINNED, so nothing can apply. If this repeats, the desk is UNMANAGED. "
               f"Fix: shrink PINNED in scripts/router_tick_durable.py. "
               f"(pinned={sorted(PINNED)}, gates={len(GATES)})")
        hlog(f"ALARM {msg}")
        append_log(f"ALARM | {msg}")
        try:
            subprocess.run([PY, "-c", "import sys; from gazbot7.notify import notify; notify(sys.argv[1], critical=True)", msg],
                           cwd=GB, env={**os.environ, "PYTHONPATH": "src"}, timeout=30)
        except Exception:
            pass

    if not valid:
        # Distinguish "nothing to do" from "wanted to act but every gate it named was pinned".
        sup = f" | SUPPRESSED-BY-PIN {blocked}" if blocked else ""
        append_log(f"changed: none{sup} | {reason}")
        hlog(f"no change{sup} | {reason}")
        return

    apply_switches(valid)
    append_log(f"changed: {valid} | {reason}")
    hlog(f"APPLIED {valid} | {reason}")
    if notify:
        try:
            subprocess.run([PY, "-c", "import sys; from gazbot7.notify import notify; notify(sys.argv[1], critical=False)", notify],
                           cwd=GB, env={**os.environ, "PYTHONPATH": "src"}, timeout=30)
        except Exception:
            pass


if __name__ == "__main__":
    main()
