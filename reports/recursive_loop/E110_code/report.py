"""E110 PHASE 0 report: descriptive tables from data/research/E110_census.parquet (spec E110_change.txt A1).
Counts before dollars; every rate carries its n; nothing is selected or ranked. Tails: D1/D2/D4 = all-out result <= -$1k/-$2k/-$4k
at 4 MNQ lots in today's points; M4 = MAE to the +37.5 hit (or flat) >= 4 x ATR14. Rows in a leg are correlated: 'days' columns and
the day-cluster bootstrap CI are the honest unit.

    .venv/bin/python reports/recursive_loop/E110_code/report.py > reports/recursive_loop/E110_census.txt
"""
from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"
PERIODS = ("TRAIN", "TEST", "FORWARD")
RNG = np.random.default_rng(110)


def load() -> pd.DataFrame:
    df = duckdb.connect().execute(f"SELECT * FROM read_parquet('{GB}/data/research/E110_census.parquet')").df()
    df["D1"] = df.usd_allout <= -1000
    df["D2"] = df.usd_allout <= -2000
    df["D4"] = df.usd_allout <= -4000
    df["M4"] = df.mae_to_hit >= 4 * df.atr * df.k
    df["win"] = df.hit37_min.notna()
    df["p_session"] = 1 - df.pos_in_range
    return df


def boot_ci(sub: pd.DataFrame, col: str, reps: int = 400):
    """day-cluster bootstrap 90% CI of the row rate of `col`"""
    g = sub.groupby("sess")[col].agg(["sum", "count"]).to_numpy()
    if len(g) < 5:
        return (np.nan, np.nan)
    idx = RNG.integers(0, len(g), size=(reps, len(g)))
    s, c = g[idx, 0].sum(1), g[idx, 1].sum(1)
    r = s / np.maximum(c, 1)
    return tuple(np.percentile(r, [5, 95]) * 100)


def pct(x):
    return f"{x*100:5.1f}%" if np.isfinite(x) else "   - "


def base_table(df, name, mask):
    print(f"\n  {name}")
    print(f"   {'period':8}{'rows':>9}{'days':>6}{'hit37':>8}{'D1':>7}{'D2':>7}{'D4':>7}{'M4':>7}{'D2 days':>9}{'D4 days':>9}{'mean $':>9}{'med $':>8}")
    for p in PERIODS:
        s = df[mask & (df.period == p)]
        if not len(s):
            continue
        print(f"   {p:8}{len(s):>9,}{s.sess.nunique():>6}{pct(s.win.mean()):>8}{pct(s.D1.mean()):>7}{pct(s.D2.mean()):>7}"
              f"{pct(s.D4.mean()):>7}{pct(s.M4.mean()):>7}{s[s.D2].sess.nunique():>9}{s[s.D4].sess.nunique():>9}"
              f"{s.usd_allout.mean():>9.0f}{s.usd_allout.median():>8.0f}")


def band_table(df, col, edges, labels, mask, title, ci=True):
    print(f"\n  {title}")
    for p in PERIODS:
        s = df[mask & (df.period == p)].copy()
        if not len(s):
            continue
        s["b"] = pd.cut(s[col], edges, labels=labels, right=False)
        d2 = s.D2.mean()
        print(f"   [{p}] rows {len(s):,}, days {s.sess.nunique()}, overall D2 {pct(d2)}   (lift = band D2 rate / overall)")
        print(f"    {'band':>10}{'rows':>9}{'share':>7}{'days':>6}{'hit37':>8}{'D1':>7}{'D2':>7}{'D4':>7}{'M4':>7}{'lift':>6}"
              f"{'D2 90% CI (day-clust)':>24}{'mean $':>8}{'D2 days':>8}{'run_left<10%':>13}")
        for b in labels:
            q = s[s.b == b]
            if not len(q):
                continue
            lo, hi = boot_ci(q, "D2") if ci else (np.nan, np.nan)
            lift = q.D2.mean() / d2 if d2 > 0 else np.nan
            print(f"    {b:>10}{len(q):>9,}{pct(len(q)/len(s)):>7}{q.sess.nunique():>6}{pct(q.win.mean()):>8}{pct(q.D1.mean()):>7}"
                  f"{pct(q.D2.mean()):>7}{pct(q.D4.mean()):>7}{pct(q.M4.mean()):>7}{lift:>6.2f}"
                  f"{f'{lo:5.1f}-{hi:5.1f}%':>24}{q.usd_allout.mean():>8.0f}{q[q.D2].sess.nunique():>8}{pct((q.run_left < .10).mean()):>13}")
        na = s[col].isna().sum()
        if na:
            print(f"    (no value: {na:,} rows)")


