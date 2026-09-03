# MGC tunnel study — 2026-09-03

Everything behind `src/gazbot7/web_static/tunnel_2026-09-03.html`. Run from the repo root with
`PYTHONPATH=src .venv/bin/python reports/tunnel_mgc/<script>.py <MGC|MNQ>`.

The pipeline itself (series build, HMM, causal filter, break/race scoring) lives in
`scripts/tunnel_fit_mgc.py` and is tested by `tests/test_tunnel_fit_mgc.py`. These are the
one-off harnesses that produced the report's tables:

| script | what it answers |
|---|---|
| `breakstudy.py` | 60-min excursion + first-passage after a break, vs a matched-hour control |
| `ctl_variants.py` | the same, against three different control populations, in ATR and in points |
| `atr_variant.py` | does the choice of ATR (at the break / before it) explain the withdrawn 1.75x? |
| `live_params.py` | the decisive one: MNQ scored with the LIVE `tunnel_watch` parameters |
| `edge_fade.py` | the operator's other reading — fade the tunnel edge back to its mid |

`fit_norm_train_{MGC,MNQ}.json` are the fitted parameters used by the harnesses: normalised
feature, fitted on the FIRST TWO THIRDS of each symbol's sessions. Every number in the report is
measured on the held-out final third. `fit_full.json` is the raw-feature MGC fit quoted in the
report's "same size in dollars" table.

**These are one-off research harnesses, not services.** Nothing here runs on a timer and nothing
here touches a switch, a book or an order path.
