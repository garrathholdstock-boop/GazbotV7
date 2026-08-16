#!/usr/bin/env python3
"""BUILD #17 + #14 — the FLOW-BENCH meter and the short-fader run-catcher log.

    PYTHONPATH=src .venv/bin/python scripts/flow_bench_meter.py [--days 10]

★★ BUILD #17 — INVERT exhaustion_short's FLOW CLAUSE INTO A BENCH INSTRUMENT.
The gate's entry test is `abs(price_move_pt) <= move_max` — heavy aggression that CANNOT move price
is absorption, and absorption is what it fades. The report's idea was to read the same clause the
other way round: when heavy flow DOES move price, that is the tape refusing to absorb, i.e. a real
directional push. As an ENTRY test it says "do not fade this one". As a ROUTER instrument it says
something larger and cheaper to act on — "the tape is not absorbing right now, so bench the faders",
which is a permission decision rather than a per-signal one.

⚠ THIS IS A METER, NOT A SWITCH. It writes a number and a suggestion; nothing reads it to bench
anything. That is deliberate: the desk's standing rule is that a memory is not a rule until it is in
the prompt, and putting an unvalidated bench signal into the prompt is how a router learns a wrong
rule. Accumulate first, then decide.

★★ BUILD #14 — LOG THE TWO SHORT FADERS AS RUN-CATCHERS.
Every mechanical exhaustion_short / rgv_short fire is stamped with whether it landed NEAR A CENSUS
RUN — the sat-out moves the desk keeps not catching. No live change; the point is to accumulate n
against a question that currently has none.

⚠ NEITHER SECTION SCORES A GATE. A fader firing into a run is not automatically wrong (fading the
end of a run is the trade), and a high flow-push reading is not automatically a bench. Both are
CONTEXT being accumulated so that a later decision has evidence instead of a hunch.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

GB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GB, "src"))

CAP = os.path.join(GB, "data", "capture.db")
DB = os.path.join(GB, "data", "gazbot7.db")
OUT = os.path.join(GB, "data", "flow_bench_meter.json")

FADERS = ("exhaustion_short", "rgv_short")
WINDOW_S = 20            # the same 20s window the gate's own clause uses
MOVE_MAX = 2.0           # cfg.move_max — above this, flow DID move price
NET_MIN = 400.0          # cfg.net_min — only judge windows with real aggression in them


def flow_push(cap, symbol: str, at_ms: int) -> tuple[float, float] | None:
    """(|net signed|, |price move|) over the gate's own 20s window, or None."""
    try:
        rows = cap.execute(
            "SELECT price, size, aggressor FROM ticks WHERE symbol=? AND ts_ms>=? AND ts_ms<=? "
            "ORDER BY ts_ms", (symbol, at_ms - WINDOW_S * 1000, at_ms)).fetchall()
    except Exception:
        return None
    if len(rows) < 3:
        return None
    net = sum((r[1] if r[2] == "buy" else -r[1]) for r in rows if r[2] in ("buy", "sell"))
    return abs(net), abs(rows[-1][0] - rows[0][0])


# ⚠ THE PROXIMITY WINDOW IS AN ASSUMPTION, STATED. census_summary.json records `runs` as a COUNT and
# lists only run START times ("08-13 13:32") in top25 — there is no end stamp. So "near a run" means
# "within NEAR_RUN_MIN of a run's start", which is a stand-in for overlap, not overlap itself. If the
# census ever records run ENDS, replace this with a real interval test rather than widening the window.
NEAR_RUN_MIN = 30


