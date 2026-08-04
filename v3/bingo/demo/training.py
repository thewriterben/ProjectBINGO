"""Training-material royalties, end to end — the dashboard number for AI itself.

  register knowledge -> train a model on it -> the model earns fees in use
  -> its teachers are paid, per asset, metered, forever

Run:  python -m bingo.demo.training   (from v3/)

The closing line is the whole point in one integer: a print-profile author
passively earning royalties every time the network's design agent — trained on
their work — is used. No platform offers that today.
"""

from __future__ import annotations

from ..models import License, LicenseTemplate, Split, SplitPayee
from ..registry import AssetRegistry
from ..training import (RoyaltyMeter, Trainer, build_corpus,
                        contribution_from_asset, earnings_by_account,
                        earnings_by_asset)


def _net_train_license():
    return License(LicenseTemplate.NETWORK_TRAINING, training_share_bps=500)


def main() -> int:
    reg = AssetRegistry()

    # Three people contribute knowledge the network's design agent learns from.
    profile = reg.register(
        kind="print-profile", title="PETG on textured PEI — 0.2mm, tuned",
        creator="acct:rosa", content=b"[print_profile] petg ...",
        license=_net_train_license(), split=Split([SplitPayee("acct:rosa", 10_000)]))
    dataset = reg.register(
        kind="failure-dataset", title="1,842 annotated first-layer failures",
        creator="acct:sam", content=b"[dataset] warp, elephant-foot, ...",
        license=_net_train_license(),
        split=Split([SplitPayee("acct:sam", 7_000), SplitPayee("acct:lab", 3_000)]))
    library = reg.register(
        kind="design-library", title="Parametric bracket family (48 parts)",
        creator="acct:theo", content=b"[library] brackets ...",
        license=_net_train_license(), split=Split([SplitPayee("acct:theo", 10_000)]))

    # The network trains its design agent on all three, weighted by how much each
    # contributed, and signs the attribution corpus.
    trainer = Trainer.create("bingo-trainer", "acct:network")
    corpus = build_corpus(trainer, "design-agent-v1", [
        contribution_from_asset(profile, units=1_842),   # examples / tokens / bytes
        contribution_from_asset(dataset, units=1_842),
        contribution_from_asset(library, units=4_800),
    ], ts="2026-08-04T00:00:00Z")

    print("Project BINGO — training-material royalties\n")
    print(f"Model: design-agent-v1   corpus {corpus['corpus_id'][:16]}…")
    print("Trained on 3 registered assets (signed attribution corpus):")
    for c in corpus["contributions"]:
        print(f"  • {c['asset_id'][:12]}…  {c['units']:>5} units  "
              f"→ {', '.join(p['account'] for p in c['payees'])}")

    # The agent is used across the month — every fee-earning action accrues 5% of
    # its fee to the training pool. (One line each here; a real month is millions.)
    meter = RoyaltyMeter()
    uses = [("quote", 2_000), ("dfm-fix", 1_500), ("spec-draft", 3_000),
            ("match", 800), ("quote", 2_400), ("spec-draft", 3_600),
            ("quote", 1_900), ("dfm-fix", 1_200)]
    for i, (kind, fee) in enumerate(uses):
        meter.record_usage("design-agent-v1", f"{kind}-{i}", fee_cents=fee,
                           training_share_bps=500)
    pool = meter.pool_cents("design-agent-v1")
    print(f"\n{len(uses)} fee-earning uses this period → training pool ${pool/100:,.2f} "
          f"(5% of ${sum(f for _, f in uses)/100:,.2f} in fees)")

    # Settle: the pool is paid out, per asset, then through each asset's split.
    legs = meter.settle(corpus)
    print("\nPaid to contributors (per asset → per payee, to the cent):")
    for asset_id, cents in sorted(earnings_by_asset(legs).items(), key=lambda kv: -kv[1]):
        print(f"  {asset_id[:12]}…  ${cents/100:>6.2f}")
    print("\nBy person:")
    for acct, cents in sorted(earnings_by_account(legs).items(), key=lambda kv: -kv[1]):
        print(f"  {acct:<14} ${cents/100:>6.2f}")

    total = sum(l.amount_cents for l in legs)
    assert total == pool, "distribution must conserve"
    print(f"\n  ✓ ${total/100:,.2f} distributed, to the cent, across {len(uses)} uses — "
          f"and it recurs every time the model is used again, forever.")
    print("\nThe integer that is the whole idea: Rosa's tuned print profile just "
          f"earned ${earnings_by_account(legs)['acct:rosa']/100:.2f} because an AI "
          "learned from it — without her lifting a finger, and without a platform's "
          "permission.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
