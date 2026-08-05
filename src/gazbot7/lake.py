"""LAKE — ONE connection over every tape we own: V5 archive + Parquet lake + hot SQLite.

Operator, 2026-08-05: *"when i ask you what we have you have to scan both. v5 has weeks of this stuff
too."* — and I had reported only the live tier, which understated MGC ticks as 2 days when the true
figure is 14, and MNQ bars as 3.8 weeks when it is 10.2.

★ THAT IS THE POINT OF THIS MODULE. The history lives in THREE places with different lifetimes:

    V5 ARCHIVE   data/v5_parquet/   frozen, ends 2026-07-17   the retired desk's capture
    PARQUET LAKE data/tape/         rolling, never pruned     written nightly by tape_mirror.py
    HOT SQLite   capture.db         5 TRADING days            what the live desk reads

Any answer to "how much tape do we have" that scans one of them is wrong, and being wrong quietly is
the failure this desk keeps repeating (the dashboard showing 6 of 8 gates, the shadow block truncated
to the 12 worst rows). `coverage()` scans all three so nobody has to remember.

★ NO DOUBLE COUNTING. The sources overlap — V5 runs to 07-17 while the lake starts 07-15 for bars — so
rows are taken by BOUNDARY, not unioned blindly: V5 contributes only days strictly before the lake's
earliest, hot contributes only days after the lake's latest (i.e. today, not yet mirrored). Deduping
50M rows on a natural key would be correct too, and far slower.

★ MIND THE GAP. V5 capture stopped 2026-07-17; V7 tick capture began 2026-07-24. For `ticks` there is a
REAL HOLE between them — bars and quotes bridge it, ticks do not. `coverage()` reports gaps explicitly
because a study that assumes contiguity across that seam will be silently wrong.

    from gazbot7.lake import connect, coverage
    con = connect()
    con.execute("SELECT count(*) FROM ticks WHERE symbol='MNQ'")
    for r in coverage(): print(r)          # what we actually hold, all sources
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import sqlite3
import subprocess

GB = "/home/alphabot/gazbot7"
LOCAL = os.environ.get("GAZBOT7_TAPE_LAKE", f"{GB}/data/tape")
V5 = os.environ.get("GAZBOT7_V5_PARQUET", f"{GB}/data/v5_parquet")
CAPTURE = f"{GB}/data/capture.db"
DEPTH = f"{GB}/data/depth.db"
BUCKET = os.environ.get("GAZBOT7_B2_BUCKET", "gazbotv7")
PREFIX = os.environ.get("GAZBOT7_B2_PREFIX", "plain/tape")
ENDPOINT = os.environ.get("GAZBOT7_B2_S3", "s3.us-east-005.backblazeb2.com")
REGION = os.environ.get("GAZBOT7_B2_REGION", "us-east-005")

# stream -> (columns kept, V5 parquet path, V5 time column, V5 seconds-per-unit)
# V5 carries two extra columns (trade_tick.exch, bar_history.recorded_at); selecting an explicit column
# list rather than * keeps the union well-typed instead of relying on positional luck.
STREAMS = {
    "ticks":  (("symbol", "ts_ms", "price", "size", "aggressor"),
               f"{V5}/ticks/trade_tick.parquet", "ts_ms", 1000),
    "quotes": (("symbol", "ts_ms", "bid", "ask", "bid_sz", "ask_sz"),
               f"{V5}/ticks/quote_tick.parquet", "ts_ms", 1000),
    "bars":   (("symbol", "timeframe", "bar_ts", "open", "high", "low", "close", "volume"),
               f"{V5}/alphabot/bar_history.parquet", "bar_ts", 1),
    "book":   (("symbol", "ts_ms", "side", "level", "price", "size"), None, "ts_ms", 1000),
    "depth":  (None, None, "ts_ms", 1000),          # wide table — keep every column
}


def _creds():
    """B2 key from the rclone config — never hardcoded, never committed."""
    try:
        out = subprocess.run(["rclone", "config", "show", "b2raw"],
                             capture_output=True, text=True, timeout=20).stdout
        acct = key = None
        for line in out.splitlines():
            if line.startswith("account"):
                acct = line.split("=", 1)[1].strip()
            elif line.startswith("key"):
                key = line.split("=", 1)[1].strip()
        return (acct, key) if acct and key else None
    except Exception:
        return None


def _lake_days(stream: str, symbol: str) -> set[str]:
    return {os.path.basename(f)[:-8]
            for f in glob.glob(f"{LOCAL}/{stream}/{symbol}/*.parquet")}


def _sql_days(stream: str, symbol: str) -> set[str]:
    db, tbl, col, scale = (DEPTH, "depth_snap", "ts_ms", 1000) if stream == "depth" else \
                          (CAPTURE, stream, "bar_ts" if stream == "bars" else "ts_ms",
                           1 if stream == "bars" else 1000)
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        rows = c.execute(
            f"SELECT DISTINCT CAST({col}/{86400*scale} AS INTEGER) FROM {tbl} WHERE symbol=?",
            (symbol,)).fetchall()
        c.close()
        return {dt.datetime.fromtimestamp(r[0] * 86400, dt.UTC).strftime("%Y-%m-%d") for r in rows}
    except Exception:
        return set()


def _v5_days(stream: str, symbol: str) -> set[str]:
    cols, path, tcol, scale = STREAMS[stream]
    if not path or not os.path.exists(path):
        return set()
    try:
        import duckdb
        c = duckdb.connect()
        rows = c.execute(
            f"SELECT DISTINCT CAST({tcol}/{86400*scale} AS BIGINT) d "
            f"FROM read_parquet('{path}') WHERE symbol=?", [symbol]).fetchall()
        c.close()
        return {dt.datetime.fromtimestamp(r[0] * 86400, dt.UTC).strftime("%Y-%m-%d") for r in rows}
    except Exception:
        return set()


def coverage(symbols=("MNQ", "MGC")) -> list[dict]:
    """What tape we ACTUALLY hold, across all three sources. Reports gaps, because a study that
    assumes contiguity across the V5→V7 seam (07-17 → 07-24) will be silently wrong."""
    out = []
    for stream in STREAMS:
        for sym in symbols:
            v5, lake, hot = _v5_days(stream, sym), _lake_days(stream, sym), _sql_days(stream, sym)
            u = v5 | lake | hot
            if not u:
                out.append({"stream": stream, "symbol": sym, "days": 0, "weeks": 0.0,
                            "v5": 0, "lake": 0, "hot": 0, "span": None, "gaps": []})
                continue
            ds = sorted(u)
            gaps = []
            for a, b in zip(ds, ds[1:]):
                da = dt.date.fromisoformat(a)
                db_ = dt.date.fromisoformat(b)
                # >4 calendar days apart is more than a weekend — a real hole
                if (db_ - da).days > 4:
                    gaps.append(f"{a}..{b}")
            out.append({"stream": stream, "symbol": sym, "days": len(u), "weeks": round(len(u)/5, 1),
                        "v5": len(v5), "lake": len(lake), "hot": len(hot),
                        "span": f"{ds[0]}..{ds[-1]}", "gaps": gaps})
    return out


def connect(*, remote: bool = False, symbol: str = "MNQ", include_v5: bool = True,
            include_hot: bool = True):
    """DuckDB connection with a view per stream spanning V5 + lake + hot.

    remote=True reads the lake from B2 instead of local Parquet (V5 and hot are local-only).
    Each view carries a `src` column ('v5' | 'lake' | 'hot') so a result can always be traced.
    """
    import duckdb

    con = duckdb.connect()
    base = LOCAL
    if remote:
        c = _creds()
        if not c:
            raise RuntimeError("no b2raw credentials in rclone config — run `rclone config`")
        con.execute("INSTALL httpfs; LOAD httpfs;")
        for k, v in (("s3_endpoint", ENDPOINT), ("s3_region", REGION),
                     ("s3_access_key_id", c[0]), ("s3_secret_access_key", c[1]),
                     ("s3_url_style", "path")):
            con.execute(f"SET {k}='{v}'")
        base = f"s3://{BUCKET}/{PREFIX}"

    con.execute(f"ATTACH '{CAPTURE}' AS cap (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DEPTH}' AS dep (TYPE sqlite, READ_ONLY)")

    for stream, (cols, v5path, tcol, scale) in STREAMS.items():
        lake_days = _lake_days(stream, symbol)
        parts = []
        sel = ", ".join(cols) if cols else "*"

        # ── V5: only days STRICTLY BEFORE the lake starts, so the overlap cannot double-count ──
        if include_v5 and v5path and os.path.exists(v5path):
            cut = f"'{min(lake_days)}'" if lake_days else "'9999-12-31'"
            parts.append(
                f"SELECT {sel}, 'v5' AS src FROM read_parquet('{v5path}') "
                f"WHERE symbol='{symbol}' AND "
                f"strftime(to_timestamp({tcol}/{scale}), '%Y-%m-%d') < {cut}")

        if lake_days:
            parts.append(f"SELECT {sel}, 'lake' AS src FROM read_parquet('{base}/{stream}/{symbol}/*.parquet')")

        # ── HOT: only days AFTER the lake's last, i.e. today, not yet mirrored ──
        if include_hot:
            tbl = "dep.depth_snap" if stream == "depth" else f"cap.{stream}"
            hcol = "bar_ts" if stream == "bars" else "ts_ms"
            hscale = 1 if stream == "bars" else 1000
            after = f"'{max(lake_days)}'" if lake_days else "'0000-01-01'"
            parts.append(
                f"SELECT {sel}, 'hot' AS src FROM {tbl} WHERE symbol='{symbol}' AND "
                f"strftime(to_timestamp({hcol}/{hscale}), '%Y-%m-%d') > {after}")

        if not parts:
            continue
        try:
            con.execute(f"CREATE VIEW {stream} AS " + " UNION ALL ".join(parts))
        except Exception:
            continue   # a stream with no usable source must not break the whole connection
    return con
