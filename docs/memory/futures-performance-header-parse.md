---
name: futures-performance-header-parse
description: "/api/futures/performance header P&L is at d['header']['today'], NOT d['today']['header'] — a wrong parse falsely reads None; the endpoint is fine, don't flag a header bug"
metadata: 
  node_type: reference
  type: reference
  originSessionId: d7443f59-d3b4-466f-b7e6-3903cacfd274
---

**GOTCHA (2026-07-10, self-inflicted false-flag):** the `/api/futures/performance` response is `{currency, net_of_fees, fee_per_rt, **header**, rolling, gate_perf, loss_buckets, ratchet}` — the P&L strip is at **`d['header']['today']`** (and `d['header']['trades_today']`, `d['header']['yest']`), NOT under a top-level `today` key. A sweep one-liner using `d.get('today',{}).get('header',{}).get('today')` reads **None** (the `today` key doesn't exist) and looks like a "header display bug" — it is NOT; the endpoint + the cockpit are fine. `d.get('today', d)` (default = d) accidentally works, which is why it read correct on some sweeps and None on others. **Correct parse: `json['header']['today']`.** I flagged a phantom bug 3× off this before catching it. Handler: `alphabot/dashboard/api/routes_futures_terminal.py:3254` (`futures_performance`).
