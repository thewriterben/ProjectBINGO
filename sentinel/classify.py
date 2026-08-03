"""The classifier — pure, deterministic, tested.

Given a promise, its observations, and the current time, decide its status.
The design bias is **catch divergence early**: a promise doesn't have to miss
its deadline to be in trouble — an off-pattern trajectory is flagged while the
person still has options. Encodes the lessons from real failures (a delivery
that sat "out for delivery" and then vanished; a system that only admitted
failure after the fact).
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (Promise, Status, GOOD_TERMINAL, BAD_STATES)


def _parse(ts: str) -> datetime:
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hours_between(a: str, b: str) -> float:
    return (_parse(b) - _parse(a)).total_seconds() / 3600.0


def classify(promise: Promise, now: str) -> tuple[Status, str]:
    """Return (status, reason). Pure: no I/O. `now` is RFC 3339 UTC."""
    # already resolved — sticky
    if promise.status in (Status.RESOLVED_KEPT.value, Status.RESOLVED_BROKEN.value):
        return Status(promise.status), "already resolved"

    obs = sorted(promise.observations, key=lambda o: o["ts"])
    last = obs[-1] if obs else None

    # a good terminal observation resolves it kept
    if last and (last["state"] in GOOD_TERMINAL or last.get("on_track") is True
                 and last["state"] in GOOD_TERMINAL):
        return Status.RESOLVED_KEPT, f"terminal state '{last['state']}'"

    past_deadline = _parse(now) >= _parse(promise.deadline)

    # no signals AND no observations → we can't see it
    if not promise.signals and not obs:
        if past_deadline:
            return Status.BREACHED, "deadline passed with no observable signal"
        return Status.UNCHECKABLE, "no observable signal on file"

    # explicit bad state, or a checker flagged off-track → diverging (or breached)
    if last and (last["state"] in BAD_STATES or last.get("on_track") is False):
        if past_deadline:
            return Status.BREACHED, f"deadline passed; last state '{last['state']}'"
        return Status.DIVERGING, f"off-pattern state '{last['state']}' before deadline"

    # deadline passed without a good terminal → breached
    if past_deadline:
        return Status.BREACHED, "deadline passed, not confirmed delivered/complete"

    # --- early-divergence heuristics (before the deadline) ---
    if last:
        # "out for delivery" that has sat too long — the Amazon lesson
        if last["state"] == "out_for_delivery":
            stale = _hours_between(last["ts"], now)
            if stale >= promise.out_for_delivery_stale_h:
                return (Status.DIVERGING,
                        f"out-for-delivery {stale:.0f}h with no delivery "
                        f"(>{promise.out_for_delivery_stale_h:.0f}h) — off-pattern")
        # silence: no fresh observation for a long time while still pre-deadline
        silence = _hours_between(last["ts"], now)
        if silence >= promise.observation_stale_h:
            return (Status.DIVERGING,
                    f"no signal update for {silence:.0f}h "
                    f"(>{promise.observation_stale_h:.0f}h) approaching deadline")

    return Status.ON_TRACK, "trajectory consistent with a kept promise"


def is_noteworthy(status: Status) -> bool:
    """Sweeps end quietly unless something needs the person. Never alert 'fine'."""
    return status in (Status.DIVERGING, Status.BREACHED, Status.RESOLVED_BROKEN)
