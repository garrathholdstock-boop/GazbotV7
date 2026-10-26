"""MANIFEST for the 2026-10-26 market-research pull (MES, M2K, MYM, MBT from IBKR). Read-only on the data; writes
reports/research/markets/MANIFEST_2026-10-26.{json,md}, which are also copied to B2 next to the raw files."""
import datetime as dt, glob, hashlib, json, os, re
import duckdb

GB = "/home/alphabot/gazbot7"
SYMS = ("MES", "M2K", "MYM", "MBT")
NAMES = {"MES": "Micro E-mini S&P 500 (CME)", "M2K": "Micro E-mini Russell 2000 (CME)", "MYM": "Micro E-mini Dow (CBOT)", "MBT": "Micro Bitcoin (CME)"}
PAT = re.compile(r"^(?P<sym>[A-Z0-9]+)_(?P<con>[A-Z0-9]+)_(?P<tf>1day|1hour|5mins|1min)\.parquet$")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def span(con, p, col):
    n, lo, hi = con.execute(f"SELECT count(*), min({col}), max({col}) FROM read_parquet('{p}')").fetchone()
    f = lambda t: dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ") if t is not None else None
    return int(n), f(lo), f(hi)


con = duckdb.connect(); out = {"created": dt.datetime.now(dt.timezone.utc).isoformat(), "pulled_by": "scripts/backfill_history.py --symbols MES,M2K,MYM,MBT --since 2026-07-20",
                             "source": "Interactive Brokers historical data via the desk's gateway (paper account DU..., read-only, clientId 81), TRADES bars, UTC epoch seconds",
                             "purpose": "operator market-suitability research 2026-10-26: are the MILs cleaner on another index? (reports/research/markets/)",
                             "b2": {"raw": "b2raw:gazbotv7/plain/backfill/", "lake": "b2raw:gazbotv7/plain/tape/bars/<SYM>/"},
                             "caveat": "lake backfill_<tf>.parquet dedups overlapping contracts by bar_ts keeping an arbitrary contract at the roll; research builds the front month per session by volume from the RAW per-contract files.",
                             "raw": [], "lake": []}
for p in sorted(glob.glob(f"{GB}/data/backfill/*.parquet")):
    m = PAT.match(os.path.basename(p))
    if not m or m["sym"] not in SYMS:
        continue
    n, lo, hi = span(con, p, "ts")
    out["raw"].append({"file": os.path.basename(p), "symbol": m["sym"], "instrument": NAMES[m["sym"]], "contract": m["con"], "timeframe": m["tf"],
                       "rows": n, "first": lo, "last": hi, "bytes": os.path.getsize(p), "sha256": sha(p)})
for s in SYMS:
    for p in sorted(glob.glob(f"{GB}/data/tape/bars/{s}/backfill_*.parquet")):
        n, lo, hi = span(con, p, "bar_ts")
        out["lake"].append({"file": f"{s}/{os.path.basename(p)}", "symbol": s, "rows": n, "first": lo, "last": hi, "bytes": os.path.getsize(p), "sha256": sha(p)})
base = f"{GB}/reports/research/markets/MANIFEST_2026-10-26"
json.dump(out, open(base + ".json", "w"), indent=1)
L = [f"# Market-research data manifest (2026-10-26)", "", f"Source: {out['source']}", f"Pulled by: `{out['pulled_by']}`", f"Purpose: {out['purpose']}",
     f"B2: raw `{out['b2']['raw']}` · lake `{out['b2']['lake']}`", f"Caveat: {out['caveat']}", "", "## Raw per-contract files", "",
     "| file | instrument | contract | tf | rows | first | last |", "|---|---|---|---|---|---|---|"]
L += [f"| {r['file']} | {r['instrument']} | {r['contract']} | {r['timeframe']} | {r['rows']:,} | {r['first']} | {r['last']} |" for r in out["raw"]]
L += ["", "## Lake files (data/tape/bars/<SYM>/)", "", "| file | rows | first | last |", "|---|---|---|---|"]
L += [f"| {r['file']} | {r['rows']:,} | {r['first']} | {r['last']} |" for r in out["lake"]]
open(base + ".md", "w").write("\n".join(L) + "\n")
print(f"manifest: {len(out['raw'])} raw files, {len(out['lake'])} lake files -> {base}.json/.md")
