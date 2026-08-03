"""Sentinel classifier tests — the divergence rules, especially the real
failures they encode. Run from the repo root:  python -m sentinel.test_sentinel
"""

from __future__ import annotations

import sys

from sentinel.classify import classify, is_noteworthy
from sentinel.models import Promise, Status


def P(**kw):
    base = dict(id="P", counterparty="X", description="d",
                deadline="2026-08-06T23:59:00Z")
    base.update(kw)
    return Promise(**base)


def main() -> int:
    # 1) no signal, before deadline → UNCHECKABLE (flagged, not silent)
    s, _ = classify(P(), now="2026-08-05T10:00:00Z")
    assert s is Status.UNCHECKABLE, s

    # 2) no signal, past deadline → BREACHED
    s, _ = classify(P(), now="2026-08-07T10:00:00Z")
    assert s is Status.BREACHED, s

    # 3) delivered terminal → RESOLVED-KEPT
    s, _ = classify(P(observations=[{"ts": "2026-08-06T12:00:00Z",
                     "state": "delivered", "note": "", "on_track": None}]),
                    now="2026-08-06T13:00:00Z")
    assert s is Status.RESOLVED_KEPT, s

    # 4) THE AMAZON LESSON: out-for-delivery that sat too long, still pre-deadline → DIVERGING
    s, reason = classify(
        P(observations=[{"ts": "2026-08-06T02:00:00Z", "state": "out_for_delivery",
                         "note": "Boise", "on_track": None}]),
        now="2026-08-06T18:00:00Z")   # 16h later, threshold 12h
    assert s is Status.DIVERGING, (s, reason)
    assert "out-for-delivery" in reason

    # 4b) out-for-delivery only a few hours → still ON-TRACK
    s, _ = classify(
        P(observations=[{"ts": "2026-08-06T14:00:00Z", "state": "out_for_delivery",
                         "note": "", "on_track": None}]),
        now="2026-08-06T17:00:00Z")   # 3h
    assert s is Status.ON_TRACK, s

    # 5) explicit bad state before deadline → DIVERGING; after → BREACHED
    s, _ = classify(P(observations=[{"ts": "2026-08-05T10:00:00Z", "state": "exception",
                     "note": "", "on_track": None}]), now="2026-08-05T11:00:00Z")
    assert s is Status.DIVERGING, s
    s, _ = classify(P(observations=[{"ts": "2026-08-05T10:00:00Z", "state": "exception",
                     "note": "", "on_track": None}]), now="2026-08-08T11:00:00Z")
    assert s is Status.BREACHED, s

    # 6) stale silence pre-deadline → DIVERGING (no update for > threshold)
    s, reason = classify(
        P(deadline="2026-08-20T00:00:00Z",
          observations=[{"ts": "2026-08-05T00:00:00Z", "state": "shipped",
                         "note": "", "on_track": None}]),
        now="2026-08-08T00:00:00Z")   # 72h silence, threshold 48h
    assert s is Status.DIVERGING, (s, reason)

    # 7) healthy in-flight, recent update → ON-TRACK, not noteworthy
    s, _ = classify(
        P(deadline="2026-08-20T00:00:00Z",
          observations=[{"ts": "2026-08-07T20:00:00Z", "state": "in_transit",
                         "note": "", "on_track": None}]),
        now="2026-08-08T00:00:00Z")
    assert s is Status.ON_TRACK and not is_noteworthy(s), s

    # noteworthy filter: only diverging/breached/broken alert
    assert is_noteworthy(Status.BREACHED) and is_noteworthy(Status.DIVERGING)
    assert not is_noteworthy(Status.ON_TRACK) and not is_noteworthy(Status.UNCHECKABLE)

    print("OK — 8 classification cases incl. the out-for-delivery and stale-silence "
          "early-divergence rules; noteworthy filter stays quiet on healthy promises.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
