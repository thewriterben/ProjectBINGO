"""L2 — Node agent.

Runs at a fabricator's site: accepts jobs, drives machines, and emits the
hash-chained, ed25519-signed PoF evidence log per specs/NODE-AGENT.md.

Signing: Ed25519. Each node holds a 32-byte seed (private key) and publishes
its public key; every evidence event is signed over its canonical body. The
chain is hash-linked (prev_hash) AND signed, so ANYONE with the node's public
key can verify the whole log independently — the property HMAC could not give.
"""

from __future__ import annotations

from .. import crypto
from ..models import (EvidenceEvent, Job, JobState, NodeInfo,
                      now_iso, sha256_hex, canonical_json)
from .drivers import MockDriver


class NodeAgent:
    def __init__(self, info: NodeInfo, driver: MockDriver | None = None,
                 seed: bytes | None = None):
        self.info = info
        self.driver = driver or MockDriver(info.machines[0].machine_id)
        self._seed, self._pk = crypto.keypair(seed)   # private seed, public key
        self.public_key_hex = self._pk.hex()
        info.public_key_hex = self.public_key_hex     # publish on the node record

    # -- evidence chain -------------------------------------------------------

    def _sign(self, payload: bytes) -> str:
        return crypto.sign(payload, self._seed, self._pk).hex()

    def _emit(self, job: Job, type_: str, data: dict):
        ev = EvidenceEvent(seq=len(job.evidence) + 1, ts=now_iso(),
                           type=type_, data=data, prev_hash=job.chain_head())
        body = canonical_json(ev.body())
        ev.sig = self._sign(body)
        ev.hash = sha256_hex(body + ev.sig.encode())
        job.evidence.append(ev)

    @staticmethod
    def verify_chain(job: Job, public_key_hex: str | None = None) -> bool:
        """Verify hash-chain integrity always. If a public key is supplied,
        also verify every event's ed25519 signature — full independent
        verification of who produced the evidence, not just that it's ordered."""
        pk = bytes.fromhex(public_key_hex) if public_key_hex else None
        prev = "0" * 64
        for ev in job.evidence:
            if ev.prev_hash != prev:
                return False
            body = canonical_json(ev.body())
            if ev.hash != sha256_hex(body + ev.sig.encode()):
                return False
            if pk is not None:
                try:
                    if not crypto.verify(body, bytes.fromhex(ev.sig), pk):
                        return False
                except ValueError:
                    return False
            prev = ev.hash
        # bind the Job's identity to the SIGNED JOB_ACCEPTED event — a relabeled
        # Job (or another node's events spliced under a different job) must fail
        ja = next((e for e in job.evidence if e.type == "JOB_ACCEPTED"), None)
        if ja and "job_id" in ja.data:
            for attr in ("job_id", "order_id", "asset_id", "qty"):
                if attr in ja.data and getattr(job, attr) != ja.data[attr]:
                    return False
            if "royalty_assets" in ja.data and \
                    [l.asset_id for l in job.royalty_lines] != ja.data["royalty_assets"]:
                return False
        return True

    # -- job lifecycle -----------------------------------------------------------

    def offer(self, job: Job, terms: dict) -> bool:
        """Accept/decline. v0 policy: accept if the material is loadable."""
        capable = any(job.material in m.materials for m in self.info.machines)
        if not capable:
            job.state = JobState.DECLINED
            return False
        job.state = JobState.ACCEPTED
        self._emit(job, "JOB_ACCEPTED",
                   {"terms_sha256": sha256_hex(canonical_json(terms)),
                    "node_id": self.info.node_id,
                    "node_pubkey": self.public_key_hex,
                    # bind job identity INTO the signed chain, so the top-level
                    # metadata can't be relabeled (asset/order/qty forgery)
                    "job_id": job.job_id, "order_id": job.order_id,
                    "asset_id": job.asset_id, "qty": job.qty,
                    "royalty_assets": [l.asset_id for l in job.royalty_lines]})
        return True

    def fabricate(self, job: Job, gcode: bytes, est_minutes_per_unit: float):
        job.state = JobState.PREPARING
        prep = self.driver.prepare(gcode)
        self._emit(job, "INPUT_HASH", prep)
        job.state = JobState.RUNNING
        if hasattr(self.driver, "run_batch"):
            # batch processes (MSLA plates, manual mode): one evidence stream
            # covering all units; driver must emit qty UNIT_COMPLETE events.
            for obs in self.driver.run_batch(job.job_id, job.qty,
                                             est_minutes_per_unit):
                self._emit(job, obs.pop("type"), obs)
            completed = sum(1 for e in job.evidence if e.type == "UNIT_COMPLETE")
            if completed != job.qty:
                job.state = JobState.FAILED
                raise RuntimeError(
                    f"batch reported {completed}/{job.qty} good units — job "
                    f"fails whole in v0 (partial-batch settlement is a v0.2 item); "
                    f"nothing settles, escrow refunds")
        else:
            for i in range(job.qty):
                serial = f"{job.job_id}-u{i + 1:03d}"
                for obs in self.driver.run_unit(serial, est_minutes_per_unit):
                    self._emit(job, obs.pop("type"), obs)
        job.state = JobState.COMPLETE
        self.info.completed_jobs += 1
        # gentle reputation accrual, capped
        self.info.reputation = min(1.0, self.info.reputation + 0.02)

    def ship(self, job: Job, carrier: str, tracking: str):
        self._emit(job, "SHIPMENT", {"carrier": carrier, "tracking": tracking})
        job.state = JobState.SHIPPED

    def confirm_delivery(self, job: Job, confirmer: str):
        """In production this is a carrier webhook or buyer confirmation
        countersigned by the node — the settlement trigger."""
        self._emit(job, "DELIVERY_CONFIRMED", {"confirmed_by": confirmer})
        job.state = JobState.DELIVERED
