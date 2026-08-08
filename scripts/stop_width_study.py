#!/usr/bin/env python3
"""IS A 1x ATR STOP TOO TIGHT FOR THE MOMENTUM GATES? — 1.0 vs 1.5 vs 2.0, on the desk's OWN entries.

Operator, 2026-08-04: "is atr 1 too tight for the momentum gates, if it was 1.5 or 2 would it let the
runs survive? the last one looks like it would. i know not all. do a quick analysis on last week and
this week."

★ WHY THIS ANCHORS TO LIVE TRADES INSTEAD OF RE-DERIVING ENTRIES.
Every entry here is one the desk actually took, at the price it actually paid. That removes the whole
class of error where a reconstructed signal set drifts from what the gate really saw (the NIPC replay
diverged from live partly on exactly that). The question is only about the EXIT, so the entries should
be given, not modelled.

★ WHERE THE ATR COMES FROM — VENUE TRUTH, NOT A REBUILD.
`trades` does not persist entry_atr. But every one of these slots runs stop_atr_mult = 1.00, so for a
trade that exited STOP the realised distance |entry - exit| IS one ATR, as the venue filled it. That is
measured, not reconstructed. STOP_UNFILLED rows are EXCLUDED from this inference: those stops never
triggered (the ContFuture stop bug), so their exit distance is not a stop distance and treating it as
one would silently corrupt every ATR in the sample.

★ ONLY STOPPED TRADES CAN CHANGE, AND THAT IS A PROOF, NOT AN ASSUMPTION.
A trade that exited TARGET or CHANDELIER never touched its stop. Moving the stop FURTHER AWAY cannot
alter a path that never reached the nearer stop, so those outcomes are invariant and are carried at
their real P&L. Widening only ever changes the trades that stopped. This is what keeps the comparison
honest: the wider stop is charged its bigger loss on every trade that still stops.

★ THE RACE, NOT THE PEAK. Each replay walks 250ms ticks in order and takes whichever of stop/target is
touched FIRST. Asking "did it later reach N R" instead would inflate the answer, which is the single
most repeated error on this desk (it turned a 29% win rate into 78% and shipped a losing config live).

Exit rules mirror scaleout_slots() exactly, including the quiet-tape clip: ATR < atr_split -> Lot A
takes $40 and Lot B takes 1.75R floored at $60; ATR >= atr_split -> the slot's own target_r, and
grind_long_B uses the real chandelier. Fee $1.50/RT, $2.00/pt.

  PYTHONPATH=src .venv/bin/python scripts/stop_width_study.py
"""
from __future__ import annotations

import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.deciders import Bar, Position, _atr, exit_chandelier_lock  # noqa: E402
from gazbot7.slot_strategy import scaleout_slots  # noqa: E402

