#!/usr/bin/env python3
"""abs_veto: what does the 55-second wait cost, and what would 2R/3R do on lot B?

★ THE QUESTION (operator, 2026-08-10): "it was armed but it waits too long — I
watched it miss some decent runs today." VETO_SECS is 55 (deciders.py:170). This
sweeps the wait at 0/5/10/15/20/25/30/55s and lot B's target at its deployed
value / 2R / 3R, on today's own signals.

★★ WHAT THIS MEASURES, AND THE ONE THING IT CANNOT.
It measures ENTRY TIMING: the same signal entered after a shorter wait, priced on
real ticks, with the stop and target raced tick-by-tick.
It does NOT model the veto's FILTERING. The 55s wait exists to re-test the thrust
and drop fakeouts; entering at 5s would also take trades the veto currently
REJECTS. `signal_journal.taken` is NULL in every row (a known dead column), so
which signals passed the veto is not recorded anywhere and cannot be recovered.
So every short-delay number here is an UPPER BOUND on the benefit: it keeps the
55s population and only moves the entry earlier. A real 5s gate would take a
larger, worse population. Treat a win here as "worth a shadow arm", never as
"ship it".

Costs are VPP=2.0, FEE=1.50/RT — the values the 08-02 correction settled on.
Exits RACE stop vs target on ticks; MFE is not a win rate.
"""
from __future__ import annotations
import sqlite3, datetime as dt, statistics, sys

GB = "/home/alphabot/gazbot7"
VPP, FEE = 2.0, 1.50
MAX_HOLD_S = 120 * 60          # multislot_core force-flat
DELAYS = [0, 5, 10, 15, 20, 25, 30, 55]
DAYS = [a for a in sys.argv[1:] if not a.startswith("--")] or ["2026-08-10"]
# --all-signals drops the armed-window filter. The veto is a GATE parameter, not a
# routing one: whether the router happened to have the gate switched on that day
# says nothing about whether 55s is the right wait. Keeping the filter answers
# "what did today's routing cost"; dropping it answers the operator's actual
# question, on every signal the gate produced.
ALL_SIGNALS = "--all-signals" in sys.argv

# Deployed ladder (scaleout_slots, verified at the resolved layer)
A_TARGET = {"abs_veto_long": 1.0, "abs_veto_short": 1.5}
B_DEPLOYED = {"abs_veto_long": 1.5, "abs_veto_short": 2.5}

# Armed windows today, from data/router_trial_log.txt. Entries before 07:00Z are
# refused by the permanent Asia block (no_open_asia) whatever the switch says, so
# the window starts there or the sweep would count trades that could never exist.
ARMED = {
    "abs_veto_short": [("07:00", "23:59")],
    "abs_veto_long":  [("07:00", "12:41")],   # benched 12:41 on the down break
}


def ms(day, hhmm):
    h, m = hhmm.split(":")
    return int(dt.datetime(*map(int, day.split("-")), int(h), int(m), tzinfo=dt.UTC).timestamp() * 1000)


