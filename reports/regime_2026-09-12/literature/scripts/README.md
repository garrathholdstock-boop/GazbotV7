Scripts that produced every desk number in REPORT.md. Run with:
  systemd-run --scope -q -p MemoryMax=900M --setenv=HOME=/root /home/alphabot/gazbot7/.venv/bin/python <script>
Inputs: data/backfill/MNQ_*_1min.parquet and MGC_*_1min.parquet (front month by daily volume).
- power.py       -> the power table (§0). The one number that reframes the desk's six months.
- costrange.py   -> cost / median RTH range, MNQ vs MGC (§4).
- straddle2.py   -> band stop-and-reverse straddle replication + day-block bootstrap (§1b).
- straddle3.py   -> chronological split + within-hour shuffle control on the fade (§1b).
- noisearea.py   -> Zarattini/Aziz/Barbon noise-area intraday momentum on MNQ + random-band placebo.
NOTE straddle v1 (discarded) filled at the SIGNAL BAR'S CLOSE - a look-ahead. v2/v3 fill at the
NEXT minute's open. Any re-use must keep that.