GB = "/home/alphabot/gazbot7"
VPP, FEE_RT = 2.0, 1.50
KS = [1.0, 1.5, 2.0]
MOMENTUM = ("grind_long", "abs_veto_long", "abs_veto_short")
# ★ THE WINDOW IS BOUNDED BY A CONFIG EPOCH, NOT BY THE OPERATOR'S "last week and this week".
# Asked for Jul 27 onward, my first run applied TODAY's exit spec to every trade in it and produced a
# +$2,477 case for widening. That number was an artefact. `data/exit_overrides.json` — the quiet-tape
# clip — was written 2026-08-02 16:24:34 and took effect at the tournament restart 60s later, so trades
# before then ran WIDE R-targets with no clip. Scoring them against today's tight $40/1.75R target lets
# the modelled trade win races the real one could never enter, and it flatters every k at once. A stop
# study is only meaningful against the exit ladder that stop actually shared.
# Cost of honesty: n collapses. Better a small honest sample than a large invalid one.
# ── THE EPOCHS ────────────────────────────────────────────────────────────────────────────────────
# Each entry is a window over which the MOMENTUM exit ladder did not change, paired with the spec that
# was actually live in it. Verified by `git log -- slot_strategy.py data/exit_overrides.json` plus the
# tournament restart log (config only takes effect on restart).
#
# ⚠ EPOCHS THAT CANNOT BE RUN, AND WHY — recorded so nobody retries them thinking it was an oversight:
#   Jul 27 → Jul 29 16:18   single-slot slate; no _A/_B sub-slots existed, so today's two-lot ladder has
#                           no counterpart. A different desk, not a different stop width.
#   Jul 31 12:51 → Aug 2    `data/exit_overrides.json` drives the exits here and it is NOT git-tracked.
#                           Only two ad-hoc snapshots survive (.pre-nipc, .pre-0801-TRUE) and neither is
#                           timestamped to a deploy, so the live ladder for that window is UNRECOVERABLE.
#                           Not merely hard — the information does not exist. (Fix forward: track it.)
EPOCHS = {
    # ★ THE USABLE PRE-CLIP SAMPLE. Dual-slot live, overrides feature not yet shipped, so every gate ran
    # its BASE spec straight out of slot_strategy.py at 06bdd75 — fully in git. The only exit change
    # inside the window touches exhaustion_short, which is not a momentum gate (diff-verified).
    "B": dict(start="2026-07-29 16:18", end="2026-07-31 12:51",
              label="pre-clip: dual-slot, NO overrides (git 06bdd75)"),
    # The current ladder: quiet-tape clip live. exit_overrides.json written 08-02 16:24:34, loaded at the
    # tournament restart 08-02 16:25:35.
    "E": dict(start="2026-08-02 16:25:35", end="2026-12-31",
              label="current: quiet-tape clip live"),
}


def epoch_b_spec(tag: str):
    """Momentum slot specs as they stood in epoch B, transcribed from `git show 06bdd75`.

    All three momentum gates sit in `_BIG_RUN`, so the scale-out splitter gave every one of them the
    same shape: Lot A a fixed 2.5R scalp, Lot B the loose-then-lock chandelier, both on the 1-ATR native
    stop, give-back off. No atr_split and no `lo` block — the quiet-tape clip did not exist yet, which is
    the single most important difference from today and the whole reason this run is separate."""
    from dataclasses import replace as _replace
    cur = {s.tag: s for s in scaleout_slots()}
    base = cur.get(tag)
    if base is None:
        return None
    common = dict(stop_atr_mult=1.0, giveback_enabled=False, adaptive_exit=False,
                  atr_split=0.0, lo_target_usd=0.0, lo_target_r=0.0, lo_floor_usd=0.0)
    if tag.endswith("_A"):
        return _replace(base, exit="scalp", target_r=2.5, **common)
    return _replace(base, exit="chandelier_lock", chandelier_start_k=3.5, lock_r=6.0, lock_k=0.5,
                    **common)
CAP_MIN = 120                      # backstop hold cap; also hard-stopped at the 21:00 UTC flatten
FLATTEN_UTC_H = 21


def load_minute_bars(con, t_from_ms: int) -> list[Bar]:
    """1-minute bars folded from the 5s capture — the shape MinuteBars feeds the gate.
    ★ bar_ts is in SECONDS in this table (verified, not assumed), and Bar.ts must also be seconds
    because _atr's halt-aware guard compares `bars[i].ts - bars[i-1].ts` against 90."""
    rows = con.execute(f"""SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) h, min(low) l,
               arg_max(close, bar_ts) c, sum(volume) v
        FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= {t_from_ms // 1000 - 7200}
        GROUP BY 1 ORDER BY 1""").fetchall()
    return [Bar(ts=int(m), open=float(c), high=float(h), low=float(l), close=float(c),
                volume=float(v or 0)) for m, h, l, c, v in rows]


def atr_at(bars: list[Bar], t0_ms: int, n: int = 20) -> float:
    """ATR-14 as the gate would have read it: on bars CLOSED STRICTLY BEFORE the entry.
    Using the entry minute itself would leak the entry bar's own range into the stop that bar's
    signal produced.

    Returns 0.0 (=> the trade is SKIPPED) when the window spans a session break. Why: two trades in
    epoch B recomputed to ATR 42.8 while the live desk plainly used ~21.5 — my folded minute bars
    reproduce the PRE-FIX cross-halt ATR bug (the 08-03 halt-aware fix exists precisely because a
    reopen gap enters true range as one enormous bar). Those 2 trades of 57 carried $388 of the $520
    model error on their own. A reconstruction that silently re-creates a bug the live desk had already
    fixed is not a counterfactual, so it is excluded and counted rather than averaged in."""
    t0_s = t0_ms // 1000
    hist = [b for b in bars if b.ts + 60 <= t0_s]
    if len(hist) < 15:
        return 0.0
    w = hist[-n:]
    if any(w[i].ts - w[i - 1].ts > 300 for i in range(1, len(w))):   # >5min hole = session break
        return 0.0
    return _atr(w)


