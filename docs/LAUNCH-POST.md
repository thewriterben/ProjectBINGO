# My printer finished a part tonight, and the designer got paid in the same atomic transaction

*Draft for: Hacker News (Show HN), r/3Dprinting, r/functionalprint, Meshtastic Discord/forum, Printables community. Adjust the opener per venue — Ben's voice, edit freely.*

---

Tonight my Creality K2 Plus finished a Meshtastic battery cage. The moment I confirmed the part was in hand, one transaction executed: the shop got $1.48 for the fabrication, the logistics pool got its share, the network kept a 3% fee, and the **designer got a $0.40 royalty — in the same atomic settlement that paid the printer.** Not an invoice. Not a platform's monthly payout at a rate they can change whenever they feel like it. A royalty enforced at the point of fabrication, because payment physically cannot route around it.

Yes, tonight the designer, the shop, and the buyer were all me. That's the point of this post: the loop works, and now it needs people who aren't me.

## Why I built this

If you make functional designs, 2025–2026 has been a series of middle fingers. Etsy's new policy killed selling prints of licensed designs — commercial licenses explicitly don't count. MakerWorld rewrote its points economy overnight and your income moved with it. Shapeways went bankrupt holding customers' money. Prusa himself declared open-hardware 3D printing "dead" after watching his open designs get commercialized without so much as a credit. The lesson every creator learned: **your income exists at the pleasure of a platform.**

Meanwhile per-unit royalties — getting paid every time your design is actually manufactured — exist only for patent portfolios and chip IP. Arm gets paid per unit. The person who designed the enclosure on your desk gets exposure.

So I built the thing I couldn't find: an open protocol where designs are registered with machine-readable licenses and royalty splits, orders are matched to a network of independent printers and shops, every job produces a hash-chained, signed proof-of-fabrication log (gcode hash, live telemetry, camera frames), and settlement releases escrow through the design's royalty split in one transaction. Remixes compose automatically — remix my bracket and I earn a share of your royalties forever, frozen at registration, no negotiation, no honor system.

No token. Nothing to buy. Settlement is dollars (regulated stablecoins optional, never required). The specs and every line of code are open — the whole thing is stdlib Python you can read in an afternoon: **github.com/thewriterben/ProjectBINGO** (see `v3/`).

## What's real and what isn't (honesty section)

Real: the content-addressed registry with composable royalty splits; the escrow ledger with asserted to-the-cent invariants; real STL analysis; the hash-chained evidence format; a working driver that ran a real print on a real K2 Plus tonight, telemetry signed into the chain, settled on receipt.

Not real yet: the money tonight was a local ledger, not a bank; signing is a placeholder pending ed25519; camera evidence didn't capture on this printer yet; and the network is one node — mine. This is a working prototype and an open spec, not a product. That's exactly why I'm posting.

## What I'm looking for: 10 designers + 10 printers, one niche

First pilot: **Meshtastic enclosures.** If you design cases, mounts, or battery cages for Meshtastic boards — or you have a reliable printer and want to be one of the first fabrication nodes — I want to run the first stranger-to-stranger transactions in this community. Designers set a per-unit royalty on their existing designs. Node operators run the open-source agent and get paid per verified job. Buyers get parts printed near them with a signed provenance chain. Everything settles transparently; every participant sees every line item.

Why Meshtastic first: this community already runs decentralized infrastructure for the hell of it, already designs in the open, and already knows the difference between a part that works and a part that's pretty. Quality expectations are declared up front (functional / standard / premium grades, frozen into the job terms), so nobody gets dinged over cosmetics they never ordered.

If that's you: [contact/Discord/issue link]. First ten of each get direct support from me getting set up.

The pitch in one sentence: every network that matters had a first transaction between strangers, and I'd rather it happen in a community that builds mesh networks for fun than anywhere else on earth.

---

*FAQ ammo for the comments:*

**"Blockchain?"** The prototype is a plain ledger. The settlement layer is designed to swap to regulated stablecoin escrow + split contracts, and supports Digital Gold (an asset I co-created — disclosed loudly, optional, never required). If the word makes you close the tab: dollars in, dollars out, and the specs work without any of it.

**"What stops someone printing a leaked file off-network?"** Nothing — same as today. On-network is what earns you buyers, routing, provenance, and settlement. Royalties are enforced for everything that flows through the network; the network's job is to be worth flowing through.

**"Why would a print farm pay designers when they don't have to?"** Because the orders come with the payment structure attached. Nodes don't pay royalties — buyers fund one escrow and the split executes at settlement. The farm gets paid *more* reliably, not less.

**"This failed before (SyncFab, etc.)."** Every prior attempt led with a token and treated the blockchain as the product. This leads with a working print and treats settlement as plumbing. The failure autopsies are in the repo (`docs/LANDSCAPE-2026.md`) — I studied the graveyard before building.
