#!/usr/bin/env python3
"""EXIT-SELECTOR SWEEP — thorough (operator 2026-07-27): sweep chandelier WIDTH, find where each
exit works per GATE x REGIME, and build a 3-way per-gate selector (scalp / tight-chand / wide-chand).

For every realised entry (07-20..27), reprice tick-honest under a whole battery of exits in ONE
tick-walk: scalp-2R + chandelier at start_k {1.5,2,2.5,3,3.5,4.5} (tight→wide) + the deployed
lock-chandelier. Tag regime@entry (live direction_router) as ALIGNED-TREND / COUNTER-TREND / CHOP.
Then:
  (1) WIDTH CURVE — each fixed exit's total (find the tight & wide sweet spots)
  (2) REGIME x EXIT — where each exit works (aligned-trend vs chop vs counter)
  (3) GATE x REGIME → best exit (the selector map) + n per cell (thin-cell honesty)
  (4) ADAPTIVE-3 selector (per gate+regime pick best of scalp/tight/wide) vs best fixed single exit,
      with LEAVE-ONE-DAY-OUT robustness (does the edge survive dropping any day, or is it one day?).

Fees $1.50/RT, $2/pt. ⚠ one week, ONE real trend day (today) → illustrative; picking best-per-cell on
the same data OVERFITS — the LODO check + cell sizes are the honesty guard. Ranking > absolute $.

  PYTHONPATH=src .venv/bin/python scripts/exit_selector_sweep.py
"""
from __future__ import annotations

import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import Position, exit_chandelier, exit_chandelier_lock, exit_scalp  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 90 * 60

# the exit battery — scalp + chandelier tight→wide + the deployed lock
KS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.5]
EXIT_NAMES = ["scalp2R"] + [f"k{k}" for k in KS] + ["lock"]


def exit_fires(name, pos, px):
    if name == "scalp2R":
        return exit_scalp(pos, px, target_r=2.0, stop_atr_mult=1.0)
    if name == "lock":
        return (exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
                or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))
    k = float(name[1:])
    return (exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75)
            or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))


def reprice_all(side, entry_px, atr, ticks):
    """One tick-walk → {exit_name: exit_px} for the whole battery."""
    peak = 0.0
    done: dict = {}
    for _ts, px in ticks:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak:
            peak = fav
        pos = Position(side, entry_px, atr, peak)
        for name in EXIT_NAMES:
            if name not in done and exit_fires(name, pos, px):
                done[name] = px
        if len(done) == len(EXIT_NAMES):
            break
    last = ticks[-1][1]
    return {name: done.get(name, last) for name in EXIT_NAMES}


