#!/usr/bin/env python3
"""OPEN-NEWS greenfield — STEP 0: interrogate the CLUSTER LABEL itself.

The census's cluster() assigns "OPEN/NEWS" by a single line:

    if 13 <= hour < 15: return "OPEN/NEWS"

...checked FIRST, before any flow or amplitude test. So the label is a CLOCK BUCKET, not a
footprint. This script measures, on the FULL parquet lake (not the 5-day capture window):

  1. base rate of the label on all 5s bars          (how much of the tape wears the label)
  2. run density per UTC hour                        (does the clock actually carry information?)
  3. what the 13-15Z runs would have been labelled had the clock rule not pre-empted them
  4. minute-of-hour histogram                        (is there a 13:30 RELEASE footprint at all?)

Writes JSON to reports/friday_v7/sections/gf_on_label.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/gf_on_label.json"
W = 180    # 15 min in 5s bars
STEP = 12  # slide 60s
MIN_ATR = 1.5
FLOW_Z = 1.0
FLOW_Z_LOOKBACK = 2 * 3600
FLOW_Z_MIN_BUCKETS = 30


def load_bars(con, since="2026-07-16"):
    return con.execute(f"""
        SELECT bar_ts, open, high, low, close FROM bars
        WHERE timeframe='5s'
          AND strftime(to_timestamp(bar_ts),'%Y-%m-%d') >= '{since}'
        ORDER BY bar_ts""").fetchall()


def detect_runs(bars, min_atr=MIN_ATR):
    """The census detector, ported verbatim in spirit: 15-min close-to-close move >= min_atr x the
    typical 15-min hi-lo range, overlaps deduped keep-strongest. Only compares windows that are
    CONTIGUOUS in wall-clock (no session-boundary straddles), which the census did NOT check."""
    rng, idx = [], []
    for i in range(0, len(bars) - W, STEP):
        if bars[i + W][0] - bars[i][0] > W * 5 + 60:   # a gap (session break) — not a real window
            continue
        rng.append(max(x[2] for x in bars[i:i + W]) - min(x[3] for x in bars[i:i + W]))
        idx.append(i)
    typ = sorted(rng)[len(rng) // 2] if rng else 0.0
    thr = min_atr * typ
    cands = sorted(((abs(bars[i + W][4] - bars[i][4]), i, bars[i + W][4] - bars[i][4])
                    for i in idx if abs(bars[i + W][4] - bars[i][4]) >= thr), reverse=True)
    runs, used = [], []
    for _, i, mv in cands:
        if not any(abs(i - j) < W for j in used):
            used.append(i)
            runs.append((i, mv))
    runs.sort()
    return runs, typ, thr, len(idx)


def main():
    con = connect(symbol="MNQ")
    bars = load_bars(con)
    print(f"bars 5s from lake: {len(bars):,}  "
          f"{dt.datetime.fromtimestamp(bars[0][0], dt.UTC)} .. {dt.datetime.fromtimestamp(bars[-1][0], dt.UTC)}")

    res = {}

    # ── 1. BASE RATE of the label on the tape ────────────────────────────────────────────
    inwin = sum(1 for b in bars if 13 <= dt.datetime.fromtimestamp(b[0], dt.UTC).hour < 15)
    res["base_rate"] = {
        "bars_total": len(bars),
        "bars_labelled_OPEN_NEWS": inwin,
        "pct_of_tape": round(100 * inwin / len(bars), 2),
        "note": "the label is TRUE on every bar inside 13:00-15:00Z and FALSE on every bar outside; "
                "conditional on the clock its precision is 1.00 and it separates nothing WITHIN the window",
    }

    # ── 2. RUN DENSITY per UTC hour ───────────────────────────────────────────────────────
    runs, typ, thr, nwin = detect_runs(bars)
    hours = {}
    for i, mv in runs:
        h = dt.datetime.fromtimestamp(bars[i][0], dt.UTC).hour
        hours.setdefault(h, []).append(abs(mv))
    barhours = {}
    for b in bars:
        h = dt.datetime.fromtimestamp(b[0], dt.UTC).hour
        barhours[h] = barhours.get(h, 0) + 1
    tot_runs = len(runs)
    per_hour = []
    for h in range(24):
        n = len(hours.get(h, []))
        bh = barhours.get(h, 0)
        share_runs = n / tot_runs if tot_runs else 0
        share_tape = bh / len(bars)
        per_hour.append({
            "hour": h, "runs": n, "bars": bh,
            "pct_runs": round(100 * share_runs, 2), "pct_tape": round(100 * share_tape, 2),
            "lift": round(share_runs / share_tape, 2) if share_tape else None,
            "median_move": round(sorted(hours[h])[len(hours[h]) // 2], 1) if n else None,
        })
    res["per_hour"] = per_hour
    res["detector"] = {"runs": tot_runs, "typ_15m_range": round(typ, 1), "threshold_pt": round(thr, 1),
                       "windows_scanned": nwin, "span": "2026-07-16..2026-08-14"}

    inw = [r for r in runs if 13 <= dt.datetime.fromtimestamp(bars[r[0]][0], dt.UTC).hour < 15]
    res["window_lift"] = {
        "runs_in_window": len(inw), "runs_total": tot_runs,
        "pct_runs_in_window": round(100 * len(inw) / tot_runs, 1),
        "pct_tape_in_window": res["base_rate"]["pct_of_tape"],
        "lift": round((len(inw) / tot_runs) / (inwin / len(bars)), 2),
        "median_move_in": round(sorted(abs(m) for _, m in inw)[len(inw) // 2], 1),
        "median_move_out": round(sorted(abs(m) for i, m in runs if (i, m) not in inw)[
            max(0, (tot_runs - len(inw)) // 2)], 1),
    }

    # ── 3. MINUTE-OF-HOUR — is there a RELEASE footprint (13:30 / 14:00 / 15:00)? ─────────
    mins = {}
    for i, mv in inw:
        t = dt.datetime.fromtimestamp(bars[i][0], dt.UTC)
        key = f"{t.hour:02d}:{t.minute // 5 * 5:02d}"
        mins[key] = mins.get(key, 0) + 1
    res["minute_hist"] = dict(sorted(mins.items()))

    # ── 4. WHAT WOULD THEY HAVE BEEN, without the clock pre-emption? ──────────────────────
    def flow_at(ts):
        return con.execute(f"""SELECT COALESCE(SUM(CASE WHEN aggressor='buy' THEN size
            WHEN aggressor='sell' THEN -size END),0) FROM ticks
            WHERE ts_ms<{ts * 1000} AND ts_ms>={(ts - 60) * 1000}""").fetchone()[0]

    def flow_z(ts, cur):
        if cur is None:
            return None
        t0 = ts - FLOW_Z_LOOKBACK
        mu, sd, n = con.execute(f"""
            WITH s AS (SELECT CAST((ts_ms/1000 - {t0}) / 60 AS INTEGER) b,
                       SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size END) f
                       FROM ticks WHERE ts_ms < {ts * 1000} AND ts_ms >= {t0 * 1000} GROUP BY 1)
            SELECT AVG(f), STDDEV_SAMP(f), COUNT(*) FROM s WHERE f IS NOT NULL""").fetchone()
        if n is None or n < FLOW_Z_MIN_BUCKETS or sd is None or sd <= 0:
            return None
        return (float(cur) - float(mu)) / float(sd)

    idxmap = {b[0]: k for k, b in enumerate(bars)}
    relabel = {}
    rows = []
    for i, mv in inw:
        ts = bars[i][0]
        f = flow_at(ts)
        fz = flow_z(ts, f)
        seg = bars[max(0, i - 60):i]
        amp = (100 * (max(x[2] for x in seg) - min(x[3] for x in seg)) / bars[i][4]) if seg else None
        if f is not None and fz is not None and abs(fz) >= FLOW_Z:
            lab = "FLOW-LED" if (f > 0) == (mv > 0) else "VACUUM"
        elif amp is not None and amp > 0.30:
            lab = "VOL-EXPANSION"
        else:
            lab = "UNCLASS"
        relabel[lab] = relabel.get(lab, 0) + 1
        rows.append({"time": dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%m-%d %H:%M"),
                     "move": round(mv), "flow": None if f is None else round(f),
                     "fz": None if fz is None else round(fz, 2),
                     "amp": None if amp is None else round(amp, 2), "would_be": lab})
    res["relabel_without_clock"] = relabel
    res["relabel_rows"] = rows
    _ = idxmap

    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_hour", "relabel_rows")}, indent=1))
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
