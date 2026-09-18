"""THE FRIDAY REPORT, REFOCUSED — one subject: his trades, and whether they can be automated.

Operator, 2026-09-18: *"the friday report is now vastly different. it doesnt need everything it
had. all it needs now is a deep analysis of my trades and to see if we can automate them."*

★ WHY THAT IS RIGHT, in the desk's own numbers: his manual trading is the only book here that has
ever cleared zero (+$78/trade against the automated gates' +$2.10). Nine of the fifteen old phases
were analysing books that are not where the money is.
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

from friday.friday_phases import PHASES, RETIRED_2026_09_18, resolve

TAIL = ("assemble", "proofread", "rev2", "final")
BODY = ("op_record", "op_conditions", "automation_gap", "run_charts")


def test_the_body_is_only_the_operator_sections():
    assert tuple(p["key"] for p in PHASES if p["key"] not in TAIL) == BODY


def test_the_reserved_tail_survived():
    """★ CLAUDE.md: 'you lose a greenfield cluster, never the revision.'"""
    assert tuple(p["key"] for p in PHASES if p["key"] in TAIL) == TAIL


def test_retired_phases_are_KEPT_not_deleted():
    """⚠ Years of accumulated method traps live in those prompts — the first-confirmation scan, the
    drift.confirmed gate, the exit-variant battery that must not be re-run. Restoring one must be a
    move, never a rewrite from memory."""
    assert len(RETIRED_2026_09_18) >= 10
    blob = " ".join(p["prompt"] for p in RETIRED_2026_09_18)
    assert "DO NOT RE-RUN THE EXIT VARIANT BATTERY" in blob
    assert "DriftRead.confirmed" in blob, "the drift-contract trap was lost with the prompts"
    assert "first confirmation" in blob.lower(), "the first-confirmation scan trap was lost"


def test_assemble_refuses_the_retired_fragments():
    """⚠⚠ THE STALE-STITCH TRAP. Every retired section's HTML is STILL ON DISK from previous weeks.
    Stitching one in would publish last month's tournament review as this week's work — and
    staleness here is invisible, because the file exists and parses."""
    a = [p for p in PHASES if p["key"] == "assemble"][0]["prompt"]
    assert "RETIRED" in a and "STALE" in a
    for retired in ("part1_live", "part2_shadow", "part25_musings", "part2_6_router"):
        assert retired in a, f"assemble does not explicitly exclude {retired}"


def test_every_body_phase_carries_the_n_limits():
    """★★★ THE FAILURE MODE OF THIS REPORT is fitting a model of his judgement on 28 positives and
    zero negatives. Every analytical phase must be told so in its own prompt — a rule that lives
    only in CLAUDE.md is a rule the phase never sees."""
    for p in PHASES:
        if p["key"] in TAIL or p["key"] == "run_charts":
            continue
        pr = p["prompt"]
        assert "NO FITTING BELOW 30 LABELLED PRESSES" in pr, f"{p['key']} missing the fitting limit"
        assert "ZERO records of him looking and NOT trading" in pr, f"{p['key']} missing negatives"
        assert "CLAIMING CANNOT BE BACKTESTED" in pr, f"{p['key']} may re-run the 120th calibration"
        assert "RANKED SHORTLIST" in pr, f"{p['key']} may end in a verdict with nothing to try"


def test_every_body_phase_carries_the_data_contract():
    """⚠ GROUP BY ENTRY, not by trade row — the rows are scale-out exits and counting them inflates
    n by ~2.5x. Plus the fabricated-fill and data_quality traps."""
    for p in PHASES:
        if p["key"] in TAIL:
            continue
        pr = p["prompt"]
        assert "GROUP BY ENTRY, NOT BY TRADE ROW" in pr, f"{p['key']} may count exit rows as trades"
        assert "0.1%" in pr, f"{p['key']} missing the fabricated-fill warning"
        assert "data_quality" in pr, f"{p['key']} missing the BADFILL/EXCLUDE filter"


def test_null_entry_source_must_stay_null():
    """⚠ 83 rows predate the column. An inferred source is indistinguishable from a recorded one."""
    for p in PHASES:
        if p["key"] in TAIL:
            continue
        assert "NEVER infer a source for a NULL row" in p["prompt"]


def test_the_macro_backdrop_is_framed_as_explanation_not_forecast():
    """⚠ Measured 2026-09-18: all four co-move, NONE predicts the next day."""
    a = [p for p in PHASES if p["key"] == "assemble"][0]["prompt"]
    assert "NONE predicts the next day" in a and "never as a forecast" in a


def test_the_budget_fits_its_window():
    """★ CLAUDE.md: the old manifest declared 1,755 min of timeouts against a 228 min body budget,
    so clock order silently decided what got built."""
    body = [p for p in PHASES if p["key"] not in TAIL]
    tail = [p for p in PHASES if p["key"] in TAIL]
    # body runs in waves of 4; automation_gap depends on two others so it is a second wave
    wave1 = max(p["timeout_s"] for p in body if not p["deps"])
    wave2 = max(p["timeout_s"] for p in body if p["deps"])
    assert (wave1 + wave2) / 60 <= 228, "the body no longer fits its budget"
    assert sum(p["timeout_s"] for p in tail) / 60 <= 200, "the tail exceeds its reserve"


def test_all_deps_resolve_and_no_artifact_has_an_unsubstituted_brace():
    """★★★ THE BUG THAT KILLED THE TAIL ON EVERY RUN (08-15): a doubled brace made assemble's
    artifact the LITERAL 'weekly_{WEEK}.html', which could never exist."""
    keys = {p["key"] for p in PHASES}
    for p in PHASES:
        assert not [d for d in p["deps"] if d not in keys], f"{p['key']} depends on a retired phase"
        art = resolve(p, "2026-09-11")["artifact"]
        assert "{" not in art, f"{p['key']} artifact has an unsubstituted brace: {art}"
