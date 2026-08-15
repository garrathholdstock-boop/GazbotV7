"""EXHAUSTION_SHORT REHAB — stage 1: build the signal table + every tick-derived feature.

Why a build stage: each of the four commissioned tests needs the SAME per-signal facts (the
20s footprint net at the fire, the price path after entry, the entry ATR), and pulling them
out of the parquet lake takes minutes. Build once, cache to JSON, sweep in milliseconds.

★ THE A/B COLLAPSE. `trades` rows are LOTS, not signals: since 2026-07-29 the gate fires two
1-lot slots (_A scalp-0.75R, _B tight-chandelier) off ONE signal, at the same second and the
same price. Counting them as two trades double-counts every stop (the legs share a stop, so
they die together) and — fatally for this study — puts a 0-minute gap between "consecutive
losses". Everything downstream is keyed on the SIGNAL.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sqlite3

from gazbot7.lake import connect

DB = "data/gazbot7.db"
OUT = "reports/friday_v7/sections/exh_signals.json"
VPP = 2.0            # MNQ $/point
WINDOW_S = 20        # the footprint's net window
NET_OFFSET_MS = 500  # validated in exh_net_validate.py (38% exact, median rel err 1.6%)
PATH_S = 900         # seconds of post-entry tape to cache per signal (covers every exit + delay test)
PRE_S = 60           # seconds of pre-entry tape (for the anchor test)


def _iso_ms(s: str) -> int:
    return int(dt.datetime.fromisoformat(s).timestamp() * 1000)


def load_signals() -> list[dict]:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    legs = [dict(r) for r in c.execute(
        "SELECT * FROM trades WHERE gate LIKE 'exhaustion_short%' "
        "AND (data_quality IS NULL OR data_quality NOT LIKE 'EXCLUDE%') ORDER BY opened_at")]
    # ★ the A/B legs do NOT share a timestamp to the microsecond — they are submitted back to
    # back and land ~60ms apart. Group on a 2s gap, not on equality.
    groups: list[list[dict]] = []
    for lg in legs:
        t = _iso_ms(lg["opened_at"])
        if groups and t - _iso_ms(groups[-1][-1]["opened_at"]) <= 2000:
            groups[-1].append(lg)
        else:
            groups.append([lg])
    sigs = []
    for v in groups:
        k = v[0]["opened_at"]
        entry = sum(x["entry_price"] for x in v) / len(v)
        sigs.append({
            "sig": len(sigs),
            "opened_at": k,
            "ts_ms": _iso_ms(k),
            "date": v[0]["closed_at"][:10],
            "n_legs": len(v),
            "entry": entry,
            "pnl": round(sum(x["pnl_usd"] for x in v), 2),
            "reasons": sorted({x["exit_reason"] for x in v}),
            "leg_pnl": {x["gate"]: round(x["pnl_usd"], 2) for x in v},
            "closed_ms": max(_iso_ms(x["closed_at"]) for x in v),
            "stop_dist": round(max(abs(x["exit_price"] - x["entry_price"])
                                   for x in v if x["exit_reason"] == "STOP"), 2)
            if any(x["exit_reason"] == "STOP" for x in v) else None,
            "era": "AB" if any(x["gate"].endswith(("_A", "_B")) for x in v) else "single",
        })
    return sigs


def main() -> None:
    sigs = load_signals()
    print(f"legs collapsed to {len(sigs)} signals")
    con = connect()

    # ── the 20s footprint net, at several candidate anchors ───────────────────────────
    # The live entry is NOT the signal instant: since 2026-07-29 an exhaustion OPEN is held
    # EXH_CONFIRM_SECS=5 before it is sent, and the tournament loop adds its own cycle. The gate
    # only ever fires when |net| >= 400, so the CORRECT anchor is the one where ~every live
    # signal clears 400 — that is a self-validating test and it is reported as one.
    anchors = [0, -3, -5, -8, -10, -13]
    con.execute("CREATE OR REPLACE TEMP TABLE anc (sig BIGINT, off INT, t0 BIGINT, t1 BIGINT)")
    con.executemany("INSERT INTO anc VALUES (?,?,?,?)", [
        (s["sig"], a, s["ts_ms"] + a * 1000 + NET_OFFSET_MS - WINDOW_S * 1000,
         s["ts_ms"] + a * 1000 + NET_OFFSET_MS)
        for s in sigs for a in anchors])
    net = collections.defaultdict(dict)
    for sg, off, n, nt, mv in con.execute("""
        SELECT a.sig, a.off,
               sum(CASE WHEN t.aggressor='buy' THEN t.size
                        WHEN t.aggressor='sell' THEN -t.size ELSE 0 END),
               count(*), max(t.price)-min(t.price)
        FROM anc a JOIN ticks t
          ON t.symbol='MNQ' AND t.ts_ms>=a.t0 AND t.ts_ms<=a.t1
        GROUP BY 1,2""").fetchall():
        net[int(sg)][int(off)] = {"net": float(n or 0), "nticks": int(nt), "rng": float(mv or 0)}

    for s in sigs:
        s["net_by_anchor"] = {str(k): v for k, v in net.get(s["sig"], {}).items()}

    cov = {a: sum(1 for s in sigs if abs(net.get(s["sig"], {}).get(a, {}).get("net", 0)) >= 400.0)
           for a in anchors}
    have = sum(1 for s in sigs if net.get(s["sig"]))
    print(f"tape available for {have}/{len(sigs)} signals")
    print("anchor test — signals clearing the live |net|>=400 floor:")
    for a in anchors:
        print(f"  entry{a:+3d}s : {cov[a]:3d}/{have}  ({100.0*cov[a]/max(1,have):.0f}%)")

    # ── the post-entry price path (MFE/MAE, the delay tests, every reprice) ───────────
    con.execute("CREATE OR REPLACE TEMP TABLE pth (sig BIGINT, t0 BIGINT, t1 BIGINT)")
    con.executemany("INSERT INTO pth VALUES (?,?,?)",
                    [(s["sig"], s["ts_ms"] - PRE_S * 1000, s["ts_ms"] + PATH_S * 1000) for s in sigs])
    path = collections.defaultdict(list)
    for sg, rel, px in con.execute("""
        SELECT p.sig, CAST(t.ts_ms - (p.t0 + %d) AS BIGINT), t.price
        FROM pth p JOIN ticks t
          ON t.symbol='MNQ' AND t.ts_ms>=p.t0 AND t.ts_ms<=p.t1
        ORDER BY 1,2""" % (PRE_S * 1000)).fetchall():
        path[int(sg)].append((int(rel), float(px)))
    for s in sigs:
        p = path.get(s["sig"], [])
        # thin to <=4000 points but ALWAYS keep the running extremes, so MFE/MAE and any
        # stop/target touch survives the compression (a naive stride would lose the wick)
        s["path"] = _thin(p)
        s["path_n"] = len(p)

    # ── entry ATR-14 on 1-min bars (halt-aware, mirroring deciders._atr) ──────────────
    # ⚠ the lake's 1m bars STOP on 2026-07-11 — only the 5s stream is current, so the minute
    # bars are rebuilt from 5s. `bar_ts - (bar_ts % 60)` on purpose: `(bar_ts/60)*60` is a
    # float no-op in DuckDB and is the exact bug that made a prior read consume 5s bars as 1m.
    bars = con.execute("""
        SELECT bar_ts - (bar_ts %% 60) AS m, max(high), min(low),
               arg_max(close, bar_ts) AS close
        FROM bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= %d
        GROUP BY 1 ORDER BY 1
        """ % (min(s["ts_ms"] for s in sigs) // 1000 - 86400 * 3)).fetchall()
    bl = [(int(b[0]), float(b[1]), float(b[2]), float(b[3])) for b in bars]
    print(f"1m bars loaded: {len(bl)}")
    for s in sigs:
        s["atr"] = _atr_at(bl, s["ts_ms"] // 1000)

    with open(OUT, "w") as f:
        json.dump({"signals": sigs, "meta": {
            "net_offset_ms": NET_OFFSET_MS, "window_s": WINDOW_S,
            "anchor_pass": {str(a): cov[a] for a in anchors}, "tape_have": have}}, f)
    print(f"wrote {OUT}")


def _thin(p, cap=4000):
    if len(p) <= cap:
        return p
    step = len(p) // cap + 1
    keep = {0, len(p) - 1}
    lo = hi = p[0][1]
    ilo = ihi = 0
    for i, (_, px) in enumerate(p):
        if px < lo:
            lo, ilo = px, i
        if px > hi:
            hi, ihi = px, i
        if i % step == 0:
            keep.add(i)
        keep.add(ilo)
        keep.add(ihi)
    return [p[i] for i in sorted(keep)]


def _atr_at(bl, ts_s, n=14):
    import bisect
    i = bisect.bisect_right([b[0] for b in bl], ts_s) - 1
    if i < n:
        return None
    w = bl[i - n:i + 1]
    trs = []
    for j in range(1, len(w)):
        pts, ph, pl, pc = w[j - 1][0], w[j - 1][1], w[j - 1][2], w[j - 1][3]
        cts, ch, cl, _ = w[j]
        r = ch - cl
        if cts - pts <= 90:                     # contiguous → the two gap terms are meaningful
            r = max(r, abs(ch - pc), abs(cl - pc))
        trs.append(r)
    return round(sum(trs) / len(trs), 2) if trs else None


if __name__ == "__main__":
    main()