def pnl(side, entry_px, exit_px, qty):
    pts = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
    return pts * VPP * qty - FEE * qty


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")
    trades = con.execute("""
        SELECT gate, side, entry_price, qty, epoch(opened_at::TIMESTAMPTZ) t0,
               strftime(opened_at::TIMESTAMPTZ,'%m-%d') d
        FROM g.trades WHERE symbol='MNQ' AND opened_at::TIMESTAMPTZ >= TIMESTAMP '2026-07-20'
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY opened_at""").fetchall()

    daycache: dict = {}

    def load_day(t0):
        s = dr.pnl.paris_day_start_utc(dt.datetime.fromtimestamp(t0, dt.UTC))
        ds = dt.datetime.fromisoformat(s).timestamp() if isinstance(s, str) else s.timestamp()
        if ds not in daycache:
            rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-1800} AND bar_ts<{ds+86400}
                GROUP BY 1 ORDER BY 1""").fetchall()
            marks = dr.replay_marks([r[0] for r in rows], [r[1] for r in rows],
                                    int(ds), int(ds+86400)) if len(rows) > dr.WINDOW else []
            daycache[ds] = (rows, marks)
        return daycache[ds]

    # per-entry repriced results
    recs = []   # (gate, regime_bucket, day, qty, {exit: pnl})
    for (gate, side, ep, qty, t0, d) in trades:
        rows, marks = load_day(t0)
        ctx = [r for r in rows if t0 - 1800 <= r[0] <= t0]
        atr = sum(r[2]-r[3] for r in ctx) / len(ctx) if len(ctx) >= 6 else 0.0
        if atr <= 0:
            continue
        ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>={int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        if len(ticks) < 2:
            continue
        st = "CHOP"
        for mt, s, _e, _n in marks:
            if mt <= t0:
                st = s
            else:
                break
        aligned = (side == "SHORT" and st == "TREND_DOWN") or (side == "LONG" and st == "TREND_UP")
        counter = (side == "SHORT" and st == "TREND_UP") or (side == "LONG" and st == "TREND_DOWN")
        bucket = "ALIGNED" if aligned else "COUNTER" if counter else "CHOP"
        exits = reprice_all(side, ep, atr, ticks[1:])
        recs.append((gate, bucket, d, {name: pnl(side, ep, exits[name], qty or 1) for name in EXIT_NAMES}))
    con.close()

    def total(rs, name):
        return sum(r[3][name] for r in rs)

    # (1) WIDTH CURVE
    print(f"EXIT-SELECTOR SWEEP — {len(recs)} entries repriced (07-20..27)  ·  fees ${FEE}/RT\n")
    print("(1) WIDTH CURVE — each fixed exit's total P&L across all entries (tight→wide):")
    for name in EXIT_NAMES:
        print(f"   {name:8} ${total(recs, name):>+7.0f}")

    # (2) REGIME x EXIT
    print("\n(2) REGIME x EXIT — total P&L, which exit wins in each regime bucket:")
    print(f"   {'bucket':9} {'n':>3} " + "".join(f"{n:>8}" for n in EXIT_NAMES))
    for bucket in ("ALIGNED", "COUNTER", "CHOP"):
        rs = [r for r in recs if r[1] == bucket]
        row = f"   {bucket:9} {len(rs):>3} " + "".join(f"{total(rs, n):>+8.0f}" for n in EXIT_NAMES)
        best = max(EXIT_NAMES, key=lambda n: total(rs, n)) if rs else "-"
        print(row + f"   → {best}")

    # (3) GATE x REGIME → best exit (+ n)
    print("\n(3) GATE x REGIME → best exit (n) — the selector map:")
    gates = sorted({r[0] for r in recs})
    print(f"   {'gate':18} {'ALIGNED':>16} {'CHOP':>16} {'COUNTER':>16}")
    for gate in gates:
        cells = []
        for bucket in ("ALIGNED", "CHOP", "COUNTER"):
            rs = [r for r in recs if r[0] == gate and r[1] == bucket]
            if rs:
                best = max(EXIT_NAMES, key=lambda n: total(rs, n))
                cells.append(f"{best}/{total(rs, best):+.0f}(n{len(rs)})")
            else:
                cells.append("-")
        print(f"   {gate:18} {cells[0]:>16} {cells[1]:>16} {cells[2]:>16}")

    # (4) ADAPTIVE-3 selector vs best fixed, with LODO
    def adaptive_total(rs, train):
        """pick best exit per (gate,bucket) learned on `train`, apply to `rs`."""
        pick = {}
        for gate in gates:
            for bucket in ("ALIGNED", "COUNTER", "CHOP"):
                tr = [r for r in train if r[0] == gate and r[1] == bucket]
                pick[(gate, bucket)] = max(EXIT_NAMES, key=lambda n: total(tr, n)) if tr else "scalp2R"
        return sum(r[3][pick[(r[0], r[1])]] for r in rs)

    def regime_total(rs, train):
        """REGIME-ONLY selector: best exit per bucket (ignore gate) — far more data per cell."""
        pick = {}
        for bucket in ("ALIGNED", "COUNTER", "CHOP"):
            tr = [r for r in train if r[1] == bucket]
            pick[bucket] = max(EXIT_NAMES, key=lambda n: total(tr, n)) if tr else "scalp2R"
        return sum(r[3][pick[r[1]]] for r in rs), pick

    best_fixed = max(EXIT_NAMES, key=lambda n: total(recs, n))
    days = sorted({r[2] for r in recs})
    print("\n(4) SELECTORS vs best fixed single exit — LEAVE-ONE-DAY-OUT (learned WITHOUT the test day):")
    _, rpick = regime_total(recs, recs)
    print(f"   best fixed single exit = {best_fixed} (${total(recs, best_fixed):+.0f})   "
          f"regime-only picks (in-sample): {rpick}")
    print(f"   {'day':>6} {'perGate':>8} {'regimeOnly':>11} {'bestFixed':>10}")
    tg = tr = tf = 0.0
    wg = wr = 0
    for day in days:
        train = [r for r in recs if r[2] != day]
        test = [r for r in recs if r[2] == day]
        g = adaptive_total(test, train)
        ro, _ = regime_total(test, train)
        f = total(test, best_fixed)
        tg += g
        tr += ro
        tf += f
        wg += g > f
        wr += ro > f
        print(f"   {day:>6} {g:>+8.0f} {ro:>+11.0f} {f:>+10.0f}")
    print(f"   {'TOTAL':>6} {tg:>+8.0f} {tr:>+11.0f} {tf:>+10.0f}")
    print(f"   OOS vs best-fixed: per-gate {tg-tf:+.0f} ({wg}/{len(days)}d)  ·  "
          f"regime-only {tr-tf:+.0f} ({wr}/{len(days)}d)")


if __name__ == "__main__":
    main()
