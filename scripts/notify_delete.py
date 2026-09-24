#!/usr/bin/env python3
"""RETRACT a Telegram alert this desk sent — list what went out, delete what was wrong.

★★★2026-09-24. Operator, after finding the step-away alert naming the wrong threshold:
"please delete any old erroneous messages." We could not. Telegram deletes a bot's own message
only by `message_id`, and `notify_operator.py` threw the API response away, so nothing the desk had
ever said was addressable. It now records the id into data/notify_sent.jsonl and this retracts it.

⚠⚠ TELEGRAM GIVES A BOT 48 HOURS. After that `deleteMessage` fails and there is nothing any tool
here can do about it — he deletes it in the app or it stays. `--list` marks every row LIVE or
EXPIRED so that limit is visible BEFORE it is hit, not discovered as a confusing API error.

⚠ A DELETION IS NOT REVERSIBLE and it removes something from HIS chat. `--match` therefore prints
what it would do and stops; it acts only with --yes. `--id` is already an explicit single target.

⚠⚠⚠ THIS SENDS NOTHING. It has no order path, it cannot alert, and it never edits a message into
saying something different — a desk that can silently REWRITE its own alarm history is far worse
than one that leaves a wrong message standing. Delete, or leave it.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

GB = "/home/alphabot/gazbot7"
SENT_LOG = f"{GB}/data/notify_sent.jsonl"
DELETE_WINDOW_S = 48 * 3600


def _creds():
    env = dict(os.environ)
    try:
        with open(f"{GB}/data/.notify_env") as fh:
            for line in fh:
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass
    return (env.get("TELEGRAM_TOKEN") or env.get("TELEGRAM_BOT_TOKEN"),
            env.get("TELEGRAM_CHAT_ID") or env.get("TELEGRAM_CHAT"))


def _rows():
    out = []
    try:
        with open(SENT_LOG) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    if r.get("message_id"):
                        out.append(r)
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return sorted(out, key=lambda r: r.get("ts") or 0)


def _age_label(ts):
    age = time.time() - float(ts or 0)
    h = age / 3600.0
    return ("LIVE   " if age < DELETE_WINDOW_S else "EXPIRED"), h


def _delete(tok, chat, mid):
    data = urllib.parse.urlencode({"chat_id": chat, "message_id": mid}).encode()
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/deleteMessage", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode()).get("ok") is True, ""
    except Exception as ex:
        # ⚠ Telegram answers a too-old message with an HTTP error, so say WHY rather than just "no".
        return False, f"{type(ex).__name__}: {ex}"


def _forget(mids):
    """Drop deleted ids from the log — a row pointing at a message that no longer exists is a
    retraction we would offer him again and again."""
    keep = [r for r in _rows() if r.get("message_id") not in mids]
    try:
        tmp = SENT_LOG + f".tmp{os.getpid()}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        with os.fdopen(fd, "w") as fh:
            for r in keep:
                fh.write(json.dumps(r) + "\n")
        os.chmod(tmp, 0o666)
        os.replace(tmp, SENT_LOG)
    except Exception as e:
        print(f"⚠ deleted from Telegram but could not update {SENT_LOG}: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="show what the desk has sent")
    ap.add_argument("--hours", type=float, default=48.0, help="how far back to look (default 48)")
    ap.add_argument("--id", type=int, action="append", help="delete this message_id (repeatable)")
    ap.add_argument("--match", help="delete every recent message containing this text")
    ap.add_argument("--yes", action="store_true", help="actually perform a --match deletion")
    a = ap.parse_args()

    rows = [r for r in _rows() if time.time() - float(r.get("ts") or 0) <= a.hours * 3600]

    if a.list or not (a.id or a.match):
        if not rows:
            print(f"nothing recorded in the last {a.hours:g}h."
                  f"\n⚠ ids are only kept for messages sent AFTER 2026-09-24 — anything older was"
                  f" never recorded and cannot be retracted from here.")
            return 0
        print(f"{'WHEN (UTC)':<20} {'ID':>9}  {'STATE':<8} TEXT")
        for r in rows:
            state, h = _age_label(r["ts"])
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r["ts"]))
            txt = " ".join((r.get("text") or "").split())[:80]
            print(f"{when:<20} {r['message_id']:>9}  {state:<8} {txt}")
        live = sum(1 for r in rows if time.time() - r["ts"] < DELETE_WINDOW_S)
        print(f"\n{len(rows)} message(s), {live} still inside Telegram's 48h deletion window.")
        return 0

    tok, chat = _creds()
    if not tok or not chat:
        print("TELEGRAM_TOKEN/CHAT_ID not configured", file=sys.stderr)
        return 1

    if a.id:
        targets = [r for r in _rows() if r["message_id"] in set(a.id)]
        unknown = set(a.id) - {r["message_id"] for r in targets}
        # ⚠ An id we never logged may still be deletable — do not refuse it, just say so.
        targets += [{"message_id": m, "ts": 0, "text": "(not in the log)"} for m in sorted(unknown)]
    else:
        targets = [r for r in rows if a.match.lower() in (r.get("text") or "").lower()]
        if not targets:
            print(f"no message in the last {a.hours:g}h contains {a.match!r}")
            return 0
        if not a.yes:
            print(f"WOULD DELETE {len(targets)} message(s) — re-run with --yes to do it:\n")
            for r in targets:
                state, _ = _age_label(r["ts"])
                print(f"  {r['message_id']:>9}  {state}  "
                      f"{' '.join((r.get('text') or '').split())[:80]}")
            return 0

    done = set()
    for r in targets:
        ok, why = _delete(tok, chat, r["message_id"])
        state, h = _age_label(r["ts"])
        if ok:
            done.add(r["message_id"])
            print(f"deleted {r['message_id']}")
        else:
            extra = "  (older than Telegram's 48h limit — delete it in the app)" \
                if r.get("ts") and h > 48 else ""
            print(f"FAILED  {r['message_id']}: {why}{extra}", file=sys.stderr)
    if done:
        _forget(done)
    return 0 if done or not targets else 1


if __name__ == "__main__":
    raise SystemExit(main())
