"""One "who got paid" picture across the whole network.

The point of the network is that value reaches the people who made it — and
those people are heterogeneous: a designer whose STL prints on a farm, a
third-generation rancher whose feed becomes an A5 cut, everyone in between. Their
money currently lives in three different places:

  * design royalties     — settled into the ledger by fabrication jobs
  * RWA physical sale     — the provenance passport's own sale split
  * token sales           — proceeds routed through that split as claims trade

This rolls all three into a single per-account total with a source breakdown, so
the rancher shows up next to the 3D-print creators in one list. Every number is
derived from settled records — ledger legs, signed passport settlements, and
replayable token ledgers — nothing shown that wasn't actually paid.
"""

from __future__ import annotations

from .register import passport_of
from .token import token_settlement

SOURCES = ("design_royalties", "rwa_sale", "token_sales")


def network_earnings(ledger, registry, tokens: dict) -> list[dict]:
    """Aggregate every account's earnings across all three value streams,
    returned as a list of {account, total_cents, sources:{...}} sorted by total."""
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

    out = [{"account": a, "total_cents": sum(s.values()), "sources": s}
           for a, s in acc.items()]
    out.sort(key=lambda r: -r["total_cents"])
    return out


def account_earnings(ledger, registry, tokens: dict, account: str) -> dict:
    """The unified earnings for a single account across all three streams."""
    for row in network_earnings(ledger, registry, tokens):
        if row["account"] == account:
            return row
    return {"account": account, "total_cents": 0, "sources": {s: 0 for s in SOURCES}}