def target_pt(spec, atr: float, qty: float) -> float | None:
    """The slot's own profit target in POINTS, quiet-tape clip included. None => chandelier-managed."""
    if spec.atr_split and atr < spec.atr_split:
        if spec.lo_target_usd:
            return spec.lo_target_usd / (VPP * qty)
        if spec.lo_target_r:
            t = spec.lo_target_r * atr
            if spec.lo_floor_usd:
                t = max(t, spec.lo_floor_usd / (VPP * qty))
            return t
    if spec.exit == "chandelier_lock":
        return None
    return spec.target_r * atr


def replay(con, side, entry, atr, t0_ms, spec, qty, k, slip_pt=0.0):
    """First touch of stop(k*atr) vs the slot's target, on real 250ms ticks. Returns (pnl, why, mins)."""
    eod = int(dt.datetime.fromtimestamp(t0_ms / 1000, dt.UTC)
              .replace(hour=FLATTEN_UTC_H, minute=0, second=0, microsecond=0).timestamp() * 1000)
    end = min(t0_ms + CAP_MIN * 60_000, eod if eod > t0_ms else t0_ms + CAP_MIN * 60_000)
    rows = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
                           AND ts_ms > {t0_ms} AND ts_ms <= {end} ORDER BY ts_ms""").fetchall()
    if not rows:
        return None
    stp = k * atr
    tgt = target_pt(spec, atr, qty)
    peak = 0.0
    for ts, px in rows:
        fav = (px - entry) if side == "LONG" else (entry - px)
        if -fav >= stp:            # stop first — charged the measured slippage past the trigger
            return (-(stp + slip_pt) * VPP * qty - FEE_RT, "STOP", (ts - t0_ms) / 60000)
        if fav > peak:
            peak = fav
        if tgt is not None:
            if fav >= tgt:
                return (tgt * VPP * qty - FEE_RT, "TARGET", (ts - t0_ms) / 60000)
        else:
            # grind_long_B is exit='chandelier_lock' — the loose-THEN-LOCK chandelier, NOT the
            # tightening exit_chandelier. Using the wrong one would model a different desk: this one
            # stays wide until lock_r then clamps, which is precisely the "let the run breathe"
            # behaviour under test. Parameters come off the spec, not from defaults.
            if exit_chandelier_lock(Position(side, entry, atr, peak), px,
                                    start_k=spec.chandelier_start_k, lock_r=spec.lock_r,
                                    lock_k=spec.lock_k):
                return (fav * VPP * qty - FEE_RT, "CHANDELIER", (ts - t0_ms) / 60000)
    ts, px = rows[-1]
    fav = (px - entry) if side == "LONG" else (entry - px)
    return (fav * VPP * qty - FEE_RT, "CAP/EOD", (ts - t0_ms) / 60000)


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "E"
    ep = EPOCHS[which]
    WIN_START, WIN_END = ep["start"], ep["end"]
    if which == "B":
        spec = {t: epoch_b_spec(t) for t in
                (f"{g}_{s}" for g in MOMENTUM for s in ("A", "B"))}
        spec = {k: v for k, v in spec.items() if v is not None}
    else:
        spec = {s.tag: s for s in scaleout_slots()}
    print(f"EPOCH {which} — {ep['label']}  [{WIN_START} → {WIN_END}]")
    a_ex = next(v for k, v in spec.items() if k.endswith('_A'))
    b_ex = next(v for k, v in spec.items() if k.endswith('_B'))
    print(f"  ladder: LotA exit={a_ex.exit} target_r={a_ex.target_r} | "
          f"LotB exit={b_ex.exit} | clip atr_split={a_ex.atr_split or 'none'}")
    con = duckdb.connect()
    con.execute(f"ATTACH '{GB}/data/capture.db' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{GB}/data/gazbot7.db' AS g (TYPE sqlite, READ_ONLY)")

    rows = con.execute(f"""SELECT gate, side, qty, entry_price, exit_price, exit_reason, pnl_usd,
               epoch(opened_at::TIMESTAMPTZ)*1000 AS t0
        FROM g.trades WHERE symbol='MNQ' AND opened_at >= '{WIN_START}' AND opened_at < '{WIN_END}'
          AND ({' OR '.join(f"gate LIKE '{g}%'" for g in MOMENTUM)})
        ORDER BY opened_at""").fetchall()

    stopped = [r for r in rows if r[5] == "STOP" and r[0] in spec]
    other = [r for r in rows if r[5] != "STOP" or r[0] not in spec]
    d0 = dt.datetime.fromtimestamp(min(r[7] for r in rows) / 1000, dt.UTC)
    d1 = dt.datetime.fromtimestamp(max(r[7] for r in rows) / 1000, dt.UTC)
    print(f"MOMENTUM gates, {d0:%b %d} -> {d1:%b %d} ({len(rows)} trades: {len(stopped)} STOPPED "
          f"(re-raceable) + {len(other)} not)")
    print(f"exits mirror scaleout_slots incl. quiet-clip | fee ${FEE_RT:.2f}/RT | ${VPP}/pt | "
          f"first-touch race on 250ms ticks | hold cap {CAP_MIN}min or {FLATTEN_UTC_H}:00 UTC\n")

    invariant = sum(r[6] for r in other)
    # ★ ATR IS RECOMPUTED, NOT INFERRED FROM THE FILL. My first pass set atr = |entry - exit| on the
    # reasoning that stop_atr_mult is 1.00, so the realised distance IS one ATR. That is wrong, and the
    # k=1.0 column caught it: a STOP fill SLIPS past the trigger (this desk has a documented ~$1,200
    # stop-slippage leak), so |entry - exit| OVERSTATES the ATR. Every modelled stop came out wider than
    # the real one, k=1.0 scored $1,377 better than the live book it was supposed to reproduce, and
    # inflated ATRs also pushed trades over the atr_split=22 quiet-clip boundary onto the wrong target.
    # So ATR is rebuilt with the desk's own halt-aware _atr on its own captured bars, and the k=1.0
    # column is kept as a live-reproduction CHECK: if it does not land near the live book, nothing here
    # is trustworthy and the run says so instead of reporting a number.
    bars = load_minute_bars(con, min(int(r[7]) for r in rows))
    print(f"minute bars for ATR: {len(bars)}")

    # ── STOP SLIPPAGE, MEASURED PER TRADE (not back-solved from the aggregate) ──────────────────────
    # The model exits EXACTLY at the stop price. Real stops fill PAST it, which is why the k=1.0 column
    # kept scoring better than the live book it is supposed to reproduce. For every live STOP the excess
    # over one recomputed ATR is the realised slippage, so it can be measured directly rather than
    # fudged. It is charged per STOP EVENT, which matters for the comparison: a wider stop produces
    # FEWER stops, so it pays this tax fewer times — a real effect the exact-fill model was hiding.
    slips = []
    for gate, side, qty, entry, exitp, _, pnl, t0 in stopped:
        a = atr_at(bars, int(t0))
        if a > 0:
            slips.append(abs(entry - exitp) - a)
    slips.sort()
    slip_pt = slips[len(slips) // 2] if slips else 0.0        # median: robust to the odd gap-through
    print(f"stop slippage measured on {len(slips)} live stops: median {slip_pt:+.2f}pt "
          f"(= ${slip_pt * VPP:.2f}/stop), mean {sum(slips)/max(len(slips),1):+.2f}pt\n")
    per_gate: dict = {}
    detail: list = []
    skipped = 0
    for gate, side, qty, entry, exitp, _, pnl, t0 in stopped:
        atr = atr_at(bars, int(t0))
        if atr <= 0:
            skipped += 1
            continue
        res = {}
        for k in KS:
            r = replay(con, side, entry, atr, int(t0), spec[gate], qty, k, slip_pt)
            if r is None:
                res = {}
                break
            res[k] = r
        if not res:
            continue
        g = per_gate.setdefault(gate, {k: 0.0 for k in KS} | {"n": 0, "live": 0.0, "atr": []})
        g["n"] += 1
        g["live"] += pnl
        g["atr"].append(atr)
        for k in KS:
            g[k] += res[k][0]
        detail.append((gate, dt.datetime.fromtimestamp(t0 / 1000, dt.UTC), atr, pnl, res))

    print(f"{'gate':<18}{'n':>4}{'ATRavg':>8}{'LIVE(1x)':>11}{'k=1.0':>10}{'k=1.5':>10}{'k=2.0':>10}"
          f"{'best':>7}")
    tot = {k: 0.0 for k in KS}
    tlive = 0.0
    for gate in sorted(per_gate):
        g = per_gate[gate]
        best = max(KS, key=lambda k: g[k])
        print(f"{gate:<18}{g['n']:>4}{sum(g['atr'])/len(g['atr']):>8.1f}{g['live']:>11.0f}"
              f"{g[1.0]:>10.0f}{g[1.5]:>10.0f}{g[2.0]:>10.0f}{best:>7.1f}")
        for k in KS:
            tot[k] += g[k]
        tlive += g["live"]
    print("-" * 78)
    print(f"{'STOPPED subtotal':<18}{sum(g['n'] for g in per_gate.values()):>4}{'':>8}{tlive:>11.0f}"
          f"{tot[1.0]:>10.0f}{tot[1.5]:>10.0f}{tot[2.0]:>10.0f}")
    print(f"{'+ invariant (never touched stop)':<40}{invariant:>+10.0f}  ({len(other)} trades, "
          f"identical under every k)")
    print("-" * 78)
    for k in KS:
        print(f"  BOOK TOTAL at k={k}: ${tot[k] + invariant:>+9.0f}"
              + ("   <- live config" if k == 1.0 else f"   ({tot[k] - tot[1.0]:+.0f} vs live)"))

    # ── THE VALIDATION GATE. k=1.0 IS the live config, so it must reproduce the live book. ──
    err = tot[1.0] - tlive
    rel = abs(err) / max(abs(tlive), 1) * 100
    print(f"\nMODEL CHECK  k=1.0 modelled ${tot[1.0]:+.0f} vs LIVE ${tlive:+.0f}  "
          f"=> error ${err:+.0f} ({rel:.0f}%)")
    if rel > 15:
        print("  ⚠ MODEL DOES NOT REPRODUCE LIVE. The k=1.5/2.0 numbers above are NOT trustworthy.")
        print("    Most likely residual: STOP-fill slippage (modelled exits fill exactly at the stop,")
        print("    real ones fill past it), so every k here is optimistic by roughly that amount.")
    else:
        print("  ✓ within 15% — the widening comparison rests on a model that can reproduce the live book.")
    if skipped:
        print(f"  ({skipped} trades skipped: fewer than 15 prior minute bars for a halt-aware ATR)")

    print("\nHOW THE STOPPED TRADES RE-RACE (does widening rescue them?)")
    for k in KS[1:]:
        rescued = sum(1 for *_, res in detail if res[k][1] != "STOP")
        worse = sum(1 for *_, res in detail if res[k][1] == "STOP")
        print(f"  k={k}: {rescued}/{len(detail)} no longer stop out; {worse} still stop "
              f"(and now lose {k / 1.0:.1f}x as much)")

    print("\nTHE OPERATOR'S 'LAST ONE' — most recent 8 stopped momentum trades:")
    print(f"  {'gate':<18}{'when':<13}{'ATR':>6}{'live':>8}   k=1.0        k=1.5        k=2.0")
    for gate, when, atr, pnl, res in detail[-8:]:
        cells = "  ".join(f"{res[k][1][:4]:<5}{res[k][0]:>+7.0f}" for k in KS)
        print(f"  {gate:<18}{when:%m-%d %H:%M}{atr:>7.1f}{pnl:>8.0f}   {cells}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
