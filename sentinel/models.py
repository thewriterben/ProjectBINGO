"""Promise Integrity data model. Times are RFC 3339 UTC strings."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class Status(str, Enum):
    ON_TRACK = "ON-TRACK"           # trajectory matches a kept promise
    DIVERGING = "DIVERGING"         # off-pattern BEFORE the deadline — alert now, options exist
    BREACHED = "BREACHED"           # deadline passed unmet — escalate
    UNCHECKABLE = "UNCHECKABLE"     # no observable signal — flagged (that's information too)
    RESOLVED_KEPT = "RESOLVED-KEPT"
    RESOLVED_BROKEN = "RESOLVED-BROKEN"


# States a checker may report from a signal, normalized across counterparties.
GOOD_TERMINAL = {"delivered", "completed", "fulfilled", "refunded", "resolved"}
BAD_STATES = {"exception", "failed", "delayed", "returned", "cancelled", "lost", "refused"}
IN_FLIGHT = {"processing", "shipped", "in_transit", "out_for_delivery", "pending"}


@dataclass
class Observation:
    ts: str                        # when observed
    state: str                     # normalized state (see sets above) or free text
    note: str = ""
    on_track: bool | None = None   # explicit override from a richer checker


@dataclass
class Promise:
    id: str
    counterparty: str
    description: str
    deadline: str                  # RFC 3339 UTC
    signals: dict = field(default_factory=dict)   # tracking_url, order_id, carrier, …
    standing_instructions: str = ""
    status: str = Status.ON_TRACK.value
    observations: list = field(default_factory=list)   # list[Observation-as-dict]
    log: list = field(default_factory=list)            # list[str], dated
    # tuning knobs (hours):
    out_for_delivery_stale_h: float = 12.0             # OFD longer than this → diverging
    observation_stale_h: float = 48.0                  # silence longer than this pre-deadline → diverging

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Promise":
        known = {k: d[k] for k in d if k in cls.__dataclass_fields__}
        return cls(**known)
