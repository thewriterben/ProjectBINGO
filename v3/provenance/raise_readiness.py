"""Raise-readiness for a machine-revenue-share offering — the honest bridge from
the signed on-chain offering to a *compliant* capital raise.

A machine revenue-share IS a security (see SECURITIES.md). This module does NOT
offer, solicit, or sell anything, and it deliberately cannot: it only
  1. renders the already-signed offering terms into a human-readable **term
     sheet** (a block-explorer view of the OPEN event - not an offer), and
  2. answers "are we ready to raise?" as a **fail-closed function** of real,
     checkable conditions - securities counsel sign-off, a registered funding
     portal / transfer agent, KYC/AML, escrow, blue-sky, reviewed marketing, and
     a genuine verified-revenue basis to underwrite. Miss any one and it returns
     NOT READY with the specific blockers.

The point is the same discipline as the rest of BINGO: you can't be "ready to
raise" with zero verified revenue or without counsel any more than you can
distribute phantom machine revenue. The gate refuses; it never blesses.

NOT legal advice. `disclosure_inputs()` produces DRAFT INPUTS for securities
counsel and a funding portal to review and complete - never a filing or an offer.
"""

from __future__ import annotations

from dataclasses import dataclass

from .machine_rwa import verify_machine_share

# The real-world conditions a compliant raise requires. Each is something only a
# human/counsel/portal can truthfully assert - the code just checks they're all
# asserted AND that a real revenue basis exists.
REQUIRED_GATES = (
    "counsel_opinion",     # securities counsel reviewed the structure + exemption
    "exemption",           # a named exemption is chosen (reg_cf / reg_d_506c / reg_a)
    "funding_portal",      # FINRA-registered funding portal or broker-dealer engaged
    "transfer_agent",      # registered transfer agent engaged
    "kyc_aml",             # KYC/AML on every investor
    "escrow",              # escrow/agent holds funds until close
    "blue_sky",            # state blue-sky obligations handled/covered
    "marketing_reviewed",  # all marketing scrubbed + counsel-reviewed
)

VALID_EXEMPTIONS = {"reg_cf", "reg_d_506c", "reg_d_506b", "reg_a"}


@dataclass
class RaiseReadiness:
    """The real-world compliance context for a raise. Every field defaults to the
    unsafe/absent value, so an empty context is NOT ready - fail-closed."""
    counsel_opinion: bool = False
    exemption: str | None = None
    funding_portal: str = ""
    transfer_agent: str = ""
    kyc_aml: bool = False
    escrow: bool = False
    blue_sky: bool = False
    marketing_reviewed: bool = False
    required_revenue_months: int = 3     # min periods of real verified revenue

    def _gate_ok(self, name: str) -> bool:
        if name == "exemption":
            return self.exemption in VALID_EXEMPTIONS
        return bool(getattr(self, name))


def _terms(doc: dict) -> dict:
    total = doc["total_shares"]
    price = doc["price_cents"]
    cap = doc["repayment_cap_cents"]
    max_raise = total * price
    return {
        "machine_id": doc["machine_id"],
        "operator": doc["operator"],
        "total_shares": total,
        "price_cents": price,
        "investor_share_bps": doc["investor_share_bps"],
        "repayment_cap_cents": cap,
        "max_raise_cents": max_raise,
        # implied max return multiple to investors at full subscription
        "max_return_multiple": (cap / max_raise) if max_raise else 0.0,
        "offering_hash": (doc.get("events") or [{}])[0].get("hash", ""),
    }


