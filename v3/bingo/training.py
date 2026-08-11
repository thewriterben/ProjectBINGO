"""Training-material royalties — automation pays the people it learned from.

The mission's core claim, turned on AI itself. When the network's design agents
are trained on registered knowledge — print profiles, design libraries, annotated
failure datasets — the contributors are paid, *per asset*, metered by how much
they contributed and how much the model is actually used. Not the pooled,
single-digit-dollar "AI bonus" Adobe and Shutterstock hand out; an individual,
per-asset, verifiable royalty stream. Nobody has built this for functional design
knowledge (VISION §1, §3-L1).

Same kernel as every other BINGO vertical, pointed at a new asset class:

  * **Content-addressed, Ed25519-signed corpus** — the attribution record of
    which assets trained a model version, and by how much. Tamper, forge, or
    reorder any part and verification fails, offline, from the document alone.
  * **Atomic split to the cent** — a royalty pool splits across contributions by
    contribution share, then each asset's cut routes through ITS OWN split
    (co-authors, derivative parents), residue → the largest contribution's first
    payee, conserving exactly.
  * **Single-use metering** — each usage event accrues to the pool exactly once;
    a replayed event id is rejected, so a model's usage can't be double-counted.
  * **Composition** — a fine-tuned model can declare a base corpus and a share;
    its usage then also pays the base model's teachers, the training analogue of
    derivative royalties.

The recurrence the whole vision rests on (VISION §2 principle 6): a model trained
once earns its contributors every time it is *used*, forever, in proportion to
what each of them gave.

    python -m bingo.demo.training   # (if a demo module is added)
"""

from __future__ import annotations

from dataclasses import dataclass

from . import crypto, keys
from .models import SplitPayee, canonical_json, sha256_hex


class TrainingError(Exception):
    """A corpus failed verification, or usage was double-counted."""


# ── identity ────────────────────────────────────────────────────────────────

@dataclass
class Trainer:
    """The network's training-attestation identity (Ed25519). It signs a corpus
    to make the attribution claim — "I trained model M on these assets, in these
    proportions" — non-repudiable. The seed is the private key; in production it
    lives in the trainer's own wallet and never leaves it. A false claim is an
    arbitration matter (VISION §3-L2), and the signature is what makes it one.
    """

    trainer_id: str
    account: str
    _seed: bytes = b""
    _pub: bytes = b""
    _signer: object = None         # bingo.keys.Signer, when custody is external

    @classmethod
    def create(cls, trainer_id: str, account: str, seed: bytes | None = None,
               signer=None) -> "Trainer":
        """Mint a trainer. No key given => a real random key.

        Never derive the key from `trainer_id`: it is published in the corpus, so
        a derived key is one any reader can recompute and sign with. Use
        `for_testing()` for reproducible fixtures, or pass `signer=` to keep the
        private key in a keystore/HSM instead of this object."""
        if signer is not None:
            return cls(trainer_id, account, b"", signer.public_key(), signer)
        seed = seed if seed is not None else keys.new_seed()
        sk, pk = crypto.keypair(seed)
        return cls(trainer_id, account, sk, pk)

    @classmethod
    def for_testing(cls, trainer_id: str, account: str) -> "Trainer":
        """Reproducible, deliberately FORGEABLE trainer - fixtures only."""
        return cls.create(trainer_id, account,
                          seed=keys.insecure_test_signer(trainer_id).export_seed())

    @property
    def pubkey_hex(self) -> str:
        return self._pub.hex()

    def sign(self, message: bytes) -> str:
        if self._signer is not None:
            return self._signer.sign(message).hex()
        return crypto.sign(message, self._seed, self._pub).hex()


# ── the attribution record ──────────────────────────────────────────────────

@dataclass
class Contribution:
    """One training asset's part in a corpus: which asset, how much it contributed
    (examples / tokens / bytes — any consistent weight), and the payees its cut
    routes to. The payees are FROZEN into the corpus (the asset's effective_split
    at training time), so the royalty settles offline, from the corpus alone,
    without re-consulting the registry — the same discipline jobs use."""

    asset_id: str
    units: int
    payees: list  # list[SplitPayee]

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "units": self.units,
            "payees": [{"account": p.account, "bps": p.bps} for p in self.payees],
        }


def contribution_from_asset(asset, units: int) -> Contribution:
    """Build a contribution from a registered [`Asset`], freezing its
    effective_split (the composed payees incl. derivative parents) as the payees.
    """
    split = asset.effective_split or asset.split
    return Contribution(asset.asset_id, units, list(split.payees))


def _corpus_body(model_version, contributions, base_corpus_id, base_share_bps, trainer_acct, trainer_pub, ts):
    return {
        "model_version": model_version,
        "contributions": contributions,  # already list[dict], in signed order
        "base_corpus_id": base_corpus_id,
        "base_share_bps": base_share_bps,
        "trainer": {"account": trainer_acct, "pubkey": trainer_pub},
        "ts": ts,
    }


