"""L2 — Node agent.

Runs at a fabricator's site: accepts jobs, drives machines, and emits the
hash-chained, signed PoF evidence log per specs/NODE-AGENT.md.

Signing: HMAC-SHA256 with a node secret as a stand-in for ed25519 — same
interface (`sign(payload) -> sig`), swapped in production. The chain
structure (each event commits to prev_hash) is the load-bearing part.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from ..models import (EvidenceEvent, Job, JobState, NodeInfo,
                      now_iso, sha256_hex, canonical_json)
from .drivers import MockDriver


class NodeAgent:
    def __init__(self, info: NodeInfo, driver: MockDriver | None = None):
        self.info = info
        self.driver = driver or MockDriver(info.machines[0].machine_id)
        self._secret = os.urandom(32)          # ed25519 keypair in production

    # -- evidence chain -------------------------------------------------------

    def _sign(self, payload: bytes) -> str:
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def _emit(self, job: Job, type_: str, data: dict):
        ev = EvidenceEvent(seq=len(job.evidence) + 1, ts=now_iso(),
                           type=type_, data=data, prev_hash=job.chain_head())
        body = canonical_json(ev.body())
        ev.sig = self._sign(body)
        ev.hash = sha256_hex(body + ev.sig.encode())
        job.evidence.append(ev)

    @staticmethod
    def verify_chain(job: Job) -> bool:
        """Anyone can verify ordering/integrity from hashes alone
        (signature verification additionally needs the node's public key)."""
        prev = "0" * 64
        for ev in job.evidence:
            if ev.prev_hash != prev:
                return False
            body = canonical_json(ev.body())
            if ev.hash != sha256_hex(body + ev.sig.encode()):
                return False
            prev = ev.hash
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
                   {"terms_sha256": sha256_hex(canonical_json(terms))})
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
