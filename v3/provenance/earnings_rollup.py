"""One "who got paid" picture across the whole network.

The point of the network is that value reaches the people who made it — and
those people are heterogeneous: a designer whose STL prints on a farm, a
third-generation rancher whose feed becomes an A5 cut, a print-profile author
whose tuning taught the network's AI, everyone in between. Their money lives in
four different places:

  * design royalties     — settled into the ledger by fabrication jobs
  * RWA physical sale     — the provenance passport's own sale split
  * token sales           — proceeds routed through that split as claims trade
  * training royalties    — the model's usage paid out through the training corpus

This rolls all four into a single per-account total with a source breakdown, so
the rancher, the 3D-print creators, and the person whose knowledge trained the
design agent all show up in one list. Every number is derived from settled
records — ledger legs, signed passport settlements, replayable token ledgers, and
the payout legs a signed training corpus distributed — nothing shown that wasn't
actually paid.
"""

from __future__ import annotations

from .register import passport_of
from .token import token_settlement

SOURCES = ("design_royalties", "rwa_sale", "token_sales", "training_royalties")


def network_earnings(ledger, registry, tokens: dict, training_legs=None) -> list[dict]:
    """Aggregate every account's earnings across all four value streams, returned
    as a list of {account, total_cents, sources:{...}} sorted by total.

    `training_legs` is the accumulated payout legs from settled training-royalty
    distributions (`bingo.training.RoyaltyMeter.settle` / `distribute` — anything
    with `.account` and `.amount_cents`). Omit it and the view is the original
    three streams, unchanged."""
    acc: dict[str, dict] = {}

    def add(account: str, source: str, cents: int):
        if cents:
            d = acc.setdefault(account, {s: 0 for s in SOURCES})
            d[source] += cents

    # 1. design royalties — from settled fabrication jobs in the ledger
    for e in ledger.journal:
        if e.kind != "JOB_SETTLEMENT":
            continue
        for l in e.legs:
            if l.memo.startswith("royalty"):
                add(l.account, "design_royalties", l.amount_cents)

    # 2. RWA physical sale — the passport's own signed value split
    for a in registry.all():
        if a.kind != "rwa":
            continue
        for leg in passport_of(registry, a).get("settlement", []):
            add(leg["account"], "rwa_sale", leg["cents"])

    # 3. token sales — proceeds routed through the provenance split as claims trade
    for td in tokens.values():
        for account, cents in token_settlement(td)["paid"].items():
            add(account, "token_sales", cents)

    # 4. training royalties — the payout legs a signed corpus distributed on usage
    for leg in (training_legs or []):
        add(leg.account, "training_royalties", leg.amount_cents)

    out = [{"account": a, "total_cents": sum(s.values()), "sources": s}
           for a, s in acc.items()]
    out.sort(key=lambda r: -r["total_cents"])
    return out


def account_earnings(ledger, registry, tokens: dict, account: str, training_legs=None) -> dict:
    """The unified earnings for a single account across all four streams."""
    for row in network_earnings(ledger, registry, tokens, training_legs):
        if row["account"] == account:
            return row
    return {"account": account, "total_cents": 0, "sources": {s: 0 for s in SOURCES}}
