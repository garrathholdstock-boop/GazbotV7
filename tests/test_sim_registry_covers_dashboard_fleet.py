"""The registrar must see EXACTLY the fleet the dashboard renders.

2026-08-19: the operator asked about "sim 55". `scripts/sim_registry.py` discovered sims by
introspecting `runner`/`shadow` for slate-shaped attributes; `web.shadow_overview_json()` renders
`default_slate() + CB_STRATEGIES + CL_GATES`. Two modules, two definitions of "the fleet". Four CL
gates that had not yet traded were invisible to the registrar, so they had no number and the board
showed "?" — and `web.sim_ids()` documents that a positional fallback would be worse, so "?" was
the honest-but-broken outcome.

A number the operator can say out loud is only useful if EVERY row on his board has one. This test
fails if the registrar's view ever falls behind the board's again.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")


def _registry_module():
    spec = importlib.util.spec_from_file_location("sim_registry", f"{GB}/scripts/sim_registry.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sim_registry"] = mod
    spec.loader.exec_module(mod)
    return mod


def _dashboard_fleet():
    """Exactly what web.shadow_overview_json() builds its board from."""
    from gazbot7.cb import CB_STRATEGIES
    from gazbot7.cl_sims import CL_GATES
    from gazbot7.shadow import default_slate
    return [v.name for v in default_slate()] + list(CB_STRATEGIES) + list(CL_GATES)


def test_registrar_discovers_every_name_the_board_renders():
    found = set(_registry_module().discover())
    missing = [n for n in _dashboard_fleet() if n not in found]
    assert not missing, (
        f"{len(missing)} sim(s) render on the shadow board but are invisible to the registrar, so "
        f'they carry no number and show as "?": {missing}. Add their source to discover().')


def test_every_dashboard_row_has_a_number():
    """The end-to-end promise: no row on the board is unnumbered."""
    if not os.path.exists(f"{GB}/data/sim_registry.json"):
        return                                    # fresh tree — nothing allocated yet
    with open(f"{GB}/data/sim_registry.json") as fh:
        ids = json.load(fh).get("ids", {})
    unnumbered = [n for n in _dashboard_fleet() if n not in ids]
    assert not unnumbered, (
        f'{len(unnumbered)} sim(s) would render as "?" on the shadow board: {unnumbered}. '
        f"Run: PYTHONPATH=src .venv/bin/python scripts/sim_registry.py")


def test_ids_are_unique_and_never_reissued():
    """An index is a position; an identifier is a promise. Two sims sharing a number breaks it."""
    with open(f"{GB}/data/sim_registry.json") as fh:
        d = json.load(fh)
    ids = d.get("ids", {})
    seen: dict[int, str] = {}
    for name, i in ids.items():
        assert i not in seen, f"id {i} is issued to BOTH {seen[i]} and {name}"
        seen[i] = name
    assert d.get("next", 0) > max(ids.values(), default=0), (
        "`next` is not beyond the highest issued id — the next allocation would REISSUE a number")