def day_rows(DAY, pool):
    sh = sqlite3.connect(f"{GB}/data/shadow.db")
    cap = sqlite3.connect(f"{GB}/data/capture.db")
    t0 = ms(DAY, "00:00"); t1 = t0 + 86400_000

    sigs = list(sh.execute(
        "SELECT ts_ms, gate, side, price, atr_pt FROM signal_journal "
        "WHERE gate LIKE 'abs_veto%' AND ts_ms>=? AND ts_ms<? ORDER BY ts_ms", (t0, t1)))
    # keep only signals inside that gate's armed window
    kept = []
    for ts, gate, side, price, atr in sigs:
        if not (atr and 0 < atr < 200):                # reject MD_STREAM-corrupted ATRs
            continue
        if ALL_SIGNALS:
            if ts >= ms(DAY, "07:00"):                 # Asia block refuses entries before this
                kept.append((ts, gate, side, price, atr))
            continue
        for a, b in ARMED.get(gate, []):
            if ms(DAY, a) <= ts < ms(DAY, b):
                kept.append((ts, gate, side, price, atr))
                break
    print(f"signals: {len(sigs)} raw -> {len(kept)} inside an armed window, sane ATR  ({DAY})")
    if not kept:
        return 1
    by_gate = {}
    for _, g, *_ in kept: by_gate[g] = by_gate.get(g, 0) + 1
    print("  " + " · ".join(f"{g} {n}" for g, n in sorted(by_gate.items())))

    ticks = cap.execute(
        "SELECT ts_ms, price FROM ticks WHERE symbol='MNQ' AND ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
        (t0, t1 + MAX_HOLD_S * 1000)).fetchall()
    print(f"  ticks loaded: {len(ticks):,}")
    T = [t for t, _ in ticks]
    import bisect

    def price_at(t_ms):
        i = bisect.bisect_left(T, t_ms)
        return ticks[i][1] if i < len(ticks) else None, i

    def race(i0, entry, stop, target, long):
        """First touch wins. Returns (exit_price, reason, seconds_held)."""
        t_start = ticks[i0][0]
        for i in range(i0, len(ticks)):
            t, p = ticks[i]
            if t - t_start > MAX_HOLD_S * 1000:
                return p, "CAP", (t - t_start) / 1000
            if long:
                if p <= stop:   return stop, "STOP", (t - t_start) / 1000
                if p >= target: return target, "TARGET", (t - t_start) / 1000
            else:
                if p >= stop:   return stop, "STOP", (t - t_start) / 1000
                if p <= target: return target, "TARGET", (t - t_start) / 1000
        p = ticks[-1][1]
        return p, "EOD", (ticks[-1][0] - t_start) / 1000

    def run(delay, b_mult):
        rows = []
        for ts, gate, side, _sp, atr in kept:
            long = (side or "").upper().startswith("L") or gate.endswith("_long")
            ep, i0 = price_at(ts + delay * 1000)
            if ep is None: continue
            R = atr * 1.0                                   # stop_atr_mult = 1.0
            stop = ep - R if long else ep + R
            out = 0.0
            for tag, mult in (("A", A_TARGET[gate]), ("B", b_mult if b_mult else B_DEPLOYED[gate])):
                tgt = ep + R * mult if long else ep - R * mult
                xp, why, _ = race(i0, ep, stop, tgt, long)
                pnl = ((xp - ep) if long else (ep - xp)) * VPP - FEE
                out += pnl
            rows.append(out)
        return rows

    for d in DELAYS:
        for label, bm in (("dep", None), ("2R", 2.0), ("3R", 3.0)):
            pool.setdefault((d, label), []).extend(run(d, bm))
    return len(kept)


def main():
    pool = {}
    total = 0
    for D in DAYS:
        try:
            total += day_rows(D, pool)
        except Exception as e:
            print(f"  {D}: skipped ({e})")
    print(f"\nPOOLED over {len(DAYS)} day(s): n={total} signals")
    best = pool
    print(f"\n{'delay':>6} | {'lot B = deployed':>22} | {'lot B = 2R':>22} | {'lot B = 3R':>22}")
    print(f"{'':>6} | {'total   per-sig':>22} | {'total   per-sig':>22} | {'total   per-sig':>22}")
    print("-" * 78)
    for d in DELAYS:
        cells = []
        for label in ("dep", "2R", "3R"):
            rows = best[(d, label)]
            tot = sum(rows); per = tot / len(rows) if rows else 0
            cells.append(f"{tot:>8.2f} {per:>7.2f}")
            best[(d, label)] = rows
        mark = "  <- deployed" if d == 55 else ""
        print(f"{d:>4}s  | " + " | ".join(f"{c:>22}" for c in cells) + mark)

    # Is any of this distinguishable from noise?
    base = best[(55, "dep")]
    print(f"\nsignals per cell: n={len(base)}")
    sd = statistics.pstdev(base) if len(base) > 1 else 0
    print(f"per-signal SD at the deployed cell: ${sd:.2f}")
    print("\n  cell vs deployed(55s) — difference, and the standard error on it:")
    for d in DELAYS:
        for label in ("dep", "2R", "3R"):
            if (d, label) == (55, "dep"): continue
            r = best[(d, label)]
            if len(r) != len(base): continue
            diffs = [a - b for a, b in zip(r, base)]
            md = sum(diffs) / len(diffs)
            se = (statistics.pstdev(diffs) / (len(diffs) ** 0.5)) if len(diffs) > 1 else 0
            t = md / se if se else 0
            flag = "  SIGNIFICANT" if abs(t) >= 2 else ""
            print(f"    {d:>3}s {label:<4} {md:+8.2f}/sig  SE {se:6.2f}  t={t:+5.2f}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
