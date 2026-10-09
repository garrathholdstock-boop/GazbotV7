"""S4 pre-launch check, zero model cost: replay the harness's v3 labeller (is_claim, entry_gate) over RECORDED S1b/S3 trades."""
from __future__ import annotations
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import sim_week_recursive as SW   # noqa: E402


def replay(tag: str):
    rows, claims = [], []
    for p in sorted(glob.glob(f"{SW.OUT}/{tag}_????-??-??.json")):
        r = json.load(open(p))
        bars, _ = SW.load_day(r["day"])
        ts = sorted(r["trades"], key=lambda t: t["opened"])
        for i, t in enumerate(ts):
            oe = SW._ep(t["opened"])
            upto = [b for b in bars if b[0] <= oe]
            done = [x for x in ts[:i] if SW._ep(x["closed"]) <= oe]
            card = SW.day_card(upto, oe, None, done)
            side_ok = any(t["side"] in q["sides"] for q in card["entry_test"]["passes"])
            rows.append({"day": r["day"], "n": i + 1, "gate": "pass" if side_ok else "violating",
                         "after_claim": bool(done and SW.is_claim(done[-1], upto)), "pnl": t["pnl_usd"]})
            cb = [b for b in bars if b[0] <= SW._ep(t["closed"])]
            claims.append({"claim": SW.is_claim(t, cb), "pts": t["points"], "usd": t["pnl_usd"]})
    return rows, claims


def main():
    out = []
    for tag in ("sline_s1b", "sline_s3"):
        rows, cl = replay(tag)
        n = len(rows)
        v = [x for x in rows if x["gate"] == "violating"]
        ps = [x for x in rows if x["gate"] == "pass"]
        green = [c for c in cl if c["usd"] > 0]
        out.append(f"{tag}: trades {n}; v3 gate PASS {len(ps)} ({len(ps)/n:.0%}, net ${sum(x['pnl'] for x in ps):,.0f}), "
                   f"VIOLATING {len(v)} ({len(v)/n:.0%}, net ${sum(x['pnl'] for x in v):,.0f})")
        out.append(f"  green trades {len(green)}; of those under 25pt {sum(1 for c in green if c['pts'] < 25)}, "
                   f"under $200 {sum(1 for c in green if c['usd'] < 200)}; v3 CLAIMS (>=2xATR14 and >=$200) {sum(1 for c in cl if c['claim'])}")
        out.append(f"  entries made right after a v3 claim: {sum(1 for x in rows if x['after_claim'])}; "
                   f"of those PASS {sum(1 for x in rows if x['after_claim'] and x['gate']=='pass')}")
    print("\n".join(out))


if __name__ == "__main__":
    main()
