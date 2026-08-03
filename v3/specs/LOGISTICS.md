# Spec: Custody, Shipment Exceptions & Agent-Mediated Resolution

**Version 0.1 — draft.** Motivated by a real failure (Aug 2026): a resin
delivery failed for reasons no system could later reconstruct; exception
handling required catching a single synchronous phone call; the orphaned
inventory's loss will land on an innocent party by default. None of those
three failure modes are acceptable in this network. Physical goods will
always go missing sometimes — what is designed here is that the *state*
never does.

## 1. Custody chain

Every physical movement (finished goods AND materials) is a chain of signed
custody hops appended to the shipment's evidence log:

```
CUSTODY_ACCEPT  { holder, from_holder, condition_note?, sig }
CUSTODY_RELEASE { holder, to_holder, sig }
SHIPMENT_EXCEPTION { holder, code, detail, next_action, deadline, sig }
DELIVERY_CONFIRMED { confirmer, sig }        # settlement trigger (unchanged)
```

Invariant: **at every instant, exactly one party is the signed custodian.**
"Where is it?" is a lookup, never an investigation. Third-party carriers that
won't sign (USPS/UPS/Amazon) are wrapped: their tracking events are ingested
by the logistics agent as attested-by-proxy custody records, explicitly
marked lower-trust — the boundary where the network's guarantees degrade is
*visible*, not pretended away.

## 2. Exceptions are states, not phone calls

A shipment exception (delivery failed, refused, damaged, lost-in-scan) is an
event with a mandatory `next_action` and `deadline` — never a dead end:

| code | default next_action |
|---|---|
| DELIVERY_FAILED | re-attempt (n≤2) → hold-at-point → route-to-alternate |
| DAMAGED | photo evidence → claim against custodian at time of damage |
| LOST | custodian-of-record liable after deadline lapse |
| REFUSED | return-to-sender, costs to refusing party absent defect claim |

**All exception handling is asynchronous-first.** The parties' agents
negotiate resolution over the order's message channel with full shipment
state attached; a human is escalated to with a *decision*, presented with
options and consequences — never with "call us back on a line that doesn't
accept calls." A missed message delays a deadline; it never orphans a
package.

## 3. Loss attribution is deterministic

When goods are lost or damaged, the custody chain names the liable party:
the custodian of record at the time of the exception (or, for proxy
carriers, the party who chose that carrier — a risk they priced when
selecting it). Settlement consequences execute from escrow and the liable
party's staked reputation, not from a chargeback shouting match. A supplier
who shipped in good faith and can show CUSTODY_RELEASE to the carrier is
structurally incapable of silently eating the loss. The network may run a
small mutual pool (funded from the network fee) for proxy-carrier losses
below a threshold — socialize the noise, attribute the signal.

## 4. Materials are shipments too

Supplier→node resupply uses the same chain. Combined with declared
`materials_on_hand`, a lost resupply triggers: exception logged → liability
attributed → replacement order auto-placed (buyer's standing authorization,
capped) → affected jobs re-routed to wet nodes. Production reads inventory
state; it never waits on a mystery.

## 5. What this does NOT claim

The network cannot make a third-party van arrive. Until suppliers and
couriers are native nodes, proxy custody is a real trust seam and is labeled
as such. The claim is narrower and absolute: within the network, every
failure has a custodian, every exception has a next action with a deadline,
every loss has an addressee, and no human is ever required to catch a phone
call to keep state from evaporating.
