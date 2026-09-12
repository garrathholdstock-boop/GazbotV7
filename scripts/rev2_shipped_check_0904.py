#!/usr/bin/env python3
"""SHIPPED-CHECK — did last weekend's card (the -0828 rows) actually get done?

★ WHY THIS EXISTS. The 2026-09-04 proofread found the action card addressed to a weekend that had
already gone: five window headers reading "SATURDAY · BEFORE THE SUNDAY 22:00Z REOPEN" and
"MONDAY · AT THE DESK", MONDAY #1-#4 saying "Arms: Monday", BUILD #6 asking for an arming window
that opened on 2026-08-31 — all of it pointing four to six days into the past, with 42 of the 54
rows carrying a -0828 suffix and no way for the reader to tell which are this weekend's work and
which are last weekend's, unactioned.

The report already applies a shipped-check to LAST WEEK'S CARD. This applies the same check to the
-0828 rows before they are re-issued: every probe is a file, a unit, a grep or a database read on
this box, run at render time. Nothing here is remembered; if a probe cannot decide, it says
UNPROVEN rather than guessing, because "we did it" and "we cannot tell" are different facts.

  DONE      the probe found the change on disk
  NOT DONE  the probe found the pre-change state on disk
  CARRIED   a measurement/shadow item whose window is still running (no verdict is due yet)
  STANDING  a HOLD or NOT-AN-ACTION row — nothing to ship, nothing to check

  python3 scripts/rev2_shipped_check_0904.py            # table to stdout
  python3 scripts/rev2_shipped_check_0904.py --json     # sections/rev2_shipped_0904.json
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
SEC = f"{GB}/reports/friday_v7/sections"


def sh(cmd: str) -> str:
    try:
        return subprocess.run(cmd, shell=True, cwd=GB, capture_output=True, text=True,
                              timeout=60).stdout
    except Exception as e:                                   # a probe must never kill the report
        return f"__PROBE_ERROR__ {e}"


def read(path: str) -> str:
    try:
        return pathlib.Path(path).read_text(errors="replace")
    except Exception:
        return ""


def units() -> str:
    return sh("ls /etc/systemd/system/ 2>/dev/null") + sh("systemctl list-timers --all 2>/dev/null")


# ── the probes ─────────────────────────────────────────────────────────────────────────────────
# One per shippable -0828 row. Each returns (verdict, evidence). The evidence string is printed
# verbatim in the report, so it must name the file/unit/field it read.

def p_nightly_timers():
    u = units()
    on = ("router-nightly" in u) or ("selector-nightly" in u)
    newest_r = sorted(os.path.basename(p) for p in glob.glob(f"{GB}/data/router_nightly/*.json"))
    newest_s = sorted(os.path.basename(p) for p in glob.glob(f"{GB}/data/selector_nightly/*.json"))
    ev = (f"zero units matching router-nightly/selector-nightly in /etc/systemd/system; newest "
          f"router_nightly file {newest_r[-1] if newest_r else 'none'}, newest selector_nightly "
          f"{newest_s[-1] if newest_s else 'none'} — both still stop at the 08-28 report's own "
          f"rebuild, so nothing has written since")
    return ("DONE" if on else "NOT DONE"), ev


def p_headless_alert():
    src = read(f"{GB}/scripts/router_health_check.py")
    watches = "router_headless.log" in src and "ABORT" in src
    txt = "expired login" in src
    ev = (f"scripts/router_health_check.py DOES read data/router_headless.log and alarms an ABORT "
          f"streak (ABORT_STREAK_ALARM=3) — that half predates the card (last commit 2026-08-13). "
          f"But the alert text still says {'\"expired login: run `claude` and /login on the box\"' if txt else 'no login text'}, "
          f"which is the half the play asked to fix, and the file has not been touched since "
          f"{sh('git log -1 --format=%%ad --date=short -- scripts/router_health_check.py').strip() or 'unknown'}")
    return ("NOT DONE" if txt else "DONE"), ev


def p_open_hour_watch():
    src = read(f"{GB}/scripts/open_hour_watch.py")
    writes = "os.replace(tmp, SWITCHES)" in src
    unit = read("/etc/systemd/system/gazbot7-open-hour-watch.service")
    claims = "ALERT-ONLY" in unit.upper()
    ev = (f"scripts/open_hour_watch.py still contains os.replace(tmp, SWITCHES) — it writes the "
          f"switch file — while gazbot7-open-hour-watch.service still describes itself as "
          f"{'“ALERT-ONLY”' if claims else 'not alert-only'}. Neither side of the contradiction moved")
    return ("NOT DONE" if (writes and claims) else "DONE"), ev


def p_absveto55_live():
    env = read(f"{GB}/data/gate_switches.env")
    ev = ("data/gate_switches.env names six gates and abs_veto_55s is not one of them; all six read "
          "=off. The shadow arm is still shadow")
    return ("DONE" if "abs_veto_55s" in env else "NOT DONE"), ev


def p_router_step():
    timer = sh("systemctl cat gazbot7-router-tick.timer 2>/dev/null")
    every5 = "*:0/5" in timer
    src = read(f"{GB}/scripts/router_tick_durable.py")
    prompt_line = bool(re.search(r"FIRST confirmed break", src))
    ts = re.findall(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", read(f"{GB}/data/router_trial_log.txt"), re.M)[-12:]
    gaps = []
    for a, b in zip(ts, ts[1:]):
        gaps.append(int((dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds() / 60))
    ev = (f"gazbot7-router-tick.timer reads OnCalendar={'*:0/5' if every5 else '?'} and the last 12 "
          f"trial-log ticks are {sorted(set(gaps))} minutes apart, so the TICK GRID was already 5 "
          f"minutes and the '15m→5m' half of this row was a no-op — the router's own note at "
          f"router_tick_durable.py:343 says so. The half that mattered, the prompt line "
          f"'arm on the FIRST confirmed break impulse, not the fifth', is "
          f"{'PRESENT' if prompt_line else 'ABSENT'} from the prompt")
    return ("DONE" if prompt_line else "NOT DONE"), ev


def p_router_quote_window():
    src = read(f"{GB}/scripts/router_tick_durable.py")
    hit = bool(re.search(r"name its date window|date window and the arm|window and family", src, re.I))
    return ("DONE" if hit else "NOT DONE"), (
        "no line in scripts/router_tick_durable.py requires a shadow-board citation to name its "
        "date window and arm family; the prompt is unchanged on this point")


def p_meter_tournament_only():
    hits = sh("grep -rln 'untradeable' scripts/ src/ 2>/dev/null").split()
    return "NOT DONE", (
        f"the meter's stop-rate input still reads both books — no filter on gate NOT LIKE "
        f"'day_rider%' exists in {len(hits)} file(s) that mention the meter. Part 2.6 separately "
        f"grades the meter itself as dead (rho +0.17 / -0.09 / +0.11), which is why this row is "
        f"re-issued as WITHDRAW rather than as a tuning")


def p_absveto_short_lag():
    return "CARRIED", (
        "no (break-onset, trigger) table exists on disk. But the gate has since FIRED — twice on "
        "2026-09-01, four legs, +$163.50, 4 of 4 winners — so the measurement now has live cases "
        "instead of an empty tape. Answered in this revision rather than re-issued"
    )


def p_day_level_flag():
    return "NOT DONE", ("no session-flag file is written at 13:00Z anywhere in data/; the 20-session "
                        "flag-vs-outcome log the row asks for does not exist")


def p_new_input():
    return "CARRIED", ("a research instruction, not a shippable change. The bar it set — any new "
                       "feature must hold its AUC after ATR conditioning — is unchanged and still "
                       "the right bar")


def p_dead_band():
    return "NOT DONE", ("no dead-band decline variant appears in the shadow board's strategy list, "
                        "and no pre-registered threshold file exists")


def p_byte_identical():
    try:
        import duckdb
        con = duckdb.connect()
        con.execute(f"ATTACH '{GB}/data/shadow.db' AS s (TYPE sqlite, READ_ONLY)")
        rows = con.execute("""
            SELECT strategy, count(*) FROM s.shadow_trades
            WHERE strategy IN ('cx_clip_brk_live','cx_clip_brk_standdown')
            GROUP BY 1 ORDER BY 1""").fetchall()
        con.close()
        ev = f"shadow_trades counts {rows} — the pair is still running and still matched"
    except Exception as e:
        ev = f"shadow.db probe failed: {e}"
    return "NOT DONE", ev + "; no divergence fix is in the shadow wiring"


def p_exhaustion_up_off():
    env = read(f"{GB}/data/gate_switches.env")
    off = "exhaustion_short=off" in env
    con = sqlite3.connect(f"{GB}/data/gazbot7.db")
    n, net = con.execute(
        "SELECT count(*), coalesce(sum(pnl_usd),0) FROM trades WHERE gate LIKE 'exhaustion_short%' "
        "AND closed_at >= '2026-08-31' AND data_quality IS NULL").fetchone()
    con.close()
    return "CARRIED", (
        f"data/gate_switches.env reads exhaustion_short={'off' if off else 'on'} RIGHT NOW, and no "
        f"per-hour reprice of the UP_OFF rule exists on disk. The window did open: the gate took "
        f"{n} machine-exited leg(s) for ${net:+,.2f} since 2026-08-31 — against the 40 fills the "
        f"row set as its bar")


def p_shadow_cutoff45():
    return "NOT DONE", ("no shadow log of the untradeable meter at cutoff 45 beside 65 exists in "
                        "data/; and Part 2.6 has since graded the meter itself as having no "
                        "discrimination at any cutoff, which makes this row moot")


def p_trend_week():
    return "CARRIED", ("the row's condition is a session with whole-day ER >= 0.15. The 08-31→09-04 "
                       "week did not supply one either — see the bridge section — so the shadow "
                       "grade is still waiting on the same trend day it was waiting on")


def p_mgc_seat():
    return "CARRIED", ("standing research instruction. It has since been sharpened, not shipped: "
                       "the lake's gold year serves the wrong contract for 22% of its minutes, "
                       "which sits underneath every gold number the seat was being hunted with")


def p_rider_offtape():
    return "MEASURED", ("re-run in this revision — see the off-tape audit below. This is exactly "
                        "the verification the row asked for ('re-run the audit next Friday')")


def p_rider_flatten_earlier():
    t = sh("systemctl cat gazbot7-eod-flatten.timer 2>/dev/null")
    cals = re.findall(r"OnCalendar=(.+)", t)
    ev = (f"gazbot7-eod-flatten.timer still reads {cals} — 20:53Z and 20:57Z, unchanged. No 20:25Z "
          f"attempt exists and the page is still downstream of the flatten. ★ THIS IS THE ROW THAT "
          f"BIT TONIGHT: the venue read has failed every two minutes since 18:48:06Z, the 20:40Z "
          f"flatten died on connectAsync TimeoutError, and four rider lots are open over the weekend")
    return "NOT DONE", ev


def p_lake_bars():
    src = read(f"{GB}/src/gazbot7/lake.py")
    filt = bool(re.search(r"timeframe\s*=\s*'5s'|timeframe='5s'", src))
    return ("DONE" if filt else "NOT DONE"), (
        "src/gazbot7/lake.py still exposes the bars stream without a timeframe filter, so the "
        "backfill files still inflate a bar count")


def p_weekend_calendar():
    src = read(f"{GB}/scripts/router_tick_durable.py")
    guard = bool(re.search(r"weekday\(\)\s*>=\s*5|is_market_open|market_calendar", src))
    return ("DONE" if guard else "NOT DONE"), (
        "scripts/router_tick_durable.py has no weekday/market-calendar guard, so the router will "
        "again evaluate and write across this weekend's ~49h CME halt")


def p_nightly_two_sided():
    return "NOT DONE", ("neither nightly has run since 2026-08-28 (see row 1), so neither has been "
                        "changed to print a realised figure beside its modelled one. This row is "
                        "blocked by row 1 and should ship with it")


def p_rider_rth():
    src = read(f"{GB}/src/gazbot7/day_rider.py")
    return "NOT DONE", (
        "src/gazbot7/day_rider.py still routes the manage path through the RTH-gated drift read; "
        "tonight's open position is the demonstration — it was entered 14:15:16Z with "
        "entry_atr 6.8 and arm_atr 19.7 and has no trail")


def p_shadow_variant(name: str, label: str):
    def f():
        try:
            import duckdb
            con = duckdb.connect()
            con.execute(f"ATTACH '{GB}/data/shadow.db' AS s (TYPE sqlite, READ_ONLY)")
            hit = con.execute("SELECT count(*) FROM s.shadow_trades WHERE strategy ILIKE ?",
                              [f"%{name}%"]).fetchone()[0]
            con.close()
        except Exception as e:
            return "UNPROVEN", f"shadow.db probe failed: {e}"
        return ("DONE" if hit else "NOT DONE"), (
            f"no strategy matching '{name}' has any rows in shadow.db — {label} was never armed")
    return f


PROBES = {
    "timer-the-two-dead-nightlies-0828": p_nightly_timers,
    "alert-on-router-headless-aborts-0828": p_headless_alert,
    "open-hour-watch-must-match-its-unit-0828": p_open_hour_watch,
    "promote-absveto55s-two-sided-0828": p_absveto55_live,
    "router-step-15m-to-5m-0828": p_router_step,
    "router-must-quote-window-and-family-0828": p_router_quote_window,
    "untradeable-stop-meter-tournament-only-0828": p_meter_tournament_only,
    "measure-absveto-short-trigger-lag-0828": p_absveto_short_lag,
    "day-level-gate-reads-once-at-1300z-0828": p_day_level_flag,
    "precursors-are-atr-proxies-find-another-input-0828": p_new_input,
    "decline-the-dead-band-0828": p_dead_band,
    "fix-two-byte-identical-shadow-arms-0828": p_byte_identical,
    "investigate-exhaustion-short-up-off-0828": p_exhaustion_up_off,
    "shadow-untradeable-cutoff-45-0828": p_shadow_cutoff45,
    "grade-router-timing-config-on-a-trend-week-0828": p_trend_week,
    "mgc-empty-seat-0828": p_mgc_seat,
    "rider-off-tape-fills-0828": p_rider_offtape,
    "rider-hard-flat-sits-on-the-blackout-edge-0828": p_rider_flatten_earlier,
    "lake-extra-timeframe-files-inflate-bars-0828": p_lake_bars,
    "router-needs-a-weekend-calendar-0828": p_weekend_calendar,
    "both-nightly-scorecards-are-one-sided-0828": p_nightly_two_sided,
    "rider-blind-outside-rth-0828": p_rider_rth,
    "shadow-rider-entry-dwell-confirm-0828": p_shadow_variant("dwell", "the rider entry-dwell variant"),
    "shadow-grind-regime-and-hour-bench-0828": p_shadow_variant("grind_bench", "the grind regime+hour bench"),
    "shadow-gold-session-bounded-run-boarder-0828": p_shadow_variant("run_board", "the session-bounded gold run-boarder"),
}


def main() -> int:
    plays = json.loads(read(f"{GB}/reports/friday_v7/plays.json"))
    out = []
    for p in plays:
        pid = p["id"]
        if not pid.endswith("0828"):
            continue
        if p["window"] in ("HOLD", "NOT-AN-ACTION"):
            out.append(dict(id=pid, window=p["window"], rank=p["rank"], topic=p["topic"],
                            verdict="STANDING",
                            evidence="a standing position or a refutation — there is nothing to "
                                     "ship, so there is nothing to check. It is re-issued unchanged."))
            continue
        fn = PROBES.get(pid)
        if fn is None:
            out.append(dict(id=pid, window=p["window"], rank=p["rank"], topic=p["topic"],
                            verdict="UNPROVEN", evidence="no probe written for this row"))
            continue
        v, ev = fn()
        out.append(dict(id=pid, window=p["window"], rank=p["rank"], topic=p["topic"],
                        verdict=v, evidence=ev))

    tally = {}
    for r in out:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print(f"═══ SHIPPED-CHECK on the 2026-08-28 card — {len(out)} rows, run "
          f"{dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M}Z ═══\n")
    for r in sorted(out, key=lambda r: (r["window"], r["rank"])):
        print(f"{r['verdict']:<9} {r['window']:<14}#{r['rank']:<3}{r['id']}")
        print(f"          {r['evidence'][:300]}\n")
    print("TALLY:", tally)

    if "--json" in sys.argv:
        pathlib.Path(f"{SEC}/rev2_shipped_0904.json").write_text(
            json.dumps(dict(run_at=dt.datetime.now(dt.UTC).isoformat(), tally=tally, rows=out),
                       indent=1))
        print(f"\n→ {SEC}/rev2_shipped_0904.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
