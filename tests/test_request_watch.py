"""THE UNREAD-REQUEST ALARM — and it must never eat the press it is watching.

★★★ THE EVENT (2026-09-17). Claim pressed 05:39:31 on a 4-lot LONG at +$262. The gateway's accept
queue had been full since 00:40 — new connections hung, established ones kept working — so the
rider timed out 244 consecutive times, exited 0 each time, and wrote a FRESH HEARTBEAT every
minute. systemd green, sweep green, dashboard green. The claim sat unread 27 minutes, EXPIRED at
CLAIM_MAX_AGE_S, and the operator found it himself at -$316.

Every existing instrument asked "is the rider alive?" and got a truthful yes. This asks the only
question he cares about: DID MY BUTTON DO ANYTHING.
"""
import datetime as dt
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import request_watch as rw

SRC = "/home/alphabot/gazbot7/scripts/request_watch.py"


def _stamp(minutes_ago):
    return (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=minutes_ago)).isoformat()


def test_a_missing_file_is_the_HEALTHY_case(tmp_path, monkeypatch):
    """The rider DELETES a request when it consumes it — absence is success, not an error."""
    monkeypatch.setattr(rw, "DATA", str(tmp_path))
    assert rw.age_of("day_rider_claim.txt") is None


def test_age_comes_from_the_PRESS_STAMP_not_mtime(tmp_path, monkeypatch):
    """⚠ mtime is the filesystem's clock and diverges whenever anything touches the file — the buy
    path's ExecStartPre copies it. What we are timing is the OPERATOR'S PRESS."""
    monkeypatch.setattr(rw, "DATA", str(tmp_path))
    (tmp_path / "day_rider_claim.txt").write_text(_stamp(20))     # written NOW, stamped 20 min ago
    age = rw.age_of("day_rider_claim.txt")
    assert 19 * 60 < age < 21 * 60, f"read {age}s — that is mtime, not the press"


def test_a_malformed_request_still_ages(tmp_path, monkeypatch):
    """A request nobody can PARSE is still a request nobody can CONSUME."""
    monkeypatch.setattr(rw, "DATA", str(tmp_path))
    (tmp_path / "day_rider_claim.txt").write_text("not-a-timestamp")
    assert rw.age_of("day_rider_claim.txt") is not None


def test_lot_suffix_still_parses(tmp_path, monkeypatch):
    """The four per-lot Claim buttons write `<stamp>|lot=N`."""
    monkeypatch.setattr(rw, "DATA", str(tmp_path))
    (tmp_path / "day_rider_claim.txt").write_text(_stamp(9) + "|lot=2")
    assert 8 * 60 < rw.age_of("day_rider_claim.txt") < 10 * 60


def test_it_pages_and_says_EXPIRED_once_past_the_limit(tmp_path, monkeypatch):
    """★ The two messages demand different actions: 'your button did nothing' vs 'your button did
    nothing AND can never fire — re-press'."""
    monkeypatch.setattr(rw, "DATA", str(tmp_path))
    monkeypatch.setattr(rw, "LOG", str(tmp_path / "l.log"))
    (tmp_path / "day_rider_claim.txt").write_text(_stamp(20))
    sent = []
    import gazbot7.notify as n
    monkeypatch.setattr(n, "notify", lambda m, **k: sent.append(m))
    monkeypatch.setattr(n, "dedupe_ok", lambda *a, **k: True)
    rw.main()
    assert sent and "EXPIRED" in sent[0] and "RE-PRESS" in sent[0]


def test_a_FRESH_request_does_not_page(tmp_path, monkeypatch):
    """⚠ The rider ticks every 60s. Paging on a 10-second-old press would train him to swipe past
    criticals, which is how a naked position gets missed."""
    monkeypatch.setattr(rw, "DATA", str(tmp_path))
    monkeypatch.setattr(rw, "LOG", str(tmp_path / "l.log"))
    (tmp_path / "day_rider_claim.txt").write_text(_stamp(0))
    sent = []
    import gazbot7.notify as n
    monkeypatch.setattr(n, "notify", lambda m, **k: sent.append(m))
    rw.main()
    assert not sent


def test_it_NEVER_consumes_the_request(tmp_path, monkeypatch):
    """⚠⚠⚠ THE SAFETY PROPERTY. A second reader that disposed of a request would silently EAT THE
    OPERATOR'S PRESS — the hazard capture_operator_read.py is built around."""
    monkeypatch.setattr(rw, "DATA", str(tmp_path))
    monkeypatch.setattr(rw, "LOG", str(tmp_path / "l.log"))
    f = tmp_path / "day_rider_claim.txt"
    f.write_text(_stamp(20))
    before = f.read_text()
    import gazbot7.notify as n
    monkeypatch.setattr(n, "notify", lambda m, **k: None)
    monkeypatch.setattr(n, "dedupe_ok", lambda *a, **k: True)
    rw.main()
    assert f.exists(), "THE ALARM DELETED THE OPERATOR'S PRESS"
    assert f.read_text() == before, "THE ALARM REWROTE THE OPERATOR'S PRESS"


def test_source_holds_no_order_path_and_no_writer():
    """★ Asserted against the SOURCE, like the capture and tape-reader guards."""
    src = open(SRC).read()
    for banned in ("placeOrder", "MarketOrder", "LimitOrder", "IB()", "connectAsync"):
        assert banned not in src, f"the alarm reached for a broker primitive: {banned}"
    for banned in ("os.remove", "os.unlink", "shutil.move"):
        assert banned not in src, f"the alarm can destroy a request: {banned}"
    # it may only ever open a request file for READING
    assert 'open(os.path.join(DATA, path))' in src
    assert '"w"' not in src.split("def log(")[0], "no writer above the log helper"
