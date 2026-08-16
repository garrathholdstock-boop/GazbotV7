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
# ★2026-08-15 nipc REMOVED — retired from the live roster (slot_strategy has no nipc SlotSpec), so
# there is no slot to arm and nothing to manage. Listing a gate the desk cannot trade made the
# router look like it managed 8 gates when it could only ever act on 6.
GATES = ["grind_long", "capitulation_long", "abs_veto_long", "exhaustion_short",
         "abs_veto_short", "rgv_short"]
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


def switch_notes(limit: int = 45) -> str:
    """The ★★ carve-out comments at the TOP of gate_switches.env.

    ★2026-08-05: these were INVISIBLE to the router. `cur` is built with
    `if "=" in s and not s.startswith("#")` and the prompt received only json.dumps(cur), so every
    written carve-out — the session's, the open-hour watcher's, the operator's — was stripped before
    the model ever saw it. The watcher was writing "this was a full break-trio pass, let it run" into
    a file the router reads values from and reasons about without. A one-way channel that looks
    two-way is worse than no channel, because both sides believe they have coordinated.
    Only the leading block is passed: that is where a fresh carve-out is prepended, and it bounds
    the prompt against the file's long historical commentary."""
    try:
        out = []
        for line in open(SW):
            if not line.startswith("#"):
                if out:
                    break          # leading comment block ended — stop at the first switch line
                continue
            out.append(line.rstrip())
            if len(out) >= limit:
                break
        return "\n".join(out)
    except Exception:
        return ""


def apply_switches(valid):
    # ★2026-08-05 SHARED LOCK. The open-hour watcher may now also write this file (arm-only) and it
    # takes data/gate_switches.lock via O_EXCL. A lock only one writer respects is not a lock — this
    # is a read-modify-write, so an interleaved write from the watcher would be silently lost or the
    # file torn. Fail CLOSED: if the lock is held, skip this tick's write entirely rather than race;
    # the next tick is 5 minutes away and benching-later is the cheap error.
    import time as _t
    _lock = f"{GB}/data/gate_switches.lock"
    _fd = None
    for _ in range(30):                       # ~3s — the watcher holds it for milliseconds
        try:
            _fd = os.open(_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            _t.sleep(0.1)
    if _fd is None:
        hlog("apply_switches SKIPPED — gate_switches.lock held (watcher writing); no change this tick")
        return
    try:
        _apply_locked(valid)
    finally:
        os.close(_fd)
        try:
            os.unlink(_lock)
        except Exception:
            pass


def _apply_locked(valid):
    lines = open(SW).read().splitlines()
    out = []
    for line in lines:
        hit = False
        for g, v in valid.items():
            if line.strip().startswith(g + "="):
                out.append(f"{g}={v}"); hit = True; break
        if not hit:
            out.append(line)
    tmp = SW + ".tmp"                      # atomic: a torn switches file beats a lost write
    with open(tmp, "w") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, SW)


def append_log(msg):
    ts = datetime.now(timezone.utc).strftime('%FT%TZ')
    try:
        with open(LOG, "a") as f:
            f.write(f"{ts} | tune | DURABLE | {msg}\n")
    except Exception:
        pass


def seg_confirm(prev: dict | None, raw: str, fresh: bool, hold: int) -> dict:
    """The direction-confirmation state machine, as a PURE function so it can be tested.

    ★2026-08-16 extracted from the tick body when SEG_HOLD became tunable. It was inline and
    therefore unpinned, which on this desk is how a hysteresis rule quietly becomes something else —
    the 08-11 flicker bug lived here and was found in production, not in a test.

    `prev` is the persisted state (dir/conf/dissent/agree) or None. `fresh` says the previous tick is
    recent enough to chain from. Returns the new state plus `held`, true when a dissenting tick was
    absorbed rather than acted on.

    SYMMETRY IS THE POINT: entering a direction costs `hold` consecutive agreeing ticks, and leaving
    a confirmed one costs `hold` consecutive dissenting ticks. An asymmetric version benched
    abs_veto_short at 01:00 and re-armed it at 01:30 on a single marginal read.
    """
    p = prev or {}
    prev_dir = p.get("dir")
    prev_conf = bool(p.get("conf"))
    prev_dis = int(p.get("dissent", 0))
    prev_agree = int(p.get("agree", 0)) if fresh else 0

    if (prev_conf and prev_dir not in (None, "FLAT") and raw != prev_dir
            and fresh and prev_dis < hold - 1):
        return {"dir": prev_dir, "conf": True, "dissent": prev_dis + 1,
                "agree": prev_agree, "held": True}
    agree = (prev_agree + 1) if (fresh and prev_dir == raw) else 1
    return {"dir": raw, "conf": raw != "FLAT" and agree >= hold,
            "dissent": 0, "agree": agree, "held": False}


