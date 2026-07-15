"""GAZBOT V7 — operator alerts with tiers + quiet hours (S9).

Two tiers, enforced in code (V5 left quiet-hours to sweep convention and it never
held):

* **critical** — safety/CRIT (naked, drift, flatten-incomplete, a monitor CRIT).
  ALWAYS sends, any hour. Silence is never worth a naked position.
* **routine** — heartbeats / status. Suppressed 22:00–06:00 Paris so a 3am buzz
  doesn't cry wolf; the safety tier is the override.

Delivery is the alphabot2 ``notify_operator.py`` (one Telegram channel), fired via
subprocess and fail-quiet — an alerting outage must never break the caller. The
send is injectable so the gating logic is tested without touching Telegram.
Clean-room.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_PARIS = ZoneInfo("Europe/Paris")
_PY = "/home/alphabot/alphabot2/.venv/bin/python"
_SCRIPT = "/home/alphabot/alphabot2/scripts/notify_operator.py"


def in_quiet_hours(now: datetime) -> bool:
    """22:00–06:00 Paris — the routine-suppression window (safety overrides it)."""
    h = now.astimezone(_PARIS).hour
    return h >= 22 or h < 6


def _subprocess_send(message: str) -> bool:
    try:
        # cwd=alphabot2 so notify_operator.py loads TELEGRAM_TOKEN/CHAT from its .env
        subprocess.run([_PY, _SCRIPT, message], check=False, timeout=15,
                       cwd="/home/alphabot/alphabot2")
        return True
    except Exception:
        return False


def notify(message: str, *, critical: bool = False, now: datetime | None = None, send=None) -> bool:
    """Send an operator alert. Routine alerts are suppressed during quiet hours;
    critical (safety) alerts always send. Returns True if sent. Fail-quiet."""
    now = now or datetime.now(UTC)
    if not critical and in_quiet_hours(now):
        return False
    return (send or _subprocess_send)(message)
