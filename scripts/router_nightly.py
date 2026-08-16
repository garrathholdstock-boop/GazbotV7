#!/usr/bin/env python3
"""ROUTER NIGHTLY — post-session performance review of the direction-router (operator 2026-07-28).

Answers the three operator questions for one Paris day:
  (1) Was it OPTIMAL / did we BLOCK ADEQUATELY?  — the router benched some gates. Every time a benched
      gate WANTED to open, the tournament logs `SUPPRESSED-OPEN: <gate> <side> would open @<px> t=<epoch>`.
      Reprice each blocked signal tick-honest (scalp-2R / 1-ATR stop) → benched-and-would've-LOST = a GOOD
      block; benched-and-would've-WON = a MISSED trade (the cost of over-benching).
  (2) Did we MISS good trades?  — the sum of blocked would-be WINNERS.
  (3) NET router value = blocked-losses-SAVED − missed-wins.
  + LEAKAGE: realised trades a managed gate took while ON that lost in a regime it maybe should've been
    benched in (a router that let a loser through).

READ-ONLY. Data = the gazbot7-tournament journal (SUPPRESSED-OPEN + DISABLED-change lines) + capture.db
(bars/ticks) + gazbot7.db (realised trades) + the live direction_router regime replay. Writes
data/router_nightly/<date>.json; prints the report. Feeds the Friday week-review (rollup of the nightlies).
⚠ blocked-signal P&L is a tick-honest ESTIMATE under a standard scalp exit (the benched trade never ran).

  PYTHONPATH=src .venv/bin/python scripts/router_nightly.py [--date YYYY-MM-DD]   (default: yesterday Paris)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections import defaultdict

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import Position, exit_scalp  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
OUTDIR = "/home/alphabot/gazbot7/data/router_nightly"
VPP, FEE = 2.0, 1.50
SUPP_RE = re.compile(r"SUPPRESSED-OPEN: (\S+) (\S+) would open @([\d.]+).*? t=(\d+)")
DISA_RE = re.compile(r"DISABLED \(no new entries\): (\[.*\]|none)")
DEDUP_GAP_S = 120   # collapse a benched gate's repeated per-tick SUPPRESSED-OPENs into one signal


def paris_day_bounds(date_str):
    """UTC [start,end) for a Paris calendar day (Paris = UTC+2 in summer)."""
    d = dt.date.fromisoformat(date_str)
    start = dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone(dt.timedelta(hours=2))) - dt.timedelta(hours=2)
    return start, start + dt.timedelta(days=1)


class JournalRotated(RuntimeError):
    """The systemd journal no longer covers the window being backfilled."""


def journal_lines(t0, t1, *, strict: bool = True):
    """Tournament log lines for [t0, t1).

    ★★2026-08-16 BUILD #8 — THIS USED TO REPORT $0/$0/$0 ON A ROTATED JOURNAL.
    systemd's journal is a RING BUFFER. Backfill a day it has already discarded and journalctl exits
    0 with empty stdout, so every downstream count is legitimately zero and the rollup publishes
    "nothing happened" about a day that traded. That is this desk's signature failure — an instrument
    reporting healthy about something it never checked — and it is worse than a crash, because a zero
    looks like a finding.

    An empty window is therefore an ERROR unless the journal is proven to still cover it. We compare
    the requested start against the OLDEST entry systemd still holds. Telling "rotated away" apart
    from "a quiet night" is the whole job: the first is a broken measurement, the second is data.
    """
    since = t0.strftime("%Y-%m-%d %H:%M:%S")
    until = t1.strftime("%Y-%m-%d %H:%M:%S")
    out = subprocess.run(["journalctl", "-u", "gazbot7-tournament", "--since", since, "--until", until,
                          "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=120)
    lines = out.stdout.splitlines()
    if lines or not strict:
        return lines
    oldest = journal_oldest_ts()
    if oldest is not None and oldest <= t0:
        return lines          # the journal DOES cover this window — genuinely a quiet night
    raise JournalRotated(
        f"journalctl returned NOTHING for {since} .. {until}, and the oldest entry it still holds is "
        f"{oldest.isoformat() if oldest else 'unknown'}. This is a BROKEN MEASUREMENT, not a quiet "
        f"night — the rollup would otherwise publish $0/$0/$0 for a day that traded. Re-run against "
        f"the DB, or pass strict=False once you have CONFIRMED the window was really silent.")


def journal_oldest_ts():
    """Timestamp of the oldest tournament entry systemd still retains, or None if it cannot be read.

    None is deliberately NOT treated as 'fine': the caller raises on it, because an unreadable
    retention boundary means we cannot tell a rotated window from a quiet one, and guessing is what
    produced the $0/$0/$0 in the first place."""
    # ⚠ NOT `-n 1` — that is the NEWEST entry. journalctl prints OLDEST-FIRST, so the retention
    # boundary is the FIRST line of an unlimited read. We stream it and stop after one line; the
    # SIGPIPE ends journalctl early, so this does not walk the whole ring buffer.
    try:
        p = subprocess.Popen(["journalctl", "-u", "gazbot7-tournament", "--no-pager",
                              "-o", "short-iso"], stdout=subprocess.PIPE, text=True)
        try:
            first = p.stdout.readline().strip()
        finally:
            p.stdout.close()
            p.terminate()
            p.wait(timeout=10)
        return dt.datetime.fromisoformat(first.split(maxsplit=1)[0]).astimezone(dt.timezone.utc)
    except Exception:
        return None


def reprice_scalp(con, side, entry_px, t0):
    """Tick-honest scalp-2R / 1-ATR-stop P&L estimate for a would-be trade at (entry_px, t0)."""
    rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, max(high) hi, min(low) lo FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={t0-1800} AND bar_ts<={t0} GROUP BY 1""").fetchall()
    atr = sum(r[1]-r[2] for r in rows)/len(rows) if len(rows) >= 6 else 0.0
    if atr <= 0:
        return None
    ticks = con.execute(f"""SELECT price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={int(t0*1000)}
        AND ts_ms<={int((t0+90*60)*1000)} ORDER BY ts_ms""").fetchall()
    if len(ticks) < 2:
        return None
    exit_px = ticks[-1][0]
    for (px,) in ticks[1:]:
        r = exit_scalp(Position(side, entry_px, atr, 0.0), px, target_r=2.0, stop_atr_mult=1.0)
        if r:
            exit_px = px
            break
    pts = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
    return pts * VPP - FEE


