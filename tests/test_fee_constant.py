"""No harness may charge a fee other than $1.50 per round trip.

★★ WHY THIS IS A TEST AND NOT A MEMO. Operator, 2026-08-13: *"have you fixed the $5 fee issue? we
have picked it up each week and fixed it in retrospect."* Exactly — it has been found and fixed
repeatedly and it kept coming back, because every fix was a grep and every grep had a blind spot:

  · the 2026-08-02 correction fixed `FEE, VPP = 5.0, 2.0` (SPACED) and missed `FEE,VPP=5.0,2.0`
    (UNSPACED) in EIGHT scripts, which were still charging $5 today;
  · my own first sweep on 08-13 globbed `scripts/afc_*.py` and missed three `trap_reclaim_*`;
  · the Friday greenfield PROMPT said "$5/round-trip" while every script it invoked used $1.50.

An over-charged fee is the worst kind of wrong because it NEVER LOOKS WRONG. At 3.3x the true
commission a marginal edge simply dies, the harness reports a clean NULL, and the finding is
recorded as "no edge there" — a false negative nobody re-opens.

$1.50/RT is venue truth: every closed trade in the ledger carries fees_usd = 1.50, measured over 487
fills. See [[mnq-fee-is-150-per-round-trip]].
"""
import ast
import glob
import re
import warnings

import pytest

ROOTS = ("/home/alphabot/gazbot7/scripts/**/*.py", "/home/alphabot/gazbot7/src/**/*.py")
OK = {1.5}
# ★ FEE, FEE_RT, FEE_PER_LOT — but NOT "FEED_STALE_S". `startswith("FEE")` flagged the router
# watcher's feed-staleness constants, which have nothing to do with commission. Anchor the name.
FEE_NAME = re.compile(r"^FEE(_[A-Z0-9_]+)?$", re.I)


def _fee_assignments(path):
    """Every executable assignment to a FEE-ish name, via AST.

    ★★ AST, NOT REGEX, AND THAT IS THE WHOLE POINT. My first version pattern-matched, and it fell
    for the EXACT confusion this desk's memory warns about: `VPP, FEE_RT = 2.0, 1.50` is CORRECT
    (VPP=2.0, FEE=1.50) but reads as "FEE_RT = 2.0" to a regex, while `FEE, VPP = 5.0, 2.0` is the
    genuine bug and looks identical. A guard that cannot tell those apart is worse than none — it
    would have produced a dozen false alarms and been switched off.
    AST also gets docstrings and comments right for free: they are not assignments, so they never
    appear here, and the historical "was FEE,VPP=5.0,2.0" warnings in the files stay untouched.
    """
    try:
        # ★ Suppress SyntaxWarning while PARSING OTHER PEOPLE'S FILES. At least one repo script has
        # an invalid escape (e.g. "\\$") in a non-raw string; that is its problem, not this guard's,
        # and letting it spray warnings through every test run is how a suite stops being read.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(open(path, errors="ignore").read())
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            # pair LHS names with RHS values POSITIONALLY for tuple assignment
            names = ([e.id for e in tgt.elts if isinstance(e, ast.Name)]
                     if isinstance(tgt, ast.Tuple) else
                     ([tgt.id] if isinstance(tgt, ast.Name) else []))
            vals = (node.value.elts if isinstance(node.value, ast.Tuple) else [node.value])
            if isinstance(tgt, ast.Tuple) and len(names) != len(vals):
                continue
            for name, val in zip(names, vals):
                if not FEE_NAME.match(name):
                    continue
                if isinstance(val, ast.Constant) and isinstance(val.value, (int, float)):
                    out.append((node.lineno, name, float(val.value)))
    return out


def _offenders():
    bad = []
    for pat in ROOTS:
        for p in glob.glob(pat, recursive=True):
            for lineno, name, val in _fee_assignments(p):
                if val not in OK:
                    bad.append(f"{p}:{lineno}  {name} = {val}  (must be 1.50)")
    return bad


def test_no_harness_charges_a_wrong_fee():
    bad = _offenders()
    assert not bad, (
        "A harness is charging a fee other than $1.50/RT. This has recurred weekly because every "
        "previous fix was a grep with a blind spot (spaced vs unspaced, one directory vs the repo). "
        "An over-charged fee kills marginal edges and reports a confident NULL:\n  "
        + "\n  ".join(bad))


def test_the_guard_catches_both_historical_spellings(tmp_path):
    """A guard that cannot fail is not a guard."""
    for spelling, should_flag in (("FEE, VPP = 5.0, 2.0", True),
                                  ("FEE,VPP=5.0,2.0", True),
                                  ("FEE_RT = 5", True),
                                  ("FEE = 2.0", True),
                                  ("VPP, FEE_RT = 2.0, 1.50", False),   # correct, reversed order
                                  ("FEE, VPP = 1.50, 2.0", False)):
        f = tmp_path / "h.py"
        f.write_text(f"x = 1\n{spelling}\n")
        hits = [a for a in _fee_assignments(str(f)) if a[2] not in OK]
        assert bool(hits) is should_flag, f"{spelling!r}: expected flag={should_flag}, got {hits}"


def test_historical_warnings_are_not_flagged(tmp_path):
    """The files keep 'was FEE,VPP=5.0,2.0' and 'Revert: FEE, VPP = 5.0, 2.0' on purpose — they are
    how a reader knows old results are suspect. The guard must not fight its own documentation."""
    f = tmp_path / "h.py"
    f.write_text('"""doc mentioning FEE, VPP = 5.0, 2.0 in prose."""\n'
                 "# Revert: FEE, VPP = 5.0, 2.0.\n"
                 "FEE, VPP = 1.50, 2.0\n")
    assert not [a for a in _fee_assignments(str(f)) if a[2] not in OK]


@pytest.mark.parametrize("path", ["/home/alphabot/gazbot7/scripts/friday/friday_phases.py"])
def test_report_prompts_quote_the_right_fee(path):
    """The Friday greenfield prompt told the model to net off ~$5/round-trip while every script it
    called used $1.50. The prompt is as load-bearing as the code."""
    s = open(path).read()
    live = [ln for ln in s.splitlines()
            if ("$5/round" in ln or "$5/RT" in ln) and "look identical" not in ln]
    assert not live, f"a report prompt still quotes a $5 fee: {live}"
