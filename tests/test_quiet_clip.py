"""★2026-08-02 — the QUIET-TAPE CLIP (atr_split / lo_target_usd / lo_target_r).

Guards the three things that could silently break the desk:
  1. OFF by default — a gate without atr_split behaves exactly as before.
  2. The choice is frozen AT ENTRY on entry ATR and never re-evaluated mid-trade.
  3. A malformed `lo` block drops ONLY the split, never the gate's normal A/B exits.
"""
from __future__ import annotations

import json

import pytest

from gazbot7 import slot_strategy as _ss
from gazbot7.slot_strategy import SlotSpec, SlotStrategy


def _spec(**kw):
    base = dict(tag="t", kind="grind", side="LONG", exit="scalp", target_r=2.5,
                stop_atr_mult=1.0, giveback_enabled=False)
    base.update(kw)
    return SlotSpec(**base)


class _Slot:
    def __init__(self, side, entry, atr, qty=1):
        self.side, self.entry_price, self.entry_atr, self.qty = side, entry, atr, qty
        self.is_flat, self.opened_at = False, None


def _manage(spec, slot, price, lo=None):
    st = SlotStrategy([spec], value_per_point=2.0)
    if lo is not None:
        st._exit_lo[spec.tag] = lo
    st._peak[spec.tag] = 0.0
    return st._manage(spec, slot, price)


# ── 1. off by default ────────────────────────────────────────────────────────
def test_no_atr_split_means_untouched_behaviour():
    s = _spec()
    assert s.atr_split == 0.0 and s.lo_target_usd == 0.0 and s.lo_target_r == 0.0
    slot = _Slot("LONG", 100.0, 10.0)
    # 2.5R = +25pt. At +20pt a plain scalp gate must NOT exit.
    assert _manage(s, slot, 120.0) is None
    assert _manage(s, slot, 125.0) == "TARGET"


def test_live_slate_has_the_split_off_unless_configured(monkeypatch, tmp_path):
    for x in _ss.scaleout_slots():
        assert x.atr_split == 0.0 or x.lo_target_usd or x.lo_target_r, x.tag


# ── 2. the dollar clip, and the entry-time freeze ────────────────────────────
def test_lot_a_banks_a_fixed_dollar_amount_when_the_split_is_armed():
    s = _spec(atr_split=22.0, lo_target_usd=40.0)
    slot = _Slot("LONG", 100.0, 10.0)          # $2/pt → $40 = +20pt
    assert _manage(s, slot, 119.0, lo=True) is None      # $38 — not yet
    assert _manage(s, slot, 120.0, lo=True) == "TARGET"  # $40 — bank it
    # and it pre-empts the normal 2.5R (+25pt) target that would otherwise still be running
    assert _manage(s, slot, 124.0, lo=True) == "TARGET"


def test_lot_b_banks_a_fixed_R_not_a_chandelier():
    s = _spec(exit="chandelier", atr_split=22.0, lo_target_r=1.75)
    slot = _Slot("SHORT", 100.0, 10.0)         # 1.75R = 17.5pt in our favour → price 82.5
    assert _manage(s, slot, 85.0, lo=True) is None
    assert _manage(s, slot, 82.5, lo=True) == "TARGET"


def test_split_not_armed_falls_through_to_the_normal_stack():
    """lo=False (entry ATR was at/above the split) → the gate's own exit runs, unchanged."""
    s = _spec(atr_split=22.0, lo_target_usd=40.0)
    slot = _Slot("LONG", 100.0, 10.0)
    assert _manage(s, slot, 120.0, lo=False) is None       # $40 ignored
    assert _manage(s, slot, 125.0, lo=False) == "TARGET"   # the real 2.5R still governs


def test_choice_is_frozen_at_entry_not_recomputed():
    """The whole point: a widening tape must not move the target away from a green position."""
    s = _spec(atr_split=22.0, lo_target_usd=40.0)
    st = SlotStrategy([s], value_per_point=2.0)
    st._peak[s.tag] = 0.0
    st._exit_lo[s.tag] = True                  # frozen ON at entry
    slot = _Slot("LONG", 100.0, 60.0)          # entry_atr now way ABOVE the split
    assert st._manage(s, slot, 120.0) == "TARGET"   # still clips — the freeze holds


