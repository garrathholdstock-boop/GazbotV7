#!/usr/bin/env python3
"""WHAT EXIT LADDER WAS LIVE AT TIME T? — reads data/config_journal.jsonl.

This is the question that could NOT be answered on 2026-08-04 and cost the stop-width study its whole
2026-07-31 → 08-02 sample. From here on it is one command.

  # what was live when that trade opened?
  PYTHONPATH=src .venv/bin/python scripts/config_at.py --at '2026-08-04 07:28'
  # every distinct config epoch, with its boundaries — the input a per-epoch study needs
  PYTHONPATH=src .venv/bin/python scripts/config_at.py --epochs
  # what changed between two starts
  PYTHONPATH=src .venv/bin/python scripts/config_at.py --diff <hashA> <hashB>
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.config_journal import config_at, rows  # noqa: E402


def _fmt(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%d %H:%M:%S")


def show(r, *, full=False):
    print(f"start   {r['ts']}   slate={r.get('slate')}  live={r.get('place_live')}  "
          f"hash={r.get('config_hash')}  slots={r.get('n_slots')}")
    g = r.get("git") or {}
    if g.get("commit"):
        warn = "  ⚠ exit_overrides.json UNCOMMITTED at this start" if g.get(
            "exit_overrides_uncommitted") else ""
        print(f"        git {g['commit']}{warn}")
    if r.get("exit_overrides_raw"):
        print(f"        overrides source: {r['exit_overrides_raw']}")
    # ★2026-08-08 — the decider tables are global, not per-slot, so nothing in a slot dump would
    # ever have shown an ATR_FLOOR change. Printed unconditionally: they are four short dicts and
    # they are the single most common thing an entry study needs to pin down.
    if r.get("gates"):
        print(f"        gates   {r['gates']}   (entry_hash={r.get('entry_hash')})")
    if full:
        print("        resolved exit ladder:")
        for tag, c in sorted((r.get("resolved") or {}).items()):
            bits = [f"{k}={v}" for k, v in c.items()
                    if v not in (0, 0.0, False, None, "") or k in ("exit",)]
            print(f"          {tag:<22} {' '.join(bits)}")
        if r.get("entry"):
            print("        resolved entry config:")
            for tag, c in sorted(r["entry"].items()):
                print(f"          {tag:<22} {c}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", help="UTC time, e.g. '2026-08-04 07:28'")
    ap.add_argument("--epochs", action="store_true", help="list distinct config epochs")
    ap.add_argument("--entry", action="store_true",
                    help="with --epochs: segment on the ENTRY config (gate params, sizing, "
                         "ATR/ER floors) instead of the exit ladder. Recorded from 2026-08-08.")
    ap.add_argument("--diff", nargs=2, metavar=("HASH_A", "HASH_B"))
    ap.add_argument("--full", action="store_true", help="print the whole resolved ladder")
    a = ap.parse_args()

    all_rows = rows()
    if not all_rows:
        print("Journal is empty — data/config_journal.jsonl has no rows yet.")
        print("It is written by gazbot7-tournament at startup, so it fills on the next restart.")
        print("⚠ It records only from today forward. Anything BEFORE the first row is unknown, and")
        print("  config_at() deliberately returns None rather than extrapolating backwards.")
        return 0

    if a.diff:
        want = {h: None for h in a.diff}
        for r in all_rows:
            if r.get("config_hash") in want and want[r["config_hash"]] is None:
                want[r["config_hash"]] = r
        ra, rb = want[a.diff[0]], want[a.diff[1]]
        if not ra or not rb:
            print(f"hash not found: {[h for h in a.diff if not want[h]]}")
            return 1
        ca, cb = ra.get("resolved") or {}, rb.get("resolved") or {}
        print(f"diff {a.diff[0]} ({ra['ts']})  ->  {a.diff[1]} ({rb['ts']})\n")
        for tag in sorted(set(ca) | set(cb)):
            if tag not in ca:
                print(f"  + {tag}  ADDED")
            elif tag not in cb:
                print(f"  - {tag}  REMOVED")
            else:
                for k in sorted(set(ca[tag]) | set(cb[tag])):
                    va, vb = ca[tag].get(k), cb[tag].get(k)
                    if va != vb:
                        print(f"  ~ {tag:<22} {k}: {va} -> {vb}")
        return 0

    if a.epochs:
        # ★2026-08-08 — --entry segments on entry_hash instead of config_hash. An ENTRY study
        # (ATR/ER floors, gate params, sizing) needs windows over which the ENTRY config held
        # still; segmenting it by the exit ladder gives windows that are wrong in both
        # directions. Rows written before 08-08 have no entry_hash and are shown as `-`, which
        # reads correctly as "not recorded" rather than "unchanged".
        key = "entry_hash" if a.entry else "config_hash"
        what = ("the resolved ENTRY config (gate params, sizing, ATR/ER floors)" if a.entry
                else "the resolved exit ladder")
        study = "entry/filter" if a.entry else "exit/stop"
        print(f"CONFIG EPOCHS — each row is a window over which {what} did not change.")
        print(f"Use these as the windows for any {study} study.\n")
        print(f"{'hash':<14}{'from (UTC)':<21}{'to (UTC)':<21}{'starts':>7}")
        eps: list = []
        for r in all_rows:
            h = r.get(key)
            if eps and eps[-1]["hash"] == h:
                eps[-1]["n"] += 1
                eps[-1]["end"] = r["ts_ms"]
            else:
                eps.append({"hash": h, "start": r["ts_ms"], "end": r["ts_ms"], "n": 1})
        for i, e in enumerate(eps):
            end = _fmt(eps[i + 1]["start"]) if i + 1 < len(eps) else "(current)"
            print(f"{(e['hash'] or '-  (not recorded)'):<14}"
                  f"{_fmt(e['start']):<21}{end:<21}{e['n']:>7}")
        if not a.entry:
            print("\n★ The exit ladder is only half the config. `--epochs --entry` segments on the "
                  "ENTRY side\n  (gate params, sizing, ATR/ER floors), recorded from 2026-08-08.")
        return 0

    if a.at:
        t = dt.datetime.fromisoformat(a.at)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.UTC)
        ms = int(t.timestamp() * 1000)
        r = config_at(ms)
        if r is None:
            first = all_rows[0]["ts"]
            print(f"UNKNOWN — {a.at} predates the journal, which begins {first}.")
            print("Deliberately NOT extrapolating backwards: applying a later ladder to earlier trades")
            print("is exactly the error that produced a false +$2,477 stop-width result on 2026-08-04.")
            return 2
        print(f"Config live at {a.at} UTC:\n")
        show(r, full=True)
        return 0

    print(f"{len(all_rows)} startup rows. Most recent:\n")
    show(all_rows[-1], full=a.full)
    print("\n(--epochs for the epoch list, --at 'YYYY-MM-DD HH:MM' for a point in time)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
