#!/usr/bin/env python3
"""REV3 — Part 2.5 §1c recomputed: the 128 live grind fires by their own 30-minute block.

TWO faults are fixed here.

(1) THE FEE WAS COUNTED TWICE. Rev2 printed this table as `sum(pnl_usd) - sum(fees_usd)`.
    `trades.pnl_usd` is ALREADY net of fees -- store.py:66 says so in the schema ("net of
    fees, venue truth"), pnl.py's docstring says so, and the invariant
    `pnl_usd == (exit-entry)*dir*qty*mult - fees_usd` holds on 765 of 765 rows in the book.
    So the control printed -$1,150.00 where the book says -$958.00, exactly 128 x $1.50 too
    low -- and it CONTRADICTED §1 of its own section, which already had -$958.00 right.

(2) THE BUCKET MEMBERSHIP WAS NOT REPRODUCIBLE. Rev2 printed 51 fires in BUILDING and 99
    outside VIOLENT-WHIPSAW, citing "Movement 3 §8's exact rule and its own ATR tercile
    boundaries (10.17 / 15.09 from regime_blocks.csv)". No reading of that sentence
    reproduces 51/99 -- four were tried, and they disagree with each other as much as with
    Rev2. So this script prints ALL FOUR and lets the spread be the finding, rather than
    picking one and calling it the answer.

The control is specification-INDEPENDENT (it does not use the blocks at all) and is stable
at -$958.00 / -$7.48 a fire. The BUILDING arm is not: its sign FLIPS across the four.

Leave-one-out here is stated rather than assumed: drop the single best DAY (by closed_at UTC
date), report the worst remaining fold. §1's own leave-one-out column uses some other
convention -- it could not be reproduced from the book under day, ISO-week or opened_at
grouping -- so the two columns are NOT comparable and this one is the defined one.

    PYTHONPATH=src .venv/bin/python scripts/rev3_grind_blocks.py
"""
import csv, json, sqlite3, collections, datetime as dt

GB = "/home/alphabot/gazbot7"
SEC = f"{GB}/reports/friday_v7/sections"


def fires():
    c = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    out = []
    for r in c.execute("SELECT * FROM trades WHERE data_quality IS NULL AND gate LIKE 'grind%'"):
        ts = dt.datetime.fromisoformat(r["opened_at"].replace("Z", "+00:00"))
        out.append(dict(blk=int(ts.timestamp()) // 1800 * 1800, pnl=r["pnl_usd"],
                        day=r["closed_at"][:10]))
    return out


def specs():
    """The four defensible readings of 'Movement 3 §8's rule on regime_blocks.csv'."""
    def rd(p):
        return list(csv.DictReader(open(f"{SEC}/{p}/regime_blocks.csv")))

    A = {int(r["blk"]): r["regime"] for r in rd("cs")}

    M = {"BUILD": "BUILDING", "WHIPSAW": "VIOLENT-WHIPSAW", "CHOP": "NORMAL-CHOP",
         "DEAD_CHOP": "DEAD-CHOP", "TREND": "CLEAN-TREND"}
    B = {int(r["blk"]): M.get(r["regime"], "NA") for r in rd("cs2")}

    def m3(ar, er):                       # Movement 3 §8, verbatim
        if ar < 0.70 and er < 0.30: return "DEAD-CHOP"
        if ar >= 1.6 and er < 0.35: return "VIOLENT-WHIPSAW"
        if er >= 0.55: return "CLEAN-TREND"
        if 0.35 <= er < 0.55: return "BUILDING"
        return "NORMAL-CHOP"

    C = {}
    for r in rd("cs2"):
        try: C[int(r["blk"])] = m3(float(r["atr_rel"]), float(r["er30"]))
        except (ValueError, TypeError): C[int(r["blk"])] = "NA"

    D = {}                                # M3 §8's SHAPE, but on the cited 10.17/15.09 terciles
    for r in rd("cs"):
        a, e = float(r["atr"]), float(r["er"])
        D[int(r["blk"])] = ("DEAD-CHOP" if a < 10.17 and e < 0.30 else
                            "VIOLENT-WHIPSAW" if a >= 15.09 and e < 0.35 else
                            "CLEAN-TREND" if e >= 0.55 else
                            "BUILDING" if 0.35 <= e < 0.55 else "NORMAL-CHOP")
    return [
        ("A", "cs/regime_blocks.csv, its own stored labels (gf_cs_regime.py's rule)", A),
        ("B", "cs2/regime_blocks.csv, its own stored labels (cs2_regime.py's rule)", B),
        ("C", "cs2's atr_rel / er30 columns + Movement&nbsp;3&nbsp;&sect;8's rule verbatim", C),
        ("D", "cs's atr / er columns + &sect;8's shape on the cited 10.17 / 15.09 terciles", D),
    ]


def main():
    F = fires()
    TOTW = sum(1 for x in F if x["pnl"] > 0)

    def score(sub, label):
        n = len(sub)
        if not n:
            return dict(arm=label, fires=0)
        net = sum(x["pnl"] for x in sub)
        w = sum(1 for x in sub if x["pnl"] > 0)
        best3 = sorted(sub, key=lambda x: -x["pnl"])[:3]
        byday = collections.defaultdict(float)
        for x in sub: byday[x["day"]] += x["pnl"]
        return dict(arm=label, fires=n, net=round(net, 2), per=round(net / n, 2),
                    win=round(100 * w / n, 1), kept=w, kept_of=TOTW,
                    strip3=round(net - sum(x["pnl"] for x in best3), 2),
                    loo=round(min(net - v for v in byday.values()), 2))

    ctl = score(F, "none (the control) — uses no block labels at all")
    print("CONTROL:", json.dumps(ctl))
    rows = {"control": ctl, "specs": []}
    for key, desc, m in specs():
        lab = {x["blk"]: m.get(x["blk"], "NA") for x in F}
        b = score([x for x in F if lab[x["blk"]] == "BUILDING"], "arm only in BUILDING")
        v = score([x for x in F if lab[x["blk"]] != "VIOLENT-WHIPSAW"], "arm except VIOLENT-WHIPSAW")
        rows["specs"].append(dict(key=key, desc=desc, building=b, except_vw=v))
        print(f"{key}: BUILDING {b['fires']:>3} {b['net']:>9.2f} {b['per']:>7.2f}   "
              f"exVW {v['fires']:>3} {v['net']:>9.2f} {v['per']:>7.2f}")

    bs = [s["building"] for s in rows["specs"]]
    rows["building_sign_flips"] = len({x["net"] > 0 for x in bs}) > 1
    rows["building_per_range"] = [min(x["per"] for x in bs), max(x["per"] for x in bs)]
    rows["building_strip3_all_negative"] = all(x["strip3"] < 0 for x in bs)
    print("\nBUILDING sign flips across specs :", rows["building_sign_flips"])
    print("BUILDING $/fire range            :", rows["building_per_range"])
    print("BUILDING strip-best-3 all negative:", rows["building_strip3_all_negative"])
    json.dump(rows, open(f"{SEC}/rev3_grind_blocks.json", "w"), indent=1)
    print("\nwrote rev3_grind_blocks.json")


main()
