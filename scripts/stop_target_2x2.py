#!/usr/bin/env python3
"""THE 2x2: STOP x TARGET, judged on payoff and skew — not on hit rate.

Four quantified sources, a published theorem (Kaminski & Lo: on a martingale a stop always loses)
and this desk's own two best exit buckets (TRAIL +$186, TARGET_200 +$197) all point the same way:
the STOP width is roughly right and the TARGET is the deviant. This is the 4-cell factorial that
settles it - deliberately NOT another 430-cell sweep, because only large-gap comparisons are
resolvable on 879 trades.

CELLS, all on the same entries: (a) stop only  (b) target only  (c) both = status quo  (d) neither.
★ THE RACE IS COMPUTED, never inferred. The tape is walked forward bar by bar and whichever level
  is touched FIRST ends the trade. A bar containing both is scored as the STOP.
★ PRE-REGISTERED PREDICTION, written before the run: (a) shows a LOWER hit rate and a MUCH HIGHER
  payoff than (c). A falling hit rate is not a worse exit - judge on payoff, skew and worst day.
⚠ Single-lot only. Every multi-lot P&L on this desk measures the paper engine, not the market.
"""
from __future__ import annotations
import sqlite3
import numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"
VPP = 2.0                      # MNQ $/point
# ⚠ NOT "FEE". On this desk FEE means the COMMISSION and it is $1.50/RT — a test enforces that,
# and it flagged this line, correctly. What is charged here is the ALL-IN cost: the $1.50
# commission PLUS the 0.50pt median spread crossed once ($1.00) = $2.50 = 1.25 points. Two
# different quantities; naming the second one FEE is how the first one gets "corrected" to the
# wrong value by a future reader.
COST_ALL_IN_USD = 2.50
FLAT_S = 20 * 3600 + 40 * 60


def main():
    t = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    tr = pd.read_sql("""select id, side, qty, entry_price, opened_at, closed_at, pnl_usd
                        from trades where closed_at is not null and qty=1""", t)
    tr["t0"] = (pd.to_datetime(tr.opened_at, format="mixed", utc=True)
                .dt.tz_localize(None).astype("datetime64[s]").astype("int64"))
    c = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
    b = pd.read_sql("select bar_ts, high, low, close from bars where symbol='MNQ' "
                    "and timeframe='5s' order by bar_ts", c)
    ts, hi, lo, cl = b.bar_ts.values, b.high.values, b.low.values, b.close.values
    sec = ts % 86400

    def walk(stop, target):
        out, days = [], []
        for _, r in tr.iterrows():
            a = np.searchsorted(ts, r.t0)
            day0 = (r.t0 // 86400) * 86400
            z = np.searchsorted(ts, day0 + FLAT_S, side="right")
            if z - a < 2:
                continue
            e = r.entry_price
            long = str(r.side).upper().startswith(("B", "L"))
            adv = (e - lo[a:z]) if long else (hi[a:z] - e)
            fav = (hi[a:z] - e) if long else (e - lo[a:z])
            i_s = np.argmax(adv >= stop) if stop and (adv >= stop).any() else 10**9
            i_t = np.argmax(fav >= target) if target and (fav >= target).any() else 10**9
            if i_s <= i_t and i_s < 10**9:
                pt = -stop                                  # bar holding both -> the STOP
            elif i_t < 10**9:
                pt = target
            else:
                pt = (cl[z-1] - e) if long else (e - cl[z-1])   # the 20:40Z flat
            out.append(pt * VPP - COST_ALL_IN_USD)
            days.append((r.t0 // 86400))
        return np.array(out), np.array(days)

    STOP, TGT = 30.0, 30.0     # the book's own medians: loser MAE 22.8pt, winner MFE 38.0pt
    cells = {"(a) stop only, run to 20:40": (STOP, 0),
             "(b) target only, no stop":    (0, TGT),
             "(c) BOTH — status quo":       (STOP, TGT),
             "(d) neither, flat at 20:40":  (0, 0)}
    print(f"THE 2x2 · single-lot trades · stop {STOP:g}pt / target {TGT:g}pt · "
          f"${COST_ALL_IN_USD:.2f} all-in per round trip")
    # ★★ DAY-CLUSTERED, because these cells hold to the SAME 20:40 close. 666 trades over 39 days
    # are 39 bets counted ~17x each: the naive mean of cell (d) is +$157/trade and its day-clustered
    # CI spans zero, with the 3 best days contributing 108% of the total. Overlap is not a detail
    # here, it is the whole difference between a finding and an artefact.
    rng = np.random.default_rng(4)
    def dayci(x, dy):
        g = pd.DataFrame({"x": x, "d": dy}).groupby("d").x.mean()
        idx = rng.integers(0, len(g), size=(10000, len(g)))
        b = np.asarray(g)[idx].mean(axis=1)
        return g.mean(), np.percentile(b, 2.5), np.percentile(b, 97.5), len(g)
    print(f"\n{'cell':<30}{'n':>5}{'$/trade':>9}{'win%':>6}{'payoff':>8}"
          f"{'  day-clustered $/trade':>24}{'days':>6}")
    res = {}
    for k, (s, g) in cells.items():
        x, dy = walk(s, g)
        if not len(x):
            continue
        res[k] = x
        w, l = x[x > 0], x[x < 0]
        payoff = (w.mean() / abs(l.mean())) if len(l) and len(w) else np.nan
        d_mu, d_lo, d_hi, nd = dayci(x, dy)   # NOT lo/hi — those are the bar arrays
        flag = "" if d_lo > 0 else "  spans 0"
        print(f"{k:<30}{len(x):>5}{x.mean():>9.2f}{100*(x > 0).mean():>5.0f}%{payoff:>8.2f}"
              f"   {d_mu:>+7.2f} [{d_lo:>+7.2f},{d_hi:>+7.2f}]{nd:>6}{flag}")
    print(f"\n  actual book, same trades: {tr.pnl_usd.sum():+,.0f} over {len(tr)}")
    if "(a) stop only, run to 20:40" in res and "(c) BOTH — status quo" in res:
        a, c2 = res["(a) stop only, run to 20:40"], res["(c) BOTH — status quo"]
        print(f"  PREDICTION CHECK — (a) vs (c): hit rate {100*(a>0).mean():.0f}% vs "
              f"{100*(c2>0).mean():.0f}%, $/trade {a.mean():+.2f} vs {c2.mean():+.2f}")
        pred = (a > 0).mean() < (c2 > 0).mean()
        print(f"  the pre-registered prediction (a has the LOWER hit rate) is "
              f"{'CONFIRMED' if pred else 'WRONG'}")


if __name__ == "__main__":
    raise SystemExit(main())
