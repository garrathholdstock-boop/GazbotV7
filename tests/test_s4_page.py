"""S4 (the "v3" line) — the DAY SCORECARD, the entry test and BRIEF_V3, tested through the REAL entry points.

reports/recursive_loop/S4_independent_review.md §8-§12. What the model sees is the assembled prompt, so the
tests run `run_day(line="v3")` and read the prompt it sends ([[a-source-text-test-is-a-lint-not-a-test]]).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import pathlib
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
sys.path.insert(0, str(GB / "src"))
sys.path.insert(0, str(GB / "scripts"))

import sim_week_recursive as SW          # noqa: E402

DAY = "2026-03-05"


def _bars(day=DAY, wobble=9.0, drift=0.05):
    d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    out = []
    for i, ts in enumerate(range(d0 - 2 * 3600, d0 + SW.WIN_END_MIN * 60 + 60, 60)):
        c = 20000 + drift * i + wobble * math.sin(i / 11.0)
        out.append((ts, c + 1.0, c - 1.0, c))
    return out


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.UTC).isoformat()


def _trade(bars, i_open, i_close, side="LONG", pts=40.0, peak=45.0):
    px = bars[i_open][3]
    d = 1 if side == "LONG" else -1
    return {"side": side, "entry": px, "exit": px + d * pts, "opened": _iso(bars[i_open][0]),
            "closed": _iso(bars[i_close][0]), "held_min": i_close - i_open, "points": pts,
            "peak_pt": peak, "pnl_usd": round(pts * SW.LOTS * SW.VPP - 6, 2), "why": "x", "entry_reason": "x"}


# ── the brief ────────────────────────────────────────────────────────────────────────────────
def test_v1_and_v2_briefs_are_untouched():
    assert hashlib.sha256(SW.BRIEF.encode()).hexdigest().startswith("b314ac3c6cb7")
    assert hashlib.sha256(SW.BRIEF_V2.encode()).hexdigest().startswith("e24645d2")


def test_brief_for_v3_and_unknown():
    assert SW.brief_for("v3") is SW.BRIEF_V3 and SW.BRIEF_V3 != SW.BRIEF_V2
    with pytest.raises(ValueError):
        SW.brief_for("v9")


@pytest.mark.parametrize("gone", [
    "Do not hold back because the count is getting high",
    "Judge each trade, not the total",
    "The Asia and London grinds are exactly that",
    "the first honest sign is enough",
    "you make the call.",
    "last exit was",
])
def test_v3_brief_drops_the_licence_phrases(gone):
    assert gone not in SW.BRIEF_V3


def test_v3_brief_carries_the_s4_content_and_no_cap_or_stop():
    b = SW.BRIEF_V3
    for need in ["DAY SCORECARD", "THE ENTRY TEST", "WHAT A CLAIM IS", "DAY: ", "BOOK: ", "NOW: ",
                 "a description, not a limit", "12 trades with the major move lost $752", "11 against it lost $1,196",
                 "298 points", "Most looks end with no action", "WAIT"]:
        assert need in b, need
    assert "NOT ALLOWED" not in b and "stop for the day" not in b.lower() and "after two losers" not in b.lower()
    assert "the leg itself has reversed" in b.lower() or "leg itself has reversed" in b
    assert "first 10 minutes" in b


# ── is_claim ────────────────────────────────────────────────────────────────────────────────
def test_is_claim_needs_both_2atr_and_200_dollars():
    bars = _bars()
    base = _trade(bars, 400, 440, pts=40)
    assert base["pnl_usd"] >= 200
    a = SW.atr14([b for b in bars if b[0] <= SW._ep(base["closed"])])
    assert SW.is_claim(base, bars) == (base["points"] >= 2 * a)
    small = dict(base, points=10.0, pnl_usd=74.0)
    assert not SW.is_claim(small, bars)
    cheap = dict(base, pnl_usd=150.0)
    assert not SW.is_claim(cheap, bars)
    red = dict(base, points=-30.0, pnl_usd=-246.0)
    assert not SW.is_claim(red, bars)


# ── day_card: the ledger equals the page ─────────────────────────────────────────────────────
def test_card_matches_the_ledger():
    bars = _bars()
    t1 = _trade(bars, 300, 330, pts=40)
    t2 = _trade(bars, 340, 350, pts=-5.0, peak=3.0); t2["pnl_usd"] = -46.0
    done = [t1, t2]
    upto = bars[:420]
    c = SW.day_card(upto, upto[-1][0], None, done)
    assert c["n_trades"] == 2 and c["winners"] == 1
    assert c["net"] == round(t1["pnl_usd"] + t2["pnl_usd"], 2)
    assert c["last_claimed"] is False
    assert c["last_claim_ts"] == (t1["closed"] if SW.is_claim(t1, bars) else None)


def test_entry_test_first_trade_passes_both_sides():
    bars = _bars()
    c = SW.day_card(bars[:200], bars[199][0], None, [])
    assert c["entry_test"]["ok"]
    assert c["entry_test"]["passes"][0]["sides"] == ["LONG", "SHORT"]


def test_entry_test_blocks_a_second_trade_in_the_same_mil_after_a_non_claim():
    bars = _bars()
    t = _trade(bars, 300, 310, pts=6.0, peak=8.0); t["pnl_usd"] = 42.0
    c = SW.day_card(bars[:330], bars[329][0], None, [t])
    if c["mil_trades"] > 0:
        assert not c["entry_test"]["ok"]
        assert any("not a claim" in f for f in c["entry_test"]["fails"])


def test_entry_test_claim_needs_15_min_and_price_beyond_best():
    bars = _bars(drift=0.5, wobble=0.5)           # steady grind up
    t = _trade(bars, 300, 340, pts=60.0, peak=20.0)       # closed after reaching only +20 of the move
    assert SW.is_claim(t, bars)
    early = SW.day_card(bars[:350], bars[349][0], None, [t])              # 9 min after the close
    assert not early["entry_test"]["ok"] and any("closed only" in f for f in early["entry_test"]["fails"])
    late = SW.day_card(bars[:360], bars[359][0], None, [t])               # 19 min after, price +30 > best +20
    assert late["entry_test"]["ok"]
    assert [p["sides"] for p in late["entry_test"]["passes"]] == [["LONG"]]    # the claimed side only
    assert late["claim_best_px"] == round(t["entry"] + 20.0, 2)
    t_hi = _trade(bars, 300, 340, pts=60.0, peak=62.0)                    # best is beyond where price is now
    notrun = SW.day_card(bars[:360], bars[359][0], None, [t_hi])
    assert not notrun["entry_test"]["ok"] and any("not still running" in f for f in notrun["entry_test"]["fails"])


def test_a_claimed_short_licenses_only_a_short():
    bars = _bars(drift=-0.5, wobble=0.5)
    t = _trade(bars, 300, 340, side="SHORT", pts=60.0, peak=20.0)
    assert SW.is_claim(t, bars)
    c = SW.day_card(bars[:360], bars[359][0], None, [t])
    assert [p["sides"] for p in c["entry_test"]["passes"]] == [["SHORT"]]


def test_from_the_seventh_trade_only_the_claim_test_counts():
    bars = _bars()
    done = []
    for k in range(6):
        t = _trade(bars, 50 + 20 * k, 60 + 20 * k, pts=-4.0, peak=2.0); t["pnl_usd"] = -38.0
        done.append(t)
    c = SW.day_card(bars[:300], bars[299][0], None, done)
    assert c["n_trades"] == 6 and not c["entry_test"]["ok"]


def test_while_holding_there_is_no_entry_test():
    bars = _bars()
    pos = {"dir": 1, "opened": dt.datetime.fromtimestamp(bars[290][0], dt.UTC)}
    c = SW.day_card(bars[:300], bars[299][0], pos, [])
    assert c["entry_test"] is None
    assert "no entry test applies" in "\n".join(SW.card_lines(c, holding=True))


# ── the assembled prompt, through the real run_day ───────────────────────────────────────────
@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(SW, "OUT", str(tmp_path))
    monkeypatch.setattr(SW, "load_day", lambda day: (_bars(day), 0))
    seen = []
    cycle = iter(__import__("itertools").cycle(["ENTER_LONG", "EXIT"]))

    def fake_ask(prompt, timeout=180):
        seen.append(prompt)
        return {"action": next(cycle), "confidence": 0.7, "reason": "DAY: x. BOOK: y. NOW: z."}
    monkeypatch.setattr(SW, "ask", fake_ask)
    return seen


def test_v3_prompt_order_and_content(harness):
    rec = SW.run_day(DAY, "RULES-TEXT-S4", "s4t", resume=False, self_aware=True, line="v3")
    assert rec["line"] == "v3" and rec["peak_def"] == "1m" and rec["page_rev"] == SW.PAGE_REV_V3
    assert harness and all(p.startswith(SW.BRIEF_V3) for p in harness)
    p = harness[-1][len(SW.BRIEF_V3):]            # the page after the brief (the brief itself names the three views)
    i_card, i_day, i_close = p.index("DAY SCORECARD - counted"), p.index("DAY VIEW - the whole"), p.index("CLOSE-IN VIEW - the last")
    assert i_card < i_day < i_close, "scorecard, then day view, then close-in view"
    assert "RULES-TEXT-S4" in p
    assert not any("YOUR BAND IS" in q or "last exit was" in q or "SO FAR:" in q for q in harness)
    assert any("ENTRY TEST:" in q for q in harness)
    assert any("HOW THIS DAY IS JUDGED" in q for q in harness)


def test_v3_calls_log_the_card_and_trades_carry_the_gate_label(harness):
    rec = SW.run_day(DAY, "", "s4g", resume=False, self_aware=True, line="v3")
    assert all("card" in c for c in rec["calls"])
    assert rec["trades"], "stub must trade"
    assert all(t.get("entry_gate") in ("pass", "violating") for t in rec["trades"])
    assert len(rec["trades"]) > 6, "no cap: the harness itself never refuses a seventh entry"


def test_v3_page_matches_the_ledger_at_every_look(harness):
    rec = SW.run_day(DAY, "", "s4l", resume=False, self_aware=True, line="v3")
    n_seen = [int(x.split("closed trade(s)")[0].split("from ")[-1]) for q in harness
              for x in q.splitlines() if "closed trade(s)" in x]
    ns = [c["card"]["n_trades"] for c in rec["calls"]]
    assert n_seen == ns, "the number printed on the page must be the number the ledger held at that look"
    assert max(ns) <= len(rec["trades"])


def test_v1_and_v2_pages_have_no_scorecard(harness):
    SW.run_day(DAY, "", "s4a", resume=False, self_aware=True, line="v2")
    SW.run_day(DAY, "", "s4b", resume=False, self_aware=True, line="v1")
    assert not any("DAY SCORECARD" in q for q in harness)


def test_v3_record_from_an_older_page_rev_is_rerun(harness, monkeypatch):
    SW.run_day(DAY, "", "s4r", resume=True, self_aware=True, line="v3")
    n = len(harness)
    SW.run_day(DAY, "", "s4r", resume=True, self_aware=True, line="v3")
    assert len(harness) == n, "same page_rev must resume"
    monkeypatch.setattr(SW, "PAGE_REV_V3", "v3.0-old")
    SW.run_day(DAY, "", "s4r", resume=True, self_aware=True, line="v3")
    assert len(harness) > n, "a changed page_rev must re-run, not inherit"