def pause_lines(df, mask, col, xs, below=True, title=""):
    """STATIC skip arithmetic (no flat-only path): what pausing the band would have removed."""
    print(f"\n  {title}")
    print(f"   {'period':8}{'x':>6}{'paused':>8}{'D2 caught':>11}{'D4 caught':>11}{'wins paused':>12}{'$ wins forgone':>15}{'$ losses avoided':>17}{'net static $':>13}{'/day':>7}")
    for p in PERIODS:
        s = df[mask & (df.period == p)]
        if not len(s):
            continue
        nd = s.sess.nunique()
        for x in xs:
            m = (s[col] < x) if below else (s[col] >= x)
            q = s[m]
            wf = q.loc[q.usd_allout > 0, "usd_allout"].sum()
            la = -q.loc[q.usd_allout < 0, "usd_allout"].sum()
            print(f"   {p:8}{x:>6}{pct(m.mean()):>8}{pct(q.D2.sum()/max(s.D2.sum(),1)):>11}{pct(q.D4.sum()/max(s.D4.sum(),1)):>11}"
                  f"{pct(q.win.sum()/max(s.win.sum(),1)):>12}{wf:>15,.0f}{la:>17,.0f}{la-wf:>13,.0f}{(la-wf)/nd:>7.0f}")


