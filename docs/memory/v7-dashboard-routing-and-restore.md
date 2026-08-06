---
name: v7-dashboard-routing-and-restore
description: dashboard.gazbot.dev/v7 routing (cloudflared→nginx→:8087) + the reports page restoration + the pending Day/Cube/Courtroom page-restore project
metadata: 
  node_type: memory
  type: project
  originSessionId: 9162c01b-c354-41a1-9fc3-162d48ae4678
---

**The stable dashboard URL is `dashboard.gazbot.dev/v7` — do NOT mint a new URL per dashboard change (operator loses report history; his explicit rule 2026-07-25).**

**Routing (verified 2026-07-25):** Cloudflare tunnel (`cloudflared`, token-based, ingress configured in the CF dashboard not a local yml) → **nginx** `/etc/nginx/sites-enabled/alphabot` → `location /v7/ { proxy_pass http://127.0.0.1:8087/; }` (trailing slash: `/v7/reports`→`:8087/reports`, `/v7/static/x`→`:8087/static/x`). `:8087` = the `gazbot7-web` service (`python -m gazbot7.web`, `src/gazbot7/web.py`, binds 0.0.0.0:8087). nginx `/`→:8080 (empty/retired), `/agent/`→:8000. **V7 static pages use RELATIVE paths** (`fetch('api/reports')`, `href="static/…"`) so they work under the `/v7/` prefix — keep it that way; absolute `/api` or `/static` would break (route to `/`→:8080).

**★ REPORTS PAGE RESTORED 2026-07-25 (commit `a214fb4`).** Was near-empty: `reports_json` in web.py only matched `weekly_<date>.html` and only 07-17 lived in the V7 app — the whole Friday-report history sat in the RETIRED V5 dir `/home/alphabot/alphabot2/alphabot/dashboard/static/`. Fix: copied the history (`weekly_2026-06-25..07-17` + `monday_*` + pdfs, all self-contained/inline-CSS) into `src/gazbot7/web_static/`, and widened the index regex to `(?:weekly|v7_big_runs)_(\d{4}-\d{2}-\d{2})\.html$`. Now **`/v7/reports`** lists all 6 reports newest-first with pdf + playbook links. This week's report = `v7_big_runs_2026-07-24.{html,pdf}` (build with `scripts/friday_v7_build.py --slug <date>` to keep the dashboard-linked filename; the date-rollover default mints a wrong-day slug).

**⏳ PENDING WEEKEND PROJECT — restore Day/Cube/Courtroom onto /v7 (operator wants his old V5 4-page dashboard back).** The V5 HTML pages EXIST in the retired dir (`day_review.html`, `cube.html`, `courtroom.html`, `daytrade_terminal.html`) — serving them is trivial (drop in web_static + nav links in `app.html`). The REAL work is their DATA: each fetches V5 `/api/*` endpoints that DON'T exist in the V7 web service and must be BUILT in `web.py` over the V7 stores (gazbot7.db/capture.db/shadow.db): `cube`→`/api/cube`; `courtroom`→`/api/courtroom/progress`; `daytrade_terminal`→`/api/activity /gate-stats /health/services /market/status /scanner /stats /stream/status /trades/recent`; `day_review`→(its endpoint TBD). V7 already serves `/api/futures/*` (tournament/promotion/execution/mnq/us-terminal) + `/api/shadow/*` + `/api/reports`. Restart = `sudo systemctl restart gazbot7-web` (drops the operator's open tab ~5s — [[warn-before-dashboard-restart]]).
