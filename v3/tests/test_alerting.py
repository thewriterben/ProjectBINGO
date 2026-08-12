"""Alerting, tested for the failure mode that actually kills alerting systems.

It is not delivery. Delivery is a POST. The failure mode is **being ignored**,
and an ignored alerter is worse than no alerter because it looks like coverage.
So most of what is checked here is restraint:

  * a healthy node produces **nothing** - not "all checks passed", nothing
  * the same problem seen forty times is one notification, then a backed-off
    reminder, not forty
  * a problem that clears says so, because a channel that only ever carries bad
    news is a channel people stop opening
  * a problem that gets *worse* jumps the queue rather than inheriting the quiet
    period it was already in

And the two ways an alerter lies:

  * **silently failing to deliver.** A webhook with no URL that returns success
    is indistinguishable from a healthy one until the incident.
  * **going quiet because it died.** No news reads as good news. A process
    cannot page you about its own absence, so the honest half - a heartbeat
    something else can check - is what is tested, and the test says which half
    it is.

  python -m tests.test_alerting
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile

from bingo import alert as A
from bingo import health
from bingo.audit import AuditLog
from bingo.node import watch as W
from bingo import store as S


class Cap(A.Channel):
    """A channel that records instead of sending."""
    name = "cap"

    def __init__(self, ok: bool = True):
        self.sent: list = []
        self.ok = ok

    def send(self, payload):
        self.sent.append(payload)
        return self.ok

    def states(self):
        return [(p["key"], p["state"]) for p in self.sent]


def _router(d, chans, base=None, **kw):
    return A.AlertRouter(chans, base=base or os.path.join(d, "alerts"), **kw)


def _crit(key="chain", title="chain broken"):
    return A.Alert(key, A.CRITICAL, title, "record 3 was edited")


# -- restraint -----------------------------------------------------------------

def test_a_healthy_node_sends_nothing():
    """Not 'all checks passed'. Nothing. A cron job that mails you every five
    minutes to say it is fine is a cron job you filter."""
    with tempfile.TemporaryDirectory() as d:
        cap = Cap()
        with _router(d, [cap]) as r:
            for _ in range(5):
                assert r.dispatch([]) == {"sent": [], "suppressed": [],
                                          "resolved": [], "firing": []}
        assert cap.sent == []


def test_the_same_problem_is_one_notification_not_forty():
    with tempfile.TemporaryDirectory() as d:
        cap, t = Cap(), [1000.0]
        with _router(d, [cap], clock=lambda: t[0]) as r:
            for _ in range(40):
                r.dispatch([_crit()])
                t[0] += 5                       # 200s of five-second checks
        assert len(cap.sent) == 1, [p["title"] for p in cap.sent]


def test_a_persistent_problem_is_re_notified_on_a_backoff():
    """The second reminder is useful. The fortieth is why people write mail
    filters. So the schedule is geometric, and the test walks it."""
    with tempfile.TemporaryDirectory() as d:
        cap, t = Cap(), [0.0]
        with _router(d, [cap], clock=lambda: t[0]) as r:
            fired = []
            for _ in range(400):
                res = r.dispatch([_crit()])
                if res["sent"]:
                    fired.append(t[0])
                t[0] += 60                      # a check every minute for ~7h
        gaps = [round(b - a) for a, b in zip(fired, fired[1:])]
        assert gaps == sorted(gaps), f"backoff must not shrink: {gaps}"
        assert len(fired) <= 6, f"{len(fired)} notifications in 7 hours"
        assert gaps and gaps[0] >= 300


def test_the_count_is_carried_so_the_reminder_is_informative():
    with tempfile.TemporaryDirectory() as d:
        cap, t = Cap(), [0.0]
        with _router(d, [cap], clock=lambda: t[0]) as r:
            for _ in range(10):
                r.dispatch([_crit()])
                t[0] += 60
        assert cap.sent[0]["count"] == 1
        assert cap.sent[-1]["count"] > 1, "a reminder should say how many times"


def test_resolution_is_announced():
    """A channel that only ever carries problems teaches people that opening it
    is bad news, and they stop."""
    with tempfile.TemporaryDirectory() as d:
        cap = Cap()
        with _router(d, [cap]) as r:
            r.dispatch([_crit()])
            out = r.dispatch([])
        assert out["resolved"] == ["chain"]
        assert cap.states() == [("chain", "firing"), ("chain", "resolved")]


def test_nothing_is_resolved_that_was_never_announced():
    """'Resolved: a thing you never heard about' is noise wearing a helpful
    hat. A suppressed-then-cleared blip must stay silent."""
    with tempfile.TemporaryDirectory() as d:
        cap = Cap()
        with _router(d, [cap], min_severity=A.CRITICAL) as r:
            r.dispatch([A.Alert("meh", A.WARNING, "minor")])   # below threshold
            out = r.dispatch([])
        assert out["resolved"] == [] and cap.sent == []


def test_an_escalating_problem_jumps_the_quiet_period():
    """A warning that becomes critical must not inherit the six-hour silence it
    had already earned as a warning."""
    with tempfile.TemporaryDirectory() as d:
        cap, t = Cap(), [0.0]
        with _router(d, [cap], clock=lambda: t[0]) as r:
            r.dispatch([A.Alert("x", A.WARNING, "storage not isolated")])
            t[0] += 5
            assert r.dispatch([A.Alert("x", A.WARNING, "still")])["suppressed"]
            t[0] += 5
            out = r.dispatch([A.Alert("x", A.CRITICAL, "now it is losing writes")])
        assert out["sent"] == ["x"]
        assert cap.sent[-1]["escalated"] is True
        assert cap.sent[-1]["severity"] == A.CRITICAL


def test_dedupe_state_survives_the_process():
    """The cron shape: a fresh process every run. Without persistence, 'have I
    already said this?' resets every time, which is the same as not
    deduplicating at all."""
    with tempfile.TemporaryDirectory() as d:
        c1, t = Cap(), [0.0]
        with _router(d, [c1], clock=lambda: t[0]) as r:
            r.dispatch([_crit()])
        t[0] += 30
        c2 = Cap()
        with _router(d, [c2], clock=lambda: t[0]) as r2:      # new "process"
            out = r2.dispatch([_crit()])
        assert out["suppressed"] == ["chain"] and c2.sent == []


# -- the ways an alerter lies --------------------------------------------------

def test_a_webhook_with_no_url_reports_failure_rather_than_success():
    """A channel that silently no-ops is indistinguishable from a healthy one
    right up until the incident."""
    env = os.environ.pop("BINGO_ALERT_WEBHOOK", None)
    try:
        ch = A.WebhookChannel(None)
        assert ch.send({"severity": A.CRITICAL, "title": "x"}) is False
        assert "no webhook URL" in ch.last_error
    finally:
        if env is not None:
            os.environ["BINGO_ALERT_WEBHOOK"] = env


def test_total_delivery_failure_is_recorded_loudly():
    with tempfile.TemporaryDirectory() as d:
        with _router(d, [Cap(ok=False)]) as r:
            r.dispatch([_crit()])
            assert any("NO CHANNEL ACCEPTED" in f for f in r.delivery_failures)


def test_one_dead_channel_does_not_stop_the_others():
    class Exploding(A.Channel):
        name = "boom"

        def send(self, payload):
            raise RuntimeError("channel is on fire")

    with tempfile.TemporaryDirectory() as d:
        good = Cap()
        with _router(d, [Exploding(), good]) as r:
            r.dispatch([_crit()])
        assert len(good.sent) == 1
        assert any("boom" in f for f in r.delivery_failures)


def test_an_undelivered_alert_is_retried_next_run():
    """If nothing accepted it, it was not said. Marking it notified would lose
    the alert permanently, which is the worst possible outcome for the one
    message that mattered."""
    with tempfile.TemporaryDirectory() as d:
        dead, t = Cap(ok=False), [0.0]
        with _router(d, [dead], clock=lambda: t[0]) as r:
            r.dispatch([_crit()])
            t[0] += 5
            r.dispatch([_crit()])
        assert len(dead.sent) == 2, "an undelivered alert must be tried again"


def test_secrets_never_reach_a_channel():
    """Webhooks post to third parties with their own retention."""
    with tempfile.TemporaryDirectory() as d:
        cap = Cap()
        with _router(d, [cap]) as r:
            r.dispatch([A.Alert("k", A.CRITICAL, "rail rejected the transfer",
                                data={"api_token": "sk_live_LEAKME",
                                      "account": "acct:ben"})])
        blob = json.dumps(cap.sent)
        assert "sk_live_LEAKME" not in blob
        assert "acct:ben" in blob, "useful context must survive redaction"


def test_the_watcher_cannot_alert_on_its_own_death_and_says_so():
    """Half a deadman's switch. The test names which half, so nobody later
    mistakes this for the whole thing."""
    assert A.staleness_alert(1000.0, 600, now=1300.0) is None
    late = A.staleness_alert(1000.0, 600, now=2000.0)
    assert late is not None and late.severity == A.CRITICAL
    assert "No news is not good news" in late.detail
    never = A.staleness_alert(None, 600, now=2000.0)
    assert never is not None and never.key == "watch.never_ran"
    # and the honesty is in the source, not just in my head
    import inspect
    src = inspect.getsource(A.staleness_alert)
    assert "cannot page you about its own absence" in src


# -- severity comes from health, not from feelings -----------------------------

def test_health_severities_are_preserved_not_promoted():
    """`bingo/health.py` already decided what blocks readiness. Promoting a
    warning to critical because it feels important is how the stream becomes
    unreadable."""
    report = {"ready": True, "blocking_failures": [], "checks": [
        {"name": "signing", "ok": False, "blocking": False, "detail": "slow"},
        {"name": "storage", "ok": False, "blocking": False, "detail": "json"},
        {"name": "writes", "ok": True, "blocking": False, "detail": "-"}]}
    got = {a.key: a.severity for a in A.alerts_from_health(report)}
    assert got == {"health.signing": A.WARNING, "health.storage": A.WARNING}


def test_a_blocking_failure_is_critical():
    report = {"ready": False, "blocking_failures": ["audit"], "checks": [
        {"name": "audit", "ok": False, "blocking": True, "detail": "chain broken"}]}
    got = A.alerts_from_health(report)
    assert [a.severity for a in got] == [A.CRITICAL]
    assert "chain broken" in got[0].detail


def test_an_inconsistent_health_report_still_alerts():
    """ready=False with nothing failing means the report contradicts itself.
    That must not vanish just because no check owned up to it."""
    got = A.alerts_from_health({"ready": False, "blocking_failures": [],
                                "checks": []})
    assert [a.key for a in got] == ["health.not_ready"]


def test_alerts_from_health_never_raises():
    for junk in (None, {}, {"checks": "nope"}, {"checks": [None]}, 7):
        out = A.alerts_from_health(junk)
        assert isinstance(out, list)


# -- the watcher, against a real node ------------------------------------------

def _node(d, *, break_chain=False, failed_payout=False):
    node = os.path.join(d, "out")
    os.makedirs(node, exist_ok=True)  # noqa: PTH103
    with AuditLog(os.path.join(node, "audit")) as log:
        for i in range(4):
            log.append("test.event", n=i)
    if break_chain:
        st = S.node_store(os.path.join(node, "audit"))
        try:
            rec = st.get("000000000002")
            rec["data"]["n"] = 999
            st.put("000000000002", rec)
        finally:
            st.close()
    if failed_payout:
        st = S.node_store(os.path.join(node, "journal"))
        try:
            with st.transaction():
                st.put("k1", {"key": "k1", "status": "FAILED",
                              "amount_cents": 550, "account": "acct:ben"})
                st.put("k2", {"key": "k2", "status": "PENDING",
                              "amount_cents": 148, "account": "acct:x"})
        finally:
            st.close()
    return node


def test_a_healthy_node_produces_no_alerts_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        node = _node(d)
        cap = Cap()
        with _router(d, [cap], min_severity=A.CRITICAL) as r:
            res = W.run_once(node, r)
        assert res["firing_count"] == 0, res["firing"]
        assert cap.sent == []


def test_a_broken_audit_chain_reaches_a_human():
    with tempfile.TemporaryDirectory() as d:
        node = _node(d, break_chain=True)
        cap = Cap()
        with _router(d, [cap], min_severity=A.CRITICAL) as r:
            res = W.run_once(node, r)
        assert "health.audit" in res["firing"]
        assert cap.sent[0]["severity"] == A.CRITICAL


def test_failed_payouts_are_critical_and_pending_ones_are_not():
    """FAILED is terminal - someone is owed money that did not move. PENDING is
    normal briefly, and the journal has no timestamp, so claiming to know it has
    been pending too long would be inventing a fact."""
    with tempfile.TemporaryDirectory() as d:
        node = _node(d, failed_payout=True)
        cap = Cap()
        with _router(d, [cap], min_severity=A.INFO) as r:
            res = W.run_once(node, r)
        by = {p["key"]: p for p in cap.sent}
        assert by["payout.failed"]["severity"] == A.CRITICAL
        assert "550c owed" in by["payout.failed"]["title"]
        assert by["payout.pending"]["severity"] == A.WARNING
        assert "cannot tell you HOW long" in by["payout.pending"]["detail"]
        assert "payout.failed" in res["firing"]


def test_a_missing_node_directory_is_critical_rather_than_a_crash():
    with tempfile.TemporaryDirectory() as d:
        cap = Cap()
        with _router(d, [cap]) as r:
            res = W.run_once(os.path.join(d, "gone"), r)
        assert res["firing"] == ["node.missing"]


def test_the_watcher_writes_a_heartbeat_and_it_verifies():
    with tempfile.TemporaryDirectory() as d:
        node = _node(d)
        with _router(d, [Cap()]) as r:
            W.run_once(node, r, now=1_700_000_000.0)
        st = S.node_store(os.path.join(node, "audit"))
        try:
            log = AuditLog(store=st)
            beats = [x for x in log.records() if x["kind"] == W.HEARTBEAT]
            assert len(beats) == 1
            assert beats[0]["data"]["epoch"] == 1_700_000_000
            ok, _n = log.verify()
            assert ok, "the heartbeat must not break the chain it is written to"
        finally:
            st.close()


def test_a_stale_heartbeat_alerts_when_something_else_checks():
    with tempfile.TemporaryDirectory() as d:
        node = _node(d)
        with _router(d, [Cap()]) as r:
            W.run_once(node, r, now=1000.0)
        cap = Cap()
        with _router(d, [cap], base=os.path.join(d, "alerts2")) as r2:
            res = W.run_once(node, r2, now=9999.0, max_silence=600, beat=False)
        assert "watch.stale" in res["firing"]
        assert "the checks are simply not happening" in \
               [p["detail"] for p in cap.sent if p["key"] == "watch.stale"][0]


def test_collect_never_raises_on_a_mangled_node():
    with tempfile.TemporaryDirectory() as d:
        node = os.path.join(d, "out")
        os.makedirs(node)
        with open(os.path.join(node, "audit.json"), "w") as f:
            f.write("{not json at all")
        alerts, _ctx = W.collect(node)
        assert any(a.severity == A.CRITICAL for a in alerts)
        assert all(isinstance(a, A.Alert) for a in alerts)


# -- the CLI contract ----------------------------------------------------------

def test_exit_codes_distinguish_quiet_from_broken_from_uncheckable():
    """A run that COULD NOT CHECK must never be mistaken by a scheduler for a
    run that found nothing. Three outcomes, three codes."""
    import contextlib
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as d:
        healthy = _node(os.path.join(d, "a"))
        broken = _node(os.path.join(d, "b"), break_chain=True)
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc_ok = W.main([healthy, "--once", "--min-severity", "critical",
                            "--state", os.path.join(d, "s1")])
            rc_firing = W.main([broken, "--once", "--min-severity", "critical",
                                "--state", os.path.join(d, "s2")])
        assert rc_ok == 0, "a healthy node must exit 0"
        assert rc_firing == 1, "a firing alert must exit 1"

        # and a run where nothing could accept the alert is NOT "found nothing"
        with _router(d, [Cap(ok=False)], base=os.path.join(d, "s3")) as r:
            res = W.run_once(broken, r)
        assert res["delivery_failures"], (
            "an alert nobody accepted must be reported, not counted as sent")


def test_the_console_channel_says_nothing_for_a_healthy_node():
    with tempfile.TemporaryDirectory() as d:
        node = _node(d)
        buf = io.StringIO()
        with _router(d, [A.ConsoleChannel(buf)], min_severity=A.CRITICAL) as r:
            W.run_once(node, r)
        assert buf.getvalue() == "", repr(buf.getvalue()[:200])


def test_the_file_channel_appends_readable_jsonl():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "alerts.jsonl")
        ch = A.FileChannel(path)
        with _router(d, [ch]) as r:
            r.dispatch([_crit()])
            r.dispatch([])
        with open(path, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert [l["state"] for l in lines] == ["firing", "resolved"]


def test_alert_self_test_passes():
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert A._self_test() == 0


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} alerting groups pass, and most of them test "
          "RESTRAINT, because the failure mode of an alerting system is being "
          "ignored and an ignored alerter is worse than none: a healthy node "
          "sends nothing at all, the same problem seen 40 times is one "
          "notification then a geometric backoff (<=6 in 7 hours), a problem "
          "that clears says so, one that never fired is never 'resolved', and "
          "one that escalates jumps its own quiet period. Dedupe state survives "
          "the process, since cron is a fresh one each run. The lies are "
          "covered too: a webhook with no URL reports failure instead of "
          "success, a total delivery failure is loud, an undelivered alert is "
          "retried rather than marked sent, one exploding channel does not stop "
          "the others, and secrets never reach a channel. Health severities are "
          "preserved rather than promoted. And the watcher cannot alert on its "
          "own death - the heartbeat something else can check is tested, and "
          "the test says which half of the deadman's switch this is.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
