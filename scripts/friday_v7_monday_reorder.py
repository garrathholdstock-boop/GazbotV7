#!/usr/bin/env python3
"""Re-rank the 2026-08-08 card into the agreed Monday execution order, and make the play
ledger REAL rather than a recommendation.

★ WHY. The card as rendered was ordered by the size of each play's headline number. The
agreed order is by EXECUTION LOGIC: forced-hand items first (things the Sunday 22:00Z
reactivate timer decides for you if you do nothing), then safety, then the measurement
infrastructure that every later judgement depends on, then the experiments.

Four changes:
  1. Three ledger fields (status / shipped_ts / outcome) on EVERY play. Part 3.3 §5 asks for
     them; adding a play that says "build a ledger" and not building it is how last week's
     card went ungraded. Defaults are PROPOSED/null/null — whoever ships a change sets them.
  2. Two plays that exist in the report (Part 3.3 §5, "The Saturday build, in priority
     order") but were never on the card: the ledger job and committing the working tree.
  3. Two window moves. The orphan-stop auditor is promoted BUILD -> SATURDAY: it is the open
     gap from the 08-06 naked-short incident, not a nice-to-have. The exhaustion exit revert
     is demoted SATURDAY -> BUILD and blocked on the shadow-repricer fix.
  4. Explicit re-rank of all three actionable windows.

⚠ THE DEPENDENCY, STATED PRECISELY. BUILD #3 (shadow repricer leaks past its own stops on
44% of trades, median overshoot 0.56xATR) inflates results that reward CUTTING EARLY. That
gates the exhaustion revert, which is a tight 8pt/12pt/120s ladder. It does NOT gate the
Lot B widening (6R, and Lot A 1.0->3.0R), which exits LATER — the same bias works against
that change, not for it. Lot B's weakness is its own failed parameter plateau (4 of 35 cells
positive, two days carrying two-thirds of the edge), which is a different objection.

Revert: cp reports/friday_v7/plays.json.pre-reorder reports/friday_v7/plays.json
"""
import json
import pathlib
import sys

PLAYS = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/plays.json")
BACKUP = PLAYS.with_suffix(".json.pre-reorder")

# ── the agreed execution order, per window ────────────────────────────────────────────────
SATURDAY = [
    "absveto-short-arm-by-default-er035-0808",     # forced: the reopen arms it either way
    "grind-long-revert-atr22-ext30-0808",          # forced: not in HOLD, 22:00Z re-arms it
    "orphan-stop-auditor-on-a-timer-0808",         # promoted from BUILD — the 08-06 open gap
    "max-hold-keep-120-add-ceiling-0808",          # safety, survives a dead loop
    "day-rider-write-trade-rows-0808",             # ★ before any day-rider judgement
    "day-rider-cut-to-1-lot-0808",                 # ★ and before any day-rider risk
    "commit-the-working-tree-0808",                # NEW
    "play-ledger-status-outcome-0808",             # NEW
    "day-rider-eff-floor-025-0808",                # only meaningful once the two above land
    "lotb-rung-widen-atrsplit24-0808",             # forward-validated experiment
]
MONDAY = [
    "chop-avoidance-is-the-biggest-number-0808",   # the principle, and the largest number
    "router-timing-window45-hold3-0808",
    "fix-midnight-reopen-reversion-only-0808",
    "meter-stayout-45-and-no-preopen-0808",        # ship the 15:00Z clause, hold the 45
    "vol-expansion-not-a-rearm-trigger-0808",
    "grade-the-bad-days-0808",
]
BUILD = [
    "fix-shadow-repricer-stop-detection-0808",     # ★ gates every 'exit earlier' re-run
    "open-rider-to-shadow-0808",
    "wide-stops-open-window-shadow-0808",          # promoted: cheap test of the ODR finding
    "exhaustion-short-exit-revert-8-12-120-0808",  # demoted from SATURDAY, BLOCKED on #1
    "keep-archiving-ticks-0808",                   # promoted: the binding constraint
    "shadow-db-data-quality-column-0808",
    "populate-signal-journal-suppressed-by-0808",
    "union-tick-sources-empty-day-must-raise-0808",
    "stop-limit-fill-plausibility-0808",
    "reconstruct-rederive-entry-atr-0808",
    "log-the-silent-return-paths-0808",
    "fix-nightly-fader-repricing-0808",
    "shrink-the-55s-wait-keep-the-test-0808",
    "quiet-clip-regime-carveout-0808",
    "nipc-short-to-shadow-0808",
    "flow-break-ignition-flow-trap-fade-shadow-0808",
    "dead-chop-fade-2000-shadow-0808",
    "grind-ext-hi-regime-conditional-0808",        # superseded by Part 3.2
    "census-cluster-labels-persist-3-0808",
]