def build_corpus(
    trainer: Trainer,
    model_version: str,
    contributions: list[Contribution],
    ts: str,
    base_corpus_id: str = "",
    base_share_bps: int = 0,
) -> dict:
    """Assemble and sign a training corpus. Contributions are stored sorted by
    asset_id so the record is canonical; the corpus_id is the SHA-256 of the body
    and the signature is over that same body — reorder or edit anything and both
    break on verify."""
    if not contributions:
        raise TrainingError("a corpus needs at least one contribution")
    if not (0 <= base_share_bps < 10_000):
        raise TrainingError("base_share_bps must be in [0, 10000)")
    ordered = sorted((c.to_dict() for c in contributions), key=lambda c: c["asset_id"])
    body = _corpus_body(model_version, ordered, base_corpus_id, base_share_bps,
                        trainer.account, trainer.pubkey_hex, ts)
    payload = canonical_json(body)
    return {**body, "corpus_id": sha256_hex(payload), "sig": trainer.sign(payload)}


def verify_corpus(corpus: dict) -> tuple[bool, list[str]]:
    """Verify a corpus from the document alone: recompute the id, check the
    trainer's signature over the body, and validate every contribution
    (positive units; payees that sum to exactly 10000 bps). Returns (ok, notes)."""
    notes: list[str] = []
    try:
        body = _corpus_body(
            corpus["model_version"], corpus["contributions"], corpus["base_corpus_id"],
            corpus["base_share_bps"], corpus["trainer"]["account"],
            corpus["trainer"]["pubkey"], corpus["ts"],
        )
        payload = canonical_json(body)
    except (KeyError, TypeError) as e:
        return False, [f"malformed corpus: {e}"]

    if sha256_hex(payload) != corpus.get("corpus_id"):
        notes.append("corpus_id does not match its body (tampered or reordered)")
        return False, notes
    try:
        ok = crypto.verify(payload, bytes.fromhex(corpus["sig"]),
                           bytes.fromhex(corpus["trainer"]["pubkey"]))
    except (ValueError, KeyError):
        ok = False
    if not ok:
        notes.append("trainer signature does not verify")
        return False, notes

    if not corpus["contributions"]:
        notes.append("empty corpus")
        return False, notes
    for c in corpus["contributions"]:
        if c.get("units", 0) <= 0:
            notes.append(f"non-positive units for {c.get('asset_id')}")
            return False, notes
        bps = sum(p["bps"] for p in c["payees"])
        if bps != 10_000:
            notes.append(f"payees for {c['asset_id']} sum to {bps} bps, not 10000")
            return False, notes
    return True, notes


# ── distribution ────────────────────────────────────────────────────────────

@dataclass
class TrainingLeg:
    """One payout: an amount to an account, attributed to the asset that earned
    it. Per-asset attribution is the whole point — this is not a pooled bonus."""

    account: str
    amount_cents: int
    asset_id: str
    memo: str


def _distribute_own(corpus: dict, pool_cents: int) -> list[TrainingLeg]:
    """Split pool_cents across THIS corpus's contributions by contribution share,
    then each asset's cut through its own payees. Two residues, both deterministic:
    the by-units floor residue goes to the largest contribution; each asset's
    per-payee floor residue goes to that asset's first payee."""
    contribs = corpus["contributions"]
    total_units = sum(c["units"] for c in contribs)
    if total_units <= 0 or pool_cents <= 0:
        return []

    # First pass: cents per asset by units share (integer floor).
    per_asset = []
    distributed = 0
    for c in contribs:
        asset_cents = (pool_cents * c["units"]) // total_units
        per_asset.append([c, asset_cents])
        distributed += asset_cents
    # By-units residue → the largest contribution (ties: earliest, since sorted).
    residue = pool_cents - distributed
    if residue > 0:
        top = max(range(len(per_asset)), key=lambda i: per_asset[i][0]["units"])
        per_asset[top][1] += residue

    # Second pass: each asset's cents through its split.
    legs: list[TrainingLeg] = []
    for c, asset_cents in per_asset:
        if asset_cents <= 0:
            continue
        tag = c["asset_id"][:8]
        alegs: list[TrainingLeg] = []
        adist = 0
        for p in c["payees"]:
            amt = (asset_cents * p["bps"]) // 10_000
            if amt > 0:
                alegs.append(TrainingLeg(p["account"], amt, c["asset_id"],
                                         f"training royalty {p['bps']}bps [{tag}]"))
                adist += amt
        ares = asset_cents - adist
        if alegs and ares > 0:
            alegs[0].amount_cents += ares
        legs.extend(alegs)
    return legs


