#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 0b: INTERROGATE THE CLUSTER LABEL BEFORE BUILDING ANYTHING ON IT.

The census calls a run FLOW-LED when, in the 60 seconds before it started, net aggressor flow was a
>=1-sigma event against its own trailing 2h AND its sign agreed with the direction the run then went:

    if flow is not None and fz is not None and abs(fz) >= FLOW_Z:
        return "FLOW-LED" if (flow > 0) == (mv > 0) else "VACUUM"

Two things have to be true for that to be a FOOTPRINT rather than a name:
  (1) it must be RARE on ordinary tape (a label true on most bars separates nothing), and
  (2) runs must wear it MORE OFTEN than ordinary tape does (lift > 1).

This measures both on the full lake (28 tick-days, 35k minutes), plus the label's precision/recall
as a run predictor and the raw directional content of the flow event itself.

Writes reports/friday_v7/sections/fl/label.json
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

FEAT = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl/feat.csv"
OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl/label.json"
FLOW_Z = 1.0
MIN_ATR = 1.5
W = 15    # the census run window, in minutes


def detect_runs(df, min_atr=MIN_ATR):
    """The census detector at 1-minute granularity: a 15-min close-to-close move >= min_atr x the
    typical 15-min hi-lo range, overlaps deduped keep-strongest, never straddling a session gap."""
    c = df["close"].to_numpy(float)
    hi = df["hi"].to_numpy(float)
    lo = df["lo"].to_numpy(float)
    ts = df["ts"].to_numpy("int64")
    ok, rng = [], []
    for i in range(len(df) - W):
        if ts[i + W] - ts[i] != W * 60:
            continue
        ok.append(i)
        rng.append(hi[i:i + W + 1].max() - lo[i:i + W + 1].min())
    typ = float(np.median(rng))
    thr = min_atr * typ
    cands = sorted(((abs(c[i + W] - c[i]), i, c[i + W] - c[i]) for i in ok
                    if abs(c[i + W] - c[i]) >= thr), reverse=True)
    runs, used = [], []
    for _, i, mv in cands:
        if not any(abs(i - j) < W for j in used):
            used.append(i)
            runs.append((i, mv))
    runs.sort()
    return runs, typ, thr, len(ok)