def main():
    # skip during the maintenance halt (desk frozen; nothing to decide)
    # ★2026-08-09 MONDAY #2, second half — "move the 21:00-22:00Z maintenance gap so the hour before
    # the reopen is supervised." The whole hour used to be skipped, which meant the desk was
    # UNOBSERVED going into the 22:00 reopen: on 08-08 all five services died at 01:54 and the only
    # thing that noticed was the event watcher. A skipped tick logs nothing at all. We keep the
    # no-decisions intent for the body of the halt and restore supervision for the last 15 minutes,
    # so at least two ticks read the desk before reactivate_gates fires at 22:00.
    _now = time.gmtime()
    if _now.tm_hour == MAINT_HOUR_UTC and _now.tm_min < 45:
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
        # ★2026-08-09 NO-READ GUARD. untradeable.py seeds score=50 and defaults chop/give to 50
        # when roundtrip/giveback cannot be computed (it refuses roundtrip below a 30pt range).
        # Under the old >=65 trigger that default was inert; under MONDAY #3's >=45 it would read
        # as a STAY-OUT, so an absent measurement would bench the whole desk — hardest of all on a
        # DEAD FEED or a no-range tape, inverting the meter's own "big range, ~0 net" semantics.
        # Label it explicitly rather than let 50 masquerade as a reading.
        _noread = _u.get("roundtrip") is None or _u.get("giveback") is None
        untr_txt = (f"score {_u['score']}/100 -> {_u['verdict']} | {_u['detail']}"
                    + ("  ⛔ NO READ — roundtrip/giveback unavailable (range under the 30pt floor, "
                       "or no tape). The 50 is a DEFAULT, not a measurement: it is NOT a stay-out."
                       if _noread else ""))
        # ★2026-08-09 C-2 — TWO-CONSECUTIVE-TICK CONFIRMATION. A stay-out benches the whole desk,
        # and at the 08-08 cutoff of 45 the score sat mid-distribution and OSCILLATED across it
        # (08-07: 46 -> 42 -> 44 -> 15, crossing twice), so a single-tick trigger would bench and
        # unbench eight gates on noise — the exact churn the prompt's own closing rule forbids.
        # The router has no memory between ticks, so persist just the last score. FAIL-SAFE: any
        # error, or a stale/no-read prior, leaves _prev_txt saying the confirmation is UNMET, and
        # the rule below reads unmet as "not a stay-out" (benching on absence is the wrong error).
        try:
            import json as _js
            _mp = f"{GB}/data/router_meter_state.json"
            _prev = {}
            try:
                with open(_mp) as _f:
                    _prev = _js.load(_f)
            except Exception:
                _prev = {}
            _age_s = int(datetime.now(timezone.utc).timestamp()) - int(_prev.get("ts", 0))
            _pv = _prev.get("score")
            _pnr = bool(_prev.get("noread", True))
            if _pv is None or _age_s > 900 or _pnr:
                _prev_txt = ("PREVIOUS TICK: none usable (missing, older than 15 min, or itself a "
                             "NO READ) -> the two-consecutive-tick confirmation is UNMET.")
            else:
                _prev_txt = (f"PREVIOUS TICK: score {_pv}/100 ({_age_s}s ago) -> confirmation is "
                             f"{'MET' if (_pv >= 55 and not _noread and _u['score'] >= 55) else 'UNMET'}.")
            untr_txt += "\n  " + _prev_txt
            try:
                _tmp = _mp + ".tmp"
                with open(_tmp, "w") as _f:
                    _js.dump({"score": _u["score"], "noread": _noread,
                              "ts": int(datetime.now(timezone.utc).timestamp())}, _f)
                os.replace(_tmp, _mp)
            except Exception:
                pass
        except Exception as _e:
            untr_txt += f"\n  PREVIOUS TICK: (state unavailable: {_e}) -> confirmation UNMET."
    except Exception as e:
        untr_txt = f"(unavailable: {e})"

    # ★★2026-08-10 SEGMENT BIAS — judge the SEGMENT, not the day.
    # The standing direction rule keyed off DAY bias, an average over the whole session and therefore
    # the last thing to notice a reversal. On a day that opens -150 and turns +200 the day aggregate
    # still reads DOWN, so longs stay benched THROUGH the trend. Same aggregate-vs-segment error the
    # ledger already records twice: the 08-04 carve-out expiry judged on a chop-diluted day, and the
    # 08-06 meter reading 87/100 STAY-OUT while a +297pt run was underway.
    #
    # ⚠ THE TRAP IN THE FIX: a 60-minute window crosses +/-40 far more often than a day average, so
    # segment-judging ALONE would turn one switch change a day into a dozen. The direction trigger
    # already flickered on 08-10 — net -29 -> -51 -> -35 in fifty minutes, three changes, zero fills.
    # So the segment reading carries a TWO-CONSECUTIVE-TICK confirmation, exactly as the untradeable
    # meter got, with the previous reading persisted. Shortening the window without the dwell would
    # make the churn worse, not better.
    # ★★★2026-08-16 SATURDAY #1 — ROUTER TIMING IS TUNED HERE, IN THE DURABLE TICK.
    # The report filed this as "one constant block in the router service; restart required" and
    # pointed at direction_router.py's WINDOW/STEP/HOLD. Those are DEAD — that timer is disabled and
    # this file does not import them. The LIVE parameters are these, and because each tick is a fresh
    # process an edit takes effect on the NEXT TICK with NO RESTART.
    #   window  60 -> 45 min   the segment the direction read is taken over
    #   step        = 5 min    already the timer cadence (*:0/5); nothing to change
    #   hold     2 -> 3 ticks  consecutive agreeing ticks to flip the effective direction
    # ⚠ THE TRADE-OFF, and it is not free: hold=3 at a 5-min cadence means 15 MINUTES to confirm a
    # direction change, both ways. Leaving a direction slower is GOOD (it re-arms, and wrongly-armed
    # is the expensive error). Entering slower is mildly BAD (it benches, which is cheap and safe).
    # Symmetric 3 is what the 40-day sweep asked for; if the bench side proves too slow, the knob to
    # split is SEG_HOLD_ENTER/SEG_HOLD_LEAVE, not a return to 2.
    # REVERT: SEG_WINDOW_MIN = 60, SEG_HOLD = 2. No restart needed either way.
    SEG_WINDOW_MIN = 45          # was 60
    SEG_HOLD = 3                 # was 2 (symmetric since 2026-08-11)
    SEG_NET_MIN = 40.0           # ⚠ NOT direction_router.NET_MIN (30.0) — that module is dead
    SEG_ER_FLOOR = 0.20
    SEG_MIN_BARS = 15            # was 20 of 60; same density over a 45-min window
    seg_txt = "(unavailable)"
    try:
        import json as _sj
        import duckdb as _sd
        _sc = _sd.connect()
        _sc.execute(f"ATTACH '{GB}/data/capture.db' AS sc (READ_ONLY)")
        _now = int(datetime.now(timezone.utc).timestamp())
        _rows = _sc.execute(
            "SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl FROM sc.bars "
            f"WHERE symbol='MNQ' AND bar_ts>={_now - SEG_WINDOW_MIN*60} GROUP BY 1 ORDER BY 1").fetchall()
        _sc.close()
        if len(_rows) >= SEG_MIN_BARS:
            _o, _l = _rows[0][1], _rows[-1][1]
            _net = _l - _o
            _path = sum(abs(_rows[i][1] - _rows[i - 1][1]) for i in range(1, len(_rows))) or 1.0
            _er = abs(_net) / _path
            # ★ A DIRECTION NEEDS EFFICIENCY, NOT JUST DISTANCE. The old day rule keyed on net
            # points alone; on a 60-minute window that is far too easy to satisfy by drifting.
            # The very first live reading of this block was UP net +53.75pt at ER 0.085 — a
            # chop-drift that would have benched shorts on nothing. Calibrated against today's own
            # tape: the real 12:00-12:41 break ran ER 0.311, the morning chop 0.031, the 179pt
            # retrace 0.115. A 0.20 floor calls the break and stays FLAT through both the chop and
            # the bounce, which is exactly the discrimination the rule is for.
            if abs(_net) > SEG_NET_MIN and _er >= SEG_ER_FLOOR:
                _raw = "DOWN" if _net < 0 else "UP"
            else:
                _raw = "FLAT"
            # ★2026-08-11 FAST WINDOW — CONTEXT ONLY, NOT A TRIGGER. The 60-min segment cannot
            # see a V-reversal: if the hour opened above a dump, a sharp recovery averages to a
            # net near zero and the rule reads FLAT or even DOWN while price runs. Live case this
            # session — 15min UP +113pt ER 0.704 while the 60-min window read DOWN -70pt ER 0.103,
            # and the operator saw the run before the instrument did. Showing the 20-min leg beside
            # the 60-min one lets the router SEE the divergence and say so, instead of being blind
            # to it. It is deliberately NOT a trigger: a fast window flips on noise, which is what
            # the 60-min window and the two-tick confirmation exist to prevent.
            try:
                _r2 = [r for r in _rows if r[0] >= _now - 20 * 60]
                if len(_r2) >= 8:
                    _n2 = _r2[-1][1] - _r2[0][1]
                    _p2 = sum(abs(_r2[i][1] - _r2[i - 1][1]) for i in range(1, len(_r2))) or 1.0
                    _e2 = abs(_n2) / _p2
                    _d2 = "UP" if _n2 > 0 else "DOWN"
                    fast_txt = (f"\n  FAST 20-min leg (CONTEXT ONLY, never a trigger): {_d2} "
                                f"net {_n2:+.0f}pt  ER {_e2:.3f}")
                    if abs(_n2) > 40 and _e2 >= 0.20:
                        fast_txt += ("  ⚠ THE 20-MIN LEG IS DIRECTIONAL. If it DISAGREES with the "
                                     "60-min read above, a reversal is under way that the 60-min "
                                     "window is averaging away. Do NOT flip the direction rule on "
                                     "this — but do NOT claim the tape is flat either, and say in "
                                     "your reason which window you are acting on and why. Ask "
                                     "whether STRUCTURE has broken (new high/low of the last 2h) "
                                     "before treating it as a trend rather than a retrace.")
                else:
                    fast_txt = ""
            except Exception:
                fast_txt = ""
            _sp = f"{GB}/data/router_segment_state.json"
            _prev_dir, _prev_conf, _prev_dis, _age = None, False, 0, 10 ** 9
            _prev_agree_raw = 0
            try:
                with open(_sp) as _f:
                    _p = _sj.load(_f)
                _prev_dir = _p.get("dir")
                _prev_conf = bool(_p.get("conf"))
                _prev_dis = int(_p.get("dissent", 0))
                _prev_agree_raw = int(_p.get("agree", 0))
                _age = _now - int(_p.get("ts", 0))
            except Exception:
                pass
            # ★2026-08-11 SYMMETRIC HYSTERESIS. This rule needed two consecutive ticks to ENTER a
            # direction but only ONE to leave it, so five confirmed UP reads were undone by a single
            # marginal tick and `abs_veto_short` was benched at 01:00 and re-armed at 01:30 — a
            # 30-minute round trip caused by the instrument, not by judgement. Entry confirmation was
            # added precisely to stop boundary flicker; the flicker simply moved to the other edge.
            # A first dissenting tick against a CONFIRMED direction now HOLDS that direction and is
            # recorded as dissent 1; a second consecutive dissent releases it. Leaving costs two
            # ticks exactly as entering does.
            # ★2026-08-16 the state machine is seg_confirm() — a pure, TESTED function.
            _st = seg_confirm({"dir": _prev_dir, "conf": _prev_conf, "dissent": _prev_dis,
                               "agree": _prev_agree_raw}, _raw, _age <= 900, SEG_HOLD)
            _dir, _conf, _dis = _st["dir"], _st["conf"], _st["dissent"]
            _agree, _held = _st["agree"], _st["held"]
            # ER is printed to 3dp because the test is `_er >= 0.20` on the RAW value: at 2dp a raw
            # 0.1996 printed as "0.20" and read FLAT, so the log contradicted its own stated floor
            # and cost real audit time. Never round a number across the threshold it is judged on.
            _hold_txt = (f"  ⚠ HELD: raw read is {_raw} but the previous tick's {_prev_dir} was "
                        f"CONFIRMED, so this is dissent 1 of 2 — the direction does NOT flip until a "
                        f"second consecutive dissent. Treat {_prev_dir} as still in force." if _held else "")
            seg_txt = (f"last {SEG_WINDOW_MIN}min: {_dir}  net {_net:+.0f}pt  ER {_er:.3f} "
                       f"(needs |net|>{SEG_NET_MIN:.0f} AND ER>={SEG_ER_FLOOR:.2f} to be directional; "
                       f"agreeing ticks {_agree}/{SEG_HOLD})  "
                       f"({len(_rows)} bars, path {_path:.0f}pt) | previous tick: "
                       f"{_prev_dir or 'none'} -> confirmation {'MET' if _conf else 'UNMET'}"
                       f"{_hold_txt}{fast_txt}")
            try:
                _t = _sp + ".tmp"
                with open(_t, "w") as _f:
                    _sj.dump({"dir": _dir, "net": _net, "er": round(_er, 3), "ts": _now,
                              "conf": bool(_conf), "dissent": int(_dis), "raw": _raw,
                              "agree": int(_agree)}, _f)
                os.replace(_t, _sp)
            except Exception:
                pass
        else:
            seg_txt = (f"(only {len(_rows)} bars in the last {SEG_WINDOW_MIN}min, "
                       f"need {SEG_MIN_BARS} — no segment read)")
    except Exception as e:
        seg_txt = f"(unavailable: {e})"

    # ★2026-08-11 SESSION WINDOW — the router had no concept of session time at all, so it armed
    # gates inside the Asia block that could not fire, and called the tape "Asia chop" for two hours
    # after Asia ended while sitting in LONDON, the desk's only positive block. Computed from the
    # SAME helper the desk gates entries with, so the router cannot disagree with the order path.
    try:
        from gazbot7 import session as _sess2
        _n2 = datetime.now(timezone.utc)
        _asia = bool(_sess2.in_asia_block(_n2))
        _h2 = _n2.hour + _n2.minute / 60.0
        _blk = ("ASIA" if _asia else "LONDON" if 7 <= _h2 < 13 else
                "US-PRE/OPEN" if 13 <= _h2 < 15 else "US-LATE" if 15 <= _h2 < 21 else "CLOSED/REOPEN")
        sess_txt = (f"{_n2:%H:%M}Z — {_blk}"
                    + ("  ⛔ NEW ENTRIES ARE REFUSED (no_open_asia). An ARM now is inert until 07:00Z "
                       "and then goes live unreviewed — only make one you would still make on the "
                       "07:00 tape. BENCHES are fully effective." if _asia else "")
                    + ("  ★ 13:30-14:45Z is where the desk's expectancy lives (+$8.93/tr, n=562)."
                       if 13 <= _h2 < 15 else "")
                    + ("  ★ LONDON is the desk's ONLY positive block (+$0.70/tr, n=1516) — do not "
                       "under-arm it, and do not call this tape 'Asia'." if _blk == "LONDON" else ""))
    except Exception as e:
        sess_txt = f"(session window unavailable: {e}) — derive it from the UTC clock yourself"

    # RUN STATE — CONTEXT ONLY. ⛔2026-08-08: the 08-06 framing below is WITHDRAWN as a routing lever.
    # The claim was:
    #     in-run aligned : TAKEN n=34 50% win +$10.34/tr | chop/no-run TAKEN n=51 16% win -$28.43/tr
    # Re-derived from scratch on the SAME 89 Mon->Thu trades, the headline cell INVERTS:
    #     in-run aligned : TAKEN n=46 41% win -$1.83/tr
    # and the 34/4/51 split is irreproducible under any run-span definition (merge gaps 0/120/300/
    # 600/900s all give 46/10/33). What survives is the MISSED side and an EXIT finding — re-pricing
    # exits on the entries already taken turns the week from -$772 to +$1,493 — NOT a routing lever.
    # Still computed and still injected, as CONTEXT. Guarded like the meter — never blocks the tick.
    try:
        import sys as _sys2
        if f"{GB}/src" not in _sys2.path:
            _sys2.path.insert(0, f"{GB}/src")
        import duckdb as _dd
        from gazbot7.runstate import _minute_bars as _mb
        from gazbot7.runstate import compute as _rc
        from gazbot7.runstate import render as _rr
        _c = _dd.connect()
        _c.execute(f"ATTACH '{GB}/data/capture.db' AS c (READ_ONLY)")
        _c.execute("use c")
        _since = int(datetime.now(timezone.utc).timestamp()) - 240 * 60
        run_txt = _rr(_rc(_mb(_c, "MNQ", _since)))
        _c.close()
    except Exception as e:
        run_txt = f"RUN STATE: (unavailable: {e}) — fall back to your own read of the tape"

    prompt = (
        "You are the GAZBOT V7 intelligent router making ONE 5-min bench/enable decision (PAPER, "
        "benching-only). Decide which of the 8 gates should be on/off on a HOLISTIC regime read "
        "(trend vs chop), not mechanical thresholds.\n\n"
        "RULES: chop (low ER, range-bound) -> bench ALL momentum (grind_long, abs_veto_long), keep "
        "reversion (capitulation_long). "
        "★★ THE DIRECTION RULE NOW JUDGES THE SEGMENT, NOT THE DAY (2026-08-10). Use the SEGMENT BIAS "
        "block (last 60 minutes): UP -> bench shorts; DOWN -> bench longs; FLAT -> the direction rule "
        "says nothing and you decide on the rest of the read. "
        "⚠ IT MUST BE CONFIRMED: the block prints 'confirmation MET/UNMET' and UNMET means DO NOT act "
        "on direction this tick. A 60-minute window crosses +/-40 far more readily than a day average, "
        "and on 08-10 the old day trigger already flickered -29 -> -51 -> -35 in fifty minutes for "
        "three switch changes and zero fills. One reading is a blip; two in a row is a segment. "
        "★ WHY THE CHANGE: day bias is an average over the whole session and the LAST thing to notice "
        "a reversal. A day that opens -150 and turns +200 still reads DOWN, so longs stay benched "
        "through the trend — the same aggregate-over-segment error that had the meter reading 87/100 "
        "STAY-OUT on 08-06 while a +297pt run was underway. DAY BIAS is still shown and is still "
        "useful CONTEXT for where you are in the session, but it is no longer the trigger. "
        "Re-arm momentum only on a real range-break WITH ER climbing + vol expanding (not a delta-blip). "
        "⛔ MONDAY #4 (2026-08-08), WRITTEN RULE: EXPANDING ATR ALONE IS NOT A RE-ARM TRIGGER. If ER is "
        "under 0.15 and there is no range break, rising ATR is chop getting wider, not a trend starting "
        "— it is violence without direction and it is the most expensive tape on the desk. All three "
        "legs (structure break + ER climbing + vol expanding) or you stay benched. This rule is "
        "fail-safe: it can only ever REDUCE arming. "
        "abs_veto_long is veto-protected (≈0-cost armed in chop unless it's firing+stopping); grind_long "
        "⛔ CORRECTED 2026-08-09 — grind_long: the old text here said 'a churner, keep OFF unless ER>=0.35 strong "
        "trend'. BOTH HALVES WERE STALE. There is NO ER floor in the code (deciders.ER_FLOOR is {}; every ER floor "
        "was deleted 08-01 and the 08-08 report refuted them), and 'churner' was measured when grind's ATR floor "
        "was 10 — SATURDAY #2 raised it to 22 on 08-08, cutting its fire count ~8x (377 -> 52 over the same 4 days). "
        "★ ITS REAL CONSTRAINT, WHICH THIS PROMPT NEVER USED TO MENTION, IS ATR14 >= 22 — enforced in code "
        "(deciders.ATR_FLOOR['grind_long']=22.0, wired at tournament.py:156), so BELOW ATR 22 THE GATE CANNOT FIRE "
        "AT ALL AND ARMING IT IS FREE. Judge it on ATR and structure, NOT on ER. "
        "⚠ Do not intersect ATR>=22 with an ER>=0.35 bar of your own: the two are near-orthogonal (each ~15% of "
        "minutes, BOTH only ~3%), so demanding both cuts grind's available legs from ~7.3/day to ~1.6/day and its "
        "SATURDAY #2 review — which needs 20 admitted legs before it can be graded AT ALL — slips from ~4 trading "
        "days to over 12. The revert is the desk's only live behaviour change this weekend and it CANNOT BE "
        "EVALUATED IF IT IS NEVER ARMED. Arm it when ATR>=22 and structure supports it. "
        "Some gates may be operator-PINNED (auto-excluded "
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
        "(b) ⛔ DELETED 2026-08-09 — SATURDAY #1 (absveto-short-arm-by-default-er035-0808), operator-picked LIVE. "
        "The old rule was 'abs_veto_short: bench it in VIOLENT WHIPSAW (ATR>=19pt AND 30-min ER<0.25)'. It is GONE, "
        "along with 'bench it on a stop-out pair'. DO NOT RE-CREATE EITHER BY HAND. "
        "★★ abs_veto_short IS NOW ARMED BY DEFAULT. Its signal is the strongest thing on the desk: +$2,290.50 over "
        "159 fires / 17 days, 4-of-4 weeks green, POSITIVE IN ALL FIVE REGIMES INCLUDING CHOP, and 53 of the 54 "
        "filters tested LOSE to simply letting it fire — (b) was one of those filters. Over the 96.7% of last week "
        "it sat benched, its identically-configured shadow twin made +$1,064.50; the router armed it for the 9% in "
        "which it lost -$559.00. The desk's arming of this gate was backwards on BOTH sides: benched through the "
        "good tape, armed into the bad. It is also EXEMPT FROM THE CHOP BENCH (MONDAY #1 carve-out). "
        "★ You retain bench authority on exactly two things: EXECUTION PATHOLOGY (naked stop, absurd entry_atr, "
        "MAX_HOLD stacking), and the standing DIRECTION rule (CONFIRMED segment bias UP -> bench shorts). Nothing else. "
        "A losing run is NOT a reason: the review below is what judges it, not your read of a bad hour. "
        "★ REVIEW: after 15 fires armed-by-default, re-bench if the armed book is negative over those 15. Count them. "
        "⚠ The ER30>=0.35 arming floor once proposed alongside this is REFUTED — no ER floor on this gate, ever. "
        "⚠ NOT YET SHIPPED, so do not assume it is filtering: the BUILDING x 13:30-20:00Z per-entry veto that "
        "SATURDAY #1 also calls for is NOT in the live code (no BUILDING regime exists in src/). The gate is "
        "currently armed by default with NO new veto in front of it. "
        "(b2) HISTORICAL, 2026-08-04, NO LONGER BINDING — kept only for the transferable lesson: judge a carve-out's "
        "EXPIRY on the current SEGMENT, not the chop-diluted day aggregate. day-ER was still only 0.10 when the segment "
        "was plainly trending, and using the day figure to keep a counter-trend gate armed would have been the same "
        "aggregate error as benching grind_long on its red day book. The standing direction rule stands on its own "
        "merits: a CONFIRMED segment bias UP -> bench shorts. "
        "(b3) HISTORICAL, 2026-08-04, NO LONGER BINDING — that day's 'do not re-arm grind_long' was an operator "
        "decision scoped to 08-04 and it expired at that day's 22:00 reopen. JUDGE grind_long FRESH ON TODAY'S TAPE. "
        "Kept for the MECHANISM, which is durable and worth knowing BEFORE you arm it: on 08-04 it was armed on a fully "
        "confirmed break and produced ZERO signals in 24 minutes, because price ran to +6.06 ATR above VWAP on a "
        "one-way move and grind is a CONTINUATION-ON-PULLBACK gate — a trend that never retraces offers it no setup "
        "(removing its ext_hi ceiling did not make it fire either, so the binding condition is pullback geometry). "
        "grind is the gate for a trend that BREATHES, not for a one-way run: arming it into a one-way run is usually "
        "~0-cost and ~0-benefit rather than harmful, and it is the RIGHT gate for a trend that pulls back. "
        "★★★ (d3) IF core_health SAYS halted=true, SAY SO IN YOUR REASON AND DO NOT CHURN SWITCHES. "
        "A halted tournament takes NO new entries, so every arm/bench you write is FICTION — it changes "
        "nothing at the venue while filling router_trial_log.txt with decisions that never executed, "
        "which corrupts the bad-call ledger you are graded from (a gate 'armed' during a halt that never "
        "fired is not a 0-cost arming, it is a non-event). Report the regime read, state 'HALTED — no "
        "effect', and change a switch ONLY if it should also hold once the halt clears. "
        "★ WHY IT HALTS, so you do not misdiagnose it: THE IBKR ACCOUNT IS SHARED. The DAY RIDER trades "
        "MNQ on clientId 4; the tournament is clientId 0 and receives NONE of its executions, so "
        "reconcile() compares its own slot total against the WHOLE account net, sees the day-rider's "
        "lots as an unattributable leak, and halts. It clears only on 'match', so while the day-rider "
        "holds (to 20:40Z) IT CANNOT SELF-CLEAR. This is NOT a fault, NOT a loss-limit (max_daily_loss_usd "
        "and loss_streak_halt are both 0, so a loss halt is impossible), and NOT something to 'fix' by "
        "flattening — that position belongs to another desk and flattening it is the 08-06 incident. "
        "Check data/day_rider_state.json: entered/direction/qty explains the venue net. "
        "★★★ (d2) 2026-08-07 13:38Z OPERATOR NARROWING — HOLD capitulation_long ONLY UNTIL 14:20Z. "
        "The operator said 'narrow it' during the violent 13:30 open (206pt of PATH for 30pt of NET since "
        "13:25, efficiency 0.146, ATR14 doubled to 39pt, three short entries stopped in 90 seconds for -$280 "
        "of which ~$100 was pure slippage). You re-armed abs_veto_long at 13:50 citing 'ATR 39.1 -> 27pt, the "
        "spike is over' — THAT NUMBER WAS WRONG: measured ATR14 was 42.1, i.e. vol had RISEN. It has been "
        "re-benched. Do NOT re-arm anything before 14:20Z except on a REAL TRIO: structure (new extreme) AND "
        "ER climbing AND vol EXPANDING MEASURED AGAINST THE SESSION BASELINE, not against the open spike — "
        "comparing ATR14 to a 1-hour window that CONTAINS the spike makes a rising ATR look like decay, which "
        "is exactly the error that produced the bad re-arm. Quote the session-baseline ratio in your reason. "
        "⚠ This is a RISK-CONTROL hold in a NAMED BAD REGIME. It is NOT blanket caution and it does NOT "
        "contradict (e): re-arm aggressively the moment a genuine trio appears, and after 14:20Z judge fresh. "
        "★★★ (e) 2026-08-07 OPERATOR DIRECTIVE, THIS SESSION ONLY — 'im sticking with you and the router today. you do "
        "everything as you see. just lean optimistic rather than super cautious.' You have FULL arming and benching "
        "authority for 2026-08-07 and the operator has explicitly asked you to WEIGHT TOWARD PARTICIPATION. "
        "CONCRETELY: when the arming case and the benching case are roughly balanced, ARM. Do not demand a third "
        "confirmation. Do not sit one more tick 'to be sure' on an ALIGNED gate in a confirmed window — that "
        "hesitation is the documented 08-04 and 08-06 error and it has cost this desk more than churn has. "
        "★ THE EVIDENCE, so you APPLY this rather than merely obey it: on 2026-08-04 abs_veto_long was armed once at "
        "04:20Z and LEFT ALONE for 18 hours. It lost 6 trades in the ER-0.06 morning chop (-$173.50) and then won 10 "
        "STRAIGHT in the ER-0.29 / ATR-doubled afternoon (+$504.00), across FIVE separate entries spanning 13:32-15:40. "
        "Day +$330.50. ARMING IS A PERMISSION WINDOW, NOT A RUN-TIMING PROBLEM — you are not trying to catch one run, "
        "you are staying armed through a PERIOD of movement and letting the gate take several bites. The morning losses "
        "were THE PRICE OF THE OPTION, not a failure. "
        "⚠ THEREFORE a losing streak is NOT by itself a bench trigger. Ask FIRST whether the REGIME explains the "
        "losses — a fader losing small in ER-0.06 chop is behaving exactly as designed. On 08-04 a mechanical "
        "'wall of STOP -> bench' would have fired at 11:45 and cost the entire +$504. Bench when the REGIME turns "
        "against the mechanism, or on execution pathology — not on a raw stop count. "
        "⚠ EXPIRES AT THE 2026-08-07 22:00 UTC REOPEN; it does NOT carry into 08-08. It does NOT override: the -$400 "
        "nipc kill criterion, the nipc HOLD, NEVER-HOLD-OVERNIGHT, the Asia block, or your duty to bench on execution "
        "pathology. 'Lean optimistic' is about REGIME judgement only — it is not a licence to arm counter-trend gates, "
        "nor to ignore a written expiry you set yourself. "
        "(c) abs_veto_long: do NOT bench it merely for being 'momentum in chop'. On the evidence it is an OVERNIGHT "
        "CHOP gate (13 blocked fires worth +$384; live and shadow both green in that cell). Bench it on VIOLENCE, "
        "not on chop. "
        "★★ (c2) 2026-08-07 OPERATOR CARVE-OUT — exhaustion_short: STOP BENCHING IT ON THE DIRECTION RULE. "
        "The general rule 'confirmed segment bias UP -> bench shorts' exists to stop MOMENTUM shorts fighting a rising tape. "
        "exhaustion_short is a FADER: shorting an exhausted up-move IS ITS ENTIRE JOB, so benching it because the "
        "day is up removes it exactly when its setup forms. Both of its logged bench reasons were that rule. "
        "⛔ CORRECTED 2026-08-09 — THE 'IT CANNOT CHURN' ARGUMENT WAS AN INSTRUMENT ARTEFACT, NOT A MEASUREMENT. "
        "This rule used to say 'it produced ZERO fires in signal_journal across 08-04..08-07 while grind_long "
        "produced 377, so it cannot churn.' That zero was unobtainable: signal_journal has only ever held FIVE "
        "gates (abs_veto_long/short, capitulation_long, grind_long, rgv_short) because cl_sims.py:273 routes every "
        "other spec.kind to e=None, and exhaustion_short is a footprint/L2 kind that falls through. IT HAS NEVER "
        "BEEN ABLE TO WRITE A ROW. It does fire: 21 live fills since the 07-29 cutover, net +$50.50. So its "
        "churn-cost is simply UNMEASURED — there is no signal-level record of this gate anywhere, journalled or "
        "bar-computable, so no existing harness can test it. Keep it armed on the MECHANISM argument above (a "
        "fader benched on day-bias sign is removed exactly when its setup forms), which stands on its own — but do "
        "NOT cite rarity as evidence, and if it starts firing repeatedly, believe the tape over this rule. "
        "The router has armed it 0 times against 6 benches — it only ever reaches 'on' via the 22:00 reactivation. "
        "So: LEAVE IT ARMED BY DEFAULT and let its rarity be the filter. Do NOT bench it on day-bias sign. "
        "⚠ (c2) DOES NOT OVERRIDE (d) BELOW — the validated FADER BENCH still applies. Bench exhaustion_short when "
        "a TREND/RUN is genuinely running against a fade (that is the tested behaviour, +$810 non-overlap n=25), or "
        "on violent whipsaw, or on execution pathology. The carve-out removes ONE trigger — day-bias SIGN — not the "
        "regime judgement. Bench it on the MECHANISM being wrong for the tape, never on the direction of the day. "
        "⚠ HONEST STATE OF THE EVIDENCE, so this is not mistaken for a validated edge: live n=71, +$81.50, 53.5% "
        "win, +$1.15/trade — but STRIP-BEST-1 TAKES IT TO -$135.50 and strip-best-2 to -$230.50, days green 5/10, "
        "and its last two sessions were -$99.50 and -$141.00. One day (07-30, +$217) carries the whole record. "
        "This carve-out is therefore an OPTION ON A CHEAP GATE, not a conviction: the operator has chosen to pay "
        "~nothing to be present when a rare setup appears. Treat the next ~20 fires as the sample that settles it, "
        "and report the running tally in your reason whenever it fires. "
        "(d) The FADER BENCH is the one router behaviour that survived every robustness test this weekend "
        "(+$810 non-overlap, n=25, stable under every independent regime tag) — keep doing it. Conversely, do NOT "
        "widen into 'stop benching momentum in TREND_UP': that idea was re-derived and REFUTED (placebo-null under "
        "two independent regime tags), so leave TREND_UP benching exactly as it is. "
        # ★2026-08-01 (audit FIX): the shipped wording said 'leave it as the operator set it', which under
        # the general RULE 're-arm momentum on a real range-break with ER climbing' reads as permission to
        # arm nipc. It is not. nipc FAILED its acceptance replay and is PINNED OFF; asking for it on is a
        # wasted tick that now raises a critical PIN-BLOCKED alarm. Revert: restore the previous sentence.
        # ★★2026-08-05: THIS PARAGRAPH WAS FALSE AND DANGEROUS THE MOMENT nipc WAS ARMED. It asserted
        # "both are OFF" and told the model to ignore them entirely — so with nipc LIVE the router was
        # blind to two armed gates and could not bench them however they bled. PINNED is also empty
        # (frozenset()), so the "pin discards it" claim was untrue as well. Corrected to state the real
        # position and to hand the router explicit bench authority, which the operator's own written kill
        # criterion requires someone to hold.
        "★ nipc_long / nipc_short (news-impulse pullback): ARMED 2026-08-05 on EXPLICIT operator "
        "instruction — \"we just need to run nipc and see how it goes. i dont care if it loses. we are on "
        "paper this is what its for\" — overriding the 08-03 bench. Its live/replay divergence is diagnosed "
        "but NOT resolved (replay +$3.1/tr vs live -$9.33/tr), and the run exists to gather live/replay "
        "PAIRS, so do NOT bench it merely for losing money or for being in chop: losing is inside the "
        "operator's stated tolerance and a bench destroys the sample being collected. "
        "★ BUT YOU DO HOLD BENCH AUTHORITY, and must use it in exactly two cases: (1) cumulative nipc P&L "
        "<= -$400 — the operator's own written kill criterion, which is at -$280 as of the arming, so it is "
        "CLOSE; (2) any execution pathology (naked stop, absurd entry_atr, MAX_HOLD exits stacking). "
        "It self-gates to 13:00-15:00 UTC and switches itself off in dead-chop, so a quiet nipc is the gate "
        "working, not a reason to touch it. Do not ARM it if it is off — that is an operator decision. "
        "★ UNTRADEABLE-DAY RULE (MONDAY #3, revised twice — read the whole rule before acting on it): "
        "if the UNTRADEABLE METER scores >=55 ON TWO CONSECUTIVE TICKS (a big range but ~0 net roundtrip + the "
        "day's move given back + gates stopping across mechanisms), bench the book and keep flat; do NOT hunt for "
        "a gate that works — a no-trade day is correct (chasing an untradeable chop cost -$900 on 07-31). "
        "⚠ THE CONFIRMATION IS MANDATORY AND IT IS COMPUTED FOR YOU — the meter block prints 'confirmation is "
        "MET/UNMET'. If it says UNMET, THERE IS NO STAY-OUT, however bad this single reading looks. MONDAY #3 "
        "shipped at 45-on-one-tick on 08-08; that fired on 55% of observations (vs 30% at 65) and the score "
        "OSCILLATED across it — 08-07 ran 46 -> 42 -> 44 -> 15, crossing twice — so each crossing would have "
        "benched and unbenched all eight gates on noise. 55-with-confirmation is the 2026-08-09 correction. "
        "⚠ 'BENCH THE BOOK' EXCLUDES abs_veto_short — same carve-out as the chop bench, for the same reason: it "
        "is positive in ALL FIVE regimes and 53 of 54 filters tested lose to letting it fire, so a stay-out is "
        "not evidence against IT specifically. Bench the other seven; leave it armed. This resolves the direct "
        "contradiction between this rule and SATURDAY #1's 'bench authority on exactly two things, nothing else'. "
        "⚠ YOUR THRESHOLD IS 55, NOT THE METER'S PRINTED LABEL. The meter module still prints 'STAY-OUT' "
        "only at >=65 and 'CAUTION' at 45-64, because three analysis harnesses classify historical days off "
        "that label and re-cutting it would silently re-label past studies. So a meter reading 'CAUTION 58' "
        "twice running IS A STAY-OUT FOR YOU, and 'CAUTION 52' is NOT. Read the SCORE, not the word. "
        "⛔⛔ A LAPSED BENCH IS NOT AN ARMING CASE — THE MOST-REPEATED ERROR ON THIS DESK. When the ONLY "
        "thing benching a gate stops applying (a stay-out lapses, a direction read goes FLAT, a carve-out "
        "expires), that gate returns to BENCHED-BY-DEFAULT. It does NOT return to armed. Arming needs a "
        "POSITIVE case made this tick; the absence of a bench is not one, and neither is 'the tape is dead' "
        "or 'nothing is stopping me'. This fired FIVE times in 24h (2026-08-10/11) and the 17:45 instance "
        "cost $92.50 by re-arming exhaustion_short, already the day's worst gate at -$137.50 with 4 of 6 "
        "lots stopped, which then stopped 4 more. ⚠ TWO NAMED EXCEPTIONS, and only these two: abs_veto_short "
        "is ARMED-BY-DEFAULT under the 08-08 carve-out (+$2,290.50 / 159 fires, positive in all five "
        "regimes), so restoring IT when a bench lapses is correct policy; capitulation_long likewise carries "
        "no start-benched flag. Every gate in MOMENTUM_START_BENCHED (grind_long, abs_veto_long) is "
        "benched-by-default and needs the MONDAY #4 trio — structure break + ER climbing + vol expanding — "
        "before it is armed. ⚠ AND WEIGH THE GATE'S OWN RECORD: per-gate evidence OUTRANKS the meter's "
        "silence. A meter going quiet says nothing about the gate; it says the meter is quiet. "
        "⛔ THE ASIA BLOCK: 00:00-07:00 UTC, NEW ENTRIES ARE REFUSED whatever your switches say. "
        "no_open_asia=True and multislot_core._open() returns before any entry (shadow n=1840, -$3.17/tr, "
        "the desk's worst block). Exits and every flatten path are UNAFFECTED. Two consequences you must "
        "act on. FIRST, an ARM decided in this window is inert now and becomes LIVE at 07:00 with nothing "
        "resetting it — gate_switches.env has no 07:00 reset, only the 22:00 reactivation. So treat an arm "
        "made in Asia as a decision ABOUT 07:00, not about now: make it only if you would still make it on "
        "the 07:00 tape, and say so in your reason. On 2026-08-11 06:10 an arm crossed that boundary "
        "unexamined. SECOND, do not spend ticks deliberating arms that cannot fire — BENCHES in this window "
        "are still fully effective and still worth making. ⚠ And do not call the tape 'Asia' after 07:00: "
        "07:00-13:00 is LONDON, the desk's ONLY positive block (+$0.70/tr, n=1516). Every tick from 07:00Z "
        "to 08:47Z on 2026-08-10 said 'Asia chop unchanged' while sitting in the one window that pays. "
        "⛔ AND NO STAY-OUT MAY TRIGGER BEFORE 15:00 UTC. The meter is a DAY aggregate; before 15:00Z it has "
        "too little of the day in it to call one, and an early stay-out benches the 13:30-14:45 window where "
        "the desk's expectancy actually lives (+$8.93/tr, n=562). Before 15:00Z, route on the TAPE. "
        "⚠ This cutoff is IN-SAMPLE on n=10 days: if it keeps the desk out of a green day twice, it goes back up. "
        "⛔ A METER MARKED 'NO READ' IS NOT A STAY-OUT, whatever its score says. The module seeds 50 and defaults "
        "to 50 when it cannot compute roundtrip/giveback, so on a dead feed or a sub-30pt range the number 50 is "
        "an ABSENCE OF EVIDENCE that happens to sit above the trigger. Benching the desk because a measurement is "
        "missing is not the same call as benching it because the day is untradeable. Route on the TAPE instead. "
        "Reversion stays through chop. DON'T THRASH — change a switch ONLY when evidence genuinely changed; "
        "most ticks are no-change.\n\n"
        f"CURRENT SWITCHES: {json.dumps(cur)}\n\n"
        f"=== ACTIVE CARVE-OUTS (top of gate_switches.env — written by the session, the operator, or "
        f"the open-hour watcher; these are INSTRUCTIONS TO YOU, honour their stated expiry) ===\n"
        f"{switch_notes()}\n\n"
        f"=== ★ SESSION WINDOW — WHICH BLOCK YOU ARE IN RIGHT NOW ===\n  {sess_txt}\n\n"
        f"=== ★ SEGMENT BIAS — THIS IS THE DIRECTION TRIGGER ===\n  {seg_txt}\n"
        f"  The DAY BIAS line in DESK VIEW below is CONTEXT, not the trigger. Act on the segment, and "
        f"only when its confirmation reads MET.\n\n"
        f"=== RUN STATE — CONTEXT ONLY, NOT A ROUTING LEVER (WITHDRAWN 2026-08-08) ===\n{run_txt}\n"
        f"  ⛔ The 08-06 claim that made this the PRIMARY discriminator (in-run aligned TAKEN "
        f"+$10.34/tr) was RE-DERIVED on the SAME 89 Mon-Thu trades and INVERTS to -$1.83/tr "
        f"(n=46, 41% win). The 34/4/51 split could not be reproduced under ANY run-span definition "
        f"(merge gaps 0/120/300/600/900s all give an identical 46/10/33). Verdict: an EXIT finding "
        f"wearing a router's coat. READ IT AS CONTEXT — NEVER flip a switch on RUN STATE alone, and "
        f"do not treat it as outranking the meter or your own read of the tape.\n\n"
        f"=== UNTRADEABLE METER === (stay-out needs SCORE>=55 on TWO CONSECUTIVE ticks, only from "
        f"15:00Z, and never on a NO READ; the printed verdict word still switches at 65 — ignore "
        f"the word, read the score. abs_veto_short is exempt)\n{untr_txt}\n"
        f"  ⚠ The meter is a DAY aggregate and is diluted by earlier chop. On 08-06 it read 87/100 "
        f"STAY-OUT while a +297pt run was underway and the desk sat flat through all of it. "
        f"NEITHER INSTRUMENT OUTRANKS THE OTHER — the 'RUN STATE wins' tie-break was WITHDRAWN "
        f"2026-08-08 along with the lever itself. Judge the SEGMENT, not the day, and form the read "
        f"from the TAPE first; the meter and RUN STATE are both confirmation.\n\n"
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
    # ★2026-08-11 was [:300] and it clipped mid-word, systematically keeping the boilerplate
    # context the router front-loads and dropping the ARGUMENT for the change it made. Two
    # consecutive bad-call reviews could not grade a decision because its justification was
    # in the clipped remainder. The ledger grades REASONING; do not clip the reasoning.
    reason = str(dec.get("reason", ""))[:1200]
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
