"""Build a verifiable provenance passport for one A5 Wagyu ribeye, end to end.

    python -m provenance.demo

Writes out/passport/<lot>.json (the machine-verifiable document) and
out/passport/<lot>.html (the certificate a human — or the grocer's customer —
can actually look at). Every actor signs their own link with their own key;
the sale routes real money to the rancher who grew the feed.

The scenario is illustrative (names are placeholders); the crypto is real and
the exact same primitives that settle a 3D-print job on the live network.
"""

from __future__ import annotations

import html
import json
import os

from bingo.models import Split, SplitPayee
from .passport import Actor, CutPassport, verify_passport

OUT = os.path.join(os.path.dirname(__file__), "..", "out", "passport")


def build() -> CutPassport:
    # --- the people (real keys; placeholder identities) --------------------
    op = Actor.create("dgd-wagyu", "DGD Wagyu Co.", "operation", "acct:op:dgd-wagyu")
    rancher = Actor.create("sadu-farms", "SADU Farms — 3rd-generation",
                           "rancher", "acct:rancher:sadu")
    proc = Actor.create("wood-river", "Wood River Processing", "processor",
                        "acct:processor:wood-river")
    carrier = Actor.create("sawtooth-cc", "Sawtooth Cold Chain", "carrier",
                           "acct:carrier:sawtooth")
    grocer = Actor.create("sun-valley-mkt", "Sun Valley Market", "grocer",
                          "acct:grocer:sun-valley")

    lot = "SV-A5-2026-0731-017"
    p = CutPassport(subject={
        "product": "A5 Wagyu ribeye",
        "lot": lot,
        "weight_lb": 0.90,
        "destination": "Sun Valley, Idaho",
    })

    # 0 — LINEAGE: genetics are the whole premium. Signed by the operation.
    p.attest(op, "LINEAGE", {
        "breed": "Wagyu (Japanese Black)",
        "tajima_pct": 96,
        "sire": "TF-Itomichi-II", "dam": "SF-Fuku-0912",
        "animal_id": "SF-2024-118", "born": "2024-03-11",
        "birth_ranch": "SADU Farms",
    }, ts="2024-03-11T09:00:00Z")

    # 1 — HUSBANDRY / FEED: the human hook. Signed by the RANCHER herself.
    p.attest(rancher, "HUSBANDRY", {
        "feed": ["ranch-grown alfalfa", "ranch-grown barley", "ranch-grown corn"],
        "feed_origin": "SADU Farms — grown by a 3rd-generation rancher",
        "ration": "free-choice forage + finishing grain",
        "days_on_feed": 640, "no_hormones": True, "no_antibiotics_finishing": True,
    }, ts="2026-05-20T07:30:00Z")

    # 2 — HARVEST + GRADE: A5 is a graded claim, so it gets attested & signed.
    p.attest(proc, "HARVEST", {
        "harvest_date": "2026-07-14", "dressed_weight_lb": 812,
        "grading": "Japanese BMS", "bms": 11, "yield_grade": "A", "grade": "A5",
        "primal": "rib",
    }, ts="2026-07-14T16:00:00Z")

    # 3 — CUT: this physical unit.
    p.attest(proc, "CUT", {
        "cut": "ribeye steak", "weight_lb": 0.90, "thickness_in": 1.25,
        "cut_date": "2026-07-28", "lot": lot,
    }, ts="2026-07-28T11:15:00Z")

    # 4 — CUSTODY / COLD CHAIN: the part a print farm never had. Signed by carrier.
    p.attest(carrier, "CUSTODY", {
        "pickup": "Wood River Processing", "dropoff": "Sun Valley Market",
        "picked_up": "2026-07-31T06:10:00Z", "delivered": "2026-07-31T09:40:00Z",
        "temp_setpoint_f": 32, "temp_max_observed_f": 34, "cold_chain_ok": True,
    }, ts="2026-07-31T09:40:00Z")

    # 5 — SALE: retail at $65/lb, decomposed across everyone who made the value.
    price = round(0.90 * 6500)                     # $65.00/lb -> 5850¢
    split = Split([
        SplitPayee("acct:grocer:sun-valley", 3000),   # 30% point of sale
        SplitPayee("acct:op:dgd-wagyu", 3000),         # 30% brand / genetics / mgmt
        SplitPayee("acct:rancher:sadu", 2200),         # 22% the feed she grew
        SplitPayee("acct:processor:wood-river", 1000), # 10% cut & A5 grading
        SplitPayee("acct:carrier:sawtooth", 800),      # 8%  cold chain
    ])
    p.record_sale(grocer, price, split, buyer="retail-customer",
                  unit="1 ribeye (0.90 lb)", ts="2026-07-31T17:05:00Z")
    return p


# --------------------------------------------------------------- certificate

_ROLE_LABEL = {"operation": "Operation", "rancher": "Rancher (feed)",
               "processor": "Processor", "carrier": "Cold chain", "grocer": "Grocer"}


