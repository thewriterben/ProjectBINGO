"""Auto-transport custody passport, three ways:

    python -m provenance.transport_demo

  1. honest move      → verifies, escrow releases to the bound carrier
  2. double brokered  → a different truck delivers → verify rejects → escrow BLOCKED
  3. damage on arrival→ verifies & releases, new damage flagged as a claim

Writes out/transport/<vin>.json + a bill-of-lading certificate for the honest
move. Names/VIN are illustrative; the crypto is real.
"""

from __future__ import annotations

import html
import json
import os

from .passport import Actor
from .transport import (TransportPassport, condition, make_acceptance,
                        verify_transport, escrow_decision)

OUT = os.path.join(os.path.dirname(__file__), "..", "out", "transport")
VIN = "WP0AB2A99NS227614"


def _actors():
    broker = Actor.create("apex-transport", "Apex Auto Transport (broker)", "broker",
                          "acct:broker:apex")
    carrier_a = Actor.create("sawtooth-hauling", "Sawtooth Hauling LLC", "carrier",
                             "acct:carrier:sawtooth")
    carrier_b = Actor.create("ghost-logistics", "Ghost Logistics (re-broker)", "carrier",
                             "acct:carrier:ghost")
    customer = Actor.create("r-snider", "Vehicle owner", "customer", "acct:customer:owner")
    return broker, carrier_a, carrier_b, customer


def _subject():
    return {"vin": VIN, "vehicle": "2022 Porsche 911 Carrera (992)",
            "origin": "Scottsdale, AZ", "destination": "Sun Valley, ID"}


def honest() -> TransportPassport:
    broker, a, _b, cust = _actors()
    pp = TransportPassport(_subject())
    pp.book(broker, a, cust, price_cents=185000, carrier_cents=160000,
            pickup_window="2026-08-05 08:00–12:00", delivery_window="2026-08-07 12:00–18:00",
            ts="2026-08-04T15:00:00Z")
    pp.pickup(a, condition(12340, damage=[], photos_sha256="a1"*16,
                           notes="clean, full inspection"), location="Scottsdale, AZ",
              ts="2026-08-05T09:20:00Z")
    pp.transit(a, "Las Vegas, NV", ts="2026-08-06T02:00:00Z")
    acc = make_acceptance(cust, vin=VIN,
                          cond=condition(12995, damage=[], photos_sha256="b2"*16),
                          ts="2026-08-07T14:05:00Z")
    pp.deliver(a, acc, condition(12995, damage=[], photos_sha256="b2"*16),
               location="Sun Valley, ID", ts="2026-08-07T14:10:00Z")
    return pp


def double_brokered() -> TransportPassport:
    broker, a, b, cust = _actors()
    pp = TransportPassport(_subject())
    pp.book(broker, a, cust, price_cents=185000, carrier_cents=160000,
            pickup_window="2026-08-05 08:00–12:00", delivery_window="2026-08-07 12:00–18:00",
            ts="2026-08-04T15:00:00Z")
    # a DIFFERENT carrier (b) actually picks up and delivers — the re-broker
    pp.pickup(b, condition(12340, photos_sha256="a1"*16), location="Scottsdale, AZ",
              ts="2026-08-05T09:20:00Z")
    acc = make_acceptance(cust, vin=VIN, cond=condition(12995), ts="2026-08-07T14:05:00Z")
    pp.deliver(b, acc, condition(12995), location="Sun Valley, ID",
               ts="2026-08-07T14:10:00Z")
    return pp


def with_damage() -> TransportPassport:
    broker, a, _b, cust = _actors()
    pp = TransportPassport(_subject())
    pp.book(broker, a, cust, price_cents=185000, carrier_cents=160000,
            pickup_window="2026-08-05 08:00–12:00", delivery_window="2026-08-07 12:00–18:00",
            ts="2026-08-04T15:00:00Z")
    pp.pickup(a, condition(12340, damage=[], photos_sha256="a1"*16),
              location="Scottsdale, AZ", ts="2026-08-05T09:20:00Z")
    dmg = condition(12995, damage=["passenger door: 3in scuff", "front lip: rock chip"],
                    photos_sha256="c3"*16)
    acc = make_acceptance(cust, vin=VIN, cond=dmg, ts="2026-08-07T14:05:00Z")
    pp.deliver(a, acc, dmg, location="Sun Valley, ID", ts="2026-08-07T14:10:00Z")
    return pp


