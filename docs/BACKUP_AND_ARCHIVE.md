# BACKUP & ARCHIVE — Backblaze B2, the Parquet lake, and how to restore

Built 2026-08-04/05. **Read this before changing retention, deleting anything, or debugging a backup.**

---

## 1. The shape of it

```
LIVE (SQLite, hot)          capture.db   5 TRADING days   ~6 GB   what the desk reads
                            depth.db     28 days          ~2.5 GB 10-level L2
                            gazbot7.db   forever          ~0.8 MB THE irreplaceable file
                                 │
                                 ▼  scripts/tape_mirror.py  (daily 21:05 UTC, verified)
LAKE (Parquet, local)       data/tape/   day-partitioned  0.044 GB/day
                                 │
                                 ▼  scripts/cloud_backup.py --tier tape  (Sun 22:30)
OFF-BOX (Backblaze B2, encrypted, never pruned)
```

**Why Parquet.** Measured on this box: one day of MNQ `book` is 16,828,512 rows = **~800 MB in SQLite,
20 MB as zstd Parquet — 40x**. The whole V5 archive went 11.75 GB → 0.641 GB (18x). Identical rows,
identical columns, nothing decimated. Format is the difference between an archive you can query and a
blob you must download whole.

**Why 5 TRADING days, not 5 calendar days.** A calendar cutoff run on a Monday keeps Mon/Sun/Sat/Fri/Thu
— only THREE trading days, because the weekend eats two. Retention counts days that actually contain
rows, so weekends and exchange holidays fall out for free.

---

## 2. Backblaze B2 — the key details

| | |
|---|---|
| Account ID | `5aecb8272eca` |
| Bucket | `gazbotv7` (an older `AlphabotV2` bucket also exists — 183 MiB, V5-era, leave it) |
| rclone remote (raw) | `b2raw:` → the bucket, unencrypted transport |
| rclone remote (crypt) | `gaz:` → crypt over `b2raw:gazbotv7` — the PRIVATE half |
| plaintext prefix | `b2raw:gazbotv7/plain/` — the tape, deliberately unencrypted |
| S3 endpoint | `s3.us-east-005.backblazeb2.com` (region `us-east-005`, **path-style**) |
| Config file | `/root/.config/rclone/rclone.conf`, mode `-rw------- root` |
| Billing | card on file; ~$6/TB/month. Current usage ≈ 0.6 GB ⇒ pennies |

### ⚠ Credentials are NOT in this repo, deliberately

The B2 application key and the crypt password/salt are **not committed anywhere in git**. Git history is
permanent and world-readable to anyone who ever clones the repo; a live storage key and the passphrase
that decrypts every backup do not belong in it.

They live in exactly two places:
1. `/root/.config/rclone/rclone.conf` on this box (root-only)
2. The operator's password manager, saved 2026-08-05 as the verbatim `[b2raw]` + `[gaz]` config block

**If both are lost the backups are unrecoverable.** Not by Backblaze, not by anyone. There is no reset.

### Caps, and the trap that cost an hour

B2 free tier is 10 GB with a **storage cap** set on **Caps & Alerts** (NOT a daily cap — that page also
has daily *bandwidth* and *transaction* caps, which is the confusion). Exceeding it returns
`403 storage_cap_exceeded` and refuses **every** upload, including a 30-byte file. Worse, the cap
counter **lags deletions** — after purging 10.5 GB the console still reported the old figure and kept
refusing. The fix is a payment method + a raised cap, not waiting.

---

## 3. The four tiers

| tier | contents | size | schedule | pruning |
|---|---|---|---|---|
| `state` | `gazbot7.db`, `shadow.db`, `exit_overrides.json`, `gate_switches.env`, `config_journal.jsonl`, `router_trial_log.txt` | ~3 MB | **hourly** | keep 30 |
| `tape` | the Parquet lake — ticks, quotes, bars, **41ms book**, 10-level depth. **PLAINTEXT** so DuckDB can query it in place | ~0.044 GB/day | Sun 22:30 UTC | **never** |
| `v5archive` | the frozen V5 desk, 84 Parquet objects | 612 MiB | one-shot, done | never |
| `archive` | raw `capture.db` + `depth.db` snapshots | ~10 GB | daily 21:25 | keep 2 |

`state` is hourly because `gazbot7.db` is ~800 KB and holds every trade, order and position the desk has
ever recorded — the only file that cannot be rebuilt from the feed, from git, or from anywhere else.
Tiers are sized by **irreplaceability**, not by bytes.

---

## 4. Restoring — rehearsed, not theoretical

Both of these were actually run on 2026-08-05, not written from the manual.

