"""LAKE — one DuckDB connection that can read the tape from local Parquet or straight off Backblaze.

Operator, 2026-08-05: "ideally duckdb can query backblaze direct no?" — it can, and now it does.

WHY THIS EXISTS. Every study written before today opened `capture.db` with a SQLite ATTACH. That worked
while capture held 28 days; it holds 5 TRADING days now, and the history lives in Parquet — locally in
`data/tape/` and permanently in B2. Without a single helper, each new harness would hand-roll its own
S3 credentials and path layout, and they would drift.

★ THE TAPE IS PLAINTEXT ON PURPOSE. Market data is what CME sells to anyone; encrypting it bought
nothing and cost the ability to query it in place. The TRADE RECORD (gazbot7.db, configs) stays behind
rclone crypt. See docs/BACKUP_AND_ARCHIVE.md.

MEASURED, B2 direct, no download:
    1,228,928 rows counted                       0.73 s
    7-day sweep, 11,195,683 rows aggregated     12.1  s
    one column across the same files             6.8  s   (pushdown works)

    from gazbot7.lake import connect
    con = connect()                       # local if present, else B2
    con.execute("SELECT count(*) FROM ticks WHERE symbol='MNQ'")

    con = connect(remote=True)            # force B2 even when a local copy exists
"""
from __future__ import annotations

import os
import subprocess

LOCAL = os.environ.get("GAZBOT7_TAPE_LAKE", "/home/alphabot/gazbot7/data/tape")
BUCKET = os.environ.get("GAZBOT7_B2_BUCKET", "gazbotv7")
PREFIX = os.environ.get("GAZBOT7_B2_PREFIX", "plain/tape")
ENDPOINT = os.environ.get("GAZBOT7_B2_S3", "s3.us-east-005.backblazeb2.com")
REGION = os.environ.get("GAZBOT7_B2_REGION", "us-east-005")
STREAMS = ("ticks", "quotes", "bars", "book", "depth")


def _creds() -> tuple[str, str] | None:
    """B2 key from the rclone config — the single source of truth.

    ★ Deliberately NOT hardcoded and NOT read from a repo file. The key lives in
    /root/.config/rclone/rclone.conf (mode 0600) and in the operator's password manager. Committing it
    would put a live storage credential into git history, which is permanent."""
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


def connect(*, remote: bool | None = None, symbol: str = "MNQ"):
    """DuckDB connection with `ticks`/`quotes`/`bars`/`book`/`depth` views over the lake.

    remote=None  → local Parquet if present, otherwise B2
    remote=True  → always B2
    remote=False → always local (raises if absent, rather than silently returning nothing)
    """
    import duckdb

    con = duckdb.connect()
    use_remote = remote
    if use_remote is None:
        use_remote = not os.path.isdir(os.path.join(LOCAL, "ticks"))

    if use_remote:
        c = _creds()
        if not c:
            raise RuntimeError("no b2raw credentials in rclone config — run `rclone config`")
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute(f"SET s3_endpoint='{ENDPOINT}'")
        con.execute(f"SET s3_region='{REGION}'")
        con.execute(f"SET s3_access_key_id='{c[0]}'")
        con.execute(f"SET s3_secret_access_key='{c[1]}'")
        con.execute("SET s3_url_style='path'")     # B2 rejects virtual-host style
        base = f"s3://{BUCKET}/{PREFIX}"
    else:
        if not os.path.isdir(os.path.join(LOCAL, "ticks")):
            raise RuntimeError(f"no local lake at {LOCAL} — pass remote=True")
        base = LOCAL

    for s in STREAMS:
        # A stream with no files yet must not break the whole connection — create what exists and skip
        # the rest, so a partially-populated lake is usable instead of unusable.
        try:
            con.execute(f"CREATE VIEW {s} AS SELECT * FROM read_parquet('{base}/{s}/{symbol}/*.parquet')")
        except Exception:
            continue
    con.execute("CREATE OR REPLACE TABLE _lake_meta AS SELECT ? AS source", [base])
    return con


def source(con) -> str:
    return con.execute("SELECT source FROM _lake_meta").fetchone()[0]
