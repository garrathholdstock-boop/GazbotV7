#!/usr/bin/env python3
"""THE MAE STUDY — does this desk have a STOP problem or a TARGET problem?

★ WHY THIS IS #1. The live book is 136 winners at +$62.69 against 400 losers at -$49.59: a 25% hit
  rate at a 1.26:1 payoff where 3:1 is needed. Every route to fixing that runs through one question
  nobody has ever measured here - how far does a trade go AGAINST us before it works? Maximum
  Adverse Excursion is absent from this desk's entire research history, and three independent
  research lenses nominated it as the single highest-value missing measurement.

★ THE METHOD. For every closed trade, walk the 5-second tape from entry to exit and record the
  worst unrealised drawdown (MAE) and best unrealised gain (MFE). Split by EVENTUAL OUTCOME. A stop
  placed just beyond the percentile that keeps 90-95% of eventual WINNERS alive is the tightest stop
  that does not destroy the book's own winners.

⚠ MFE IS NOT A WIN RATE, and this study does not pretend otherwise. MAE and MFE are both measured;
  no claim is made that a target "would have been reached" without racing it against the stop.
⚠ CONTAMINATION (R3): the paper engine's 0.1% adverse fill is 84x punitive on MNQ multi-lot orders,
  so pnl_usd - and therefore the WINNER/LOSER LABEL - is contaminated on the 164 multi-lot trades.
  Everything is reported twice: all trades, and single-lot only.
⚠ LOWER BOUND (R4): IBKR streaming data is aggregated snapshots, not tick-by-tick, so a true MAE
  may be worse than measured. Every percentile here is a FLOOR.
⚠ Trades whose window the tape does not cover are reported as UNMEASURED, never silently dropped.
"""
from __future__ import annotations
import sqlite3
import numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
VPP = 2.0


def load():
    t = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    tr = pd.read_sql("""select id, symbol, side, qty, entry_price, exit_price, opened_at,
        closed_at, pnl_usd, exit_reason, gate, data_quality from trades
        where closed_at is not null and entry_price is not null""", t)
    # ⚠ NEVER ASSUME THE UNIT. pandas 2.x preserves the parsed resolution, so these ISO strings
    # become datetime64[us] and .astype("int64") yields MICROseconds - a //10**9 put every trade in
    # January 1970 and the study measured ZERO of 879 windows. Convert explicitly to seconds.
    # Same family as DuckDB's integer division reading 5s bars as 1m for hours.
    for col, dst in (("opened_at", "t0"), ("closed_at", "t1")):
        tr[dst] = (pd.to_datetime(tr[col], format="mixed", utc=True)
                   .dt.tz_localize(None).astype("datetime64[s]").astype("int64"))
    c = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
    bars = pd.read_sql("select bar_ts, high, low from bars where symbol='MNQ' and timeframe='5s'"
                       " order by bar_ts", c)
    return tr, bars


def excursions(tr, bars):
    ts = bars.bar_ts.values; hi = bars.high.values; lo = bars.low.values
    mae, mfe, ok = [], [], []
    for _, r in tr.iterrows():
        a, b = np.searchsorted(ts, r.t0), np.searchsorted(ts, max(r.t1, r.t0 + 5), side="right")
        if b - a < 1:
            mae.append(np.nan); mfe.append(np.nan); ok.append(False); continue
        h, l = hi[a:b].max(), lo[a:b].min()
        long = str(r.side).upper().startswith(("B", "L"))
        mae.append((r.entry_price - l) if long else (h - r.entry_price))
        mfe.append((h - r.entry_price) if long else (r.entry_price - l))
        ok.append(True)
    tr = tr.copy()
    tr["mae_pt"] = np.maximum(mae, 0); tr["mfe_pt"] = np.maximum(mfe, 0); tr["measured"] = ok
    tr["win"] = tr.pnl_usd > 0
    return tr