**Rebuild access on a new machine.** Paste the saved `[b2raw]` + `[gaz]` block into `rclone.conf`, then:
```bash
rclone lsd gaz:                       # lists state/ tape/ v5archive/
rclone cat gaz:state/<stamp>/exit_overrides.json
```
Verified from a clean config on a fresh path: real contents decrypted correctly.

**Query the tape — DIRECTLY, no download.** ★2026-08-05: the tape half is now PLAINTEXT precisely so
this works. Use the helper rather than hand-rolling S3 settings:
```python
from gazbot7.lake import connect
con = connect()                 # local Parquet if present, else B2
con = connect(remote=True)      # force B2
con.execute("SELECT count(*) FROM ticks WHERE symbol='MNQ'")
```
Measured against B2 with nothing cached: 1,228,928 rows counted in **0.73s**; a 7-day sweep over
**11,195,683 rows in 12.1s**; one column across the same files in **6.8s** — column and row-group
pushdown fetch only the bytes the query touches. Local and B2 return identical counts.

S3 endpoint `s3.us-east-005.backblazeb2.com`, region `us-east-005`, **path-style URLs** (B2 rejects
virtual-host style). Credentials are read from the rclone config by `lake.py`, never hardcoded.

**Query the ENCRYPTED half** (state, and the v5 trade tables) — must come through rclone, since crypt
means B2 hands DuckDB ciphertext:
```bash
rclone copy gaz:v5archive/ticks /tmp/x
duckdb -c "SELECT aggressor, count(*) FROM read_parquet('/tmp/x/trade_tick.parquet')
           WHERE symbol='MGC' GROUP BY 1"
```
Verified: 21,841,466 trade ticks and 31,121,448 quote ticks round-tripped exactly, and the MGC live
trades read back as **433 trades / +$1,103.40** — identical to the figure computed from the original.

---

## 5. ★★ The interlock — why retention cannot lose tape

`prune_capture.py` **may not delete a day that `tape_mirror.py` has not exported AND verified by row
count.** The mirror writes a manifest of verified `(table, symbol, day)` partitions; the prune clamps
its cutoff to the oldest day with rows that is missing from it.

If the mirror stops, the prune stops and `capture.db` grows. **Growth is a nuisance you notice; a silent
gap in the tape is not** — and the latter is exactly what cost the 07-31→08-02 exit ladder, which is
unrecoverable because `exit_overrides.json` was untracked.

Proven both directions on 2026-08-05: with an empty manifest the prune deleted **0 rows**; removing one
real partition (`ticks|MNQ|2026-07-29`) moved the clamp to exactly that day.

### Two bugs found while proving it — both FAILED SAFE, which is why they would have hidden

1. The floor walked the manifest for the first **calendar** gap — but 2026-07-18 is a Saturday. A
   weekend looked identical to a missing archive, so the clamp parked there forever and the prune would
   have reported "0 rows" while the disk filled.
2. The day-bucket scan yields buckets with **no rows**; the export skipped them silently while the floor
   counted them as unmirrored. The two sides disagreed permanently.

Neither would have lost data. Both would have quietly disabled retention — the same shape as the router
pin logging "no change" for 411 ticks.

---

## 6. Sizing (measured, not estimated)

```
capture.db      1.22 GB/day (both symbols)      book alone is 82% of it
depth.db        0.088 GB/day
parquet lake    0.044 GB/day        ← 28x smaller than the same data in SQLite

5 trading days hot + 2 months of lake  =  11.2 GB
12 months of lake                      =  24.5 GB
runway on the current disk             ≈  2+ years
```

The earlier "4 weeks of everything = 34 GB and does not fit" was a **SQLite** number. As Parquet the
same window is ~1.4 GB. **Retention on local disk was the wrong lever; format was the right one.**

---

## 7. Operational notes

- `cloud_backup.py` is **inert until configured** — no remote ⇒ logs and exits 0. Enabling the timers
  before credentials existed was harmless.
- **SQLite is never copied live.** A WAL database cannot be safely `cp`-ed; every DB goes through
  `VACUUM INTO` to a temp snapshot which is uploaded then deleted.
- ⚠ **The `cold`/`archive` tiers stage the whole tier to `/tmp` before uploading.** The V5 upload took
  the disk from 18 GB free to 9 GB. On a box running a live desk that is tighter than it should be —
  upload file-by-file if this is ever reused for something large.
- `--dry-run` on any tier prints the exact file list and byte count and uploads nothing.

## 7b. ★ ENCRYPTED vs PLAINTEXT — split by sensitivity, not by habit

Everything was encrypted at first because "financial records". That conflated two different things:

* **The record of YOUR TRADING** — `gazbot7.db`, configs, P&L, order history. Genuinely private.
  **Encrypted** (`gaz:`), and it must be: it is the one thing that says what you did.