def _report(name: str, pp: TransportPassport):
    d = pp.to_dict()
    ok, notes = verify_transport(d)
    dec = escrow_decision(d)
    print(f"\n=== {name} ===")
    for e in d["events"]:
        who = d["signers"][e["signer"]]["name"]
        print(f"  {e['seq']}. {e['type']:<8} [{who}]")
    print(f"  verify_transport → {'OK' if ok else 'REJECTED'}: {notes[-1] if not ok else notes[-2]}")
    money = f"${dec['amount_cents']/100:,.2f} → {dec['to']}" if dec["release"] else "— held/blocked"
    print(f"  escrow → {dec['status']}: {money}")
    if dec.get("damage_claim"):
        print(f"  ⚠ damage claim: {', '.join(dec['damage_claim']['new_damage'])}")
    return d, ok, dec


# --------------------------------------------------------------- certificate

def certificate_html(pp: dict) -> str:
    esc = escrow_decision(pp)
    ok, _ = verify_transport(pp)
    s = pp["subject"]
    e = html.escape
    rows = ""
    for ev in pp["events"]:
        who = pp["signers"][ev["signer"]]
        d = ev["data"]
        detail = ""
        if ev["type"] == "BOOKING":
            detail = f'carrier bound: {e(d["carrier"]["name"])} · escrow ${d["price_cents"]/100:,.2f}'
        elif ev["type"] in ("PICKUP", "DELIVERY"):
            c = d.get("condition", {})
            dmg = ", ".join(c.get("damage", [])) or "no damage noted"
            detail = f'odo {c.get("odometer","?"):,} · {e(dmg)} · {e(d.get("location",""))}'
        elif ev["type"] == "TRANSIT":
            detail = e(d.get("location", ""))
        rows += (f'<li><div class=ev><span class=etype>{ev["type"]}</span>'
                 f'<span class=ewho>{e(who["role"])} · {e(who["name"])}</span></div>'
                 f'<div class=edata>{detail}</div>'
                 f'<div class=esig>✓ signed {ev["sig"][:16]}… · {e(ev["ts"])}</div></li>')
    claim = ""
    if esc.get("damage_claim"):
        claim = ('<div class=claim>⚠ New damage recorded at delivery, absent at pickup — '
                 'both ends signed, so this claim can\'t be disputed away:<br>'
                 + e(", ".join(esc["damage_claim"]["new_damage"])) + '</div>')
    verdict = "VERIFIED" if ok else "REJECTED"
    vcolor = "#1a7f4b" if ok else "#b00020"
    esc_color = "#1a7f4b" if esc["release"] else "#b00020"
    return _TEMPLATE.format(
        vehicle=e(s["vehicle"]), vin=e(s["vin"]), origin=e(s["origin"]),
        dest=e(s["destination"]), carrier=e((pp.get("bound_carrier") or {}).get("name", "")),
        rows=rows, verdict=verdict, vcolor=vcolor,
        esc_status=esc["status"], esc_color=esc_color,
        esc_line=(f'${esc["amount_cents"]/100:,.2f} released to the bound carrier'
                  if esc["release"] else e(esc["reason"])),
        claim=claim, head=pp["chain_head"][:24], payload=e(json.dumps(pp)))


