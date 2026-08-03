"""Creator earnings — the whole vision in a number a designer can open.

Aggregates a creator's royalties from the settlement journal: total paid, units
that paid it, and a per-design breakdown. This is what a designer sees — "your
bracket earned you $X across Y prints on Z machines, and you never lifted a
finger" — the emotional payload the network exists to deliver. Derived purely
from settled ledger entries; nothing shown that wasn't actually paid.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DesignEarning:
    asset_id: str
    title: str
    cents: int = 0
    units: int = 0


@dataclass
class CreatorEarnings:
    account: str
    total_cents: int = 0
    units: int = 0                       # units that paid this creator (may span designs)
    machines: int = 0                    # distinct nodes that fabricated for them
    orders: int = 0
    designs: list = field(default_factory=list)   # list[DesignEarning], desc by cents

    def to_dict(self) -> dict:
        return {
            "account": self.account,
            "total_cents": self.total_cents,
            "units": self.units,
            "machines": self.machines,
            "orders": self.orders,
            "designs": [{"asset_id": d.asset_id, "title": d.title,
                         "cents": d.cents, "units": d.units} for d in self.designs],
        }


def _title_of(registry, asset_id: str) -> str:
    try:
        return registry.get(asset_id).title
    except Exception:
        return asset_id[:12] + "…"


def _asset_for_tag(tag: str, royalty_assets: list[str]) -> str:
    """A royalty leg's memo carries the asset tag (first 8 hex of the id).
    Resolve it to the full asset id recorded in the entry's provenance."""
    for aid in royalty_assets:
        if aid.startswith(tag):
            return aid
    return tag


def creator_earnings(ledger, registry, account: str) -> CreatorEarnings:
    """Sum every royalty leg paid to `account` across the settlement journal,
    attributing each to its design and counting units, machines, and orders."""
    out = CreatorEarnings(account=account)
    designs: dict[str, DesignEarning] = {}
    machines: set[str] = set()
    orders: set[str] = set()

    for e in ledger.journal:
        if e.kind != "JOB_SETTLEMENT":
            continue
        royalty_legs = [l for l in e.legs
                        if l.account == account and l.memo.startswith("royalty")]
        if not royalty_legs:
            continue
        prov = e.provenance or {}
        qty = int(prov.get("qty", 0) or 0)
        royalty_assets = prov.get("royalty_assets", []) or []
        node_id = prov.get("node_id")
        if node_id:
            machines.add(node_id)
        if e.order_id:
            orders.add(e.order_id)
        out.units += qty
        for leg in royalty_legs:
            out.total_cents += leg.amount_cents
            tag = leg.memo.split("[")[-1].rstrip("]") if "[" in leg.memo else ""
            aid = _asset_for_tag(tag, royalty_assets)
            d = designs.get(aid)
            if d is None:
                d = DesignEarning(asset_id=aid, title=_title_of(registry, aid))
                designs[aid] = d
            d.cents += leg.amount_cents
            d.units += qty

    out.machines = len(machines)
    out.orders = len(orders)
    out.designs = sorted(designs.values(), key=lambda d: d.cents, reverse=True)
    return out


def statement_text(e: CreatorEarnings) -> str:
    """A plain-text creator statement — the shareable receipt of getting paid."""
    lines = [
        f"BINGO creator statement — {e.account}",
        "=" * 44,
        f"Total earned:  ${e.total_cents / 100:,.2f}",
        f"Across:        {e.units} units · {len(e.designs)} design(s) · "
        f"{e.machines} machine(s) · {e.orders} order(s)",
        "",
        "By design:",
    ]
    if not e.designs:
        lines.append("  (no royalties yet)")
    for d in e.designs:
        lines.append(f"  {d.title:<34} ${d.cents / 100:>8.2f}  ({d.units} units)")
    lines += ["",
              "Paid automatically, at the point of fabrication, on every unit —",
              "no invoice, no platform's mercy. This is your money."]
    return "\n".join(lines)