def main():
    df = load()
    meta = json.load(open(f"{GB}/data/research/E110_census_meta.json"))
    live, leg = df.in_live_window, df.in_leg_window
    allm = pd.Series(True, index=df.index)
    print("E110 PHASE 0 - THE WIDEST-NET CENSUS (descriptive only; spec reports/recursive_loop/E110_change.txt A1)")
    print(f"built {meta['built_at'][:19]}Z  detector sha {meta['sha']}  rows {meta['rows']:,}  S_ref {meta['sref']:.1f}pt (NQ 2025-01-30..07-24)")
    print("Exit model for $: 4 MNQ lots all out at +37.5pt (today's points) from a fill 0.25pt adverse, else marked at the last bar before 20:40Z; $6 fees; no stop.")
    print("Every candidate is independent (no flat-only path): this is WHERE the trades would be and what each would have done, not a desk P&L.")
    print("\n0. DATA & HYGIENE")
    print(f"   dropped: {meta['dropped']}   rolls back-adjusted: {len(meta['rolls'])}")
    for r in meta["rolls"]:
        print(f"     {r['seg']:5} {r['at']}  +{r['gap_pts']}pt ({r['gap_pct']}%)")
    print(f"   overnight-gap sensitivity (NQ 2015-2025-06): {json.dumps(meta['sensitivity'])}")
    for p in PERIODS:
        s = df[df.period == p]
        print(f"   {p:8} sessions {s.sess.nunique():>5}  rows {len(s):>9,}  live-window rows {s.in_live_window.sum():>8,}  leg-window rows {s.in_leg_window.sum():>8,}"
              f"  EST share {pct(1-s.edt.mean())}  roll_adj rows {s.roll_adj.sum():,}")

    print("\n1. BASELINE - every candidate, no filter")
    base_table(df, "LIVE WINDOW (02:00-13:30Z, after the 05:00 Paris veto) - the v1.02 opportunity set", live)
    base_table(df, "LEG-ROBOT WINDOW (06:00-19:40Z)", leg)
    base_table(df, "ALL SLOTS (open+30min .. 19:40Z)", allm)
    base_table(df, "LIVE WINDOW without roll-adjacent sessions", live & ~df.roll_adj)

    F3 = ([0, .05, .10, .15, .25, .50, np.inf], ["0-5%", "5-10%", "10-15%", "15-25%", "25-50%", "50%+"])
    print("\n2. THE OPERATOR'S QUESTION - distance from the MIL extreme (F3 off_extreme = (leg extreme - price) / leg so far), LIVE WINDOW")
    band_table(df, "off_extreme", *F3, live, "F3 off_extreme bands")
    pause_lines(df, live, "off_extreme", (0.05, 0.10, 0.15), True, "STATIC 'pause if within x of the leg extreme' (P1-P3), LIVE WINDOW")
    print("\n   same, LEG-ROBOT WINDOW")
    band_table(df, "off_extreme", *F3, leg, "F3 off_extreme bands (leg window)", ci=False)

    print("\n3. OTHER DEFINITIONS OF 'NEAR THE EXTREME' (LIVE WINDOW)")
    band_table(df, "p_session", *F3, live, "P1 of the cloud draft: distance from the SESSION extreme ahead, as share of session range so far")
    pause_lines(df, live, "p_session", (0.05, 0.10, 0.15), True, "STATIC 'pause if within x of the session extreme'")
    band_table(df, "pos_in_range_360", [0, .5, .85, .95, 1.01], ["<.50", ".50-.85", ".85-.95", ".95+"], live, "F5b position in trailing-360-min range", ci=False)

    print("\n4. LEG STAGE (LIVE WINDOW)")
    band_table(df, "leg_ext_atr", [0, 6, 9, 12, 15, 20, np.inf], ["<6", "6-9", "9-12", "12-15", "15-20", "20+"], live, "F1 leg extension in ATR14", ci=False)
    band_table(df, "leg_ext_frac", [0, .5, .75, 1.0, 1.5, np.inf], ["<.5", ".5-.75", ".75-1", "1-1.5", "1.5+"], live, "F2 leg extension / trailing-250-session median leg", ci=False)
    band_table(df, "leg_age_min", [0, 60, 120, 240, np.inf], ["0-60", "60-120", "120-240", "240+"], live, "F4 leg age (min)", ci=False)
    band_table(df, "rvol30", [0, 1.2, 1.5, 2, np.inf], ["<1.2", "1.2-1.5", "1.5-2", "2+"], live, "F6 rvol30", ci=False)
    tq = df[live & (df.period == "TRAIN")].stall.quantile([.25, .5, .75]).tolist()
    band_table(df, "stall", [0, *tq, 1.01], ["Q1", "Q2", "Q3", "Q4"], live, f"F7 stall (TRAIN quartiles {[round(x,2) for x in tq]})", ci=False)

    print("\n5. SPLITS of F3 (LIVE WINDOW) - EDT/EST and long/short, each shown, never pooled away")
    for nm, m in (("EDT", df.edt), ("EST", ~df.edt), ("LONG", df.dir > 0), ("SHORT", df.dir < 0)):
        band_table(df, "off_extreme", *F3, live & m, f"F3 - {nm}", ci=False)

    print("\n6. WHERE THE EXTREMES ARE (hindsight labels, LIVE WINDOW)")
    for p in PERIODS:
        s = df[live & (df.period == p)]
        if not len(s):
            continue
        t = s[s.D2]
        print(f"   [{p}] all rows {len(s):,}: run_left median {s.run_left.median():.2f}; entered after the leg's final extreme (turn already in, unconfirmed) {pct((s.min_to_turn < 0).mean())};"
              f" in the last 10% of the leg {pct((s.run_left < .10).mean())}")
        if len(t):
            print(f"          D2 rows {len(t):,} on {t.sess.nunique()} days: run_left median {t.run_left.median():.2f}; turn already in {pct((t.min_to_turn < 0).mean())};"
                  f" last 10% {pct((t.run_left < .10).mean())}; off_extreme median {t.off_extreme.median():.3f}; leg age median {t.leg_age_min.median():.0f} min;"
                  f" pos_in_range median {t.pos_in_range.median():.2f}")
            print(f"          D2 share by F3 band: " + ", ".join(f"{b} {pct(((t.off_extreme >= lo) & (t.off_extreme < hi)).mean())}"
                                                              for b, lo, hi in zip(F3[1], F3[0][:-1], F3[0][1:])))
    print("\n7. THE NAMED LIVE ENTRIES (FORWARD)")
    import datetime as dt
    for when in ("2026-10-16 04:00", "2026-10-23 08:15"):
        st = int(dt.datetime.fromisoformat(when + "+00:00").timestamp())
        r = df[df.slot_ts == st]
        print(f"   {when}Z: " + ("not in the candidate set" if r.empty else
              r[["dir", "off_extreme", "p_session", "pos_in_range", "leg_age_min", "leg_ext_atr", "mae_to_hit", "final_pts", "usd_allout", "run_left", "min_to_turn"]].round(3).to_dict("records")[0].__repr__()))


if __name__ == "__main__":
    main()