_TEMPLATE = """<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Custody record — {vehicle}</title><style>
:root{{--ink:#12151a;--dim:#6b7480;--line:#e3e7ec;--paper:#f6f8fa;--card:#fff;--accent:#2d6cdf;--hi:#1a7f4b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);
font:15px/1.55 system-ui,sans-serif;padding:2rem 1rem 4rem}}main{{max-width:680px;margin:0 auto}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:1.8rem 2rem;box-shadow:0 8px 30px rgba(0,0,0,.05)}}
.kick{{letter-spacing:.24em;text-transform:uppercase;font-size:.66rem;color:var(--accent);font-weight:700}}
h1{{font-size:1.5rem;margin:.3rem 0 .2rem}}.sub{{color:var(--dim);margin:0;font-size:.92rem}}
.seal{{float:right;text-align:center;border:2px solid {vcolor};color:{vcolor};border-radius:8px;
padding:.5rem .7rem;font-weight:700;font-size:.7rem;letter-spacing:.06em}}
h2{{font-size:.7rem;letter-spacing:.16em;text-transform:uppercase;color:var(--dim);margin:1.8rem 0 .7rem;border-bottom:1px solid var(--line);padding-bottom:.4rem}}
ol.chain{{list-style:none;margin:0;padding:0}}ol.chain li{{position:relative;padding:0 0 1rem 1.3rem;border-left:2px solid var(--line);margin-left:.3rem}}
ol.chain li:before{{content:"";position:absolute;left:-7px;top:.3rem;width:12px;height:12px;border-radius:50%;background:var(--accent);border:2px solid var(--card)}}
.ev{{display:flex;justify-content:space-between;gap:.5rem;flex-wrap:wrap}}.etype{{font-weight:700;font-size:.8rem;letter-spacing:.04em}}
.ewho{{color:var(--dim);font-size:.82rem}}.edata{{font-size:.9rem;margin:.15rem 0}}
.esig{{font-family:ui-monospace,monospace;font-size:.68rem;color:var(--hi)}}
.escrow{{border:1px solid var(--line);border-radius:8px;padding:.9rem 1rem;margin-top:.6rem}}
.escrow b{{color:{esc_color}}}.claim{{background:#fff6e5;border:1px solid #f0c98a;border-radius:8px;padding:.8rem 1rem;margin-top:.8rem;font-size:.9rem}}
.foot{{margin-top:1.4rem;font-size:.76rem;color:var(--dim)}}.hash{{font-family:ui-monospace,monospace;color:var(--ink)}}
details{{margin-top:.6rem}}summary{{cursor:pointer;color:var(--accent);font-size:.78rem}}pre{{white-space:pre-wrap;word-break:break-all;font-size:.6rem;color:var(--dim);background:#eef1f4;padding:.6rem;border-radius:6px}}
</style></head><body><main><div class=card>
<div class=seal>{verdict}<br><small>Ed25519</small></div>
<div class=kick>Vehicle custody record</div>
<h1>{vehicle}</h1><p class=sub>VIN {vin} · {origin} → {dest} · carrier of record: {carrier}</p>

<h2>Chain of custody — each handoff signed by the party who made it</h2>
<ol class=chain>{rows}</ol>

<h2>Escrow</h2>
<div class=escrow><b>{esc_status}</b> — {esc_line}.<br>
<span style=color:#6b7480;font-size:.85rem>Escrow can only release to the carrier identity bound at booking. A re-brokered load can't settle.</span></div>
{claim}

<div class=foot>Verifies from nothing but this document: every link Ed25519-signed and hash-chained;
pickup and delivery must be the carrier bound at booking; the customer's acceptance is co-signed.
Chain head <span class=hash>{head}…</span>
<details><summary>Verify this record yourself (raw document)</summary><pre>{payload}</pre></details></div>
</div></main></body></html>"""


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    d, ok, dec = _report("1. HONEST MOVE", honest())
    _report("2. DOUBLE BROKERED (different truck delivers)", double_brokered())
    _report("3. DELIVERED WITH NEW DAMAGE", with_damage())

    path = os.path.join(OUT, f"{VIN}.json")
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
    cert = os.path.join(OUT, f"{VIN}.html")
    with open(cert, "w") as f:
        f.write(certificate_html(d))
    print(f"\nwrote {os.path.relpath(path)}\n      {os.path.relpath(cert)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
