"""Reputation: per-grade vectors, network-maintained (not self-reported),
staking/slashing, probation, buyer claim-quality. Run:

  python -m tests.test_reputation
"""

from __future__ import annotations

import sys

from bingo.reputation import ReputationBook, PROBATION_COMPLETIONS
from bingo.match import score_nodes
from bingo.models import Machine, NodeInfo


def node(nid, tier=2, rep=0.5):
    return NodeInfo(node_id=nid, operator=f"acct:{nid}", name=nid, lat=0, lon=0,
                    tier=tier, rate_cents_per_hour=400,
                    machines=[Machine("m", "K2", "fdm", (350, 350, 350), ["PLA"], 0.3)],
                    materials_on_hand=["PLA"], reputation=rep)


def main() -> int:
    book = ReputationBook()

    # per-grade vector: a node proves itself at F, stays neutral at P
    r = book.node("n1")
    for _ in range(6):
        r.record_completion("F", "fdm", on_time=True, qa_pass=True)
    assert r.score("F", "fdm") > 0.8, r.score("F", "fdm")
    assert abs(r.score("P", "fdm") - 0.5) < 0.15, "unrated at P despite F history"

    # network-maintained: score comes from the book, node can't inflate its own
    assert book.node_score("n1", "F", "fdm") == r.score("F", "fdm")

    # probation: a brand-new node is down-ranked and graduates after N completions
    fresh = book.node("n2")
    assert fresh.is_probationary()
    for _ in range(PROBATION_COMPLETIONS):
        fresh.record_completion("F", "fdm")
    assert not fresh.is_probationary()

    # staking + slashing: fraud is net-negative; expelled node scores 0 + excluded
    bad = book.node("n3")
    bad.stake(10_000)
    for _ in range(4):
        bad.record_completion("F", "fdm")
    good_before = bad.score("F", "fdm")
    bad.record_dispute_lost("F", "fdm")
    bad.slash(10_000, expel=True)
    assert bad.slashed_cents == 10_000 and bad.staked_cents == 0
    assert bad.score("F", "fdm") == 0.0 and good_before > 0.0

    # matching is grade-aware and excludes the expelled node
    nodes = [node("n1"), node("n3")]
    scored = score_nodes(nodes, required_tier=0, material="PLA",
                         buyer_lat=0, buyer_lon=0, reputation_book=book, grade="F")
    ids = [s.node.node_id for s in scored]
    assert "n3" not in ids, "expelled node must be excluded from matching"
    assert ids and ids[0] == "n1", "proven node ranks first"

    # buyer reputation: chronic bad claims tank claim quality
    b = book.buyer("acct:picky")
    for _ in range(3):
        b.record_claim(upheld=False)
    b.record_claim(upheld=True)
    assert b.claim_quality() == 0.25, b.claim_quality()
    assert book.buyer("acct:clean").claim_quality() == 1.0

    # round-trip persistence
    import tempfile, os
    p = os.path.join(tempfile.mkdtemp(), "rep.json")
    book.save(p)
    b2 = ReputationBook.load(p)
    assert b2.node("n1").score("F", "fdm") == r.score("F", "fdm")

    print("OK — per-grade vectors, network-maintained scores, probation, "
          "stake/slash/expel, grade-aware matching exclusion, buyer claim-quality, persistence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