def census_runs(days: int) -> list[tuple[int, int]]:
    """(start_ms, end_ms) windows around recent census run STARTS."""
    p = os.path.join(GB, "reports", "friday_v7", "sections", "census_summary.json")
    try:
        with open(p) as f:
            d = json.load(f)
    except Exception:
        return []
    year = dt.datetime.now(dt.UTC).year
    out = []
    for r in (d.get("top25") or []):
        t = r.get("time")
        if not t:
            continue
        try:
            st = dt.datetime.strptime(f"{year}-{t}", "%Y-%m-%d %H:%M").replace(tzinfo=dt.UTC)
        except Exception:
            continue
        ms = int(st.timestamp() * 1000)
        out.append((ms - NEAR_RUN_MIN * 60_000, ms + NEAR_RUN_MIN * 60_000))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    a = ap.parse_args()

    since = int((dt.datetime.now(dt.UTC) - dt.timedelta(days=a.days)).timestamp())
    try:
        db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        fires = db.execute(
            "SELECT gate, opened_at, pnl_usd, epoch_opened FROM ("
            "  SELECT gate, opened_at, pnl_usd, "
            "         CAST(strftime('%s', opened_at) AS INTEGER) epoch_opened FROM trades "
            "  WHERE symbol='MNQ' AND data_quality IS NULL) "
            "WHERE epoch_opened >= ? ORDER BY epoch_opened", (since,)).fetchall()
        db.close()
    except Exception as e:
        print(f"trades unreadable: {e}")
        return 1

    from gazbot7.tournament import _base
    fader_fires = [r for r in fires if _base(r[0]) in FADERS]
    if not fader_fires:
        print(f"no {'/'.join(FADERS)} fires in the last {a.days} days — nothing to accumulate")
        return 0

    cap = None
    try:
        cap = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)
    except Exception:
        pass

    runs = census_runs(a.days)
    pushed = absorbed = unknown = 0
    in_run = 0
    rows = []
    for gate, opened, pnl, ts in fader_fires:
        fp = flow_push(cap, "MNQ", ts * 1000) if cap else None
        if fp is None:
            unknown += 1
            state = "unknown"
        else:
            net, move = fp
            if net < NET_MIN:
                state = "quiet"          # not enough aggression for the clause to mean anything
            elif move > MOVE_MAX:
                state = "PUSHED"         # heavy flow DID move price -> the tape is not absorbing
                pushed += 1
            else:
                state = "absorbed"
                absorbed += 1
        near = any(s <= ts * 1000 <= e for s, e in runs)
        in_run += bool(near)
        rows.append({"gate": _base(gate), "ts": ts, "pnl": pnl,
                     "flow_state": state, "near_census_run": near})

    if cap:
        cap.close()

    print(f"FLOW-BENCH METER — {len(fader_fires)} short-fader fires over {a.days} days\n")
    print(f"  PUSHED   (heavy flow DID move price — the bench case)  {pushed}")
    print(f"  absorbed (heavy flow could not move price — fade on)   {absorbed}")
    print(f"  unknown / too quiet to judge                           {unknown + len(rows) - pushed - absorbed - unknown}")
    for st in ("PUSHED", "absorbed"):
        sel = [r for r in rows if r["flow_state"] == st]
        if sel:
            tot = sum(r["pnl"] or 0 for r in sel)
            print(f"    {st:<9} n={len(sel):>3}  net ${tot:>9,.2f}  ${tot/len(sel):>7.2f}/trade")
    print(f"\n  BUILD #14 — near a census run: {in_run} of {len(rows)}"
          + ("" if runs else "   ⚠ no census runs on disk — run scripts/run_census.py first"))

    with open(OUT, "w") as f:
        json.dump({"generated": dt.datetime.now(dt.UTC).isoformat(), "days": a.days,
                   "pushed": pushed, "absorbed": absorbed, "near_run": in_run,
                   "n": len(rows), "rows": rows[-200:],
                   "_note": "METER ONLY — nothing reads this to bench anything. A high PUSHED count "
                            "is a candidate bench signal, not a bench. Accumulate, then decide."},
                  f, indent=1)
    print(f"\n  -> {OUT}")
    print("  ⚠ Neither number scores a gate. A fader firing into a run is not automatically wrong — "
          "fading\n    the END of a run is the trade — and a PUSHED reading is not automatically a bench.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
