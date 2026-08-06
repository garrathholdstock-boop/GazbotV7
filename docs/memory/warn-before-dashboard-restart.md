---
name: warn-before-dashboard-restart
description: Warn Garrath before restarting alphabot-dashboard — it drops his open /futures tab mid-session
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ccb6199e-59b1-4963-8e0b-88c88bf59bac
---

Restarting `alphabot-dashboard` (to deploy a cockpit/display change) briefly drops the backend for the operator's OPEN browser tab — the live page goes dead/frozen for a few seconds and reads as "you killed the dashboard." On 2026-07-02 a silent dashboard restart to ship the losses-scoreboard change did exactly this and alarmed Garrath.

**Why:** the restart is idempotent and server-recovers in ~5s (NRestarts stays 0, all endpoints return 200 after), but the operator watching the live tab has no warning and sees it die.

**How to apply:** before `sudo systemctl restart alphabot-dashboard`, tell Garrath it will blink his open tab for a few seconds and he'll need to refresh. Restart is still auto-allowed (no approval needed) — this is a heads-up, not a gate. Also: the live cockpit is served at **`/futures`** (the current futures terminal), NOT `/terminal` (legacy, same HTML today but the wrong name to cite). Check `/futures` when verifying the dashboard. Related: [[weekend-no-flatten-no-fuss]].
