# Verified Provenance: Premium Wagyu as DGD's Flagship Real-World Asset

*One-pager for the John conversation — a way to make the DGD / Project BINGO thesis land on something you can hold in your hand and sell tomorrow.*

## The insight

A5 Tajima ribeye sells for $65 a pound because of its **provenance**, not its protein. What the customer in Sun Valley is paying for is the 96% Tajima genetics, the specific grains and alfalfa a named third-generation rancher grew, the A5 grade, and the intact cold chain. Strip the story away and it's just expensive meat. **The premium *is* the provenance.**

And the provenance market is broken. "Wagyu" and "Kobe" are among the most counterfeited claims in food — mislabeling is widely reported at every level from importer to menu. Today the entire premium rests on a paper label and blind trust: the grocer trusts John, the customer trusts the label. Not one link in the chain — genetics → feed → grade → cold chain — can actually be *proven* by the person paying for it.

That gap is exactly what DGD and BINGO were built to close. DGD's whole thesis (Crypto Fair Value, the Digital Gold Standard Benchmark) is *real value made verifiable and portable.* Gold is the canonical case. **But premium Wagyu is a better first showcase than gold** — because unlike a bar in a vault, its value is *almost entirely* provenance and story, it's already generating revenue, and it comes with a human being at the center that people root for.

## Why this asset, first

- **Value density + a story people already pay a premium for.** The willingness-to-pay for authenticity is proven every time a $65/lb cut leaves the case.
- **The real chain already exists and John controls it.** Genetics, the rancher's feed, the processor, the cold-chain run into Sun Valley — these are real, documented steps today, just not yet cryptographically attested.
- **A human hook that gold can't match.** A third-generation rancher who grows the exact grains and alfalfa the cattle are finished on. Value should route to *her*, on every cut — not as a thank-you in the marketing, as a line in the settlement.
- **Emotionally undeniable.** "Scan the cut, see who raised the feed, and know she got paid for it" sells the entire technology thesis in one gesture.

## What we'd actually ship

A **verifiable provenance passport** for each cut — built on the *exact same* proof primitives already running and tested in Project BINGO (Ed25519 signatures, a hash-chained event log, atomic value routing). Each link is signed by the party who made it:

**lineage** (genetics, 96% Tajima) → **husbandry** (the rancher signs the feed *she grew*) → **harvest + A5 grade** (processor signs the graded claim) → **cold-chain custody** (carrier signs temps held) → **sale** (proceeds split, automatically, across everyone who created the value).

The passport verifies from nothing but itself — no server, no middleman, offline — and it routes real money. In the working demo, on a single 0.90 lb A5 ribeye sold at $65/lb, the rancher who grew the feed is paid **$12.87 on that one cut**, atomically, at the moment of sale.

## How it grows DGD

This is a concrete first real-world asset to anchor CFV/DGSB on — a tangible, revenue-generating product that demonstrates *verified value* instead of describing it. It's a wedge for adoption: a premium producer and a high-end grocer both get something they want today (an authenticity guarantee that justifies and defends the price), and every passport is a live demonstration of the DGD thesis in the wild. The same rail extends to any premium producer whose margin depends on a provenance claim.

## The ask

Not "should DGD support BINGO" in the abstract. It's: **let's make your beef the flagship.** Concretely — put one real cut through a passport as a pilot: capture the genetics, the rancher's feed, the grade, the cold-chain run, and issue a certificate the grocer can show a customer. Prove verified provenance on a product we already own and already sell.

---

*A working passport (JSON + a printable certificate) and its standalone verifier already exist in the Project BINGO repo (`provenance/`, `python -m provenance.demo`), sharing the same crypto that settles a fabrication job on the network. The scenario in the demo uses placeholder names — the real genetics, the rancher's story, and her account plug straight in.*
