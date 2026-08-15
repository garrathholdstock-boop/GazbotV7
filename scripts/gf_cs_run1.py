"""CHOP-DAY SCALP — Step 5: first pass over every candidate, at the operator's
guessed exits (bank tiny: 0.5R and 1R off a 1-ATR stop).  IN-SAMPLE ONLY."""
from __future__ import annotations

import pandas as pd

import gf_cs_bt as B
import gf_cs_lib as L

pd.set_option("display.width", 200)

CACHE: dict = {}
GRID = [(1.0, 0.5), (1.0, 1.0), (0.75, 0.75), (1.5, 0.75)]


def main() -> None:
    rows = []
    for name in B.CANDIDATES:
        for ks, kt in GRID:
            t = B.backtest(name, ks, kt, 600, days=L.IS_DAYS, cache=CACHE)
            s = L.stats(t)
            rows.append(dict(cand=name, stop=ks, tgt=kt, **s,
                             days=t["day"].nunique() if len(t) else 0,
                             stops=int((t["reason"] == "STOP").sum()) if len(t) else 0,
                             tgts=int((t["reason"] == "TARGET").sum()) if len(t) else 0,
                             times=int((t["reason"] == "TIME").sum()) if len(t) else 0))
            print(rows[-1], flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(f"{B.OUT}/pass1.csv", index=False)
    print("\n=== PASS 1, in-sample 2026-07-16..08-07 (13 days) ===")
    print(df.sort_values("net", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
