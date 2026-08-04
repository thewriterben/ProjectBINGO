"""Training-material royalties: a signed attribution corpus (tamper/forge/reorder
caught offline), an atomic pool split by contribution share then through each
asset's own split (co-authors paid, conserved to the cent), single-use usage
metering (no double count), recurrence (pay per unit of use, forever), and
base-model composition (a fine-tune pays the base model's teachers). Run:

  python -m tests.test_training
"""

from __future__ import annotations

import copy
import json
import sys

from bingo.models import Split, SplitPayee, License, LicenseTemplate
from bingo.registry import AssetRegistry
from bingo.training import (
    Contribution, RoyaltyMeter, Trainer, TrainingError, build_corpus,
    contribution_from_asset, distribute, earnings_by_account, earnings_by_asset,
    verify_corpus,
)


def payees(*pairs):
    return [SplitPayee(acct, bps) for acct, bps in pairs]


def sample_corpus(trainer=None):
    """A model trained on three assets with different contributions; the middle
    asset is co-authored (two payees)."""
    trainer = trainer or Trainer.create("net-trainer", "acct:network")
    contribs = [
        Contribution("asset-profile", 600, payees(("acct:alice", 10_000))),
        Contribution("asset-dataset", 300, payees(("acct:bob", 7_000), ("acct:carol", 3_000))),
        Contribution("asset-fails", 100, payees(("acct:dave", 10_000))),
    ]
    return build_corpus(trainer, "design-agent-v1", contribs, ts="t0"), trainer