def distribute(corpus: dict, pool_cents: int, base_corpus: dict | None = None) -> list[TrainingLeg]:
    """Distribute a royalty pool to a corpus's contributors, to the cent.

    If the corpus declares a base corpus and share, that share flows first to the
    base model's contributors (recursively — a base may have its own base), and
    the remainder (including the base's rounding residue) is distributed to this
    corpus's own contributions. So a fine-tune's usage still pays the teachers of
    the model it was built on. `base_corpus` must be supplied when
    `base_share_bps > 0`, or the base share cannot be honored and the call fails
    closed rather than silently keeping the base's money."""
    if pool_cents <= 0:
        return []
    base_bps = corpus.get("base_share_bps", 0)
    if base_bps > 0:
        if base_corpus is None:
            raise TrainingError(
                f"corpus {corpus['corpus_id'][:8]} owes {base_bps}bps to base "
                f"{corpus['base_corpus_id'][:8]} but no base corpus was supplied"
            )
        if base_corpus.get("corpus_id") != corpus.get("base_corpus_id"):
            raise TrainingError("supplied base corpus is not the one this corpus derives from")
        base_cents = (pool_cents * base_bps) // 10_000
        legs = distribute(base_corpus, base_cents)  # recurse
        # Whatever actually reached the base (it may floor to 0 on a tiny pool)
        # is spent there; everything else — including the base's rounding
        # residue — is distributed to this corpus, so nothing is lost.
        base_paid = sum(l.amount_cents for l in legs)
        own_cents = pool_cents - base_paid
        legs.extend(_distribute_own(corpus, own_cents))
    else:
        legs = _distribute_own(corpus, pool_cents)

    total = sum(l.amount_cents for l in legs)
    if total != pool_cents:
        raise TrainingError(f"distribution did not conserve: {total} != {pool_cents}")
    return legs


# ── metering + recurrence ───────────────────────────────────────────────────

class RoyaltyMeter:
    """Accrues a training-royalty pool per model version from usage events, and
    drains it to a verified corpus's contributors.

    A *usage event* is any fee-earning network action the trained model performed
    (a quote it priced, a spec it drafted, a match it made). A configured share of
    that fee accrues to the model's training-royalty pool. Each event settles into
    the pool exactly ONCE — a replayed event id is rejected — so usage can't be
    double-charged. Draining (settle) empties the pool; later usage accrues afresh
    and the next settle pays only the increment. That is the recurrence: pay once
    per unit of real use, forever.
    """

    def __init__(self) -> None:
        self._pool: dict[str, int] = {}    # model_version -> undistributed cents
        self._earned: dict[str, int] = {}  # model_version -> lifetime accrued
        self._paid: dict[str, int] = {}    # model_version -> lifetime distributed
        self._seen: set[str] = set()       # metered event ids (single-use)

    def record_usage(self, model_version: str, event_id: str, fee_cents: int,
                     training_share_bps: int) -> int:
        """Meter one usage event: accrue `fee_cents * share` to the model's pool.
        Rejects a replayed event id (double count). Returns the cents accrued."""
        if event_id in self._seen:
            raise TrainingError(f"usage event {event_id!r} already metered (double count)")
        if not (0 <= training_share_bps <= 10_000):
            raise TrainingError("training_share_bps out of range")
        if fee_cents < 0:
            raise TrainingError("fee_cents must be non-negative (a negative fee "
                                "would drain the royalty pool)")
        self._seen.add(event_id)
        accrued = (fee_cents * training_share_bps) // 10_000
        self._pool[model_version] = self._pool.get(model_version, 0) + accrued
        self._earned[model_version] = self._earned.get(model_version, 0) + accrued
        return accrued

    def pool_cents(self, model_version: str) -> int:
        return self._pool.get(model_version, 0)

    def lifetime_earned(self, model_version: str) -> int:
        return self._earned.get(model_version, 0)

    def lifetime_paid(self, model_version: str) -> int:
        return self._paid.get(model_version, 0)

    def settle(self, corpus: dict, base_corpus: dict | None = None) -> list[TrainingLeg]:
        """Drain the model's accrued pool to its corpus's contributors. Verifies
        the corpus first (fails closed on a bad one), pays through the split, and
        zeroes the pool. Returns the payout legs (empty if nothing accrued)."""
        ok, notes = verify_corpus(corpus)
        if not ok:
            raise TrainingError(f"refusing to settle against an unverified corpus: {notes}")
        mv = corpus["model_version"]
        pool = self._pool.get(mv, 0)
        if pool <= 0:
            return []
        legs = distribute(corpus, pool, base_corpus)
        self._pool[mv] = 0
        self._paid[mv] = self._paid.get(mv, 0) + pool
        return legs


# ── statements ──────────────────────────────────────────────────────────────

def earnings_by_account(legs: list[TrainingLeg]) -> dict[str, int]:
    """Total training royalties per payee account."""
    out: dict[str, int] = {}
    for leg in legs:
        out[leg.account] = out.get(leg.account, 0) + leg.amount_cents
    return out


def earnings_by_asset(legs: list[TrainingLeg]) -> dict[str, int]:
    """Total training royalties earned per training asset — the per-asset
    accounting the pooled 'AI bonus' models cannot produce."""
    out: dict[str, int] = {}
    for leg in legs:
        out[leg.asset_id] = out.get(leg.asset_id, 0) + leg.amount_cents
    return out