def readiness_report(doc: dict, verified_revenue_periods: list[int],
                     ctx: RaiseReadiness) -> dict:
    """Fail-closed: is this offering ready to be raised on, compliantly?

    Ready requires ALL of: the on-chain offering itself verifies; every REQUIRED
    gate is truthfully asserted in `ctx`; and there is a REAL verified-revenue
    basis (>= required_revenue_months of periods, each strictly positive - you
    can't underwrite a machine that hasn't provably earned). Returns a structured
    report; `is_ready` is True only if `blockers` is empty.
    """
    blockers: list[str] = []
    satisfied: list[str] = []

    # 0) the offering must itself be a valid, signed, replayable instrument
    ok, notes = verify_machine_share(doc)
    if not ok:
        blockers.append(f"offering does not verify: {notes[-1] if notes else '?'}")
    else:
        satisfied.append("on-chain offering verifies (signed cap table replays)")

    # 1) the human/legal gates - each is something only counsel/portal can assert
    for gate in REQUIRED_GATES:
        if ctx._gate_ok(gate):
            val = getattr(ctx, gate)
            satisfied.append(f"{gate}" + (f" = {val}" if isinstance(val, str) and val else ""))
        else:
            blockers.append(f"missing: {gate}")

    if ctx.exemption is not None and ctx.exemption not in VALID_EXEMPTIONS:
        blockers.append(f"unknown exemption {ctx.exemption!r} (expected one of "
                        f"{sorted(VALID_EXEMPTIONS)})")

    # 2) a REAL revenue basis to underwrite - the honest core. No phantom raises.
    periods = list(verified_revenue_periods or [])
    positive = [p for p in periods if p > 0]
    basis = sum(positive)
    # floor the caller-controlled threshold to >=1 so "no revenue" can never
    # satisfy the gate (and never hits a 0/0 in the note below)
    required = max(1, ctx.required_revenue_months)
    if len(positive) < required:
        blockers.append(
            f"insufficient verified-revenue history: {len(positive)} positive "
            f"period(s), need >= {required} "
            f"(underwrite from real, PoF-verified earnings - not projections)")
    else:
        satisfied.append(f"verified-revenue basis: {len(positive)} periods, "
                         f"${basis/100:,.2f} total, ${basis/len(positive)/100:,.2f}/period")

    return {
        "is_ready": not blockers,
        "blockers": blockers,
        "satisfied": satisfied,
        "exemption": ctx.exemption,
        "revenue_basis_cents": basis,
        "revenue_periods": len(positive),
        "terms": _terms(doc) if ok else None,
    }


def term_sheet(doc: dict, verified_revenue_periods: list[int] | None = None) -> str:
    """A human-readable term sheet rendered from the SIGNED offering - a
    block-explorer view of the OPEN event, pinned to its hash. This is NOT an
    offer to sell securities; it renders terms that already exist on the ledger.

    Fails closed: a forged or tampered offering (one that doesn't verify from the
    document alone) is refused, so this can never render attacker-controlled
    top-level numbers under a 'signed offering' banner."""
    ok, why = verify_machine_share(doc)
    if not ok:
        raise ValueError(f"refusing to render a term sheet for an offering that "
                         f"does not verify: {why[-1] if why else '?'}")
    t = _terms(doc)
    periods = [p for p in (verified_revenue_periods or []) if p > 0]
    lines = [
        "DRAFT TERM SHEET - NOT AN OFFER TO SELL SECURITIES",
        "(informational rendering of a signed offering; see SECURITIES.md)",
        "",
        f"Instrument     machine revenue-share (a security in the US)",
        f"Machine        {t['machine_id']}",
        f"Operator       {t['operator']}",
        f"Offering ref   {t['offering_hash'][:16]}... (signed OPEN event)",
        "",
        f"Shares         {t['total_shares']:,} @ ${t['price_cents']/100:,.2f}",
        f"Max raise      ${t['max_raise_cents']/100:,.2f} (if fully subscribed)",
        f"Investor share {t['investor_share_bps']/100:.2f}% of each machine-revenue "
        f"event, until repaid",
        f"Repayment cap  ${t['repayment_cap_cents']/100:,.2f} "
        f"(~ {t['max_return_multiple']:.2f}x the max raise), then 100% reverts to "
        f"the operator",
    ]
    if periods:
        basis = sum(periods)
        lines += [
            "",
            f"Revenue basis  {len(periods)} PoF-verified period(s), "
            f"${basis/100:,.2f} total, ${basis/len(periods)/100:,.2f}/period "
            f"(historical; NOT a projection or guarantee)",
        ]
    else:
        lines += [
            "",
            "Revenue basis  NONE YET - no PoF-verified earnings history. This "
            "offering cannot be responsibly underwritten until the machine has a "
            "real, verified revenue record.",
        ]
    lines += [
        "",
        "This is not an offer, solicitation, or recommendation. Any actual raise "
        "must go through a registered funding portal or broker-dealer under a "
        "valid exemption, with counsel-reviewed disclosures, KYC/AML, and transfer "
        "restrictions. Returns are not guaranteed; the instrument is illiquid.",
    ]
    return "\n".join(lines)


