"""THE DESK BRIEF (E119) is gospel: the mechanics Claude reads must be exactly what the live robot does. These tests fail the moment the
robot's constants and the brief disagree, or a versioned layer is edited without a version line."""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")
import hybrid_robot as H  # noqa: E402
from gazbot7 import desk_brief as DB  # noqa: E402


def _mech():
    return DB.mechanics_from_robot(H)


def test_mechanics_are_generated_from_the_robot():
    m = _mech()
    tgt = float(H.TARGETS.split(",")[0]) / H.PV
    assert m["target_pts"] == tgt and m["lots"] == H.QTY and m["lock_usd"] == H.LOCK_USD and m["mil_cap"] == H.MIL_CAP
    assert m["exit_live"] == H.L.read_switch(H.SWITCH, "hybrid_exit_live")
    text = DB.mechanics(m)
    assert f"+{tgt:g} points" in text and f"{H.QTY} MNQ" in text and f"${H.LOCK_USD:,.0f}" in text and f"At most {H.MIL_CAP} claims" in text
    assert ("DO NOT close the real position" in text) == (not m["exit_live"])


def test_the_hand_written_layers_never_restate_a_mechanic_number_that_could_drift():
    """Numbers that belong to the code (target, lock, cap, flat time) must live in the generated block, not in strategy.md/experience.md -
    except where experience cites what happened (dated). strategy.md must not hard-code the lock or the cap."""
    s = DB._read("strategy.md")
    assert "1,000" not in s and "claims per" not in s.lower()
    assert "flattened at 13:30" not in s and "flattened at 13:30" not in DB._read("experience.md")


def test_every_layer_is_versioned_and_experience_lines_are_dated_and_cited():
    assert re.fullmatch(r"D\d+", DB.version())
    for ln in DB._read("experience.md").splitlines():
        if ln.startswith("- "):
            assert re.match(r"- 20\d\d-\d\d-\d\d \(E\d+", ln), ln


def test_the_build_stamps_version_and_a_static_sha_that_ignores_the_live_state():
    a, sa = DB.build(_mech(), {"now_utc": "05:00Z", "mins_to_us_open": 510, "mil_dir": 1, "mil_claims": 0, "mil_cap": 2})
    b, sb = DB.build(_mech(), {"now_utc": "09:00Z", "mins_to_us_open": 270, "mil_dir": -1, "mil_claims": 1, "mil_cap": 2})
    assert sa == sb and a != b and sa["version"] == DB.version()
    assert '"action":"ENTER_LONG|ENTER_SHORT|EXIT|HOLD|WAIT"' in a          # the reply contract S.ask parses