def main():
    ap = argparse.ArgumentParser()
    # default = the just-completed Paris day (Paris now − 3h, so a ~22:50 UTC cron reviews the day that
    # rolled at 22:00 UTC; a daytime manual run reviews today-so-far).
    ap.add_argument("--date", default=(dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
                                       - dt.timedelta(hours=3)).strftime("%Y-%m-%d"))
    date = ap.parse_args().date
    t0, t1 = paris_day_bounds(date)
    lines = journal_lines(t0, t1)

    # (a) blocked signals, deduped per gate
    raw = defaultdict(list)   # gate -> [(side, px, epoch)]
    for ln in lines:
        m = SUPP_RE.search(ln)
        if m:
            raw[m.group(1)].append((m.group(2), float(m.group(3)), int(m.group(4)) // 1000))  # t is ms → s
    blocked = defaultdict(list)
    for gate, evs in raw.items():
        evs.sort(key=lambda e: e[2])
        last = -1e9
        for side, px, ep in evs:
            if ep - last >= DEDUP_GAP_S:
                blocked[gate].append((side, px, ep))
                last = ep

    # (b) regime timeline (router replay)
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    ds = t0.timestamp()
    rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1""").fetchall()
    marks = dr.replay_marks([r[0] for r in rows], [r[1] for r in rows], int(ds), int(ds+86400)) if len(rows) > dr.WINDOW else []
    regime_time = defaultdict(int)
    for _mt, s, _e, _n in marks:
        regime_time[s] += 1

    # (c) reprice the blocked signals
    per_gate = {}
    for gate, sigs in blocked.items():
        won = lost = 0
        won_pnl = lost_pnl = 0.0
        for side, px, ep in sigs:
            p = reprice_scalp(con, side, px, ep)
            if p is None:
                continue
            if p >= 0:
                won += 1
                won_pnl += p
            else:
                lost += 1
                lost_pnl += p
        per_gate[gate] = dict(n=len(sigs), won=won, won_pnl=won_pnl, lost=lost, lost_pnl=lost_pnl,
                              net_blocked=won_pnl+lost_pnl)

    con.close()

    # ── report ──
    tot_marks = sum(regime_time.values()) or 1
    print(f"ROUTER NIGHTLY — {date} (Paris)   ·   regime: "
          + "  ".join(f"{k} {100*v//tot_marks}%" for k, v in sorted(regime_time.items())))
    print("router knobs: ER>=%.2f |net|>=%.0f · DOWN_OFF=%s UP_OFF=%s CHOP_OFF=%s\n"
          % (dr.ER_TREND, dr.NET_MIN, sorted(dr.DOWN_OFF), sorted(dr.UP_OFF), sorted(dr.CHOP_OFF)))
    print("BLOCKED SIGNALS (each = a benched gate that wanted to open; repriced tick-honest scalp-2R):")
    print(f"  {'gate':16} {'blocked':>7} {'would-WIN $':>12} {'would-LOSE $':>13} {'net blocked':>12}  verdict")
    saved = missed = 0.0
    for gate in sorted(per_gate, key=lambda g: per_gate[g]["net_blocked"]):
        b = per_gate[gate]
        saved += -b["lost_pnl"]     # losses we avoided
        missed += b["won_pnl"]      # wins we gave up
        v = "GOOD block" if b["net_blocked"] < 0 else "over-bench (missed wins)" if b["net_blocked"] > 0 else "-"
        print(f"  {gate:16} {b['n']:>7} {b['won_pnl']:>+12.0f} {b['lost_pnl']:>+13.0f} {b['net_blocked']:>+12.0f}  {v}")
    router_value = saved - missed
    print(f"\n  → blocked-losses SAVED ${saved:+.0f}  ·  wins MISSED ${missed:+.0f}  ·  NET ROUTER VALUE ${router_value:+.0f}")
    print("  (net<0 blocked = the block helped; net>0 = we benched winners. NET VALUE>0 = router earned its keep.)")

    # (d) leakage — realised managed-gate losers by regime@entry
    con2 = duckdb.connect()
    con2.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    tr = con2.execute(f"""SELECT gate, side, pnl_usd, epoch(opened_at::TIMESTAMPTZ) te FROM g.trades
        WHERE symbol='MNQ' AND epoch(opened_at::TIMESTAMPTZ)>={ds} AND epoch(opened_at::TIMESTAMPTZ)<{ds+86400}
        AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE')""").fetchall()
    con2.close()

    def reg_at(te):
        st = "CHOP"
        for mt, s, _e, _n in marks:
            if mt <= te:
                st = s
            else:
                break
        return st
    # ★★2026-08-16 BUILD #3 — LEAKAGE NOW MEANS "THE ROUTER WAS WRONG", NOT "THE GATE LOST".
    #
    # Two faults were reported against this detector. The first — that its universe was too narrow
    # and it printed ZERO on a week when -$241 leaked through a gate outside it — is already fixed:
    # `dr.MANAGED` is DOWN_OFF | UP_OFF | CHOP_OFF, and exhaustion_short joined UP_OFF on 08-15, so
    # the universe is now all six gates. That half needed no code.
    #
    # The second is still here and is the more misleading one: this counted EVERY losing trade from a
    # managed gate, while `reg_at()` computed the regime at entry and only PRINTED it. So a gate that
    # lost money in a regime the router correctly left it ON in was booked as "leakage" — conflating
    # "the router failed to bench something its own rules say to bench" with "a gate had a bad trade".
    # The desk's standing rule is that NO rule lets the router bench a gate that is simply bleeding;
    # an instrument that scores it on bleeding teaches exactly the wrong lesson.
    #
    # So the split: TRUE leakage is a loser that fired while ON **in a regime where the gate's own
    # routing rule says OFF**. Everything else is an ordinary loss and is reported separately, not
    # counted against the router.
    # ⚠ THE CARVE-OUT IS PART OF THE RULE, NOT AN EXCEPTION TO IT. abs_veto_short is EXEMPT from the
    # chop bench by operator decision pending its 15-fire arm-by-default review: +$2,290.50 over 159
    # fires / 17 days, positive in ALL FIVE regimes including chop, and 53 of 54 filters tested LOSE
    # to just letting it fire. Without this the detector books its chop losers as router failures
    # and argues, nightly, for benching the one gate the evidence says not to.
    CHOP_EXEMPT = {"abs_veto_short"}

    def _should_be_off(gate: str, regime: str) -> bool:
        if regime == "TREND_UP":
            return gate in dr.UP_OFF
        if regime == "TREND_DOWN":
            return gate in dr.DOWN_OFF
        if regime == "CHOP":
            return gate in dr.CHOP_OFF and gate not in CHOP_EXEMPT
        return False

    # ★★★2026-08-16 THE REAL REASON IT REPORTED ZERO, AND IT IS BIGGER THAN THE UNIVERSE.
    # `trades.gate` holds the SLOT TAG — 'exhaustion_short_A', 'grind_long_B' — ever since the
    # dual-slot scale-out went live on 2026-07-29. `dr.MANAGED` holds BASE names. So `g in MANAGED`
    # matched nothing from the current book, and this detector has been structurally blind for three
    # weeks: it printed a confident $0 on 08-11, 08-12 and 08-13, days the desk demonstrably lost
    # money. That is not a narrow universe, it is a detector that could not see any trade at all.
    # tournament._base() is the desk's own tag->gate map and exists for exactly this.
    from gazbot7.tournament import _base
    managed_losers = [(_base(g), p, reg_at(te)) for g, side, p, te in tr
                      if _base(g) in dr.MANAGED and p < 0]
    leak = [(g, p, r) for g, p, r in managed_losers if _should_be_off(g, r)]
    other = [(g, p, r) for g, p, r in managed_losers if not _should_be_off(g, r)]
    leak_pnl, other_pnl = sum(p for _g, p, _r in leak), sum(p for _g, p, _r in other)
    print(f"\nLEAKAGE — losers that fired while ON in a regime the router's OWN rules say to bench: "
          f"{len(leak)} trades, ${leak_pnl:+.0f}")
    for g, p, r in sorted(leak, key=lambda x: x[1])[:6]:
        print(f"    {g:16} ${p:+7.1f}  regime@entry={r}   <- the router should have had this OFF")
    if not leak:
        print("    (none — every managed-gate loser fired in a regime where its rule says ON)")
    print(f"  for contrast, ORDINARY losses on managed gates (rule says ON, gate just lost): "
          f"{len(other)} trades, ${other_pnl:+.0f}")
    print("  ⚠ Only the first number is the router's. Benching on the second is the error the desk "
          "has a standing rule against.")

    out = dict(date=date, regime_pct={k: round(100*v/tot_marks, 1) for k, v in regime_time.items()},
               blocked=per_gate, saved=round(saved), missed=round(missed), router_value=round(router_value),
               leakage_n=len(leak), leakage_pnl=round(leak_pnl),
               # kept separate and explicitly named so no downstream reader can mistake one for the
               # other — the previous field silently mixed them.
               managed_loss_n=len(other), managed_loss_pnl=round(other_pnl),
               leakage_universe=sorted(dr.MANAGED))
    import os
    os.makedirs(OUTDIR, exist_ok=True)
    with open(f"{OUTDIR}/{date}.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUTDIR}/{date}.json")


if __name__ == "__main__":
    main()
