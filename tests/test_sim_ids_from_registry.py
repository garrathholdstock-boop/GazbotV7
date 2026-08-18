"""The sim number on the shadow board must come from data/sim_registry.json.

★★★2026-08-18. shadow.html numbered sims from a hardcoded `_ID_ORDER` array whose INDEX+1 was
rendered as "#". The registry allocates ids once and persists them, so the two drifted until
**51 of 57 names on the board were mislabelled** and 15 registered sims were missing entirely.

It was not cosmetic. The operator asked "is sim 23 the same tech as our rgv_short gate?" — the
board's #23 was `rg_long_fast_v` (registry #29), the registry's #23 is `exhaustion_rev`, and a whole
exchange was spent confidently answering about the wrong strategy.

Two surfaces numbering one thing differently is the failure `pnl.py` exists to prevent.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.web import sim_ids  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
PAGE = os.path.join(ROOT, "src", "gazbot7", "web_static", "shadow.html")
REG = os.path.join(ROOT, "data", "sim_registry.json")


def test_the_hardcoded_array_is_gone_and_cannot_come_back():
    """★ THE DEFECT ITSELF. A positional array beside a persisted registry WILL drift."""
    page = open(PAGE, encoding="utf-8").read()
    assert not re.search(r'const\s+_ID_ORDER\s*=\s*\[', page), \
        "shadow.html is numbering sims positionally again — that is the bug"
    assert "r.sim_id" in page, "the page must take the id from the API payload"


def test_unknown_renders_a_question_mark_never_a_position():
    """An invented number is indistinguishable from a real one — which is how this broke."""
    page = open(PAGE, encoding="utf-8").read()
    assert 'const idOf = s => (s in _SIM_IDS ? _SIM_IDS[s] : "?");' in page


def test_sim_ids_reads_the_registry():
    ids = sim_ids(REG)
    reg = json.load(open(REG))["ids"]
    assert ids == {k: int(v) for k, v in reg.items() if isinstance(v, int)}
    assert ids["rg_long_fast_v"] == 29, "the number the operator was shown as 23"
    assert ids["exhaustion_rev"] == 23, "what #23 actually is"


def test_a_missing_or_broken_registry_yields_no_ids_not_wrong_ids(tmp_path):
    """★ FAIL TO '?', NEVER TO A GUESS. Empty dict -> every row renders "?" -> visibly unknown."""
    assert sim_ids(str(tmp_path / "does_not_exist.json")) == {}
    bad = tmp_path / "corrupt.json"
    bad.write_text("{ not json")
    assert sim_ids(str(bad)) == {}


def test_ids_are_unique_so_a_number_identifies_one_sim():
    ids = sim_ids(REG)
    dupes = {v for v in ids.values() if list(ids.values()).count(v) > 1}
    assert not dupes, f"duplicate sim ids make the number meaningless: {dupes}"