def main():
    df = pd.read_csv(FEAT)
    res = {"tape": {"minutes": len(df), "days": int(df["day"].nunique()),
                    "span": f"{df['day'].min()}..{df['day'].max()}"}}

    fz = df["fz"].to_numpy(float)
    flow = df["flow"].to_numpy(float)
    have = ~np.isnan(fz)

    # ── 1. BASE RATE: how much of ordinary tape wears a >=1-sigma flow event at all ───────────
    ev = have & (np.abs(fz) >= FLOW_Z)
    res["base_rate"] = {
        "minutes_with_fz": int(have.sum()),
        "flow_events_|fz|>=1": int(ev.sum()),
        "pct_of_tape": round(100 * ev.sum() / have.sum(), 2),
        "note": "this is the FLOW-EVENT rate; FLOW-LED additionally needs the sign to agree with the "
                "move that follows, VACUUM is the same event with the sign disagreeing — so the pair "
                "SPLITS this slice of tape and neither can be rarer than it",
    }
    for z in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        res["base_rate"][f"pct_|fz|>={z}"] = round(100 * (have & (np.abs(fz) >= z)).sum() / have.sum(), 2)

    # a directionally-labelled version of the label on ORDINARY tape (using the next 15 min as "the
    # move", exactly as the census uses the run's own direction)
    f15 = df["fwd15"].to_numpy(float)
    lab_ok = ev & ~np.isnan(f15) & (f15 != 0)
    agree = lab_ok & ((flow > 0) == (f15 > 0))
    res["base_rate"]["pct_tape_FLOW_LED_by_same_rule"] = round(
        100 * agree.sum() / (have & ~np.isnan(f15)).sum(), 2)
    res["base_rate"]["pct_tape_VACUUM_by_same_rule"] = round(
        100 * (lab_ok & ~((flow > 0) == (f15 > 0))).sum() / (have & ~np.isnan(f15)).sum(), 2)

    # ── 2. THE RUNS on the same tape, and what they wear ─────────────────────────────────────
    runs, typ, thr, nwin = detect_runs(df)
    res["detector"] = {"runs": len(runs), "typ_15m_range_pt": round(typ, 1),
                       "threshold_pt": round(thr, 1), "windows_scanned": nwin,
                       "note": "1-min granularity port of run_census.py's 5s detector, run over the "
                               "whole lake instead of the 5-day capture window"}
    labels, rows = {}, []
    for i, mv in runs:
        f, z = flow[i], fz[i]
        if not np.isnan(z) and abs(z) >= FLOW_Z:
            lab = "FLOW-LED" if (f > 0) == (mv > 0) else "VACUUM"
        else:
            lab = "OTHER"
        labels[lab] = labels.get(lab, 0) + 1
        rows.append({"time": pd.to_datetime(df["ts"].iloc[i], unit="s", utc=True).strftime("%m-%d %H:%M"),
                     "move": round(float(mv), 1), "flow": round(float(f), 1),
                     "fz": None if np.isnan(z) else round(float(z), 2), "label": lab})
    res["runs_by_label"] = labels
    res["run_rows"] = rows

    # ── 3. LIFT — is a run MORE likely to wear the label than ordinary tape is? ───────────────
    run_idx = np.zeros(len(df), bool)
    for i, _ in runs:
        run_idx[i] = True
    p_run = run_idx.sum() / have.sum()
    p_run_given_ev = run_idx[ev].sum() / max(1, ev.sum())
    nfl = labels.get("FLOW-LED", 0)
    res["lift"] = {
        "P(run start) on any minute": round(p_run, 5),
        "P(run start | |fz|>=1)": round(p_run_given_ev, 5),
        "lift_flow_event": round(p_run_given_ev / p_run, 2) if p_run else None,
        "pct_runs_labelled_FLOW_LED": round(100 * nfl / len(runs), 1),
        "pct_tape_wearing_a_flow_event": res["base_rate"]["pct_of_tape"],
        "verdict_note": "if the share of RUNS that are FLOW-LED is no higher than the share of TAPE "
                        "carrying a same-signed flow event, the label carries no information about runs",
    }

    # ── 4. PRECISION / RECALL of the label as a run predictor, by threshold ───────────────────
    pr = []
    for z in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        sig = have & (np.abs(fz) >= z)
        hits = run_idx[sig].sum()
        pr.append({"fz_min": z, "signals": int(sig.sum()),
                   "runs_caught": int(hits),
                   "precision_pct": round(100 * hits / max(1, sig.sum()), 3),
                   "recall_pct": round(100 * hits / max(1, run_idx.sum()), 1),
                   "lift": round((hits / max(1, sig.sum())) / p_run, 2) if p_run else None})
    res["precision_recall"] = pr

    # ── 5. the RAW directional content of the flow event (the mechanism under the label) ──────
    dirn = np.sign(flow)
    edge = []
    for z in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        for n in (5, 15, 30):
            col = df[f"fwd{n}"].to_numpy(float)
            m = have & (np.abs(fz) >= z) & ~np.isnan(col)
            if m.sum() < 30:
                continue
            signed = dirn[m] * col[m]
            edge.append({"fz_min": z, "horizon_min": n, "n": int(m.sum()),
                         "mean_pt_in_flow_direction": round(float(signed.mean()), 3),
                         "median": round(float(np.median(signed)), 3),
                         "pct_positive": round(100 * float((signed > 0).mean()), 1),
                         "t_stat": round(float(signed.mean() / (signed.std(ddof=1) / np.sqrt(len(signed)))), 2)})
    res["raw_directional_edge"] = edge

    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "run_rows"}, indent=1))
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
