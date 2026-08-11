#!/usr/bin/env python3
"""CLAIM AUDIT — what were Garrath's hands actually worth?

Every MANUAL_CLAIM is the operator overriding the machine: he saw green on the screen and banked it
instead of letting the slot's configured exit run. Until now that was invisible — the claimed P&L just
landed in the ledger as if the desk had earned it, and the only way to find out what the machine would
have done was a Friday archaeology dig. On 2026-07-31 that dig found the week's +$625 was +$1,223 of
hand-claims sitting on top of a machine that lost $598 — a fact worth knowing every week, not once.

This turns it into a standing number. For each MANUAL_CLAIM: reconstruct the entry ATR, replay the
tape forward from the entry on 250ms ticks, and run the slot's OWN exit rule over it to find where the
machine would have got out. Delta = what the hand banked minus what the machine would have banked.
Also reports MFE (the best the trade ever offered) so you can see whether a claim caught the top or
left money behind.

  PYTHONPATH=src ./.venv/bin/python scripts/claim_audit.py [--days N] [--json]

Honest limits, read before quoting:
  * The counterfactual uses the exit config loaded RIGHT NOW (data/exit_overrides.json +
    slot_strategy). It is "would today's machine still need your hands?", NOT "what did the machine
    that was loaded that day do". Exit config has changed repeatedly (07-31, 08-01) and we do not
    keep a config history, so the retrospective version is not computable. Forward-looking, this is
    the number that matters — but do not read old rows as history.
  * Exits fill at the exact level with no slippage, so the MACHINE side is a CEILING; the desk's
    standing finding is live losses run 1.1-3.1x modelled ([[shadow-sim-understates-losses]]). A
    positive delta is therefore CONSERVATIVE — the real machine would have done a bit worse.
  * Fee $1.50/round trip — venue truth, every closed trade carries fees_usd = 1.50. Both sides of the
    comparison pay it, so it cancels in the delta; it is applied anyway so the levels are honest.
  * The hand side is REAL money from the ledger. Only the machine side is modelled.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime

sys.path.insert(0, "/home/alphabot/gazbot7/src")

import duckdb  # noqa: E402

from gazbot7.deciders import (Position, exit_chandelier, exit_chandelier_lock,  # noqa: E402
                              exit_scalp)
from gazbot7.slot_strategy import scaleout_slots  # noqa: E402

GB = "/home/alphabot/gazbot7"
STORE = f"{GB}/data/gazbot7.db"
CAP = f"{GB}/data/capture.db"
OUT = f"{GB}/data/claim_audit.json"
VPP = 2.0            # MNQ $ per point
FEE_RT = 1.50        # venue truth
ATR_N = 14
MAX_HOLD_S = 120 * 60   # the desk's outer cap; the machine must exit by here


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)



# ── THE DAY RIDER IS A DIFFERENT DESK WITH A DIFFERENT COUNTERFACTUAL ────────────────────
# (2026-08-11, operator: "if im claiming profits every time how is that bad?")
# slot_exit_cfg() returns None for gate='day_rider' — it has no scale-out ladder, so pricing
# its claims against the tournament's exit spec is meaningless and they would sit in the
# UNPRICED bucket forever. Its machine exit is its OWN rule, and there are only two ways it
# ever leaves a trade on its own:
#   1. the ARMED TRAIL — arm once ARM_ATR_MULT x ATR ahead of entry, then trail
#      TRAIL_ATR_MULT x ATR off the running peak (ATR frozen at entry);
#   2. the 20:40Z HARD FLAT, which is where it ends up whenever the trail never arms.
# The 600pt venue stop is last-resort insurance, modelled for completeness.
#
# ★ WHY THIS IS THE RIGHT QUESTION. The battery found holding to the flat beat 25 exit
# variants, and the ONE thing that beat holding was the armed trail. So "what the machine
# would have done" IS trail-or-clock — and a hand-claim is only good if it beats that.
DR_ARM_ATR_MULT = 4.0        # day_rider.ARM_ATR_MULT
DR_TRAIL_ATR_MULT = 2.0      # day_rider.TRAIL_ATR_MULT
DR_FLAT_UTC_MIN = 20 * 60 + 40
DR_VENUE_STOP_PT = 600.0
DR_FEE_RT = 1.5


def dr_entry_atr(con, ts_ms: int) -> float | None:
    """The rider's OWN ATR: 14 one-minute true ranges (drift.py:128). Deliberately NOT
    claim_audit's entry_atr() — that is ATR-14 built for the tournament's stop distances, and
    scoring a desk against a volatility unit it does not use would be a different instrument
    answering a different question."""
    t_s = ts_ms // 1000
    rows = con.execute(f"""
        SELECT CAST(bar_ts / 60 AS BIGINT) m, MAX(high) h, MIN(low) l, ARG_MAX(close, bar_ts) c
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
          AND bar_ts < {t_s} AND bar_ts >= {t_s - 60 * 60}
        GROUP BY 1 ORDER BY 1""").fetchall()
    if len(rows) < 3:
        return None
    trs = [max(rows[i][1] - rows[i][2], abs(rows[i][1] - rows[i - 1][3]),
               abs(rows[i][2] - rows[i - 1][3])) for i in range(1, len(rows))]
    return (sum(trs[-14:]) / min(14, len(trs))) if trs else None


def day_rider_hold(con, entry: float, d: int, qty: float, t0_ms: int, atr: float):
    """Simulate the rider's own exit from entry. Returns (pnl_usd, exit_px, reason, armed).

    Priced on TICKS, and the trail is raced tick-by-tick against the clock — a trail level and
    a 20:40 flatten are not interchangeable and whichever comes FIRST is the one that happened.
    """
    t0 = t0_ms // 1000
    day = datetime.fromtimestamp(t0, UTC).date()
    flat_s = int(datetime(day.year, day.month, day.day,
                          DR_FLAT_UTC_MIN // 60, DR_FLAT_UTC_MIN % 60, tzinfo=UTC).timestamp())
    ticks = con.execute(f"""
        SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
          AND ts_ms >= {t0_ms} AND ts_ms <= {flat_s * 1000} ORDER BY ts_ms""").fetchall()
    if not ticks:
        return None
    arm_at = DR_ARM_ATR_MULT * atr
    trail_by = DR_TRAIL_ATR_MULT * atr
    stop_px = entry - d * DR_VENUE_STOP_PT
    peak = entry
    armed = False
    for ts, px in ticks:
        if d * (px - entry) > d * (peak - entry):
            peak = px
        if not armed and d * (peak - entry) >= arm_at:
            armed = True
        if armed:
            tl = peak - d * trail_by
            if (px <= tl) if d > 0 else (px >= tl):
                return (round(d * (tl - entry) * VPP * qty - DR_FEE_RT * qty, 2), tl,
                        "TRAIL", True)
        if (px <= stop_px) if d > 0 else (px >= stop_px):
            return (round(d * (stop_px - entry) * VPP * qty - DR_FEE_RT * qty, 2), stop_px,
                    "VENUE_STOP", armed)
    px = ticks[-1][1]
    # ⚠ PROVISIONAL IF THE DAY IS NOT OVER. Run before 20:40Z the tick stream simply ends at
    # "now", so this is not the clock flat — it is the price this minute, and the remaining
    # hours can move it a long way. The nightly audit runs at 21:30Z and is therefore always
    # complete; an intraday run is not, and must not be read as a verdict. Observed the first
    # time this was ever run: 17:22Z, with 3h18m still to go.
    incomplete = (ticks[-1][0] // 1000) < flat_s - 120
    return (round(d * (px - entry) * VPP * qty - DR_FEE_RT * qty, 2), px,
            "OPEN-SO-FAR" if incomplete else "CLOCK_FLAT", armed)


def entry_atr(con, ts_ms: int) -> float | None:
    """ATR-14 on 1-MINUTE bars as of the entry. The desk does not persist entry_atr on the trade
    ([[position-orphan-entry-atr-cascade]]), so it is reconstructed. The grind sweep measured this
    reconstruction against the ATR implied by real stop distances and found it within 1.6%.

    NOTE capture.db only stores 5s bars, and `bar_ts` is in SECONDS (not ms) — so fold 5s into
    minutes here rather than assuming a 1m timeframe exists."""
    t_s = ts_ms // 1000
    rows = con.execute(f"""
        SELECT CAST(bar_ts / 60 AS BIGINT) m, MAX(high) h, MIN(low) l,
               ARG_MAX(close, bar_ts) c
        FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts < {t_s} AND bar_ts >= {t_s - 60 * 60}
        GROUP BY 1 ORDER BY 1 DESC LIMIT {ATR_N + 1}""").fetchall()
    if len(rows) < ATR_N + 1:
        return None
    rows = rows[::-1]
    trs = []
    for i in range(1, len(rows)):
        _, h, lo, _ = rows[i]
        pc = rows[i - 1][3]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return sum(trs) / len(trs) if trs else None


def slot_exit_cfg(tag: str):
    """The live exit rule for this exact sub-slot tag, read from the running slate (so it picks up
    exit_overrides.json). Returns the SlotSpec or None if the tag is no longer on the roster."""
    for s in scaleout_slots():
        if s.tag == tag:
            return s
    return None


def hand_mfe(con, side: str, entry_px: float, t0_ms: int, t1_ms: int) -> float | None:
    """Best favourable excursion in POINTS over the HAND's actual holding period.
    Deliberately independent of the machine replay: the machine may stop out early, and measuring MFE
    only up to that point understates what the trade offered (it produced impossible >100% 'kept'
    figures in the first cut). This is the denominator for 'how close to the top did the claim land'."""
    row = con.execute(f"""
        SELECT {'MAX(price)' if side == 'LONG' else 'MIN(price)'} FROM c.ticks
        WHERE symbol='MNQ' AND ts_ms >= {t0_ms} AND ts_ms <= {t1_ms}""").fetchone()
    if not row or row[0] is None:
        return None
    return (row[0] - entry_px) if side == "LONG" else (entry_px - row[0])


def machine_exit(con, spec, side: str, entry_px: float, atr: float, t0_ms: int):
    """Replay the tape forward from the entry and run the slot's OWN exit rule tick by tick.
    Returns (exit_price, reason, seconds_held, mfe_points). Uses the desk's exit functions directly
    rather than reimplementing them — the same discipline repricer.py follows."""
    ticks = con.execute(f"""
        SELECT ts_ms, price FROM c.ticks
        WHERE symbol='MNQ' AND ts_ms >= {t0_ms} AND ts_ms <= {t0_ms + MAX_HOLD_S * 1000}
        ORDER BY ts_ms""").fetchall()
    if not ticks:
        return None, "no_ticks", None, None

    pos = Position(side=side, entry_price=entry_px, entry_atr=atr)
    stop_mult = spec.stop_atr_mult or 1.0
    mfe = 0.0
    for ts, px in ticks:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        mfe = max(mfe, fav)

        # native 1-ATR protective stop, checked first — the desk's stop is server-side and
        # the tape-primary guard flattens AT the level, so a breach ends the trade here.
        adverse = (entry_px - px) if side == "LONG" else (px - entry_px)
        if adverse >= stop_mult * atr:
            return entry_px - stop_mult * atr * (1 if side == "LONG" else -1), "STOP", (ts - t0_ms) / 1000, mfe

        if spec.exit == "scalp":
            r = exit_scalp(pos, px, target_r=spec.target_r, stop_atr_mult=stop_mult)
        elif spec.exit == "chandelier_lock":
            r = exit_chandelier_lock(pos, px, start_k=spec.chandelier_start_k,
                                     lock_r=spec.lock_r, lock_k=spec.lock_k)
        else:
            r = exit_chandelier(pos, px, start_k=spec.chandelier_start_k,
                                min_k=spec.chandelier_min_k, tighten=spec.chandelier_tighten)
        if r:
            return px, r, (ts - t0_ms) / 1000, mfe

    ts, px = ticks[-1]
    return px, "MAX_HOLD", (ts - t0_ms) / 1000, mfe


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="only claims from the last N days (0 = all)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of the table")
    a = ap.parse_args()

    sq = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    sq.row_factory = sqlite3.Row
    where = "exit_reason='MANUAL_CLAIM'"
    if a.days:
        where += f" AND closed_at >= datetime('now','-{a.days} days')"
    claims = list(sq.execute(f"SELECT * FROM trades WHERE {where} ORDER BY opened_at"))

    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (READ_ONLY)")

    rows, tot_hand, tot_mach, unpriced = [], 0.0, 0.0, 0
    for t in claims:
        tag = t["gate"]
        t0 = _ms(t["opened_at"])

        # ── DAY RIDER: priced against ITS OWN machine exit, not the tournament ladder ──
        if str(tag or "").startswith("day_rider"):
            d = 1 if t["side"] == "LONG" else -1
            dr_atr = dr_entry_atr(con, t0)
            res = day_rider_hold(con, float(t["entry_price"]), d, float(t["qty"]),
                                 t0, dr_atr) if dr_atr else None
            if res is None:
                unpriced += 1
                rows.append(dict(id=t["id"], gate=tag, opened=t["opened_at"],
                                 hand=t["pnl_usd"], machine=None, delta=None,
                                 note="no tick/ATR history for the rider hold"))
                continue
            mach, mpx, mreason, armed = res
            hand = float(t["pnl_usd"])
            tot_hand += hand
            tot_mach += mach
            mfe = hand_mfe(con, t["side"], t["entry_price"], t0, _ms(t["closed_at"]))
            mfe_usd = (mfe or 0) * VPP * float(t["qty"])
            rows.append(dict(
                id=t["id"], gate=tag, side=t["side"], opened=t["opened_at"],
                hand=round(hand, 2), machine=round(mach, 2), delta=round(hand - mach, 2),
                machine_exit=f"{mreason}{'*' if armed else ''}",
                machine_held_s=None,
                hand_held_s=round((_ms(t["closed_at"]) - t0) / 1000),
                mfe_pt=round(mfe or 0, 2), mfe_usd=round(mfe_usd, 2),
                captured_pct=round(100 * hand / mfe_usd, 1) if mfe_usd else None,
                entry_atr=round(dr_atr, 2),
                # The trail-armed flag matters more than it looks: if the trail NEVER armed,
                # the rider's machine exit was simply the 20:40 clock, and the comparison is
                # "your hand vs the close" — not "your hand vs the trail".
                note=f"rider hold -> {mreason} @ {mpx:.1f}"
                     f"{' (trail ARMED)' if armed else ' (trail never armed)'}"
                     + (" ⚠PROVISIONAL: the 20:40Z flat has not happened yet"
                        if mreason == "OPEN-SO-FAR" else "")))
            continue

        spec = slot_exit_cfg(tag)
        atr = entry_atr(con, t0)
        if spec is None or atr is None:
            unpriced += 1
            rows.append(dict(id=t["id"], gate=tag, opened=t["opened_at"], hand=t["pnl_usd"],
                             machine=None, delta=None,
                             note="tag off roster" if spec is None else "no ATR history"))
            continue

        px, reason, held, _ = machine_exit(con, spec, t["side"], t["entry_price"], atr, t0)
        mfe = hand_mfe(con, t["side"], t["entry_price"], t0, _ms(t["closed_at"]))
        if px is None:
            unpriced += 1
            rows.append(dict(id=t["id"], gate=tag, opened=t["opened_at"], hand=t["pnl_usd"],
                             machine=None, delta=None, note=reason))
            continue

        d = 1 if t["side"] == "LONG" else -1
        mach = (px - t["entry_price"]) * d * VPP * t["qty"] - FEE_RT
        hand = float(t["pnl_usd"])
        tot_hand += hand
        tot_mach += mach
        rows.append(dict(
            id=t["id"], gate=tag, side=t["side"], opened=t["opened_at"],
            hand=round(hand, 2), machine=round(mach, 2), delta=round(hand - mach, 2),
            machine_exit=reason, machine_held_s=round(held or 0),
            hand_held_s=round((_ms(t["closed_at"]) - t0) / 1000),
            mfe_pt=round(mfe or 0, 2), mfe_usd=round((mfe or 0) * VPP * t["qty"], 2),
            captured_pct=round(100 * hand / ((mfe or 0) * VPP * t["qty"]), 1) if mfe else None,
            entry_atr=round(atr, 2), note=""))

    summary = dict(
        generated=datetime.now(UTC).isoformat(timespec="seconds"),
        n_claims=len(claims), n_priced=len(claims) - unpriced, n_unpriced=unpriced,
        hand_total=round(tot_hand, 2), machine_total=round(tot_mach, 2),
        delta_total=round(tot_hand - tot_mach, 2),
        delta_per_claim=round((tot_hand - tot_mach) / max(1, len(claims) - unpriced), 2),
        basis="machine side = exit config loaded NOW, exact-level fills, no slippage (a CEILING); "
              "fee $1.50/RT both sides; hand side is real ledger money",
    )
    json.dump(dict(summary=summary, claims=rows), open(OUT, "w"), indent=2)

    if a.json:
        print(json.dumps(dict(summary=summary, claims=rows), indent=2))
        return 0

    print(f"\nCLAIM AUDIT — {summary['n_claims']} manual claims "
          f"({summary['n_priced']} priced, {summary['n_unpriced']} not)\n")
    print(f"{'id':>4} {'gate':<20}{'opened (UTC)':<21}{'hand':>8}{'machine':>9}{'delta':>8}"
          f"  {'mexit':<12}{'MFE$':>8}{'kept%':>7}")
    for r in rows:
        if r.get("machine") is None:
            print(f"{r['id']:>4} {r['gate']:<20}{r['opened'][:19]:<21}{r['hand']:>8.2f}"
                  f"{'—':>9}{'—':>8}  {r['note']}")
            continue
        print(f"{r['id']:>4} {r['gate']:<20}{r['opened'][:19]:<21}{r['hand']:>8.2f}"
              f"{r['machine']:>9.2f}{r['delta']:>8.2f}  {r['machine_exit']:<12}"
              f"{r['mfe_usd']:>8.0f}{(r['captured_pct'] if r['captured_pct'] is not None else 0):>7.0f}")
    print("\n" + "-" * 96)
    print(f"  HAND banked      ${summary['hand_total']:>10,.2f}")
    print(f"  MACHINE would    ${summary['machine_total']:>10,.2f}   (ceiling — no slippage)")
    print(f"  ★ HANDS WORTH    ${summary['delta_total']:>10,.2f}   "
          f"(${summary['delta_per_claim']:,.2f} per claim)")
    print("-" * 96)
    print(f"  written to {OUT}")
    print("  basis:", summary["basis"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
