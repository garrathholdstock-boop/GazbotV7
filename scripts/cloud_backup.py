#!/usr/bin/env python3
"""OFF-BOX BACKUP to Backblaze B2 (or any rclone remote). CREDENTIALS NOT INCLUDED.

Operator, 2026-08-04: "cant we backup to a backup service like backblaze? cheaper than doubling my HD
on the server" — then "write the script and timer, leave creds blank."

★★ NOTHING LEAVES THIS BOX UNTIL YOU RUN `rclone config`. If the remote named in REMOTE does not exist,
every tier logs "remote not configured" and exits 0. That is deliberate: a backup job that fails loudly
into a page at 03:00 for a machine that was never configured is worse than useless. Check with
`--dry-run` first — it prints the exact file list and byte count that WOULD upload, and uploads nothing.

WHY OFF-BOX AT ALL. The local backups are on the SAME DISK as the thing they protect, so today they
guard against accidental deletion and nothing else. And they are a hidden 2x multiplier: every GB of
capture.db costs 1 GB live plus 2 GB of local copies. B2 is ~$6/TB/month, so the entire ~25 GB need is
about $0.15/month against $10-40/month for more server disk.

★ WHAT MATTERS MOST IS THE SMALLEST FILE. data/gazbot7.db is ~700 KB and holds every trade, order and
position the desk has ever recorded — the only file that cannot be reconstructed from anywhere. capture
and depth are market data: losing them costs research tape, not desk state, and they rebuild forward
from the feed. So the tiers are sized by IRREPLACEABILITY, not by bytes.

★ SQLITE IS NEVER COPIED LIVE. A running SQLite database in WAL mode cannot be safely `cp`-ed — you get
a torn file that may or may not open. Every DB is snapshotted with `VACUUM INTO` first (the same
mechanism gazbot7-backup already uses), then the SNAPSHOT is uploaded and deleted.

★ ENCRYPTION IS AN RCLONE CONCERN, NOT THIS SCRIPT'S. Point REMOTE at an rclone `crypt` remote and
Backblaze only ever holds ciphertext. These are financial records, so that is the recommended setup —
see SETUP below. The trade-off is that a lost passphrase means lost backups; store it somewhere else.

SETUP (run as root, once, when you have the key):
    rclone config
      n) new remote -> name: b2raw -> storage: b2 -> account: <keyID> -> key: <applicationKey>
      n) new remote -> name: gaz   -> storage: crypt
         remote: b2raw:<your-bucket>/gazbot7
         filename_encryption: standard ; password: <passphrase you keep elsewhere>
    rclone lsd gaz:            # should succeed and list nothing
    PYTHONPATH=src .venv/bin/python scripts/cloud_backup.py --tier state --dry-run

USAGE
    --tier state    ~1 MB   gazbot7.db + configs        hourly      (the irreplaceable set)
    --tier archive  ~10 GB  capture.db + depth.db       daily, halt (research tape)
    --tier cold     ~12 GB  the frozen V5 archive       once, by hand
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

GB = "/home/alphabot/gazbot7"
REMOTE = os.environ.get("GAZBOT7_BACKUP_REMOTE", "gaz:")   # set to your rclone remote (crypt advised)
LOG = f"{GB}/data/cloud_backup.log"
# ★ Cap the upload so a backup can never starve the market-data feed. 8 MB/s is generous off-hours and
# invisible during the halt; raise it only if you have measured headroom.
BWLIMIT = os.environ.get("GAZBOT7_BACKUP_BWLIMIT", "8M")

TIERS = {
    # tier: (label, [(path, is_sqlite)], keep_versions)
    "state": ("irreplaceable desk state", [
        (f"{GB}/data/gazbot7.db", True),
        (f"{GB}/data/exit_overrides.json", False),
        (f"{GB}/data/gate_switches.env", False),
        (f"{GB}/data/config_journal.jsonl", False),
        (f"{GB}/data/router_trial_log.txt", False),
        (f"{GB}/data/shadow.db", True),
    ], 30),
    "archive": ("research tape", [
        (f"{GB}/data/depth.db", True),
        (f"{GB}/data/capture.db", True),
    ], 2),
    "cold": ("frozen V5 archive (one-shot)", [
        ("/home/alphabot/alphabot2/data/alphabot.db", True),
        ("/home/alphabot/alphabot2/data/ticks.db", True),
    ], 1),
}


def log(msg: str) -> None:
    line = f"{dt.datetime.now(dt.UTC):%FT%TZ} {msg}"
    print(line)
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def remote_ok() -> bool:
    """True only if the rclone remote actually exists AND answers."""
    try:
        r = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True, timeout=30)
        name = REMOTE.split(":")[0] + ":"
        if name not in (r.stdout or ""):
            return False
        r2 = subprocess.run(["rclone", "lsd", REMOTE, "--max-depth", "1"],
                            capture_output=True, text=True, timeout=60)
        return r2.returncode == 0
    except Exception:
        return False


def snapshot(path: str, into: str) -> str | None:
    """Consistent copy. SQLite goes through VACUUM INTO — a live WAL database must never be cp-ed."""
    dst = os.path.join(into, os.path.basename(path))
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        try:
            con.execute("VACUUM INTO ?", (dst,))
        finally:
            con.close()
        return dst
    except Exception as e:
        log(f"  VACUUM INTO failed for {os.path.basename(path)}: {e}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=sorted(TIERS), required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="print exactly what WOULD upload, upload nothing")
    a = ap.parse_args()
    label, items, keep = TIERS[a.tier]
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")

    present = [(p, s) for p, s in items if os.path.exists(p)]
    total = sum(os.path.getsize(p) for p, _ in present)
    log(f"tier={a.tier} ({label}) — {len(present)} file(s), {total/1e9:.2f} GB, remote={REMOTE}")
    for p, is_sql in present:
        log(f"   {os.path.getsize(p)/1e6:>9.1f} MB  {p}{'  [sqlite -> VACUUM INTO]' if is_sql else ''}")

    if a.dry_run:
        log("DRY RUN — nothing uploaded. Configure with `rclone config`, then re-run without --dry-run.")
        return 0
    if not remote_ok():
        log(f"remote '{REMOTE}' NOT CONFIGURED — nothing uploaded, exiting cleanly. "
            f"See the SETUP block in this file.")
        return 0                      # ★ never fail the host timer for an unconfigured backup

    tmp = tempfile.mkdtemp(prefix="gazbak-", dir="/tmp")
    try:
        staged = []
        for p, is_sql in present:
            if is_sql:
                s = snapshot(p, tmp)
                if s:
                    staged.append(s)
            else:
                d = os.path.join(tmp, os.path.basename(p))
                shutil.copy2(p, d)
                staged.append(d)
        if not staged:
            log("nothing staged — aborting")
            return 0
        dest = f"{REMOTE}{a.tier}/{stamp}/"
        cmd = ["rclone", "copy", tmp, dest, "--bwlimit", BWLIMIT, "--transfers", "2",
               "--retries", "3", "--stats", "0", "--log-level", "NOTICE"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if r.returncode != 0:
            log(f"UPLOAD FAILED rc={r.returncode}: {(r.stderr or '')[:300]}")
            return 0
        up = sum(os.path.getsize(s) for s in staged)
        log(f"uploaded {len(staged)} file(s), {up/1e9:.2f} GB -> {dest}")

        # prune old versions remotely — keep N most recent stamped directories for this tier
        r2 = subprocess.run(["rclone", "lsf", f"{REMOTE}{a.tier}/", "--dirs-only"],
                            capture_output=True, text=True, timeout=120)
        dirs = sorted(x.strip("/") for x in (r2.stdout or "").splitlines() if x.strip())
        for old in dirs[:-keep] if keep else []:
            subprocess.run(["rclone", "purge", f"{REMOTE}{a.tier}/{old}"],
                           capture_output=True, text=True, timeout=600)
            log(f"  pruned old version {old}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)   # ★ staged snapshots never linger on the full disk
    return 0


if __name__ == "__main__":
    sys.exit(main())
