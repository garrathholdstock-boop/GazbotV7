"""CHOP-DAY SCALP — Step 1b: what the LIVE desk did inside each regime block.

Attributes every live MNQ trade to the 30-min regime block it OPENED in, so we can
price the donation the chop scalp is supposed to replace.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs"


def main() -> None:
    blk = pd.read_csv(f"{OUT}/regime_blocks.csv")
    c = sqlite3.connect("/home/alphabot/gazbot7/data/gazbot7.db")
    t = pd.read_sql(
        "SELECT gate, side, qty, opened_at, closed_at, pnl_usd, fees_usd, exit_reason "
        "FROM trades WHERE symbol='MNQ' AND data_quality IS NULL "
        "AND opened_at >= '2026-07-16'", c)
    t["ts"] = (pd.to_datetime(t["opened_at"], utc=True, format="mixed")
               .astype("datetime64[ns, UTC]").astype("int64") // 10**9)
    t["blk"] = t["ts"] - t["ts"] % 1800
    t["net"] = t["pnl_usd"]                      # pnl_usd already net of the $1.50/RT fee?
    m = t.merge(blk[["blk", "day", "regime", "tod", "atr", "er"]], on="blk", how="left")
    m["regime"] = m["regime"].fillna("NO-BLOCK")

    print("=== fee sanity: mean fee per trade per contract ===")
    print((t["fees_usd"] / t["qty"]).describe().round(3).to_string())

    print("\n=== live desk by REGIME (open-block), 07-16..08-14 ===")
    g = m.groupby("regime").agg(n=("net", "size"), net=("net", "sum"),
                                w=("net", lambda s: (s > 0).sum()))
    g["win%"] = (100 * g["w"] / g["n"]).round(1)
    g["$/tr"] = (g["net"] / g["n"]).round(2)
    print(g.sort_values("net").to_string())

    print("\n=== live desk by REGIME x TOD ===")
    g2 = m.groupby(["tod", "regime"]).agg(n=("net", "size"), net=("net", "sum"))
    g2["$/tr"] = (g2["net"] / g2["n"]).round(2)
    print(g2.to_string())

    print("\n=== THIS WEEK 08-10..08-14 by regime ===")
    wk = m[m["opened_at"] >= "2026-08-10"]
    g3 = wk.groupby("regime").agg(n=("net", "size"), net=("net", "sum"),
                                  w=("net", lambda s: (s > 0).sum()))
    g3["$/tr"] = (g3["net"] / g3["n"]).round(2)
    print(g3.to_string())

    print("\n=== THIS WEEK by day x gate ===")
    p = wk.pivot_table(index="gate", columns=wk["opened_at"].str[:10],
                       values="net", aggfunc="sum").fillna(0).round(1)
    p["TOTAL"] = p.sum(axis=1)
    print(p.to_string())
    print("\nday totals:")
    print(wk.groupby(wk["opened_at"].str[:10])["net"].agg(["size", "sum"]).to_string())

    m.to_csv(f"{OUT}/live_by_regime.csv", index=False)


if __name__ == "__main__":
    main()
