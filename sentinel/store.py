"""JSON promise store + a sweep that classifies every open promise.

The scheduled Sentinel agent fetches signals with web tools and appends
Observations; this runs the deterministic classifier over them, updates
status, and returns the noteworthy items to surface.
"""

from __future__ import annotations

import json
import os

from .classify import classify, is_noteworthy
from .models import Promise, Status


class PromiseStore:
    def __init__(self, path: str):
        self.path = path
        self.promises: list[Promise] = []

    def load(self) -> "PromiseStore":
        if os.path.exists(self.path):
            with open(self.path) as f:
                data = json.load(f)
            self.promises = [Promise.from_dict(p) for p in data.get("promises", [])]
        return self

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({"promises": [p.to_dict() for p in self.promises]}, f, indent=2)

    def add(self, promise: Promise) -> None:
        self.promises.append(promise)

    def open_promises(self) -> list[Promise]:
        return [p for p in self.promises
                if p.status not in (Status.RESOLVED_KEPT.value,
                                    Status.RESOLVED_BROKEN.value)]

    def sweep(self, now: str) -> list[dict]:
        """Classify every open promise, update status + log, and return the
        noteworthy ones (diverging / breached / newly broken)."""
        alerts = []
        for p in self.open_promises():
            status, reason = classify(p, now)
            changed = status.value != p.status
            p.status = status.value
            if changed:
                p.log.append(f"{now} · → {status.value}: {reason}")
            if is_noteworthy(status):
                alerts.append({"id": p.id, "counterparty": p.counterparty,
                               "status": status.value, "reason": reason,
                               "instructions": p.standing_instructions,
                               "description": p.description})
        return alerts