def certificate_html(pp: dict) -> str:
    subj = pp["subject"]
    signers = pp["signers"]
    esc = html.escape

    def line_row(l):
        name = esc(signers.get(_acct_owner(signers, l["account"]), {}).get("name", l["account"]))
        who = _acct_label(signers, l["account"])
        pct = l["bps"] / 100
        hi = "rancher" in l["account"]
        return (f'<div class="leg{" hi" if hi else ""}">'
                f'<div class="legtop"><span>{esc(who)}</span>'
                f'<span class="amt">${l["cents"]/100:,.2f}</span></div>'
                f'<div class="bar"><i style="width:{pct}%"></i></div>'
                f'<div class="legsub">{pct:g}%{" · the hands that grew the feed" if hi else ""}</div>'
                f'</div>')

    def event_row(e):
        rec = signers.get(e["signer"], {})
        role = _ROLE_LABEL.get(rec.get("role", ""), rec.get("role", ""))
        return (f'<li><div class="ev"><span class="etype">{esc(e["type"])}</span>'
                f'<span class="ewho">{esc(role)} · {esc(rec.get("name",""))}</span></div>'
                f'<div class="edata">{esc(_summ(e))}</div>'
                f'<div class="esig">✓ signed {e["sig"][:16]}… · {esc(e["ts"])}</div></li>')

    legs = "".join(line_row(l) for l in pp.get("settlement", []))
    evs = "".join(event_row(e) for e in pp["events"])
    ok, notes = verify_passport(pp)
    price = next((e["data"]["price_cents"] for e in pp["events"]
                  if e["type"] == "SALE"), 0)
    return _TEMPLATE.format(
        product=esc(subj["product"]), lot=esc(subj["lot"]),
        weight=subj["weight_lb"], dest=esc(subj["destination"]),
        price=f'{price/100:,.2f}', legs=legs, events=evs,
        head=pp["chain_head"][:24], verdict="VERIFIED" if ok else "INVALID",
        vcolor="#1a7f4b" if ok else "#b00020",
        note=esc(notes[-2] if len(notes) >= 2 else notes[-1]),
        payload=esc(json.dumps(pp)))


def _acct_owner(signers, account):
    for aid, rec in signers.items():
        if rec.get("account") == account:
            return aid
    return account


def _acct_label(signers, account):
    rec = signers.get(_acct_owner(signers, account), {})
    return rec.get("name", account.replace("acct:", ""))


def _summ(e) -> str:
    d = e["data"]
    t = e["type"]
    if t == "LINEAGE":
        return f'{d["breed"]} · {d["tajima_pct"]}% Tajima · animal {d["animal_id"]}'
    if t == "HUSBANDRY":
        return f'{d["feed_origin"]} · {", ".join(d["feed"])} · {d["days_on_feed"]} days on feed'
    if t == "HARVEST":
        return f'Grade {d["grade"]} (BMS {d["bms"]}) · dressed {d["dressed_weight_lb"]} lb'
    if t == "CUT":
        return f'{d["cut"]} · {d["weight_lb"]} lb · lot {d["lot"]}'
    if t == "CUSTODY":
        return (f'cold chain {"OK" if d.get("cold_chain_ok") else "BROKEN"} · '
                f'≤{d["temp_max_observed_f"]}°F · {d["pickup"]} → {d["dropoff"]}')
    if t == "SALE":
        return f'${d["price_cents"]/100:,.2f} · {d["unit"]} · split {len(d["legs"])} ways'
    return json.dumps(d)


