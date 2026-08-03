"""L3 — Orchestrator: the pipeline embryo.

intake -> DFM -> quote -> match -> dispatch -> track -> logistics -> settle

Each stage is a function today and an independently replaceable agent
tomorrow (the stage boundaries here mirror the open interfaces in the
vision doc). One class so the demo reads as one story.
"""

from __future__ import annotations

import uuid

from .dfm import analyze, DfmReport
from .ledger import Ledger
from .match import score_nodes, allocate
from .models import Asset, Job, JobState, Order, RoyaltyLine
from .node.agent import NodeAgent
from .quote import quote_job, apply_network_fee
from .registry import AssetRegistry


class OrderRejected(Exception):
    pass


class Orchestrator:
    def __init__(self, registry: AssetRegistry, ledger: Ledger, nodes: list[NodeAgent]):
        self.registry = registry
        self.ledger = ledger
        self.nodes = {a.info.node_id: a for a in nodes}
        self.orders: dict[str, Order] = {}

    # -- intake -> quote -> match -> escrow ------------------------------------

    def place_order(self, *, buyer: str, asset_id: str, qty: int, material: str,
                    buyer_lat: float, buyer_lon: float,
                    declared_use: str = "commercial",
                    required_tier: int = 0,
                    dfm_override: DfmReport | None = None,
                    extra_royalty_assets: list | None = None) -> tuple[Order, DfmReport]:
        """dfm_override: for assets that aren't raw STL (e.g. pre-sliced,
        already-proven gcode), the caller supplies time/mass estimates
        instead of geometric analysis.
        extra_royalty_assets: additional Assets (e.g. a process package, a
        derivative parent) whose per-unit royalty rides on this order — each
        settles to its OWN effective split, not the design's."""
        asset = self.registry.get(asset_id)
        extra_royalty_assets = extra_royalty_assets or []

        if dfm_override is not None:
            dfm = dfm_override
        else:
            stl = self.registry.get_content(asset)
            # DFM against the smallest candidate envelope (conservative)
            envelopes = [m.envelope_mm for a in self.nodes.values() for m in a.info.machines]
            smallest = min(envelopes, key=lambda e: e[0] * e[1] * e[2])
            dfm = analyze(stl, smallest)
        if not dfm.ok:
            raise OrderRejected(f"DFM failed: {dfm.issues}")

        scored = score_nodes([a.info for a in self.nodes.values()],
                             required_tier=required_tier, material=material,
                             buyer_lat=buyer_lat, buyer_lon=buyer_lon)
        allocation = allocate(qty, scored)

        quotes = [quote_job(node, asset, dfm, q, material, buyer_lat, buyer_lon,
                            declared_use) for node, q in allocation]
        # design royalty (per quote) + one extra line per extra asset, each at
        # its own per-unit rate. jq.royalty_cents carries the TOTAL for the
        # fee/subtotal math; the per-asset breakdown lives in royalty_lines.
        design_royalty = {id(jq): jq.royalty_cents for jq in quotes}
        for jq in quotes:
            jq.royalty_cents = design_royalty[id(jq)] + sum(
                a.license.per_unit_cents * jq.qty for a in extra_royalty_assets)
        total = apply_network_fee(quotes)

        order = Order(order_id=f"ord-{uuid.uuid4().hex[:8]}", buyer=buyer,
                      asset_id=asset_id, qty=qty, material=material,
                      buyer_lat=buyer_lat, buyer_lon=buyer_lon,
                      declared_use=declared_use, total_cents=total)
        for jq in quotes:
            lines = [RoyaltyLine(asset.asset_id, design_royalty[id(jq)],
                                 asset.effective_split.payees)]
            for a in extra_royalty_assets:
                c = a.license.per_unit_cents * jq.qty
                if c > 0:
                    lines.append(RoyaltyLine(a.asset_id, c, a.effective_split.payees))
            job = Job(job_id=f"job-{uuid.uuid4().hex[:8]}", order_id=order.order_id,
                      asset_id=asset_id, node_id=jq.node.node_id, qty=jq.qty,
                      material=material,
                      fabrication_cents=jq.fabrication_cents,
                      material_cents=jq.material_cents,
                      energy_cents=jq.energy_cents,
                      logistics_cents=jq.logistics_cents,
                      royalty_lines=lines,
                      fee_cents=jq.fee_cents)
            assert job.royalty_cents == jq.royalty_cents, "royalty lines must sum to quoted royalty"
            order.jobs.append(job)

        self.orders[order.order_id] = order
        self.ledger.fund_escrow(order)      # buyer pays at placement
        return order, dfm

    # -- dispatch -> fabricate -> ship -> deliver -> settle ------------------------

    def execute_order(self, order: Order, dfm: DfmReport,
                      narrate=lambda s: None, gcode: bytes | None = None,
                      confirm_delivery=None) -> list[Job]:
        """gcode: operator-supplied sliced file for real hardware; falls back
        to the deterministic slice stub for simulated nodes.
        confirm_delivery: optional callable(job) -> confirmer string; defaults
        to the simulated carrier webhook. Real runs pass a human/webhook hook."""
        asset = self.registry.get(order.asset_id)
        gcode = gcode or self._slice_stub(order, dfm)
        settled = []
        for job in order.jobs:
            agent = self.nodes[job.node_id]
            terms = {"job_id": job.job_id, "qty": job.qty,
                     "payment_cents": job.job_total_cents}
            if not agent.offer(job, terms):
                job.state = JobState.FAILED
                narrate(f"  ✗ {agent.info.name} declined {job.job_id} (re-route in v0.2)")
                continue
            narrate(f"  ▸ {agent.info.name} accepted {job.job_id} ({job.qty} units)")
            agent.fabricate(job, gcode, est_minutes_per_unit=dfm.est_hours_per_unit * 60)
            narrate(f"    fabricated {job.qty} units — {len(job.evidence)} PoF events, "
                    f"chain head {job.chain_head()[:12]}…")
            agent.ship(job, carrier="usps", tracking=f"94{uuid.uuid4().hex[:14]}")
            confirmer = (confirm_delivery(job) if confirm_delivery
                         else "carrier:usps-webhook")
            agent.confirm_delivery(job, confirmer=confirmer)

            assert NodeAgent.verify_chain(job), "PoF chain verification failed"
            entry = self.ledger.settle_job(order, job)
            job.state = JobState.SETTLED
            settled.append(job)
            narrate(f"    ✓ settled atomically — journal entry #{entry.entry_id}, "
                    f"{len(entry.legs)} legs")
        return settled

    @staticmethod
    def _slice_stub(order: Order, dfm: DfmReport) -> bytes:
        """Deterministic gcode stand-in; a real slicer (PrusaSlicer/OrcaSlicer CLI)
        drops in here. What matters for PoF is that its hash is committed."""
        return (f"; bingo v0 sliced {order.asset_id[:12]} "
                f"vol={dfm.volume_mm3:.0f}mm3 material={order.material}\n"
                f"G28\nG1 Z0.2\n; …\n").encode()
