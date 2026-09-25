"""THE OPERATOR STAND-DOWN MUST SURVIVE BOTH THINGS THAT ARM GATES (2026-09-25).

★★★ Operator: "why was grind activated? i told you to disactivate all other gates." Then: "yes
make it durable until i lift it."

⚠⚠⚠ WHAT WENT WRONG THE FIRST TIME. On 09-24 the six switches were set to `off` by hand and he was
told the bench would last one session. That was WRONG ABOUT THE MECHANISM. It was not the midnight
re-arm that undid it — it was THE ROUTER, five minutes later, doing its job on its own regime read
(16:11Z "ARMING THE ALIGNED LONG MOMENTUM PAIR"). grind_long then took 4 fills, 4 stops, -$168.50.
Nothing had told the router an instruction existed.

★ SETTING SWITCH VALUES IS NOT AN INSTRUCTION TO ANYTHING. Only two places are, and BOTH are
required — either alone leaves the stand-down half-built:
   1. HOLD in reactivate_gates.py  — stops the 00:00 Paris re-arm
   2. the ⛔ block atop gate_switches.env — spliced into EVERY router prompt by switch_notes()
"""
import sys

SW = "/home/alphabot/gazbot7/data/gate_switches.env"
RG = "/home/alphabot/gazbot7/scripts/reactivate_gates.py"
GATES = {"grind_long", "capitulation_long", "abs_veto_long",
         "exhaustion_short", "abs_veto_short", "rgv_short"}


def test_all_six_are_in_HOLD_so_the_midnight_reopen_cannot_arm_them():
    sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
    import reactivate_gates as rg
    assert GATES <= set(rg.HOLD), f"missing from HOLD: {GATES - set(rg.HOLD)}"


def test_the_reopen_actually_leaves_everything_off():
    """★ Assert the RESULT, never the roster. HOLD only acts on gates that were just reactivated,
    so reading the set is not proof — run the thing and look at the file it would write."""
    sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
    import reactivate_gates as rg
    new, react = rg.reactivate_all(open(SW).read())
    for g in sorted(rg.HOLD & set(react)) + sorted(rg.MOMENTUM_START_BENCHED):
        new = rg._apply(new, g, "off")
    armed = [l for l in new.splitlines()
             if "=" in l and not l.strip().startswith("#") and l.strip().endswith("=on")]
    assert not armed, f"the reopen would arm {armed} despite the stand-down"


def test_the_router_is_told_in_the_one_place_it_reads():
    """⚠⚠ THE LOAD-BEARING HALF. switch_notes() splices the TOP 45 LINES of the switch file into
    every router prompt; values are passed as json and carry no instruction at all. A stand-down
    written only as `off` values is a stand-down the router never hears about."""
    sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
    from router_tick_durable import switch_notes
    n = switch_notes()
    # ⚠ NORMALISE FIRST. The banner is a COMMENT BLOCK, so any phrase can be split by a line
    # break and a "# " — asserting on the raw text tests the line wrapping, not the instruction.
    flat = " ".join(l.lstrip("# ").strip() for l in n.splitlines())
    assert "OPERATOR STAND-DOWN" in flat
    assert "DO NOT ARM ANY GATE, FOR ANY REASON, ON ANY EVIDENCE" in flat
    assert "arming authority is SUSPENDED" in flat


def test_the_block_sits_inside_the_spliced_window():
    """⚠ switch_notes() takes the LEADING block only. A stand-down pushed below it by a future
    carve-out would be silently invisible — which is how the 08-05 one-way channel failed."""
    head = open(SW, encoding="utf-8").read().splitlines()[:45]
    assert any("OPERATOR STAND-DOWN" in l for l in head)
    assert any("DO NOT ARM ANY GATE" in l for l in head)


def test_the_stale_LET_IT_RUN_notes_are_explicitly_superseded():
    """⚠ The header still carries 09-14 and 08-28 watcher notes saying "LET IT RUN" for
    grind_long/abs_veto_long. CLAUDE.md: text granting a standing carve-out found anywhere is STALE
    — say so rather than acting on it. Deleting history is worse than marking it."""
    head = "\n".join(open(SW, encoding="utf-8").read().splitlines()[:45])
    assert "STALE" in head and "SUPERSEDED by this" in head


def test_lifting_it_requires_BOTH_halves_and_says_so():
    """⚠ Half a lift is the worst state: the router arms freely while the reopen still benches, so
    the gates flicker and neither mechanism looks wrong."""
    head = "\n".join(open(SW, encoding="utf-8").read().splitlines()[:45])
    assert "TO LIFT" in head and "Both, or the stand-down is only half-lifted" in head
    assert "Both, or it is half-lifted" in open(RG, encoding="utf-8").read()


def test_the_untracked_half_has_a_tracked_restore_path():
    """⚠⚠⚠ `data/gate_switches.env` IS GITIGNORED — deliberately, because the router rewrites it
    every five minutes. But the ⛔ block inside it is not STATE, it is an OPERATOR INSTRUCTION, and
    an instruction living on one disk is a restart or a header reset away from vanishing silently.
    The gates would arm again and nothing would say why.
    ★ This test is the alarm; ops/OPERATOR_STANDDOWN_2026-09-25.md is the restore path."""
    doc = open("/home/alphabot/gazbot7/ops/OPERATOR_STANDDOWN_2026-09-25.md", encoding="utf-8").read()
    assert "OPERATOR STAND-DOWN" in doc and "DO NOT ARM ANY GATE" in doc, \
        "the restore copy no longer contains the block it is meant to restore"
    assert "TO LIFT" in doc and "rgv_short" in doc