# ── 3. config validation is fail-safe ────────────────────────────────────────
@pytest.mark.parametrize("lo,split", [
    ({"a_usd": 0, "b_r": 1.75}, 22),      # zero dollar clip
    ({"a_usd": 40, "b_r": 0}, 22),        # zero R
    ({"a_usd": 40, "b_r": 1.75}, 0),      # no threshold
    ({"a_usd": 9999, "b_r": 1.75}, 22),   # absurd dollar
    ({"a_usd": 40, "b_r": 99}, 22),       # absurd R
    ("not-a-dict", 22),
])
def test_bad_lo_block_drops_only_the_split_never_the_gate(tmp_path, monkeypatch, lo, split):
    p = tmp_path / "eo.json"
    p.write_text(json.dumps({"grind_long": {"a_r": 2.5, "b": "wide", "atr_split": split, "lo": lo}}))
    monkeypatch.setattr(_ss, "_EXIT_OVERRIDES_PATH", str(p))
    ov = _ss._load_exit_overrides()
    assert ov["grind_long"]["a_r"] == 2.5 and ov["grind_long"]["b"] == "wide"   # gate intact
    assert "atr_split" not in ov["grind_long"]                                  # split dropped


def test_good_lo_block_is_accepted_and_reaches_both_lots(tmp_path, monkeypatch):
    p = tmp_path / "eo.json"
    p.write_text(json.dumps({"grind_long": {"a_r": 2.5, "b": "wide",
                                            "atr_split": 22, "lo": {"a_usd": 40, "b_r": 1.75}}}))
    monkeypatch.setattr(_ss, "_EXIT_OVERRIDES_PATH", str(p))
    d = {s.tag: s for s in _ss.scaleout_slots()}
    assert d["grind_long_A"].atr_split == 22 and d["grind_long_A"].lo_target_usd == 40
    assert d["grind_long_B"].atr_split == 22 and d["grind_long_B"].lo_target_r == 1.75
    # Lot A keeps its normal 2.5R for the high-ATR path; Lot B keeps its wide chandelier
    assert d["grind_long_A"].target_r == 2.5
    assert d["grind_long_B"].exit == "chandelier_lock"


def test_lot_b_can_never_clip_tighter_than_lot_a():
    """★2026-08-02 REGRESSION GUARD. Lot A is a fixed $40 (=20pt at $2/pt); Lot B is 1.75R.
    1.75R < 20pt for any ATR below 11.4 — so without a dollar floor the RUNNER banks before the
    SCALP and the scale-out is upside down. ATR<11 is ~17% of MNQ minute bars, so this is live."""
    a = _spec(tag="a", atr_split=22.0, lo_target_usd=40.0)
    b = _spec(tag="b", exit="chandelier", atr_split=22.0, lo_target_r=1.75, lo_floor_usd=60.0)
    for atr in (6.0, 8.0, 10.0, 11.4, 12.0, 15.0, 17.4, 20.0, 21.9):
        a_pt = a.lo_target_usd / 2.0
        b_pt = max(b.lo_target_r * atr, b.lo_floor_usd / 2.0)
        assert b_pt > a_pt, f"lots inverted at ATR {atr}: A {a_pt}pt vs B {b_pt}pt"
        # and prove it through the real exit path, not just the arithmetic
        assert _manage(b, _Slot("LONG", 100.0, atr), 100.0 + a_pt, lo=True) is None, atr
        # +1 tick past the level: exact float equality at the boundary is not a meaningful guarantee
        assert _manage(b, _Slot("LONG", 100.0, atr), 100.0 + b_pt + 0.25, lo=True) == "TARGET", atr


def test_b_floor_below_lot_a_is_rejected_by_config(tmp_path, monkeypatch):
    """A floor at or under Lot A's clip would re-open the inversion — drop the floor, keep the split."""
    p = tmp_path / "eo.json"
    p.write_text(json.dumps({"grind_long": {"a_r": 2.5, "b": "wide", "atr_split": 22,
                                            "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 30}}}))
    monkeypatch.setattr(_ss, "_EXIT_OVERRIDES_PATH", str(p))
    ov = _ss._load_exit_overrides()
    assert ov["grind_long"]["atr_split"] == 22          # split survives
    assert ov["grind_long"]["lo_b_floor"] == 0.0        # bad floor dropped
