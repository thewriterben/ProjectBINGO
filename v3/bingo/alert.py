"""Telling a human, without training them to ignore you.

The previous increment produced signal: a tamper-evident audit log and a health
report that separates *live* from *ready*. Nothing reads them. A signal nobody
is watching is a signal that does not exist, and "the dashboard would have shown
it" is what people say after an outage nobody saw.

The hard part of alerting is not delivery. It is that **the failure mode of an
alerting system is being ignored**, and an ignored alerter is *worse* than no
alerter, because it looks like coverage. Three things follow, and they are the
whole design:

  1. **Deduplicate.** A broken audit chain is one problem, not one problem per
     minute. An alert has a stable `key`; repeats increment a counter instead of
     sending again, and re-notification backs off geometrically.
  2. **Say when it clears.** A channel that only ever receives problems teaches
     people that opening it is bad news, and they stop. Resolution notices are
     not politeness, they are what makes the stream worth reading.
  3. **Stay quiet otherwise.** Nothing is sent for a healthy node. The
     `sentinel` module already worked this way for delivery promises; this is the
     same discipline pointed at the node itself.

And one thing an alerter genuinely cannot do for itself:

  **A process cannot page you about its own absence.** If the watcher dies,
  crashes, or is never scheduled, no amount of code inside it will notice - the
  code is not running. `staleness_alert()` exists so *something else* can catch
  it: a second node, an operator's uptime check, or a poll of `/api/health`,
  which surfaces the last heartbeat. Calling that a deadman's switch would be a
  lie; it is half of one, and the other half is not code.

Secrets never reach a channel. Webhooks post to Slack, PagerDuty, whatever -
third parties, over the network, into systems with their own retention. The same
redaction the audit log uses applies here, for the same reason.

  python -m bingo.alert --self-test
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from . import store as _store
from .audit import _redact

__all__ = ["Alert", "CRITICAL", "WARNING", "INFO", "Channel", "ConsoleChannel",
           "FileChannel", "WebhookChannel", "AlertRouter", "alerts_from_health",
           "staleness_alert"]

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"

_RANK = {INFO: 0, WARNING: 1, CRITICAL: 2}

#: Re-notify schedule for a problem that is still happening, in seconds since
#: the last notification. Geometric on purpose: the second reminder is useful,
#: the fortieth is why people write mail filters.
BACKOFF = (0, 300, 1800, 7200, 21600, 86400)


@dataclass
class Alert:
    key: str                     # stable identity; two alerts with one key are
                                 # the same problem, however many times seen
    severity: str
    title: str
    detail: str = ""
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.severity not in _RANK:
            raise ValueError(f"unknown severity {self.severity!r}")
        self.data = _redact(self.data)

    def to_dict(self, **extra) -> dict:
        d = {"key": self.key, "severity": self.severity, "title": self.title,
             "detail": self.detail, "data": self.data}
        d.update(extra)
        return d


# -- delivery ------------------------------------------------------------------

class Channel(ABC):
    """Somewhere an alert can land.

    `send` returns True on success. It must **not** raise: a channel that throws
    takes the whole watcher down with it, and the watcher going down is the one
    failure nothing else will notice.
    """

    name = "channel"

    @abstractmethod
    def send(self, payload: dict) -> bool: ...


class ConsoleChannel(Channel):
    name = "console"

    def __init__(self, stream=None):
        self._out = stream or sys.stdout

    def send(self, payload: dict) -> bool:
        try:
            mark = {CRITICAL: "!!", WARNING: " !", INFO: "  "}[payload["severity"]]
            state = payload.get("state", "firing")
            seen = payload.get("count", 1)
            times = f" (x{seen})" if seen > 1 else ""
            print(f"{mark} [{state}] {payload['title']}{times}\n"
                  f"     {payload['detail']}", file=self._out)
            return True
        except Exception:                          # noqa: BLE001
            return False


class FileChannel(Channel):
    """Append-only JSONL. Deliberately *not* the audit log: an alert is an
    interpretation, and mixing interpretations into the evidence chain would
    make the evidence arguable."""

    name = "file"

    def __init__(self, path: str):
        self.path = path

    def send(self, payload: dict) -> bool:
        try:
            parent = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(parent, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return True
        except OSError:
            return False


class WebhookChannel(Channel):
    """POST to Slack / PagerDuty / anything that takes JSON.

    Fail-closed in the sense that matters here: without a URL it reports failure
    rather than pretending to have delivered. A channel that silently no-ops is
    indistinguishable from a healthy one right up until the incident.
    """

    name = "webhook"

    def __init__(self, url: str | None = None, *, timeout: float = 10.0,
                 opener=None):
        self.url = url or os.environ.get("BINGO_ALERT_WEBHOOK") or None
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen
        self.last_error: str | None = None

    def send(self, payload: dict) -> bool:
        if not self.url:
            self.last_error = "no webhook URL configured"
            return False
        try:
            body = json.dumps({
                "text": f"[{payload['severity']}] {payload['title']}",
                "alert": payload}, sort_keys=True).encode()
            req = urllib.request.Request(
                self.url, data=body, method="POST",
                headers={"Content-Type": "application/json"})
            with self._opener(req, timeout=self.timeout) as r:
                ok = 200 <= getattr(r, "status", 200) < 300
            self.last_error = None if ok else "non-2xx response"
            return ok
        except (urllib.error.URLError, OSError, ValueError, TypeError) as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return False


# -- routing -------------------------------------------------------------------

class AlertRouter:
    """Dedupe, back off, and announce resolution.

    State lives in the storage seam, because a watcher run from cron is a fresh
    process every time. Without persistence "have I already said this?" resets on
    every run, which is the same as not deduplicating at all - and that is how an
    alerter becomes a mail filter rule.
    """

    def __init__(self, channels, *, base: str | None = None, store=None,
                 clock=None, min_severity: str = INFO):
        self.channels = list(channels)
        self._own = store is None
        self._store = store if store is not None else _store.node_store(
            base or os.path.join("out", "alerts"))
        self._clock = clock or time.time
        self.min_severity = min_severity
        self.delivery_failures: list[str] = []

    # -- the entry point --
    def dispatch(self, alerts) -> dict:
        """Take the CURRENT set of firing alerts and reconcile it with what was
        firing last time. Anything absent from `alerts` that was firing before
        has resolved."""
        now = self._clock()
        current = {a.key: a for a in alerts
                   if _RANK[a.severity] >= _RANK[self.min_severity]}
        sent, suppressed, resolved = [], [], []

        with self._store.transaction():
            known = {k: v for k, v in self._store.items()}

            for key, alert in current.items():
                st = known.get(key)
                if st is None:
                    st = {"key": key, "first_seen": now, "count": 0,
                          "notified_at": None, "notify_stage": 0,
                          "severity": alert.severity}
                st["count"] += 1
                st["last_seen"] = now
                escalated = _RANK[alert.severity] > _RANK[st.get("severity", INFO)]
                st["severity"] = alert.severity

                if self._should_notify(st, now) or escalated:
                    payload = alert.to_dict(
                        state="firing", count=st["count"],
                        first_seen=st["first_seen"], ts=now,
                        escalated=bool(escalated))
                    if self._deliver(payload):
                        st["notified_at"] = now
                        # escalation restarts the ladder: a problem that just got
                        # worse should not inherit a 6-hour quiet period
                        st["notify_stage"] = (0 if escalated
                                              else min(st["notify_stage"] + 1,
                                                       len(BACKOFF) - 1))
                    sent.append(key)
                else:
                    suppressed.append(key)
                self._store.put(key, st)

            for key, st in known.items():
                if key in current:
                    continue
                if st.get("notified_at") is not None:
                    # only announce resolution for something we actually
                    # announced - "resolved: a thing you never heard about" is
                    # noise wearing a helpful hat
                    self._deliver({
                        "key": key, "severity": INFO, "state": "resolved",
                        "title": f"resolved: {key}",
                        "detail": f"cleared after {st['count']} observation(s)",
                        "data": {}, "ts": now, "count": st["count"]})
                    resolved.append(key)
                self._store.delete(key)

        return {"sent": sent, "suppressed": suppressed, "resolved": resolved,
                "firing": sorted(current)}

    def _should_notify(self, st: dict, now: float) -> bool:
        if st["notified_at"] is None:
            return True
        return (now - st["notified_at"]) >= BACKOFF[st["notify_stage"]]

    def _deliver(self, payload: dict) -> bool:
        """Delivered if ANY channel took it.

        A failure on one channel is recorded rather than swallowed. If every
        channel fails, `delivery_failures` is what an operator (or the next
        health check) has to go on - an alerting system that cannot deliver and
        does not say so is the quietest possible failure.
        """
        ok = False
        for ch in self.channels:
            try:
                if ch.send(payload):
                    ok = True
                else:
                    self.delivery_failures.append(
                        f"{ch.name}: {getattr(ch, 'last_error', 'send failed')}")
            except Exception as e:                 # noqa: BLE001
                self.delivery_failures.append(f"{ch.name}: {type(e).__name__}: {e}")
        if not ok:
            self.delivery_failures.append(
                f"NO CHANNEL ACCEPTED alert {payload.get('key')!r}")
        return ok

    def close(self) -> None:
        if self._own:
            self._store.close()

    def __enter__(self):
        return self

    def __exit__(self, *e):
        self.close()


# -- detectors -----------------------------------------------------------------

def alerts_from_health(report: dict) -> list[Alert]:
    """Turn a health report into alerts, preserving its severity judgement.

    Blocking failures are critical; warnings are warnings. Promoting a warning
    to critical because it *feels* important is exactly how the stream becomes
    unreadable, and `bingo/health.py` already made that call once."""
    out: list[Alert] = []
    try:
        for c in report.get("checks", []):
            if c.get("ok"):
                continue
            out.append(Alert(
                key=f"health.{c.get('name')}",
                severity=CRITICAL if c.get("blocking") else WARNING,
                title=f"health check '{c.get('name')}' is failing",
                detail=str(c.get("detail", ""))))
        if not report.get("ready", True) and not any(
                a.severity == CRITICAL for a in out):
            # ready=False with no failing check means the report itself is
            # inconsistent, which is its own problem and must not vanish
            out.append(Alert(key="health.not_ready", severity=CRITICAL,
                             title="node reports NOT READY",
                             detail=f"blocking: {report.get('blocking_failures')}"))
    except Exception as e:                         # noqa: BLE001
        out.append(Alert(key="health.unreadable", severity=CRITICAL,
                         title="health report could not be read",
                         detail=f"{type(e).__name__}: {e}"))
    return out


def staleness_alert(last_run_epoch: float | None, max_silence: float,
                    *, now: float | None = None) -> Alert | None:
    """Half of a deadman's switch, and only half.

    A process cannot page you about its own absence - if the watcher is not
    running, none of its code is either. This is here so something ELSE can
    notice: a second node, an uptime check, or a poll of `/api/health`. Naming
    it a deadman's switch would be a lie; the other half is not code.
    """
    now = time.time() if now is None else now
    if last_run_epoch is None:
        return Alert(key="watch.never_ran", severity=CRITICAL,
                     title="the node watcher has never run",
                     detail="no heartbeat recorded. Nothing is checking this "
                            "node, and nothing will tell you if that stays true.")
    silent = now - last_run_epoch
    if silent > max_silence:
        return Alert(
            key="watch.stale", severity=CRITICAL,
            title="the node watcher has stopped running",
            detail=f"last heartbeat {int(silent)}s ago, limit {int(max_silence)}s. "
                   f"No news is not good news - the checks are simply not "
                   f"happening.",
            data={"silent_seconds": int(silent)})
    return None


# -- self-test -----------------------------------------------------------------

def _self_test() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        sent: list = []

        class Cap(Channel):
            name = "cap"

            def send(self, payload):
                sent.append(payload)
                return True

        t = [1000.0]
        with AlertRouter([Cap()], base=os.path.join(d, "alerts"),
                         clock=lambda: t[0]) as r:
            a = Alert("x", CRITICAL, "chain broken", "record 3 was edited")
            assert r.dispatch([a])["sent"] == ["x"]
            t[0] += 10
            assert r.dispatch([a])["suppressed"] == ["x"]   # deduped
            t[0] += 400
            assert r.dispatch([a])["sent"] == ["x"]         # backed off, then re-sent
            t[0] += 10
            assert r.dispatch([])["resolved"] == ["x"]
        assert [p["state"] for p in sent] == ["firing", "firing", "resolved"]
    print("OK - alert self-test passes: a repeated problem is deduplicated, "
          "re-notified only after the backoff, and announced when it clears.")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m bingo.alert")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return _self_test()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
