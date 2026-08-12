"""The record of what the node did, and whether it can be trusted.

Three things under test, all of which are only worth anything if they hold up
under someone actively trying to make them lie.

**The audit log.** Plain structured logging answers "what happened" to a reader
who trusts the file. After an incident the question is different: *is this file
still telling me what happened, or did whoever got in delete the four lines about
themselves?* A log an attacker can edit is not evidence, it is a story. So the
log is hash-chained with the same kernel every other document in this repo uses,
and the tests here delete, edit, reorder, truncate and splice records and require
every one of those to be **caught**.

**Redaction.** The most common way a security control becomes a vulnerability is
by logging what it was protecting. Real bearer tokens, real seeds and real coin
scratch codes go through the real code path here, and the test greps the actual
serialized output for them.

**The restore drill.** Every system that ever lost data had backups. What it did
not have was a restore anyone had performed.

  python -m tests.test_observability
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from bingo import audit as A
from bingo import health, keys, store as S
from bingo.node import backup as B
from bingo.payout import MockRail, PayoutEngine
from bingo.settlement import Leg

V3_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LEGS = [Leg("acct:node:printer-7", 550, "fabrication"),
        Leg("acct:ben", 148, "royalty 8000bps [design]")]


def _log(d, name="audit", **kw):
    return A.AuditLog(os.path.join(d, name), **kw)


def _fill(log, n=6):
    for i in range(n):
        log.append("test.event", actor=f"acct:{i}", n=i)
    return log.records()


# -- the chain holds, and breaking it is detected ------------------------------

def test_a_clean_chain_verifies():
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        _fill(log, 6)
        ok, notes = log.verify()
        assert ok, notes
        assert "chain intact" in notes[-1]
        assert log.head()["seq"] == 5


def test_editing_a_record_in_place_is_caught():
    """The intruder-tidying-up case, which is the whole reason for the chain."""
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        recs = _fill(log, 6)
        recs[2]["data"]["n"] = 999
        ok, notes = A.verify_audit(recs)
        assert not ok and "edited after it was written" in notes[-1]


def test_deleting_a_record_is_caught():
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        recs = _fill(log, 6)
        del recs[3]
        ok, notes = A.verify_audit(recs)
        assert not ok
        assert "missing, reordered, or spliced" in notes[-1]


def test_truncating_the_tail_is_caught_only_against_a_known_head():
    """Worth being precise rather than overclaiming. Lopping records off the END
    leaves a chain that is internally perfect - it is a valid prefix. Nothing
    inside the file can detect that, exactly as with the coin ledger in round 6.
    What catches it is comparing against a head you already knew, or an external
    anchor. The test pins the honest boundary so nobody later assumes more."""
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        recs = _fill(log, 6)
        known_head = recs[-1]["hash"]
        truncated = recs[:3]
        ok, _n = A.verify_audit(truncated)
        assert ok, "a prefix is internally consistent - that is the point"
        assert truncated[-1]["hash"] != known_head, (
            "and comparing to a head you already held is what catches it")


def test_reordering_two_records_is_caught():
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        recs = _fill(log, 6)
        recs[2], recs[3] = recs[3], recs[2]
        ok, _n = A.verify_audit(recs)
        assert not ok


def test_splicing_in_a_record_from_another_log_is_caught():
    """A record that is perfectly valid on its own - correct hash, real
    signature if signed - and simply does not belong to this chain.

    This test found a real gap. A hash chain identifies a *sequence of
    contents*, not the log that produced it: two nodes recording the same events
    in the same order build byte-identical chains, and a record lifted from one
    into the other was undetectable - there was genuinely nothing to detect. The
    fix is a per-log id minted at genesis and carried inside the signed body, so
    a record is bound to its own chain regardless of content. Both cases below:
    the easy one (different content) and the one that was silently passing.
    """
    with tempfile.TemporaryDirectory() as d:
        with _log(d, "a") as a, _log(d, "b") as b:
            ra = _fill(a, 4)
            for i in range(4):
                b.append("test.event", actor="acct:someone-else", n=i * 10)
            rb = b.records()
            assert a.log_id() != b.log_id()
            ok, notes = A.verify_audit(ra[:2] + [rb[2]] + ra[3:])
            assert not ok and "spliced" in notes[-1]

    # the case the chain alone could not catch: IDENTICAL content, two logs
    with tempfile.TemporaryDirectory() as d:
        with _log(d, "c") as c, _log(d, "e") as e:
            rc = _fill(c, 4)
            re_ = _fill(e, 4)                     # same events, same order
            assert c.log_id() != e.log_id()
            ok, notes = A.verify_audit(rc[:2] + [re_[2]] + rc[3:])
            assert not ok and "another log" in notes[-1], (
                "a record from a different log with identical content must "
                "still be caught - that is what the log id is for")


def test_the_verifier_never_raises_on_hostile_input():
    """Same rule as every other verifier here: `(ok, notes)` on ANY input. A
    file that survived an incident is exactly where malformed input comes from."""
    for junk in (None, "", [], {}, 7, [None], [{"seq": "x"}], [[]],
                 [{"seq": 0}], [{"seq": True, "ts": "", "kind": "", "actor": "",
                                 "data": {}, "prev": "0" * 64, "hash": "x"}],
                 [{"seq": 0, "ts": 1, "kind": "k", "actor": "a",
                   "data": {"x": object}, "prev": "0" * 64, "hash": "z"}]):
        ok, notes = A.verify_audit(junk)
        assert isinstance(ok, bool) and isinstance(notes, list), junk


# -- signatures ----------------------------------------------------------------

def test_signed_records_verify_and_a_forged_one_does_not():
    with tempfile.TemporaryDirectory() as d:
        signer = keys.insecure_test_signer("node-1")
        pub = signer.public_key().hex()
        with _log(d, signer=signer) as log:
            recs = _fill(log, 4)
        ok, _n = A.verify_audit(recs, expect_pubkey_hex=pub)
        assert ok
        # re-hash after tampering so the CHAIN still passes - only the signature
        # can catch this one, which is the case worth having signatures for
        recs[1]["data"]["n"] = 42
        recs[1]["hash"] = A.record_hash(recs[1])
        recs[2]["prev"] = recs[1]["hash"]
        recs[2]["hash"] = A.record_hash(recs[2])
        recs[3]["prev"] = recs[2]["hash"]
        recs[3]["hash"] = A.record_hash(recs[3])
        ok, notes = A.verify_audit(recs, expect_pubkey_hex=pub)
        assert not ok and "signature does not verify" in notes[-1]


def test_an_unsigned_record_is_refused_when_a_key_is_required():
    """Requiring a signature only when one happens to be present is not a
    requirement. That lesson cost this codebase round 8."""
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        recs = _fill(log, 3)                      # unsigned
        ok, notes = A.verify_audit(
            recs, expect_pubkey_hex=keys.insecure_test_signer("k").public_key().hex())
        assert not ok and "unsigned but a signing key was required" in notes[-1]


def test_a_signature_from_the_wrong_key_is_refused():
    with tempfile.TemporaryDirectory() as d:
        with _log(d, signer=keys.insecure_test_signer("real")) as log:
            recs = _fill(log, 3)
        other = keys.insecure_test_signer("attacker").public_key().hex()
        ok, notes = A.verify_audit(recs, expect_pubkey_hex=other)
        assert not ok and "not the expected key" in notes[-1]


# -- redaction -----------------------------------------------------------------

def test_real_secrets_never_reach_the_log():
    """Through the real code path, then grep the real serialized output."""
    secrets = {
        "api_token": "sk_live_51H8xQ2eZvKYlo2C",
        "Authorization": "Bearer super-secret-value-here",
        "seed_hex": "a" * 64,
        "passphrase": "correct horse battery staple",
        "scratch_code": "DGD-SCRATCH-77219",
        "X-Auth-Token": "another-one",
        "private_key": "-----BEGIN PRIVATE KEY-----",
    }
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        log.append("http.request", actor="1.2.3.4", path="/api/redeem",
                   headers=secrets, body={"nested": {"password": "hunter2"}})
        blob = json.dumps(log.records())
        for v in list(secrets.values()) + ["hunter2"]:
            assert v not in blob, f"leaked {v!r} into the audit log"
        assert blob.count(A.REDACTED) >= len(secrets)
        # ...and the harmless context survived, or the log would be useless
        assert "/api/redeem" in blob and "1.2.3.4" in blob


def test_redaction_is_biased_but_not_indiscriminate():
    """Over-broad redaction has its own failure mode: a log that hides the
    answer. A bare "auth" in the key list matched `authenticated` and silently
    blanked the field recording whether a request passed authentication - a
    RESULT, not a credential, and the one an operator would use to count failed
    intrusions. Found by the HTTP wiring test below."""
    assert "auth" not in A.SENSITIVE_KEYS
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        log.append("http.request", authenticated=False, author="acct:ben",
                   Authorization="Bearer leak-me", api_token="leak-me-too")
        data = log.records()[0]["data"]
        assert data["authenticated"] is False, "the result was redacted away"
        assert data["author"] == "acct:ben"
        assert data["Authorization"] == A.REDACTED
        assert data["api_token"] == A.REDACTED


def test_redaction_survives_hostile_shapes():
    """A log writer that can be made to explode by a request body is a denial of
    service on the record itself."""
    deep = cur = {}
    for _ in range(50):
        cur["next"] = {}
        cur = cur["next"]
    cur["token"] = "leaked?"
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        log.append("t", huge="x" * 100_000, deep=deep, wide=list(range(5_000)),
                   weird=object())
        rec = log.records()[0]
        blob = json.dumps(rec)
        assert "leaked?" not in blob
        assert len(blob) < 20_000, "one hostile body must not bloat the log"
        ok, _n = log.verify()
        assert ok


def test_an_audit_write_failure_never_breaks_the_caller():
    """An audit write that can fail a payout gets disabled by the first person it
    inconveniences. It must record the gap instead."""
    with tempfile.TemporaryDirectory() as d:
        log = _log(d)

        class Broken:
            def transaction(self):
                raise OSError(28, "No space left on device")

        log._store, real = Broken(), log._store
        assert log.append("t", x=1) == {}
        assert log.errors and "OSError" in log.errors[0]
        log._store = real
        log.close()


# -- concurrency, honestly -----------------------------------------------------

WORKER = r'''
import sys, os, time
sys.path.insert(0, sys.argv[1])
os.environ["BINGO_STORE"] = sys.argv[3]
from bingo.audit import AuditLog
log = AuditLog(sys.argv[2])
for i in range(6):
    log.append("worker.event", actor=sys.argv[4], i=i)
    time.sleep(0.01)
log.close()
'''


def _concurrent_appends(base: str, backend: str, n: int = 4) -> tuple[bool, int]:
    with tempfile.TemporaryDirectory() as wd:
        script = os.path.join(wd, "w.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(WORKER)
        procs = [subprocess.Popen(
            [sys.executable, script, V3_DIR, base, backend, f"w{i}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(n)]
        for p in procs:
            _o, err = p.communicate(timeout=180)
            assert p.returncode == 0, err.decode()[:400]
    env = os.environ.get("BINGO_STORE")
    os.environ["BINGO_STORE"] = backend
    try:
        st = S.node_store(base)
        try:
            log = A.AuditLog(store=st)
            ok, _n = log.verify()
            return ok, len(log.records())
        finally:
            st.close()
    finally:
        if env is None:
            os.environ.pop("BINGO_STORE", None)
        else:
            os.environ["BINGO_STORE"] = env


def test_concurrent_appends_fork_the_chain_on_json_and_it_is_detected():
    """Appending is a read-modify-write: computing `prev` means reading the head.
    Under JSON two processes read the same head and the chain forks or loses
    records outright.

    The claim is deliberately narrow. This is NOT "JSON is fine because we catch
    it" - a detected corruption is still a corruption, and an audit log that
    fails to verify is an audit log you cannot use. It is: the failure is loud
    rather than silent, and the fix is the SQLite backend, checked below.

    Bounded retry for the same reason as `test_node_storage`: losing a race is
    probabilistic, and an assertion that *usually* holds is precisely the
    flakiness these tests are about. The loop observes the real behaviour under
    real contention with a hard bound, so a real fix turns it red rather than
    letting it quietly pass."""
    with tempfile.TemporaryDirectory() as d:
        seen = []
        for attempt in range(4):
            ok, n = _concurrent_appends(os.path.join(d, f"audit{attempt}"),
                                        "json")
            seen.append((ok, n))
            if not ok or n < 24:
                return
        assert False, (
            f"4 rounds of 4 concurrent appenders and the JSON backend produced "
            f"a clean, complete chain every time: {seen}. Either JsonStore has "
            f"grown cross-process locking - in which case this should become "
            f"the opposite assertion - or the contention here stopped reaching "
            f"the losing window.")


def test_concurrent_appends_hold_on_sqlite():
    """Exact and unconditional, because it is deterministic by construction -
    unlike the JSON case above, which needs a retry loop because losing a race
    is by nature probabilistic. That asymmetry IS the difference between the
    backends, so it stays visible."""
    with tempfile.TemporaryDirectory() as d:
        ok, n = _concurrent_appends(os.path.join(d, "audit"), "sqlite")
        assert ok and n == 24, f"chain ok={ok}, {n}/24 records"


# -- what it is wired into -----------------------------------------------------

def test_payouts_are_audited_without_the_journal_changing():
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        rail = MockRail()
        eng = PayoutEngine(rail, journal_path=os.path.join(d, "j.jsonl"),
                           audit=log)
        eng.pay_legs(LEGS, order_id="ord-1", job_id="job-1")
        kinds = [r["kind"] for r in log.records()]
        assert kinds == ["payout.attempt"] * 2, kinds
        d0 = log.records()[0]["data"]
        assert d0["amount_cents"] == 550 and d0["status"] == "PAID"
        assert d0["job_id"] == "job-1" and d0["idem_key"]
        ok, _n = log.verify()
        assert ok
        # a replay pays nothing, so it must also record nothing new
        eng.pay_legs(LEGS, order_id="ord-1", job_id="job-1")
        assert len(log.records()) == 2, "an idempotent replay logged a new payout"


def test_http_requests_are_audited_including_the_refused_ones():
    """A 401 nobody wrote down is a failed intrusion nobody can count."""
    import threading
    import urllib.error
    import urllib.request
    from bingo import httpguard as G

    class Echo(G.HardenedHandler):
        def handle_get(self, u):
            return self.send_json({"ok": True})

    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        srv = G.build_server(Echo, "127.0.0.1", 0,
                             G.Policy(auth_token="t" * 32), audit=log)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/coin?c=SECRETCOIN",
                                   timeout=10).read()
            try:
                urllib.request.urlopen(urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/redeem", data=b"{}",
                    method="POST"), timeout=10)
            except urllib.error.HTTPError:
                pass
        finally:
            srv.shutdown()
            srv.server_close()
            t.join(timeout=5)

        recs = log.records()
        assert len(recs) == 2, [r["data"] for r in recs]
        # keyed by method, NOT by position. Each request gets its own connection
        # and therefore its own handler thread, and the audit write happens in
        # that thread - so the two records can land in either order. An earlier
        # version of this test asserted the positional order and failed roughly
        # once in forty, which is a flaky assertion rather than a real defect.
        by = {r["data"]["method"]: r["data"] for r in recs}
        assert by["GET"]["status"] == 200
        assert by["POST"]["status"] == 401, by["POST"]
        assert by["POST"]["authenticated"] is False
        assert by["POST"]["path"] == "/api/redeem"
        blob = json.dumps(recs)
        assert "SECRETCOIN" not in blob, (
            "the query string was logged - coin credentials travel there")
        ok, _n = log.verify()
        assert ok


# -- health --------------------------------------------------------------------

def test_health_separates_live_from_ready():
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        _fill(log, 3)
        st = S.open_store(os.path.join(d, "s.json"))
        try:
            r = health.report(store=st, audit=log, writes_enabled=False, tls=False)
        finally:
            st.close()
        assert r["live"] is True and r["ready"] is True
        names = {c["name"] for c in r["checks"]}
        assert {"signing", "storage", "audit", "writes", "tls"} <= names
        # the JSON backend must show up as a warning, not a pass
        storage = [c for c in r["checks"] if c["name"] == "storage"][0]
        assert storage["ok"] is False and storage["blocking"] is False
        assert "storage" in r["warnings"] and not r["blocking_failures"]


def test_a_broken_audit_chain_makes_the_node_not_ready():
    """The one blocking check. A node whose own record of itself does not verify
    is not a node anyone should send value to, whatever else is true of it."""
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        _fill(log, 4)
        st = log._store
        bad = dict(st.items())["000000000002"]
        bad["data"]["n"] = 999
        st.put("000000000002", bad)
        r = health.report(audit=log)
        assert r["ready"] is False and "audit" in r["blocking_failures"]


def test_health_reports_properties_never_values():
    """The most-scraped URL on any service must not become the reconnaissance
    one. It says whether a token is configured, never the token."""
    tok = "sk-live-do-not-appear-anywhere"
    with tempfile.TemporaryDirectory() as d, _log(d) as log:
        blob = json.dumps(health.report(audit=log, writes_enabled=bool(tok)))
        assert tok not in blob
        assert d not in blob, "the report leaked a filesystem path"


def test_health_never_raises():
    class Exploding:
        def describe(self):
            raise RuntimeError("nope")

    class Unverifiable:
        errors: list = []

        def verify(self):
            raise RuntimeError("nope")

    r = health.report(store=Exploding(), audit=Unverifiable())
    assert r["live"] is True and r["ready"] is False
    assert "audit" in r["blocking_failures"]


# -- the restore drill ---------------------------------------------------------

def _node(d: str) -> str:
    """A node directory with something in every collection."""
    node = os.path.join(d, "out")
    os.makedirs(os.path.join(node, "blobs"), exist_ok=True)
    os.makedirs(os.path.join(node, "keys"), exist_ok=True)
    with open(os.path.join(node, "keys", "node-1.json"), "w") as f:
        f.write('{"encrypted": "do-not-back-me-up"}')
    with open(os.path.join(node, "blobs", "abc123"), "wb") as f:
        f.write(b"content-addressed blob")

    for name, payload in (("manifests", {"asset-1": {"title": "bracket"}}),
                          ("reputation", {"nodes": {"n1": {"staked_cents": 100}}})):
        st = S.node_store(os.path.join(node, name))
        try:
            with st.transaction():
                for k, v in payload.items():
                    st.put(k, v)
        finally:
            st.close()

    with A.AuditLog(os.path.join(node, "audit")) as log:
        for i in range(5):
            log.append("test.event", n=i)
    return node


def test_the_restore_drill_passes_on_a_healthy_node():
    with tempfile.TemporaryDirectory() as d:
        node = _node(d)
        r = B.drill(node, quiet=True)
        assert r["ok"], r
        assert set(r["collections"]) == {"manifests", "reputation", "audit"}
        assert r["collections"]["audit"]["chain_verifies"] is True
        assert r["collections"]["audit"]["records"] == 5


def test_the_drill_fails_when_a_backup_would_not_restore():
    """The drill has to be able to say no, or running it means nothing."""
    with tempfile.TemporaryDirectory() as d:
        node = _node(d)
        real_backup = B.backup

        def lossy(node_dir, dest, **kw):
            out = real_backup(node_dir, dest, **kw)
            st = S.open_store(os.path.join(dest, "manifests.json"))
            try:
                st.delete("asset-1")           # a backup that silently drops one
            finally:
                st.close()
            return out

        B.backup = lossy
        try:
            r = B.drill(node, quiet=True)
        finally:
            B.backup = real_backup
        assert r["ok"] is False
        assert r["collections"]["manifests"]["missing"] == ["asset-1"]


def test_a_scrambled_audit_restore_fails_the_drill_even_with_the_right_count():
    """Record count is not integrity. A restore that returned the same number of
    rows with the chain broken must fail."""
    with tempfile.TemporaryDirectory() as d:
        node = _node(d)
        real_backup = B.backup

        def scrambling(node_dir, dest, **kw):
            out = real_backup(node_dir, dest, **kw)
            st = S.open_store(os.path.join(dest, "audit.json"))
            try:
                rec = st.get("000000000002")
                rec["data"]["n"] = 99          # same count, broken chain
                st.put("000000000002", rec)
            finally:
                st.close()
            return out

        B.backup = scrambling
        try:
            r = B.drill(node, quiet=True)
        finally:
            B.backup = real_backup
        assert r["ok"] is False
        assert r["collections"]["audit"]["records"] == 5, "count unchanged"
        assert r["collections"]["audit"]["chain_verifies"] is False


def test_key_material_is_never_backed_up():
    """A security decision, not an oversight - so it gets a test that would fail
    the day someone 'fixes' it for completeness."""
    with tempfile.TemporaryDirectory() as d:
        node = _node(d)
        dest = os.path.join(d, "bak")
        out = B.backup(node, dest, quiet=True)
        assert out["skipped"] == ["keys"]
        assert not os.path.exists(os.path.join(dest, "keys"))
        found = []
        for root, _dirs, files in os.walk(dest):
            for f in files:
                with open(os.path.join(root, f), "rb") as fh:
                    if b"do-not-back-me-up" in fh.read():
                        found.append(os.path.join(root, f))
        assert not found, f"key material reached the backup: {found}"
        # and the things that SHOULD be there are
        assert os.path.exists(os.path.join(dest, "blobs", "abc123"))


def test_the_backup_cli_reports_failure_rather_than_exiting_zero():
    import contextlib
    import io
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as d:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = B.main([os.path.join(d, "nope"), "--to", os.path.join(d, "b")])
            rc2 = B.main([os.path.join(d, "empty-ish"), "--drill"])
        assert rc == 1
        assert rc2 == 1, "a drill with nothing to restore is not a pass"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} observability groups pass: the audit log is "
          "hash-chained, so editing, deleting, reordering and splicing records "
          "are all CAUGHT (and tail-truncation is honestly pinned as caught "
          "only against a known head or an anchor); signatures are required "
          "unconditionally when a key is expected, not merely checked when "
          "present; real bearer tokens, seeds, passphrases and coin codes are "
          "put through the real path and never appear in the output, query "
          "strings included; an audit write that fails records the gap instead "
          "of breaking the payout; concurrent appenders fork the chain on JSON "
          "(loudly) and hold on SQLite; health separates live from ready and a "
          "broken chain makes a node NOT ready; and the restore drill restores "
          "record by record, fails on a lossy or scrambled backup, and never "
          "backs up key material.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