* **MARKET TAPE** — ticks, bars, book, depth. This is data CME sells to anyone with a subscription.
  There is nothing to protect, and encrypting it cost something real: crypt means **DuckDB cannot read
  it**, so every study had to download whole files first. **Plaintext** (`b2raw:gazbotv7/plain/`).

The worst anyone can read out of the plaintext half is *what the market did* — never what we did.

## 8. What is deliberately NOT backed up

- `capture.db`'s 5-day hot window beyond what the lake already holds — regenerable from the feed
- Code — that is git's job
- `/tmp`, logs, `.venv`

## 9. Timers

```
gazbot7-tape-mirror.timer          daily 21:05 UTC   SQLite -> verified Parquet (BEFORE the prune)
gazbot7-capture-prune.timer        daily 21:15 UTC   retention, clamped by the interlock
gazbot7-cloud-backup-archive.timer daily 21:25 UTC   raw DB snapshots
gazbot7-vacuum (one-shot)                21:40 UTC   reclaim after prune; NOT a standing timer
gazbot7-cloud-backup-state.timer   hourly :07        the irreplaceable set
gazbot7-cloud-backup-tape.timer    Sun 22:30 UTC     the permanent corpus
```

⚠ A weekly VACUUM timer was **removed**: `systemctl restart` on it fired the service immediately and ran
a VACUUM during market hours. Only the one-shot remains. If you re-add it, schedule the *service*, do
not enable a timer that can trigger on restart.


---

## APPENDIX — live retention & journal facts (moved from CLAUDE.md, 2026-08-13)

**The tape no longer lives only in SQLite.** `capture.db` holds **5 TRADING days** (days with rows, so
weekends/holidays do not consume the window); everything older is **Parquet** — locally in `data/tape/`
and permanently in Backblaze B2. Same rows, same columns, **28x smaller**.

- **Query history via `gazbot7.lake.connect()`**, NOT by ATTACHing capture.db. It gives
  `ticks/quotes/bars/book/depth` views over local Parquet, or straight off B2 when local is absent.
  Measured: 11.2M rows aggregated in 12.1s over the network. Most existing harnesses still ATTACH
  capture.db and will silently see only 5 days — check before trusting an old script's window.
- **B2 is split by sensitivity.** Market tape is PLAINTEXT (`b2raw:gazbotv7/plain/`) so DuckDB can read
  it in place; the trade record (`gazbot7.db`, configs) is ENCRYPTED (`gaz:` crypt). Credentials live in
  `/root/.config/rclone/rclone.conf` and the operator's password manager — **never in git**.
- **★ THE INTERLOCK:** `prune_capture.py` may not delete a day `tape_mirror.py` has not exported AND
  verified by row count. If the mirror stops, the prune stops and capture.db grows. Growth you notice;
  a silent gap in the tape you do not.
- `data/exit_overrides.json` is now git-tracked and every desk startup journals its RESOLVED exit ladder
  to `config_journal.jsonl` — `scripts/config_at.py --at/--epochs/--diff`. Reconstructing a config epoch
  by hand is what made 07-31→08-02 unrecoverable.
- **★2026-08-08 THE JOURNAL NOW RECORDS THE ENTRY SIDE TOO.** It used to log the exit ladder only, on the
  reasoning that entry params were "already recorded by slot_strategy.py and git". Both halves were
  false — **git does not record an uncommitted tree, and source is not the resolved config.** Proven the
  same day: SATURDAY #2 changed a live entry floor (`ATR_FLOOR` 10→22, `ext_hi` deleted), the desk
  restarted, and the journal logged `changed_from_previous: false`. Rows now carry `entry` (per-slot
  params/sizing) + `gates` (the global `ATR_FLOOR`/`ER_FLOOR`/`ER_CEIL`/`ER_BAND` dicts) + `entry_hash`.
  Read with **`config_at.py --epochs --entry`**. `config_hash` keeps its exit-only meaning so every
  existing scan stays valid; pre-08-08 rows show `- (not recorded)`, which is *unknown*, not *unchanged*.
- **★2026-08-08 A DIRTY TREE NOW SHOWS UP IN THE SWEEP.** `sweep.py::check_config_committed()` WARNs if
  `exit_overrides.json` / `deciders.py` / `slot_strategy.py` / `multislot_core.py` are uncommitted. The
  journal had been stamping `exit_overrides_uncommitted: true` at every startup since 08-04 and **nothing
  consumed it** while five live behaviours existed only as working-tree edits. WARN not CRIT on purpose:
  a dirty tree is a bookkeeping failure, not an order-path failure, and a CRIT would train you to ignore
  a red sweep on a desk that is trading fine.
- ⚠ `scratchpad/` (807MB), `scratch/` and `*.pre-*` snapshots were **not** in `.gitignore` until 08-08.
  A "commit everything" would have put ~826MB into the repo. They are ignored now.
