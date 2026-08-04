"""APPEND-ONLY JOURNAL OF THE RESOLVED DESK CONFIG, written at every startup.

Operator, 2026-08-04: "do the startup config logging too".

★ THE PROBLEM THIS SOLVES, AND IT COST REAL WORK THE SAME DAY.
The stop-width study (1.0 vs 1.5 vs 2.0 ATR) had to be split by "config epoch", because comparing a
stop width across two different profit ladders is meaningless. Reconstructing those epochs meant reading
`git log` for slot_strategy.py, cross-referencing the tournament restart log, and guessing — and for
2026-07-31 → 08-02 it FAILED OUTRIGHT: `data/exit_overrides.json` was untracked, so the exit ladder the
desk actually ran in that window is unrecoverable. ~20 momentum trades of sample were lost on a question
worth $1,000+. Tracking the file in git (commit 2cd3f56) makes it visible, but visibility is not history:
a runtime write that nobody commits still leaves no record.

★ WHY IT LOGS THE **RESOLVED** CONFIG, NOT THE SOURCE FILE.
The live ladder is not what is in `exit_overrides.json`; it is what `scaleout_slots()` RETURNS after the
overrides, the scale-out splitter, the `_BIG_RUN` classification and the quiet-tape clip have all been
applied. This desk's own standing rule is "verify config via scaleout_slots(), never source", because
that slate has silently dropped things before — the ER/ATR floors, the ER-hold shadow, the regime-3 exit
selector and base target_r have all been eaten by it. Logging the source file would faithfully record
something the desk was not running.

★ EVERY START GETS A ROW, even when nothing changed. "The desk restarted at T with config X" is exactly
the fact epoch reconstruction needs, and a change-only log cannot answer "what was live at 14:00?"
without assuming no gaps. `config_hash` makes change detection a trivial scan, so nothing is lost by
being complete. Cost is ~2KB per start; at the current ~40 restarts/week that is ~4MB/year.

★ NEVER BREAKS THE DESK. Any failure is swallowed and logged. A journal that can stop the desk from
starting would be far worse than no journal — this is a record-keeping nicety, not the order path.

Read it back with `scripts/config_at.py` — that answers "what exit ladder was live at time T", which
is the question that could not be answered today.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from datetime import UTC, datetime

log = logging.getLogger("config_journal")

JOURNAL = os.environ.get("GAZBOT7_CONFIG_JOURNAL",
                         "/home/alphabot/gazbot7/data/config_journal.jsonl")

# The exit-relevant fields only. A full SlotSpec dump would bury the ladder in entry params that
# slot_strategy.py and git already record; these are the fields a stop/target study needs.
_EXIT_FIELDS = ("exit", "target_r", "stop_atr_mult", "fixed_stop_pt", "fixed_target_pt",
                "vol_adaptive_chandelier", "chandelier_start_k", "chandelier_min_k",
                "chandelier_tighten", "lock_r", "lock_k", "giveback_enabled", "giveback_arm_usd",
                "giveback_usd", "adaptive_exit", "max_hold_s", "flat_by_utc_s",
                "atr_split", "lo_target_usd", "lo_target_r", "lo_floor_usd")


def _git_head(repo: str = "/home/alphabot/gazbot7") -> dict:
    try:
        out = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain",
                                "data/exit_overrides.json"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return {"commit": out or None, "exit_overrides_uncommitted": bool(dirty)}
    except Exception:
        return {"commit": None, "exit_overrides_uncommitted": None}


def resolved_config(specs) -> dict:
    """The exit ladder as the desk will actually run it, keyed by slot tag."""
    out = {}
    for s in specs:
        out[s.tag] = {f: getattr(s, f) for f in _EXIT_FIELDS if hasattr(s, f)}
    return out


def record(specs, *, slate: str, place_live: bool, extra: dict | None = None) -> dict | None:
    """Append one row describing this startup. Returns the row, or None if it could not be written."""
    try:
        cfg = resolved_config(specs)
        # hash the resolved ladder only, so a restart with an identical ladder hashes identically
        # regardless of commit or timestamp — that is what makes change-detection a simple scan.
        h = hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:12]
        raw = None
        try:
            with open("/home/alphabot/gazbot7/data/exit_overrides.json") as fh:
                raw = json.load(fh)
        except Exception:
            pass
        row = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "ts_ms": int(time.time() * 1000),
            "event": "startup",
            "slate": slate,
            "place_live": place_live,
            "config_hash": h,
            "n_slots": len(cfg),
            "git": _git_head(),
            "exit_overrides_raw": raw,   # the SOURCE, kept beside the RESOLVED for divergence checks
            "resolved": cfg,
        }
        if extra:
            row.update(extra)
        prev = last_hash()
        row["changed_from_previous"] = (prev is not None and prev != h)
        with open(JOURNAL, "a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        log.info("config journal: slate=%s hash=%s slots=%d live=%s%s",
                 slate, h, len(cfg), place_live,
                 "  ★ CHANGED from previous start" if row["changed_from_previous"] else "")
        return row
    except Exception as e:
        # A record-keeping failure must never stop the desk starting.
        log.warning("config journal write FAILED (continuing): %s", e)
        return None


def last_hash() -> str | None:
    """config_hash of the most recent row, or None. Reads the tail rather than the whole file."""
    try:
        with open(JOURNAL, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 65536))
            lines = [ln for ln in fh.read().decode(errors="replace").splitlines() if ln.strip()]
        for ln in reversed(lines):
            try:
                return json.loads(ln).get("config_hash")
            except Exception:
                continue
    except FileNotFoundError:
        return None
    except Exception:
        return None
    return None


def rows(path: str | None = None) -> list[dict]:
    """All journal rows, oldest first. Corrupt lines are skipped, not fatal."""
    out = []
    try:
        with open(path or JOURNAL) as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
    except FileNotFoundError:
        return []
    return out


def config_at(ts_ms: int, path: str | None = None) -> dict | None:
    """The config that was live at ts_ms = the last startup at or before it.

    ★ Returns None for a time BEFORE the journal begins rather than guessing from the earliest row.
    Extrapolating backwards is precisely the error that produced a confident +$2,477 for a 2.0x stop
    earlier today: today's ladder was applied to trades that predated it. An honest "unknown" is the
    only correct answer before the journal's first entry."""
    best = None
    for r in rows(path):
        if r.get("ts_ms") is not None and r["ts_ms"] <= ts_ms:
            best = r
        elif r.get("ts_ms", 0) > ts_ms:
            break
    return best
