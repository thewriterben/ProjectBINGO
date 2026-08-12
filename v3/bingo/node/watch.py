"""The thing that actually looks, on a schedule, and tells someone.

    python -m bingo.node.watch out --once
    python -m bingo.node.watch out --interval 300
    */5 * * * *  cd /srv/bingo && python -m bingo.node.watch out --once

Everything before this increment produced signal and nothing read it. This reads
it: the health report, the audit chain, the payout journal, and the watcher's own
heartbeat, once per run, into `bingo.alert.AlertRouter`.

Two decisions worth stating, because both are the difference between an alerter
someone keeps and one they mute:

**A healthy node prints nothing and sends nothing.** Not "all checks passed" -
nothing. A cron job that mails you every five minutes to say it is fine is a cron
job you filter, and a filtered alerter is worse than none because it looks like
coverage.

**The watcher records a heartbeat into the audit log every run.** It cannot
alert on its own death - if it is not running, neither is any of its code. The
heartbeat is there so something else can: `--check-stale` from a second node, or
a poll of `/api/health`, which surfaces the same timestamp. Half a deadman's
switch, and the other half is not code.

Exit codes are for the scheduler, so a run that could not check is never
mistaken for a run that found nothing:

    0  checked, nothing firing
    1  checked, something is firing
    2  could NOT check (node unreadable, or no channel accepted an alert)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from bingo import alert as A
from bingo import health, store as S
from bingo.audit import AuditLog

HEARTBEAT = "watch.heartbeat"


def _open(node_dir: str, name: str):
    base = os.path.join(node_dir, name)
    if not (os.path.exists(base + ".json") or os.path.exists(base + ".db")):
        return None
    return S.node_store(base)


def collect(node_dir: str, *, now: float | None = None,
            max_silence: float | None = None) -> tuple[list, dict]:
    """Look at the node once. Returns (alerts, context).

    Never raises: a watcher that dies on a malformed file is a watcher that
    stops watching precisely when something is wrong with the files.
    """
    now = time.time() if now is None else now
    alerts: list[A.Alert] = []
    ctx: dict = {"node_dir": node_dir}

    if not os.path.isdir(node_dir):
        return ([A.Alert(key="node.missing", severity=A.CRITICAL,
                         title=f"node directory {node_dir} does not exist",
                         detail="nothing to check - is the path right, or did "
                                "the volume go away?")], ctx)

    # -- audit chain + heartbeat --
    log = None
    last_beat = None
    try:
        st = _open(node_dir, "audit")
        if st is not None:
            log = AuditLog(store=st)
            for rec in reversed(log.records()):
                if rec.get("kind") == HEARTBEAT:
                    last_beat = rec.get("data", {}).get("epoch")
                    break
    except Exception as e:                         # noqa: BLE001
        alerts.append(A.Alert(key="audit.unreadable", severity=A.CRITICAL,
                              title="the audit log could not be read",
                              detail=f"{type(e).__name__}: {e}"))

    # -- health, which already made the severity judgements --
    store = None
    try:
        store = _open(node_dir, "journal") or _open(node_dir, "manifests")
        report = health.report(store=store, audit=log)
        ctx["ready"] = report["ready"]
        alerts.extend(A.alerts_from_health(report))
    except Exception as e:                         # noqa: BLE001
        alerts.append(A.Alert(key="health.crashed", severity=A.CRITICAL,
                              title="the health check itself failed",
                              detail=f"{type(e).__name__}: {e}"))
    finally:
        if store is not None:
            store.close()

    # -- money that did not move --
    try:
        alerts.extend(_payout_alerts(node_dir))
    except Exception as e:                         # noqa: BLE001
        alerts.append(A.Alert(key="payout.unreadable", severity=A.WARNING,
                              title="the payout journal could not be read",
                              detail=f"{type(e).__name__}: {e}"))

    if max_silence is not None:
        stale = A.staleness_alert(last_beat, max_silence, now=now)
        if stale is not None:
            alerts.append(stale)
    ctx["last_heartbeat"] = last_beat
    ctx["log"] = log
    return alerts, ctx


def _payout_alerts(node_dir: str) -> list:
    """FAILED is terminal and someone is owed money that did not move. PENDING is
    normal briefly and suspicious for long - but this cannot see how long without
    a timestamp on the record, so it reports the count and says so rather than
    inventing a threshold it cannot enforce."""
    st = _open(node_dir, "journal")
    if st is None:
        return []
    try:
        recs = [v for _k, v in st.items()]
    finally:
        st.close()
    out = []
    failed = [r for r in recs if r.get("status") == "FAILED"]
    pending = [r for r in recs if r.get("status") == "PENDING"]
    if failed:
        owed = sum(int(r.get("amount_cents") or 0) for r in failed)
        out.append(A.Alert(
            key="payout.failed", severity=A.CRITICAL,
            title=f"{len(failed)} payout(s) FAILED - {owed}c owed and unmoved",
            detail="FAILED is terminal: these will not retry on their own. "
                   "Someone is owed money that did not move.",
            data={"count": len(failed), "cents": owed}))
    if pending:
        out.append(A.Alert(
            key="payout.pending", severity=A.WARNING,
            title=f"{len(pending)} payout(s) still PENDING",
            detail="Normal briefly. The journal carries no timestamp, so this "
                   "cannot tell you HOW long - check before assuming it is "
                   "fine, and run retry_pending() if the rail has recovered.",
            data={"count": len(pending)}))
    return out


def run_once(node_dir: str, router, *, max_silence: float | None = None,
             now: float | None = None, beat: bool = True) -> dict:
    now = time.time() if now is None else now
    alerts, ctx = collect(node_dir, now=now, max_silence=max_silence)
    result = router.dispatch(alerts)
    log = ctx.get("log")
    if beat and log is not None:
        # written AFTER dispatch, so a run that died mid-dispatch does not leave
        # a heartbeat claiming everything was checked
        log.append(HEARTBEAT, actor="watch", epoch=int(now),
                   firing=len(result["firing"]))
        log.close()
    elif log is not None:
        log.close()
    result["firing_count"] = len(result["firing"])
    result["delivery_failures"] = list(router.delivery_failures)
    return result


def _channels(args) -> list:
    chans: list = [A.ConsoleChannel()]
    if args.alert_file:
        chans.append(A.FileChannel(args.alert_file))
    if args.webhook or os.environ.get("BINGO_ALERT_WEBHOOK"):
        chans.append(A.WebhookChannel(args.webhook))
    return chans


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m bingo.node.watch",
        description="Watch a node and alert a human when it stops being "
                    "trustworthy. Silent when healthy.")
    ap.add_argument("node_dir", help="the node's output directory, e.g. out")
    ap.add_argument("--once", action="store_true",
                    help="check once and exit (the cron shape)")
    ap.add_argument("--interval", type=float, default=None,
                    help="check every N seconds until interrupted")
    ap.add_argument("--alert-file", default=None,
                    help="append alerts as JSONL here")
    ap.add_argument("--webhook", default=None,
                    help="POST alerts here (or set $BINGO_ALERT_WEBHOOK)")
    ap.add_argument("--check-stale", type=float, default=None, metavar="SECONDS",
                    help="alert if the last heartbeat is older than this. Only "
                         "meaningful from a DIFFERENT process than the one "
                         "writing heartbeats - see the module docstring.")
    ap.add_argument("--min-severity", choices=(A.INFO, A.WARNING, A.CRITICAL),
                    default=A.WARNING)
    ap.add_argument("--state", default=None,
                    help="where to keep dedupe state (default <node_dir>/alerts)")
    a = ap.parse_args(argv)

    router = A.AlertRouter(
        _channels(a), base=a.state or os.path.join(a.node_dir, "alerts"),
        min_severity=a.min_severity)
    try:
        while True:
            r = run_once(a.node_dir, router, max_silence=a.check_stale)
            if r["delivery_failures"]:
                for f in r["delivery_failures"]:
                    print(f"x alert delivery failed: {f}", file=sys.stderr)
                return 2
            if a.interval is None or a.once:
                return 1 if r["firing_count"] else 0
            time.sleep(a.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        router.close()


if __name__ == "__main__":
    sys.exit(main())
