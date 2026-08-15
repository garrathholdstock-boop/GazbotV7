#!/usr/bin/env python3
"""AUDIT #8 — does the gold break gate survive on PRODUCTION's bar source?

The lab built its 1-minute OHLC from the depth MID (`minute_bars(q, col="mid")`, a resample of the
250ms quote book). The live shadow folds `md`'s TRADE bars. Those are not the same tape: the mid
moves when nobody trades, and a trade print can sit anywhere inside the spread. A 60-minute extreme
computed from one is not the 60-minute extreme of the other, so the gate does not fire in the same
places — and the shadow would be forward-validating a gate the lab never measured.

The fix is NOT to make production imitate the lab. Production's input is the real one. So: re-run the
two surviving cells with the trigger computed from TRADE bars, race them on the SAME quote book with
the SAME true_pnl, and report what the gate is actually worth on the tape it will really see.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.levelbreak import detect_break, read_book          # noqa: E402
from gf_mgc_tape import VPP, load_quotes, minute_bars           # noqa: E402

FEE_TRUE = 1.50          # the racer crosses both legs; commission only on top


def trade_bars(t0_ms: int, t1_ms: int) -> pd.DataFrame:
    """Production's actual input: 1-min TRADE bars, folded from the 5s tape.

    ⚠ NOT `timeframe='1m'` — the lake holds only 10,888 of those for MGC and they are all `src='v5'`,
    a retired desk. The live shadow's MinuteBars folds md's 5s trade bars into minutes, so that is
    what the comparison must use. Reading the 1m rows instead compares against the wrong desk's tape
    and silently spans a different window.
    """
    from gazbot7 import lake
    c = lake.connect(symbol="MGC")
    df = c.execute(
        "SELECT bar_ts, any_value(open) AS open, max(high) AS high, min(low) AS low, "
        "  arg_max(close, bar_ts) AS close FROM bars "
        "WHERE symbol='MGC' AND timeframe='5s' AND bar_ts BETWEEN ? AND ? "
        "GROUP BY bar_ts ORDER BY bar_ts", [t0_ms // 1000, t1_ms // 1000]).df()
    df.index = pd.to_datetime(df["bar_ts"], unit="s", utc=True)
    g = df.resample("1min")
    return pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(),
                         "low": g["low"].min(), "close": g["close"].last()}).dropna()


def atr14(b: pd.DataFrame) -> pd.Series:
    pc = b["close"].shift(1)
    tr = pd.concat([b["high"] - b["low"], (b["high"] - pc).abs(), (b["low"] - pc).abs()],
                   axis=1).max(axis=1)
    return tr.rolling(14).mean()


def fires(bars: pd.DataFrame, look=60, margin=0.10) -> list[tuple[int, int, float]]:
    """(entry_ms_at_BAR_CLOSE, brk, level) — the close stamp, never the label (the 08-14 look-ahead)."""
    a = atr14(bars)
    h, lo, c = bars["high"].to_numpy(), bars["low"].to_numpy(), bars["close"].to_numpy()
    out, n = [], look + 1
    for i in range(n, len(bars)):
        av = a.iloc[i]
        if not (av > 0):
            continue
        hit = detect_break(h[i - n:i + 1], lo[i - n:i + 1], c[i - n:i + 1], float(av),
                           look_min=look, margin_atr=margin)
        if hit:
            out.append((int(bars.index[i].value // 10**6) + 60_000, hit[0], hit[1]))
    return out


def main() -> None:
    q = load_quotes()
    mid = minute_bars(q, col="mid")
    t0, t1 = int(q.index[0].value // 10**6), int(q.index[-1].value // 10**6)
    trd = trade_bars(t0, t1)
    trd = trd[(trd.index >= mid.index[0]) & (trd.index <= mid.index[-1])]

    print(f"window   {mid.index[0]:%Y-%m-%d} -> {mid.index[-1]:%Y-%m-%d}")
    print(f"mid bars {len(mid):>7,}    trade bars {len(trd):>7,}    "
          f"minutes present in both {len(mid.index.intersection(trd.index)):,}")

    fm, ft = fires(mid), fires(trd)
    sm = {(t // 60_000, b) for t, b, _ in fm}
    st = {(t // 60_000, b) for t, b, _ in ft}
    both = sm & st
    print(f"\nBREAK FIRES   mid-bar {len(sm):>4}   trade-bar {len(st):>4}   "
          f"in BOTH {len(both):>4}")
    if sm and st:
        print(f"  overlap: {len(both)/len(sm):.0%} of the lab's fires survive, "
              f"{len(both)/len(st):.0%} of production's were in the lab")
    print(f"  lab-only {len(sm - both):>4}   production-only {len(st - both):>4}")


if __name__ == "__main__":
    main()


# ════════════════════════════════════════════════════════════════════════════════════════════════
# THE DECISIVE PART — race BOTH fire sets identically and see where the money actually lives
# ════════════════════════════════════════════════════════════════════════════════════════════════
import numpy as np                                                    # noqa: E402

from gf_mgc_tape import race                                          # noqa: E402


def book_rows(con=None):
    """The 250ms depth snapshots, as a numpy-indexable array for causal lookup."""
    from gazbot7 import lake
    c = con or lake.connect(symbol="MGC")
    cols = ", ".join(f"bid{k}p, bid{k}s, ask{k}p, ask{k}s" for k in range(1, 11))
    return c.execute(
        f"SELECT ts_ms, {cols} FROM depth WHERE symbol='MGC' AND bid1p>0 AND ask1p>0 "
        f"AND ask1p-bid1p BETWEEN 0 AND 5 ORDER BY ts_ms").df()


def raced(hits, q, bk, bk_ts, *, band=1.0, stop_atr=3.0, trail_atr=2.0, arm_atr=2.0,
          cap_min=480, cooldown_min=45, bars=None):
    """Apply the HOLE condition and the shipped 45-min PER-SIDE cooldown, then race each survivor.

    ⚠ The cooldown is not a detail: without it this trigger fires 773 times where the shipped cell
    fires 157. Comparing bar sources on the un-cooled trigger compares a gate nobody ships.
    """
    # ⚠ NOT `q.index.view("int64") // 10**6`. This index is datetime64[ms], so .view already gives
    # MILLISECONDS and the divide applies the ms conversion a second time — 1784163780000 becomes
    # 1784163. searchsorted then puts every fire past the end of the tape and the race returns an
    # EMPTY book with no error, which reads exactly like "the gate never fired". Convert explicitly.
    qt = (q.index.tz_convert("UTC").tz_localize(None)
          .astype("datetime64[ms]").astype("int64").to_numpy())
    bid, ask = q["bid1p"].to_numpy(), q["ask1p"].to_numpy()
    a = atr14(bars)
    out, cool = [], {1: -1, -1: -1}
    for ts, brk, level in hits:
        if ts - cool[brk] < cooldown_min * 60_000:
            continue
        j = np.searchsorted(bk_ts, ts, side="right") - 1       # last snapshot AT OR BEFORE
        if j < 0 or ts - bk_ts[j] > 5_000:
            continue
        b = read_book(bk.iloc[j].to_dict(), brk, level, band)
        if b.obstacle != 0:                                     # VACUUM only — the surviving cell
            continue
        i = np.searchsorted(qt, ts, side="left")
        if i >= len(qt):
            continue
        side = -brk                                             # FADE
        k = a.index.get_indexer([pd.Timestamp(ts - 60_000, unit="ms", tz="UTC")], method="ffill")[0]
        atr = float(a.iloc[k]) if k >= 0 else 0.0
        if not (atr > 0):
            continue
        fill_in = ask[i] if side > 0 else bid[i]
        mid_in = (bid[i] + ask[i]) / 2.0
        stop = mid_in - side * stop_atr * atr
        fo, mo, reason, mins, _, _ = race(qt[i:], bid[i:], ask[i:], side, fill_in=fill_in,
                                          mid_in=mid_in, stop=stop, target=None,
                                          trail=trail_atr * atr, cap_ms=cap_min * 60_000,
                                          arm_at=arm_atr * atr)
        cool[brk] = ts
        out.append({"ts": ts, "side": side,
                    "pnl": round(side * (fo - fill_in) * VPP - FEE_TRUE, 2)})
    return pd.DataFrame(out, columns=["ts", "side", "pnl"])


def compare():
    q = load_quotes()
    mid, t0, t1 = minute_bars(q, col="mid"), None, None
    t0 = int(q.index[0].value // 10**6); t1 = int(q.index[-1].value // 10**6)
    trd = trade_bars(t0, t1)
    trd = trd[(trd.index >= mid.index[0]) & (trd.index <= mid.index[-1])]
    bk = book_rows(); bk_ts = bk["ts_ms"].to_numpy()

    rm = raced(fires(mid), q, bk, bk_ts, bars=mid)
    rt = raced(fires(trd), q, bk, bk_ts, bars=trd)
    shared = set(rt["ts"] // 60_000) & set(rm["ts"] // 60_000)
    rm_only = rm[~(rm["ts"] // 60_000).isin(shared)]

    print("\n" + "═" * 78)
    print("HOLE-BREAK FADE, both directions, identical race and cost ($1.50 on crossed fills)")
    print("═" * 78)
    for nm, d in (("LAB   (depth-mid bars)", rm), ("PROD  (md trade bars)", rt),
                  ("  of which LAB-ONLY  ", rm_only)):
        if len(d):
            print(f"{nm}   n={len(d):>4}   net ${d['pnl'].sum():>9,.0f}   "
                  f"exp ${d['pnl'].mean():>7.2f}/tr   win {(d['pnl'] > 0).mean():>5.1%}")


if __name__ == "__main__" and "--race" in sys.argv:
    compare()
