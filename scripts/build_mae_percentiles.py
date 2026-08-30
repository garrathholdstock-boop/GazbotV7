#!/usr/bin/env python3
"""Precompute the ADVERSE-EXCURSION distribution, per session block, so the dashboard can say
"this drawdown is at the Nth percentile" instead of inventing a threshold.

Operator holds naked and manages by hand, so the question that matters mid-trade is not "am I down"
but "is this NORMAL down, or is this one of the bad ones". That is only answerable against a
distribution, and a distribution is only honest if it is measured rather than assumed.

METHOD. For every session in the 1-min lake, enter LONG and SHORT at each block's start and record
the worst adverse excursion reached WITHIN each elapsed-time bucket (15m, 30m, 1h, 2h, 4h, to-flat).
★ CONDITIONING ON TIME HELD IS THE WHOLE POINT. A first cut measured only the full hold to 20:40Z
and produced a 171pt LONDON median — against which any 30-minute drawdown looks harmless, so the
meter would have said "normal" to almost everything and been worse than no meter. A position 30
minutes old must be compared with other positions 30 minutes old.
Both directions are pooled: the operator's entry direction is his own, and a one-sided distribution
would inherit the sample's drift. Reported in ATR units too, because 60pt means different things on
a 12pt-ATR day and a 40pt one.

Re-run when the tape character changes; the artifact carries its own build date and sample size.
"""
from __future__ import annotations
import argparse, datetime as dt, json, statistics as st, sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")

# ⚠ MGC IS $10.00/POINT, five times MNQ. The distribution is in POINTS so the multiplier does not
# enter it — but anything that converts these to dollars must use the right one, and a gold drawdown
# priced with the MNQ multiplier reads one fifth of its real size.
VPP_BY_SYMBOL = {"MNQ": 2.0, "MGC": 10.0}

BLOCKS = {"ASIA": (0, 7 * 60), "LONDON": (7 * 60, 13 * 60 + 30),
          "US": (13 * 60 + 30, 20 * 60 + 40)}
FLAT = 20 * 60 + 40
PCTS = [10, 25, 50, 75, 90, 95, 99]
ELAPSED = [15, 30, 60, 120, 240, 10 ** 6]          # minutes since entry; the last = hold to the flat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="MNQ", choices=sorted(VPP_BY_SYMBOL))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    SYM = a.symbol
    from gazbot7.lake import connect
    from gazbot7.deciders import _atr, Bar
    con = connect(symbol=SYM)   # ⚠ defaults to MNQ; passing this is mandatory
    days = [r[0].isoformat() for r in con.execute(
        "SELECT DISTINCT CAST(to_timestamp(bar_ts) AS DATE) d FROM bars WHERE symbol=? "
        "AND timeframe='1min' ORDER BY d", [SYM]).fetchall()]
    out = {"built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"), "symbol": SYM,
           "usd_per_point": VPP_BY_SYMBOL[SYM], "blocks": {}}
    for name, (start, _end) in BLOCKS.items():
        buckets = {e: {"pt": [], "atr": []} for e in ELAPSED}
        for day in days:
            t0 = dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp()
            rows = con.execute("SELECT bar_ts,open,high,low,close FROM bars WHERE symbol=? "
                               "AND timeframe='1min' AND bar_ts>=? AND bar_ts<? ORDER BY bar_ts",
                               [SYM, int(t0), int(t0 + 86400)]).fetchall()
            idx = {}
            for i, b in enumerate(rows):
                t = dt.datetime.fromtimestamp(b[0], dt.UTC); idx[t.hour * 60 + t.minute] = i
            i0, i1 = idx.get(start), idx.get(FLAT)
            if i0 is None or i1 is None or i1 - i0 < 60:
                continue
            atr = _atr([Bar(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), 0.0)
                        for r in rows[max(0, i0 - 60):i0]])
            e = rows[i0][1]
            for d in (1, -1):                       # BOTH sides pooled — see docstring
                mae = 0.0
                for j in range(i0, i1 + 1):
                    hi, lo = rows[j][2], rows[j][3]
                    mae = max(mae, (e - lo) if d > 0 else (hi - e))
                    held = j - i0
                    for cut in ELAPSED:
                        if held == cut or (cut == ELAPSED[-1] and j == i1):
                            buckets[cut]["pt"].append(mae)
                            if atr > 0:
                                buckets[cut]["atr"].append(mae / atr)
        blk = {}
        for cut, v in buckets.items():
            if len(v["pt"]) < 40:
                continue
            key = "flat" if cut == ELAPSED[-1] else str(cut)
            blk[key] = {"n": len(v["pt"]),
                        "pt": {str(p): round(st.quantiles(v["pt"], n=100)[p - 1], 1) for p in PCTS},
                        "atr": {str(p): round(st.quantiles(v["atr"], n=100)[p - 1], 2)
                                for p in PCTS} if v["atr"] else {}}
        if not blk:
            continue
        out["blocks"][name] = blk
        row = "  ".join(f"{k}:{blk[k]['pt']['50']:.0f}/{blk[k]['pt']['90']:.0f}"
                        for k in ("15", "30", "60", "120", "flat") if k in blk)
        print(f"  {name:<7} median/p90 pt by minutes held -> {row}")
    path = a.out or (f"/home/alphabot/gazbot7/data/mae_percentiles"
                     f"{'' if SYM == 'MNQ' else '_' + SYM}.json")
    json.dump(out, open(path, "w"), indent=1)
    print(f"\nwrote {path} (built {out['built']}, {SYM} @ ${VPP_BY_SYMBOL[SYM]:.2f}/pt)")


if __name__ == "__main__":
    main()