def main() -> int:
    # ── corpus signs and verifies from the document alone ────────────────────
    corpus, trainer = sample_corpus()
    ok, notes = verify_corpus(corpus)
    assert ok, notes
    # round-trips as plain JSON, still verifies offline
    assert verify_corpus(json.loads(json.dumps(corpus)))[0]

    # tamper: inflate a contribution's units → id no longer matches the body
    t = copy.deepcopy(corpus)
    t["contributions"][0]["units"] = 9_999
    assert not verify_corpus(t)[0], "tampered units must be caught"

    # forge: swap in a different trainer's pubkey but keep the signature
    imposter = Trainer.create("imposter", "acct:evil")
    f = copy.deepcopy(corpus)
    f["trainer"]["pubkey"] = imposter.pubkey_hex
    assert not verify_corpus(f)[0], "forged trainer must be caught"

    # reorder: shuffle the contribution list → canonical body changes, id breaks
    r = copy.deepcopy(corpus)
    r["contributions"].reverse()
    assert not verify_corpus(r)[0], "reordered contributions must be caught"

    # a payee split that doesn't sum to 10000 is rejected
    bad = copy.deepcopy(corpus)
    bad["contributions"][0]["payees"][0]["bps"] = 9_000
    # (recompute id+sig over the bad body so we isolate the split check)
    bad_trainer = trainer
    from bingo.models import canonical_json, sha256_hex
    from bingo.training import _corpus_body
    body = _corpus_body(bad["model_version"], bad["contributions"], bad["base_corpus_id"],
                        bad["base_share_bps"], bad["trainer"]["account"],
                        bad["trainer"]["pubkey"], bad["ts"])
    bad["corpus_id"] = sha256_hex(canonical_json(body))
    bad["sig"] = bad_trainer.sign(canonical_json(body))
    assert not verify_corpus(bad)[0], "under-summing payees must be caught"

    # ── distribution: by contribution share, then each asset's own split ─────
    # Pool of $100.00 over units 600/300/100 = 6000/3000/1000 cents by asset.
    legs = distribute(corpus, 10_000)
    assert sum(l.amount_cents for l in legs) == 10_000, "must conserve to the cent"
    by_asset = earnings_by_asset(legs)
    assert by_asset["asset-profile"] == 6_000
    assert by_asset["asset-dataset"] == 3_000
    assert by_asset["asset-fails"] == 1_000
    # the co-authored dataset ($30.00) splits 70/30 within itself
    by_acct = earnings_by_account(legs)
    assert by_acct["acct:alice"] == 6_000
    assert by_acct["acct:bob"] == 2_100      # 70% of 3000
    assert by_acct["acct:carol"] == 900      # 30% of 3000
    assert by_acct["acct:dave"] == 1_000

    # residue: a pool that doesn't divide evenly still conserves, remainder → the
    # largest contribution (asset-profile).
    legs = distribute(corpus, 10_001)
    assert sum(l.amount_cents for l in legs) == 10_001
    assert earnings_by_asset(legs)["asset-profile"] == 6_001  # got the extra cent

    # ── single-use metering + recurrence ─────────────────────────────────────
    meter = RoyaltyMeter()
    mv = "design-agent-v1"
    # each fee-earning use accrues 5% (500bps) of its fee to the training pool
    meter.record_usage(mv, "job-1", fee_cents=2_000, training_share_bps=500)  # +100
    meter.record_usage(mv, "job-2", fee_cents=6_000, training_share_bps=500)  # +300
    assert meter.pool_cents(mv) == 400
    # a replayed event is refused (no double count)
    try:
        meter.record_usage(mv, "job-1", fee_cents=2_000, training_share_bps=500)
        assert False, "replayed usage event must be rejected"
    except TrainingError as e:
        assert "double count" in str(e)

    # settle drains the pool to the contributors, conserving
    paid = meter.settle(corpus)
    assert sum(l.amount_cents for l in paid) == 400
    assert meter.pool_cents(mv) == 0
    assert meter.lifetime_paid(mv) == 400
    # settling again with nothing accrued pays nothing (safe)
    assert meter.settle(corpus) == []
    # recurrence: new usage accrues afresh; next settle pays only the increment
    meter.record_usage(mv, "job-3", fee_cents=10_000, training_share_bps=500)  # +500
    paid2 = meter.settle(corpus)
    assert sum(l.amount_cents for l in paid2) == 500
    assert meter.lifetime_earned(mv) == 900 and meter.lifetime_paid(mv) == 900

    # settle refuses an unverified corpus (fail closed)
    try:
        meter.settle(t)  # the tampered corpus from above
        assert False, "must refuse to settle an unverified corpus"
    except TrainingError:
        pass

    # ── base-model composition: a fine-tune pays the base model's teachers ────
    base = corpus  # the v1 corpus is the base
    ft_trainer = Trainer.create("net-trainer", "acct:network")
    fine_tune = build_corpus(
        ft_trainer, "design-agent-v2",
        [Contribution("asset-newdata", 1_000, payees(("acct:erin", 10_000)))],
        ts="t1", base_corpus_id=base["corpus_id"], base_share_bps=2_000,  # 20% up to the base
    )
    assert verify_corpus(fine_tune)[0]
    ft_legs = distribute(fine_tune, 10_000, base_corpus=base)
    assert sum(l.amount_cents for l in ft_legs) == 10_000, "composition must conserve"
    ba = earnings_by_account(ft_legs)
    # 20% ($20) flowed to the base's contributors; 80% ($80) to erin.
    assert ba["acct:erin"] == 8_000
    base_total = sum(v for k, v in ba.items() if k != "acct:erin")
    assert base_total == 2_000
    # and within the base, the same 60/30/10 units split applied to $20:
    assert ba["acct:alice"] == 1_200        # 60% of 2000
    assert ba["acct:bob"] == 420            # 70% of (30% of 2000 = 600)
    assert ba["acct:carol"] == 180          # 30% of 600
    assert ba["acct:dave"] == 200           # 10% of 2000

    # a corpus that owes a base share but is handed no base fails closed
    try:
        distribute(fine_tune, 10_000)
        assert False, "must not silently keep the base's share"
    except TrainingError:
        pass

    # ── plugs into the real asset registry (frozen effective_split) ───────────
    reg = AssetRegistry()
    design = reg.register(
        kind="design", title="Bracket", creator="acct:maker",
        content=b"solid bracket {}",
        license=License(LicenseTemplate.NETWORK_TRAINING, training_share_bps=500),
        split=Split(payees(("acct:maker", 10_000))),
    )
    contrib = contribution_from_asset(design, units=250)
    assert contrib.asset_id == design.asset_id
    assert contrib.payees[0].account == "acct:maker"
    c2, tr2 = Trainer.create("t", "acct:net"), None
    corp2 = build_corpus(c2, "m", [contrib], ts="t")
    assert verify_corpus(corp2)[0]
    assert sum(l.amount_cents for l in distribute(corp2, 4_242)) == 4_242

    print("OK — training corpus signs & verifies offline (tamper/forge/reorder/"
          "under-summing splits all caught); a royalty pool splits by contribution "
          "share then through each asset's own split, conserving to the cent with "
          "co-authors paid; usage is metered single-use (no double count) and "
          "recurs (pay per unit of use, forever); a fine-tune pays the base model's "
          "teachers via composition; and it plugs into the real asset registry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