_TEMPLATE = """<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Provenance passport — {product}</title><style>
:root{{--ink:#1c1a17;--dim:#7a7266;--line:#e4ddd1;--paper:#faf7f1;--card:#fff;--gold:#a9852f;--hi:#1a7f4b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);
font:16px/1.6 Georgia,"Times New Roman",serif;padding:2rem 1rem 4rem}}
main{{max-width:680px;margin:0 auto}}.card{{background:var(--card);border:1px solid var(--line);
border-radius:6px;padding:2rem 2.2rem;box-shadow:0 1px 0 #fff inset,0 8px 30px rgba(0,0,0,.06)}}
.kick{{letter-spacing:.32em;text-transform:uppercase;font-size:.68rem;color:var(--gold);font-family:system-ui,sans-serif}}
h1{{font-size:1.9rem;margin:.3rem 0 .2rem;font-weight:600}}.sub{{color:var(--dim);margin:0}}
.badge{{display:inline-block;background:#1c1a17;color:#f6e9c8;border-radius:4px;padding:.15rem .5rem;
font-family:system-ui,sans-serif;font-weight:700;letter-spacing:.05em;font-size:.8rem;margin-left:.4rem}}
.seal{{float:right;text-align:center;border:2px solid {vcolor};color:{vcolor};border-radius:50%;
width:92px;height:92px;display:flex;flex-direction:column;justify-content:center;font-family:system-ui,sans-serif;
font-weight:700;font-size:.72rem;letter-spacing:.08em;line-height:1.2}}.seal small{{font-weight:400;font-size:.6rem;color:var(--dim)}}
h2{{font-size:.72rem;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);
font-family:system-ui,sans-serif;margin:2rem 0 .8rem;border-bottom:1px solid var(--line);padding-bottom:.4rem}}
ol.chain{{list-style:none;margin:0;padding:0}}ol.chain li{{position:relative;padding:0 0 1.1rem 1.4rem;border-left:2px solid var(--line);margin-left:.3rem}}
ol.chain li:before{{content:"";position:absolute;left:-7px;top:.35rem;width:12px;height:12px;border-radius:50%;background:var(--gold);border:2px solid var(--card)}}
ol.chain li:last-child{{border-left-color:transparent}}
.ev{{display:flex;justify-content:space-between;align-items:baseline;gap:.5rem;flex-wrap:wrap}}
.etype{{font-family:system-ui,sans-serif;font-weight:700;font-size:.78rem;letter-spacing:.05em}}
.ewho{{color:var(--dim);font-size:.82rem}}.edata{{font-size:.92rem;margin:.15rem 0}}
.esig{{font-family:ui-monospace,monospace;font-size:.7rem;color:var(--hi)}}
.leg{{margin:.5rem 0}}.legtop{{display:flex;justify-content:space-between;font-size:.9rem}}
.amt{{font-variant-numeric:tabular-nums}}.bar{{height:7px;background:#efe9dd;border-radius:4px;overflow:hidden;margin:.2rem 0}}
.bar i{{display:block;height:100%;background:var(--gold)}}.leg.hi .bar i{{background:var(--hi)}}
.leg.hi .legtop{{font-weight:700;color:var(--hi)}}.legsub{{font-size:.72rem;color:var(--dim);font-family:system-ui,sans-serif}}
.foot{{margin-top:1.6rem;font-size:.74rem;color:var(--dim);font-family:system-ui,sans-serif;line-height:1.5}}
.hash{{font-family:ui-monospace,monospace;color:var(--ink)}}details{{margin-top:.6rem}}summary{{cursor:pointer;color:var(--gold);font-family:system-ui,sans-serif;font-size:.78rem}}
pre{{white-space:pre-wrap;word-break:break-all;font-size:.62rem;color:var(--dim);background:#f3eee3;padding:.6rem;border-radius:4px}}
</style></head><body><main><div class=card>
<div class=seal>{verdict}<small> Ed25519</small></div>
<div class=kick>Verified provenance passport</div>
<h1>{product}<span class=badge>{price} · $65/lb</span></h1>
<p class=sub>Lot {lot} · {weight} lb · destined for {dest}</p>

<h2>Chain of custody — every link signed by the party who made it</h2>
<ol class=chain>{events}</ol>

<h2>Where your ${price} goes — routed automatically, at the sale</h2>
{legs}

<div class=foot>
This document verifies from nothing but itself: each link carries an Ed25519 signature
under its signer's own key, hash-chained so no link can be altered or reordered without
breaking the seal. {note}.<br>
Chain head <span class=hash>{head}…</span><br>
The rancher who grew the feed is paid on this cut — not thanked in the marketing, paid.
Same proof grammar that settles a job on the Project&nbsp;BINGO network.
<details><summary>Verify this passport yourself (raw document)</summary><pre>{payload}</pre></details>
</div></div></main></body></html>"""


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    p = build()
    pp = p.to_dict()
    lot = pp["subject"]["lot"]
    jpath = os.path.join(OUT, f"{lot}.json")
    hpath = os.path.join(OUT, f"{lot}.html")
    with open(jpath, "w") as f:
        json.dump(pp, f, indent=2)
    with open(hpath, "w") as f:
        f.write(certificate_html(pp))

    ok, notes = verify_passport(pp)
    print(f"Passport for {pp['subject']['product']} — lot {lot}")
    print("chain of custody:")
    for e in pp["events"]:
        rec = pp["signers"][e["signer"]]
        print(f"  {e['seq']}. {e['type']:<9} ← {rec['role']:<9} {rec['name']}")
    print("\nvalue routing on the $%.2f sale:" % (
        next(e['data']['price_cents'] for e in pp['events'] if e['type'] == 'SALE') / 100))
    for l in pp["settlement"]:
        star = "  ← the feed she grew" if "rancher" in l["account"] else ""
        print(f"  {l['account']:<28} {l['bps']/100:>5.1f}%  ${l['cents']/100:>6.2f}{star}")
    print(f"\nverify_passport → {'OK' if ok else 'FAIL'}")
    for n in notes:
        print("  ·", n)
    print(f"\nwrote {os.path.relpath(jpath)}\n      {os.path.relpath(hpath)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
