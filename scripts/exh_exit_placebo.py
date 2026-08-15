"""EXHAUSTION_SHORT REHAB — the exit grid's PLACEBO: does the exit rule work, or did the tape
just fall?

The exit grid says a 1.5xATR stop with a 2R target turns the same 87 live entries that actually
lost $84.50 into thousands of dollars. Before that becomes a recommendation it has to survive
the obvious objection: this gate only ever SHORTS, and a wide stop with a long hold on a tape
that drifted DOWN prints money from ANY entry, signal or no signal.

★ THE CONTROL IS PAIRED. Each random shot inherits a REAL signal's exact stop and target width
in POINTS and its exact day, so stop geometry, target geometry, session and hour are all held
fixed and the ONLY thing that changes is WHEN we entered. An earlier version gave every shot
its day's MEDIAN ATR, which is not the same experiment — on 2026-07-27 the per-signal ATR runs
10.2 to 47.9pt, so a day-median stop is a different trade from the one the grid scored.

Both books are entered at the TAPE price at their own timestamp (not the live fill), so
execution slippage cannot flatter the real leg either.
"""
from __future__ import annotations

import collections
import json
import random
import statistics

from gazbot7.lake import connect

VPP, FEE = 2.0, 1.50          # MNQ $/pt, $ per ROUND TRIP per lot
IN = "reports/friday_v7/sections/exh_signals.json"
OUT = "reports/friday_v7/sections/exh_exit_placebo.json"
PATH_S = 900
DRAWS = 60
RNG = random.Random(20260815)

# (label, stop, target) — ("atr", k) = k x that signal's OWN entry ATR; ("r", m) = m x the stop
RULES = [("stop 1.5xATR / target 2.0R / 15min cap", ("atr", 1.5), ("r", 2.0)),
         ("stop 1.5xATR / target 0.75R / 15min cap", ("atr", 1.5), ("r", 0.75)),
         ("stop 1.0xATR / target 0.75R / 15min cap", ("atr", 1.0), ("r", 0.75)),
         ("stop 20pt / target 24pt / hold 300", 20.0, 24.0),
         ("stop 8pt / target 12pt / hold 120", 8.0, 12.0)]
HOLD = {"stop 20pt / target 24pt / hold 300": 300, "stop 8pt / target 12pt / hold 120": 120}


def main() -> None:
    S = [s for s in json.load(open(IN))["signals"] if s["path_n"] > 0 and s["atr"]]
    span = collections.defaultdict(lambda: [10 ** 15, 0])
    for s in S:
        d = span[s["date"]]
        d[0], d[1] = min(d[0], s["ts_ms"]), max(d[1], s["ts_ms"])

    # draw -1 = the real book; draws 0..N-1 = paired random books (same signal, random time)
    shots = []
    for s in S:
        shots.append({"i": len(shots), "draw": -1, "src": s, "t0": s["ts_ms"]})
    for k in range(DRAWS):
        for s in S:
            a, b = span[s["date"]]
            shots.append({"i": len(shots), "draw": k, "src": s,
                          "t0": RNG.randint(a, max(b, a + 60_000))})
    print(f"shots: {len(shots)}  (1 real book of {len(S)} + {DRAWS} paired random books)")

    con = connect()
    con.execute("CREATE OR REPLACE TEMP TABLE sh (i BIGINT, t0 BIGINT)")
    con.executemany("INSERT INTO sh VALUES (?,?)", [(s["i"], s["t0"]) for s in shots])
    ent = dict(con.execute("""
        SELECT s.i, arg_min(t.price, t.ts_ms) FROM sh s JOIN ticks t
          ON t.symbol='MNQ' AND t.ts_ms>=s.t0 AND t.ts_ms<=s.t0+5000 GROUP BY 1""").fetchall())
    print(f"entry price found for {len(ent)}/{len(shots)}")

    out = {}
    for label, sp_r, tp_r in RULES:
        hold = HOLD.get(label, PATH_S)
        lv = []
        for sh in shots:
            e = ent.get(sh["i"])
            if e is None:
                continue
            src = sh["src"]
            sp = src["atr"] * sp_r[1] if isinstance(sp_r, tuple) else sp_r
            tp = sp * tp_r[1] if isinstance(tp_r, tuple) else tp_r
            lv.append((sh["i"], float(e), float(e) + sp, float(e) - tp,
                       sh["t0"], sh["t0"] + hold * 1000, float(src["n_legs"])))
        con.execute("CREATE OR REPLACE TEMP TABLE lv (i BIGINT, e DOUBLE, stop DOUBLE, "
                    "tgt DOUBLE, t0 BIGINT, tend BIGINT, lots DOUBLE)")
        con.executemany("INSERT INTO lv VALUES (?,?,?,?,?,?,?)", lv)
        res = con.execute("""
            SELECT l.i, l.e, l.stop, l.tgt, l.lots,
                   min(CASE WHEN t.price >= l.stop THEN t.ts_ms END),
                   min(CASE WHEN t.price <= l.tgt  THEN t.ts_ms END),
                   arg_max(t.price, t.ts_ms)
            FROM lv l JOIN ticks t
              ON t.symbol='MNQ' AND t.ts_ms>=l.t0 AND t.ts_ms<=l.tend
            GROUP BY l.i, l.e, l.stop, l.tgt, l.lots""").fetchall()
        draw_of = {s["i"]: s["draw"] for s in shots}
        bydraw, exits = collections.defaultdict(float), collections.Counter()
        for i, e, stop, tgt, lots, ts_s, ts_t, px_end in res:
            if ts_s is not None and (ts_t is None or ts_s <= ts_t):
                pnl, why = (e - stop) * VPP - FEE, "STOP"
            elif ts_t is not None:
                pnl, why = (e - tgt) * VPP - FEE, "TARGET"
            else:
                pnl, why = (e - px_end) * VPP - FEE, "TIME"
            bydraw[draw_of[int(i)]] += pnl * lots
            if draw_of[int(i)] == -1:
                exits[why] += 1
        real = bydraw.pop(-1, 0.0)
        v = sorted(bydraw.values())
        out[label] = {"real_entries": round(real, 2), "real_exits": dict(exits),
                      "draws": len(v), "mean": round(statistics.mean(v), 2),
                      "median": round(statistics.median(v), 2),
                      "p05": round(v[max(0, int(0.05 * len(v)))], 2),
                      "p95": round(v[min(len(v) - 1, int(0.95 * len(v)))], 2),
                      "min": round(v[0], 2), "max": round(v[-1], 2),
                      "real_pctile": round(100.0 * sum(1 for x in v if x < real) / len(v), 1),
                      "entry_alpha": round(real - statistics.mean(v), 2)}
        o = out[label]
        print(f"{label:42s} REAL {o['real_entries']:9.2f} | RANDOM mean {o['mean']:9.2f} "
              f"p05 {o['p05']:9.2f} p95 {o['p95']:9.2f} max {o['max']:9.2f} | "
              f"real pctile {o['real_pctile']:5.1f} | entry alpha {o['entry_alpha']:9.2f}")

    json.dump(out, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
