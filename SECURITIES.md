# Securities notice

**Interim wording — not legal advice. Obtain securities counsel before raising money on any of this.**

BINGO is mostly infrastructure that proves provenance and routes payment to the people who made value — manufacturing, provenance passports, transport custody, training royalties, promo coins. Those do not raise capital from investors and are not the subject of this notice.

Two verticals *can* move money from outside backers/holders, and only these two are addressed here:

- **`v3/provenance/machine_rwa.py`** — financing a machine by selling shares of its future revenue.
- **`v3/provenance/token.py`** — a transferable claim on a real-world asset.

## The rule that governs, regardless of what we call it

US securities law looks at **economic substance, not labels or file format**. The *Howey* test makes something a security (an "investment contract") when there is an investment of money, in a common enterprise, with a reasonable expectation of profit, derived from the efforts of others. The *Reves* test does the parallel work for note-like/revenue-share instruments. The SEC's 2025–2026 crypto overhaul (Project Crypto; the March 2026 joint SEC/CFTC guidance) is more permissive for *crypto*, but it explicitly preserves this rule — "tokenized securities are and will continue to be securities." **A disclaimer that something is "a technical primitive, not a securities offering" does not change the analysis, and can be read as evidence that we knew the question.**

The code in this repo is software — it records who holds what and what a verified machine paid back. It does **not** itself offer, solicit, or sell any instrument. But the moment that software is used to conduct an actual raise, and paired with any marketing, a securities transaction exists and must be done compliantly. Keep a bright line between the neutral ledger primitive and any capital-raising workflow.

## Machine revenue-share (`machine_rwa.py`) — this is a security

Selling fractional shares of a machine's future revenue for a capped return (e.g. 1.2x) satisfies all four *Howey* prongs and reads as a security under *Reves*. Treat it as one. A real raise must ship through a compliant offering, for example:

- **Reg CF** (Regulation Crowdfunding) via a registered funding portal or broker-dealer — best fit for a community-scale raise; per-investor and annual caps, Form C disclosure.
- **Reg D 506(c)** — verified-accredited investors only; general solicitation permitted.
- **Reg A+ (Tier 2)** — larger raises; requires SEC qualification and ongoing reporting.

...plus KYC/AML, state blue-sky compliance, transfer restrictions, and — because the instrument contemplates resale — transfer-agent and trading-venue rules for any secondary market. Confirm current thresholds with counsel (they are inflation-adjusted).

## RWA claim tokenization (`token.py`) — depends on what the token is and how it's sold

- **Consumptive claim** (one buyer redeems for a specific good they want — e.g. the A5 ribeye): likely **not** a security, but may still be subject to warehouse-receipt law (UCC Art. 7), money-transmitter / prepaid-access rules, and consumer-protection law.
- **Investment claim** (fractional, freely-tradable, resale-royalty-bearing, marketed for appreciation/return): likely **is** a securities offering under *Howey*.

The resale-royalty and secondary-sale features in `token.py` make the investment case easy to reach. Decide, per backing asset and per how it is sold, which case applies, and design for it — do not rely on one blanket "not a security" disclaimer.

## Demos and marketing are evidence

Illustrative demo output and pitch language ("paid back 1.2x," "strangers financed a printer") are exactly the profit representations *Howey* looks for. They are fine as illustrations of the software; they are **not** an offer, and they must not be used to solicit real investment outside a compliant offering with counsel-reviewed disclosures.

## See also

The fuller analysis, with the vertical-by-vertical *Howey*/*Reves* breakdown, the 2025-2026 regulatory changes, and a checklist of questions for counsel, is in the CMN project doc `SECURITIES-FRAMING-MEMO.md`.

---

*This notice is interim and non-binding. The 2026 SEC guidance it references is itself non-binding and evolving. Nothing here is legal advice; confirm everything with a qualified securities attorney before acting.*
