"""GAZBOT V7 — minimal systemd notify (S9 watchdog).

A hung asyncio loop can't be caught by ``Restart=on-failure`` (the process hasn't
crashed) and can't run its own liveness probe. systemd's watchdog is the answer:
core sends ``WATCHDOG=1`` each status cycle; if the loop wedges, systemd stops
seeing pings past ``WatchdogSec`` and restarts the unit (which then re-adopts the
position via S2). ``READY=1`` is sent once so ``Type=notify`` considers core up.

Pure stdlib socket to ``$NOTIFY_SOCKET`` — no dependency. A **no-op when not run
under systemd** (env unset), so ``python -m gazbot7.core`` and the tests are
unaffected. Clean-room.
"""

from __future__ import annotations

import os
import socket


def sd_notify(state: str) -> bool:
    """Best-effort send of a systemd notify datagram (e.g. 'READY=1',
    'WATCHDOG=1'). Returns False (no-op) when not under systemd or on any error."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False
    try:
        if addr.startswith("@"):  # abstract namespace socket
            addr = "\0" + addr[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(addr)
            s.sendall(state.encode())
        return True
    except Exception:
        return False