def report(df, label):
    m = df[df.measured]
    w, l = m[m.win], m[~m.win]
    print(f"\n{'='*74}\n{label}   n={len(m)} measured  ({len(df)-len(m)} unmeasured)"
          f"   winners {len(w)}  losers {len(l)}\n{'='*74}")
    if not len(w) or not len(l):
        print("  not enough of one class"); return None
    print(f"{'percentile':>12}{'WINNERS mae':>14}{'LOSERS mae':>13}{'winners mfe':>14}")
    for p in (50, 75, 80, 90, 95, 99):
        print(f"{p:>11}%{w.mae_pt.quantile(p/100):>13.1f}pt{l.mae_pt.quantile(p/100):>12.1f}pt"
              f"{w.mfe_pt.quantile(p/100):>13.1f}pt")
    print(f"{'mean':>12}{w.mae_pt.mean():>13.1f}pt{l.mae_pt.mean():>12.1f}pt{w.mfe_pt.mean():>13.1f}pt")

    print(f"\n  ★ THE STOP TABLE — what each stop width would have done to THIS book")
    print(f"{'stop pt':>9}{'$':>8}{'winners kept':>15}{'losers cut early':>18}"
          f"{'loss saved $':>14}{'winner $ lost':>15}{'NET $':>10}")
    best = None
    for s in (5, 8, 10, 12, 15, 20, 25, 30, 40, 60):
        kept = (w.mae_pt <= s).mean()
        cut = (l.mae_pt > s)
        # a loser whose MAE exceeded s would have closed at -s instead of its actual loss
        saved = float((l[cut].pnl_usd.abs() - s * VPP * l[cut].qty).clip(lower=0).sum())
        # a winner whose MAE exceeded s would have been stopped: lose its gain AND pay -s
        hurt = w[w.mae_pt > s]
        lost = float((hurt.pnl_usd + s * VPP * hurt.qty).sum())
        net = saved - lost
        star = ""
        if kept >= 0.90 and (best is None or net > best[1]):
            best = (s, net); star = "  <-"
        print(f"{s:>9}{s*VPP:>8.0f}{100*kept:>14.0f}%{100*cut.mean():>17.0f}%"
              f"{saved:>14,.0f}{lost:>15,.0f}{net:>+10,.0f}{star}")
    print(f"\n  book as it stands: {m.pnl_usd.sum():+,.0f}")
    if best:
        print(f"  best stop keeping >=90% of winners: {best[0]}pt (${best[0]*VPP:.0f}) "
              f"-> book would be {m.pnl_usd.sum()+best[1]:+,.0f}")
    return m


def main():
    tr, bars = load()
    df = excursions(tr, bars)
    print(f"MAE STUDY — {len(df)} closed trades, 5-second tape, MNQ @ ${VPP}/pt")
    print(f"  tape covers {df.measured.sum()} of {len(df)} trade windows")
    report(df, "ALL TRADES")
    report(df[df.qty == 1], "SINGLE-LOT ONLY (clean of the paper engine's multi-lot fill bias)")
    m = df[df.measured & (df.qty == 1)]
    print(f"\n  ── the question behind the question ──")
    w, l = m[m.win], m[~m.win]
    print(f"  a winner goes against us a median {w.mae_pt.median():.1f}pt before it works.")
    print(f"  a loser goes against us a median {l.mae_pt.median():.1f}pt.")
    sep = l.mae_pt.median() - w.mae_pt.median()
    print(f"  separation: {sep:+.1f}pt  -> " + ("THERE IS A STOP THAT SEPARATES THEM"
          if sep > 2 else "THE TWO POPULATIONS OVERLAP - no stop width separates winners from losers"))
    print(f"  winners' MFE median {w.mfe_pt.median():.1f}pt vs the book's median win "
          f"{w.pnl_usd.median()/VPP:.1f}pt -> "
          f"{100*(w.pnl_usd.median()/VPP)/max(w.mfe_pt.median(),1e-9):.0f}% of the favourable "
          f"move was captured")
    df.to_csv(f"{GB}/reports/mae_study_2026-09-13.csv", index=False)
    print(f"\n  per-trade rows -> reports/mae_study_2026-09-13.csv")


if __name__ == "__main__":
    raise SystemExit(main())