# -- draft inputs for counsel / funding portal (NOT a filing, NOT an offer) ----

_STANDARD_RISK_FACTORS = [
    "Revenue is not guaranteed. Payouts depend entirely on the machine winning "
    "and completing paid jobs on the network; it may earn little or nothing.",
    "Operator-dependent. Returns rely on the essential efforts of the operator, "
    "who runs the machine and the jobs; operator default or under-performance "
    "directly impairs the investment.",
    "Single-machine / single-network concentration. This is one machine on an "
    "early-stage network with limited demand history - not a diversified pool.",
    "Illiquidity. There is no established secondary market; a majority of "
    "tokenized real-world-asset value trades not at all. Backers should expect "
    "to hold to the repayment cap or lose their capital.",
    "Capped upside. Investor return is capped at the repayment cap; after that, "
    "100% of revenue reverts to the operator.",
    "Early-stage / technology risk. The network, hardware, and settlement rails "
    "are prototype-stage; software or hardware failure can interrupt revenue.",
    "Regulatory risk. Securities and money-transmission rules are evolving "
    "(Project Crypto, GENIUS Act implementation); treatment may change.",
]


def disclosure_inputs(doc: dict, verified_revenue_periods: list[int],
                      ctx: RaiseReadiness) -> dict:
    """Assemble DRAFT INPUTS for a securities counsel / funding portal to review
    and complete (e.g. toward a Reg CF Form C). This is NOT a filing, NOT an
    offer, and NOT legal advice - it is a structured starting point built from the
    signed offering and the real verified-revenue basis. Fails closed if there is
    no verified-revenue basis (you cannot draft an honest use-of-proceeds and
    financial picture from a machine that has not provably earned). Also fails
    closed if the offering itself does not verify."""
    ok, why = verify_machine_share(doc)
    if not ok:
        raise ValueError(f"offering does not verify: {why[-1] if why else '?'}")
    periods = [p for p in (verified_revenue_periods or []) if p > 0]
    if not periods:
        raise ValueError("no verified-revenue basis: cannot assemble honest "
                         "disclosure inputs for a machine with no PoF-verified "
                         "earnings history")
    t = _terms(doc)
    basis = sum(periods)
    return {
        "DISCLAIMER": ("DRAFT INPUTS FOR COUNSEL / FUNDING PORTAL - not a filing, "
                       "not an offer, not legal advice. Counsel must review and "
                       "complete before any use."),
        "issuer": {"operator_account": t["operator"], "machine_id": t["machine_id"]},
        "security": ("Machine revenue-share: a capped claim on a share of one "
                     "machine's future PoF-verified network revenue."),
        "exemption_sought": ctx.exemption,
        "offering_terms": t,
        "use_of_proceeds": (f"Finance/expand machine '{t['machine_id']}' "
                            f"(up to ${t['max_raise_cents']/100:,.2f})."),
        "financial_basis": {
            "verified_periods": len(periods),
            "total_verified_revenue_cents": basis,
            "mean_period_revenue_cents": basis // len(periods),
            "source": "sum of acct:node legs from settled, PoF-verified jobs "
                      "(verified_machine_revenue) - historical, not a projection",
        },
        "risk_factors": list(_STANDARD_RISK_FACTORS),
        "still_required_from_counsel": [
            "confirm exemption + eligibility", "Form C / offering statement",
            "issuer financial statements to the required level",
            "per-investor and aggregate limits", "funding portal + transfer agent",
            "escrow arrangement", "state blue-sky", "final risk factors + legends",
        ],
    }
