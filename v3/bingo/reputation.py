"""L2/L3 — Reputation, maintained BY THE NETWORK, never self-reported.

A node cannot claim its own reputation — that's the whole point. The network
records outcomes (completions, failures, QA results, dispute verdicts) and
derives a score. Reputation is a vector, not a scalar: demonstrated
consistency per (grade, process), so a bedroom printer with flawless
functional-grade history is excellent at grade F and simply unrated at grade
P — never wrongly trusted, never wrongly penalized. Staking makes fraud
net-negative; probation graduates new nodes on low-stakes work first. Buyers
carry reputation too (claim quality), so chronic bad-faith disputes get priced.

Spec: specs/ACCEPTANCE.md ("Reputation is a vector, not a scalar").
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict

from . import store as _store


def _base(path: str) -> str:
    """`out/reputation.json` -> `out/reputation`, so `node_store` can pick the
    extension that matches the backend. A caller who has always passed
    `...json` keeps writing exactly that file under the default."""
    root, ext = os.path.splitext(path)
    return root if ext.lower() in (".json", ".db", ".sqlite", ".sqlite3") else path

PROBATION_COMPLETIONS = 3          # completions before a node leaves probation
PROBATION_MAX_JOB_CENTS = 5_000    # probationary nodes only take low-stakes work


@dataclass
class GradeStats:
    completed: int = 0
    failed: int = 0
    on_time: int = 0
    qa_pass: int = 0
    disputes_lost: int = 0

    def score(self) -> float:
        """[0,1] from observed outcomes. Neutral prior 0.5 with no history;
        rewards completion + on-time + QA pass, punishes failure + lost disputes."""
        n = self.completed + self.failed
        if n == 0:
            return 0.5
        completion = self.completed / n
        on_time_rate = self.on_time / self.completed if self.completed else 0.0
        qa_rate = self.qa_pass / self.completed if self.completed else 0.0
        dispute_penalty = min(0.5, self.disputes_lost * 0.1)
        raw = 0.5 * completion + 0.25 * on_time_rate + 0.25 * qa_rate - dispute_penalty
        return max(0.0, min(1.0, raw))


@dataclass
class NodeRep:
    node_id: str
    prior: float = 0.5                 # seed reputation before any history
    staked_cents: int = 0              # slashable stake
    slashed_cents: int = 0
    expelled: bool = False
    stats: dict = field(default_factory=dict)   # "grade:process" -> GradeStats

    def _key(self, grade: str, process: str) -> str:
        return f"{grade}:{process}"

    def _stats(self, grade: str, process: str) -> GradeStats:
        k = self._key(grade, process)
        s = self.stats.get(k)
        if s is None:
            s = GradeStats()
            self.stats[k] = s
        elif isinstance(s, dict):     # rehydrated from JSON
            s = GradeStats(**s)
            self.stats[k] = s
        return s

    def total_completed(self) -> int:
        return sum((s if isinstance(s, GradeStats) else GradeStats(**s)).completed
                   for s in self.stats.values())

    def is_probationary(self) -> bool:
        return self.total_completed() < PROBATION_COMPLETIONS

    def score(self, grade: str, process: str) -> float:
        if self.expelled:
            return 0.0
        s = self._stats(grade, process)
        n = s.completed + s.failed
        observed = s.score()
        # blend prior with observed, weighting observed as history accrues
        w = min(1.0, n / 5.0)
        blended = (1 - w) * self.prior + w * observed
        if self.is_probationary():
            blended *= 0.85           # slight down-rank until graduated
        return round(blended, 4)

    # -- outcome recording (network-called) --
    def record_completion(self, grade, process, on_time=True, qa_pass=True):
        s = self._stats(grade, process)
        s.completed += 1
        s.on_time += 1 if on_time else 0
        s.qa_pass += 1 if qa_pass else 0

    def record_failure(self, grade, process):
        self._stats(grade, process).failed += 1

    def record_dispute_lost(self, grade, process):
        self._stats(grade, process).disputes_lost += 1

    def stake(self, cents: int):
        self.staked_cents += cents

    def slash(self, cents: int, expel: bool = False):
        take = min(cents, self.staked_cents)
        self.staked_cents -= take
        self.slashed_cents += take
        if expel:
            self.expelled = True
        return take

    def to_dict(self):
        d = asdict(self)
        return d


@dataclass
class BuyerRep:
    buyer: str
    claims_filed: int = 0
    claims_upheld: int = 0
    claims_rejected: int = 0     # scored out-of-grade / frivolous

    def claim_quality(self) -> float:
        if self.claims_filed == 0:
            return 1.0            # no claims = no problem
        return round(self.claims_upheld / self.claims_filed, 4)

    def record_claim(self, upheld: bool):
        self.claims_filed += 1
        if upheld:
            self.claims_upheld += 1
        else:
            self.claims_rejected += 1


class ReputationBook:
    """Network-held record of node and buyer reputation."""

    def __init__(self):
        self.nodes: dict[str, NodeRep] = {}
        self.buyers: dict[str, BuyerRep] = {}

    def node(self, node_id: str, prior: float = 0.5) -> NodeRep:
        r = self.nodes.get(node_id)
        if r is None:
            r = NodeRep(node_id=node_id, prior=prior)
            self.nodes[node_id] = r
        return r

    def buyer(self, buyer: str) -> BuyerRep:
        r = self.buyers.get(buyer)
        if r is None:
            r = BuyerRep(buyer=buyer)
            self.buyers[buyer] = r
        return r

    def node_score(self, node_id: str, grade: str, process: str, prior: float = 0.5) -> float:
        return self.node(node_id, prior).score(grade, process)

    def save(self, path: str, *, store=None):
        """Persist through the storage seam (`bingo/store.py`).

        Same upgrade as the asset registry: this was a bare `json.dump` into an
        open handle, so a crash mid-write left a truncated book. It holds node
        **stakes** as well as scores, which is real value at risk, and it is
        read-modify-written by every settlement.

        `path` keeps its meaning - the same JSON file, same shape, now written
        atomically and fsynced.
        """
        st = store if store is not None else _store.node_store(_base(path))
        try:
            with st.transaction():
                st.put("nodes", {k: v.to_dict() for k, v in self.nodes.items()})
                st.put("buyers", {k: asdict(v) for k, v in self.buyers.items()})
        finally:
            if store is None:
                st.close()

    @classmethod
    def load(cls, path: str, *, store=None) -> "ReputationBook":
        book = cls()
        if store is not None:
            data = dict(store.items())
        else:
            # under the default backend `_base(path) + ".json"` is `path` itself,
            # so a book written by the old code loads unchanged
            st = _store.node_store(_base(path))
            try:
                data = dict(st.items())
            finally:
                st.close()
        for k, v in data.get("nodes", {}).items():
            book.nodes[k] = NodeRep(**v)
        for k, v in data.get("buyers", {}).items():
            book.buyers[k] = BuyerRep(**v)
        return book