NEW_PLAYS = [
    {
        "id": "commit-the-working-tree-0808",
        "window": "SATURDAY", "rank": 0,
        "topic": "★ Commit the working tree — five live behaviours exist only as uncommitted edits",
        "play": "Commit every uncommitted change that is currently live, then make "
                "`exit_overrides_uncommitted: true` FAIL the sweep instead of being journalled and "
                "ignored. The flag already exists and is already written at every desk startup; "
                "nothing has ever acted on it.",
        "mechanism": "config integrity / reproducibility",
        "arms_when": "N/A — infrastructure.",
        "exit": "N/A.",
        "tier": "LIVE",
        "number": "Five live behaviours exist only as uncommitted working-tree edits. "
                  "`config_journal.jsonl` flags `exit_overrides_uncommitted: true` at every startup "
                  "and nothing consumes it. Reconstructing a config epoch by hand is what made "
                  "07-31→08-02 unrecoverable, and the REV2 audit of last week's card took hours of "
                  "archaeology that a commit history would have made a query.",
        "kill": "None — this is reproducibility, not a hypothesis. If the sweep starts failing on it, "
                "that is the mechanism working.",
        "owner": "Garrath — git commit, then one clause in sweep.py",
        "revert": "N/A. Committing cannot change live behaviour; it only records it.",
        "rationale": "An uncommitted live behaviour is a behaviour that cannot be reverted, diffed or "
                     "reproduced. The desk already journals a flag that says this is happening and no "
                     "instrument reads it — the same shape as `signal_journal.suppressed_by` being NULL "
                     "in all 596 rows.",
        "section_ref": "Part 3.3 (REV2 · Q2) §5 — 'The Saturday build, in priority order' #2",
        "verification": "git status clean on the desk tree; sweep goes red if it is not.",
        "suggested_mode": "infrastructure",
    },
    {
        "id": "play-ledger-status-outcome-0808",
        "window": "SATURDAY", "rank": 0,
        "topic": "★ The play ledger — status / shipped_ts / outcome on every play, plus a Monday grader",
        "play": "The three fields are now written on all 50 rows of plays.json (defaults "
                "PROPOSED / null / null). Two things remain: whoever applies a change sets "
                "`status` and `shipped_ts` at the time they apply it, and a Monday job fills "
                "`outcome` from the trade book on the gate each play names.",
        "mechanism": "plays.json ledger + a scheduled grader",
        "arms_when": "N/A — infrastructure.",
        "exit": "N/A.",
        "tier": "LIVE",
        "number": "Last week's 24-play card had no outcome field, so nothing graded it and nothing "
                  "grades the new one either. The REV2 audit had to hand-derive all 24 grades: 15 "
                  "shipped in some form, 4 never built, 3 overtaken, 1 partly done, 1 flatly violated. "
                  "The card claimed £3,150/wk; the five sessions that followed it came in at −$772.50 "
                  "on 110 trades. The single most expensive line was old #19 — the card said SHADOW "
                  "news-impulse-pullback and do NOT arm it, it was armed live the next day, and it is "
                  "−$434.50 over 49 trades at 24.5% win.",
        "kill": "None. Without it, next Friday repeats this week's archaeology.",
        "owner": "Claude — the Monday grader; Garrath — set status/shipped_ts when applying a change",
        "revert": "Drop the three fields. Nothing reads them yet except the grader.",
        "rationale": "Three fields turn 'did we do it, and did it work?' from hours of archaeology into "
                     "a query. It is the cheapest thing on this card and it compounds every week.",
        "section_ref": "Part 3.3 (REV2 · Q2) §1 and §5 — 'The Saturday build, in priority order' #1",
        "verification": "Next Friday: the card grades itself with no hand-derivation.",
        "suggested_mode": "infrastructure",
    },
]

BLOCKED = {
    "exhaustion-short-exit-revert-8-12-120-0808":
        "★ BLOCKED on BUILD #1 (fix-shadow-repricer-stop-detection-0808). This is a tighter, "
        "earlier exit, and the repricer leaks past its own stops on 44% of trades (median "
        "overshoot 0.56×ATR) — which is precisely the bias that inflates 'cut earlier' results. "
        "Re-derive it AFTER the repricer is fixed. The gate's ENTRY stays parked either way. "
        "⚠ Note this dependency does NOT extend to the Lot B widening: that exits LATER, so the "
        "same bias runs against it, and its real objection is its own failed parameter plateau.",
}


def main():
    rows = json.loads(PLAYS.read_text())
    if any(r["id"] == "play-ledger-status-outcome-0808" for r in rows):
        print("card already re-ordered (ledger play present) — nothing to do (idempotent).")
        return 0
    BACKUP.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    rows.extend(NEW_PLAYS)
    idx = {r["id"]: r for r in rows}

    missing = [p for p in SATURDAY + MONDAY + BUILD if p not in idx]
    if missing:
        raise SystemExit(f"FATAL — order references unknown play ids: {missing}")

    # 1 · the ledger fields, on every row
    for r in rows:
        r.setdefault("status", "PROPOSED")
        r.setdefault("shipped_ts", None)
        r.setdefault("outcome", None)

    # 2 · window moves + re-rank
    moved = []
    for window, order in (("SATURDAY", SATURDAY), ("MONDAY", MONDAY), ("BUILD", BUILD)):
        for i, pid in enumerate(order, start=1):
            r = idx[pid]
            if r["window"] != window:
                moved.append(f"{pid}: {r['window']} → {window}")
                r["window"] = window
            r["rank"] = i

    # 3 · the one real dependency, written on the play itself
    for pid, note in BLOCKED.items():
        idx[pid]["blocked_by"] = "fix-shadow-repricer-stop-detection-0808"
        idx[pid]["play"] = note + " " + idx[pid]["play"]

    # HOLD / NOT-AN-ACTION keep their existing ranks; they are not an execution queue.
    PLAYS.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    print(f"plays.json re-ordered — {len(rows)} plays (2 new).")
    print(f"  ledger fields added to all {len(rows)} rows (status/shipped_ts/outcome)")
    for m in moved:
        print(f"  MOVED  {m}")
    print(f"  BLOCKED exhaustion-short-exit-revert → BUILD #1")
    for window, order in (("SATURDAY", SATURDAY), ("MONDAY", MONDAY), ("BUILD", BUILD)):
        print(f"\n  {window}:")
        for i, pid in enumerate(order, start=1):
            print(f"    {i:>2}. {pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
