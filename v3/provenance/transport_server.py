"""Live auto-transport demo — the "watch double brokering get blocked" screen.

For a screen-share with a broker. One load is booked to a carrier; you pick who
actually delivers — the booked carrier, or a different truck (a re-broker) — and
the escrow releases or blocks in front of them. Same engine as
provenance/transport.py; this just puts a face on it.

    python -m provenance.transport_server        # http://127.0.0.1:8780
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .passport import Actor
from .transport import (TransportPassport, condition, make_acceptance,
                        verify_transport, escrow_decision)

VIN = "WP0AB2A99NS227614"
PRICE, CARRIER_PAY = 185000, 160000


def _actors():
    return (Actor.create("apex", "Apex Auto Transport", "broker", "acct:broker:apex"),
            Actor.create("sawtooth", "Sawtooth Hauling LLC", "carrier", "acct:carrier:sawtooth"),
            Actor.create("ghost", "Ghost Logistics", "carrier", "acct:carrier:ghost"),
            Actor.create("owner", "Vehicle owner", "customer", "acct:customer:owner"))


def _subject():
    return {"vin": VIN, "vehicle": "2022 Porsche 911 Carrera (992)",
            "origin": "Scottsdale, AZ", "destination": "Sun Valley, ID"}


def simulate(delivering: str = "booked", damage: bool = False) -> dict:
    """Build a custody chain where `delivering` is either the booked carrier or a
    re-broker, then verify + decide escrow. This is the whole demo."""
    broker, sawtooth, ghost, cust = _actors()
    pp = TransportPassport(_subject())
    pp.book(broker, sawtooth, cust, price_cents=PRICE, carrier_cents=CARRIER_PAY,
            pickup_window="Aug 5, 8–12", delivery_window="Aug 7, 12–6", ts="2026-08-04T15:00:00Z")
    carrier = sawtooth if delivering == "booked" else ghost
    pp.pickup(carrier, condition(12340, photos_sha256="a1" * 16), "Scottsdale, AZ",
              ts="2026-08-05T09:20:00Z")
    dmg = ["passenger door: 3in scuff"] if damage else []
    dcond = condition(12995, damage=dmg, photos_sha256="b2" * 16)
    acc = make_acceptance(cust, vin=VIN, cond=dcond,
                          booking_hash=pp.events[0]["hash"], ts="2026-08-07T14:05:00Z")
    pp.deliver(carrier, acc, dcond, "Sun Valley, ID", ts="2026-08-07T14:10:00Z")

    d = pp.to_dict()
    ok, notes = verify_transport(d)
    dec = escrow_decision(d)
    return {
        "delivering": carrier.name,
        "bound_carrier": pp.bound_carrier["name"],
        "verified": ok,
        "reason": notes[-1] if not ok else "pickup & delivery both signed by the booked carrier",
        "escrow": {"status": dec["status"], "to": dec.get("to"),
                   "amount_cents": dec.get("amount_cents", 0),
                   "damage_claim": dec.get("damage_claim")},
        "events": [{"type": e["type"], "who": d["signers"][e["signer"]]["name"],
                    "role": d["signers"][e["signer"]]["role"],
                    "is_bound": d["signers"][e["signer"]].get("pubkey") == pp.bound_carrier["pubkey"]}
                   for e in d["events"]],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200, ctype="application/json"):
        body = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(PAGE, ctype="text/html; charset=utf-8")
        if u.path.startswith("/api/simulate"):
            from urllib.parse import parse_qs
            q = parse_qs(u.query)
            return self._send(simulate(q.get("carrier", ["booked"])[0],
                                       q.get("damage", ["0"])[0] in ("1", "true")))
        return self._send({"error": "not found"}, 404)


_PAGE_TMPL = """<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Auto transport — double-broker block, live</title><style>
:root{--bg:#0b0d11;--card:#151922;--ink:#eef2f7;--dim:#8b96a6;--line:#232a35;--accent:#3b82f6;--ok:#22c55e;--bad:#ef4444;--amber:#f59e0b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,sans-serif;padding:1.5rem 1rem 4rem}
main{max-width:720px;margin:0 auto}h1{font-size:1rem;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.load{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1.2rem 1.4rem;margin:1rem 0}
.load h2{margin:.1rem 0;font-size:1.35rem}.load .meta{color:var(--dim);font-size:.9rem}
.book{display:flex;gap:1.2rem;flex-wrap:wrap;margin-top:.8rem;font-size:.9rem}
.book b{color:var(--ink)}.book span{color:var(--dim)}
.choose{margin:1.4rem 0 .4rem;color:var(--dim);font-size:.82rem;letter-spacing:.08em;text-transform:uppercase}
.btns{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}
button.act{padding:1rem;border-radius:12px;border:1px solid var(--line);background:#1b2130;color:var(--ink);cursor:pointer;text-align:left;font:inherit}
button.act b{display:block;font-size:1rem;margin-bottom:.2rem}button.act span{color:var(--dim);font-size:.82rem}
button.act.good b{color:var(--ok)}button.act.bad b{color:var(--bad)}button.act:hover{border-color:var(--accent)}
.dmg{margin:.8rem 0;color:var(--dim);font-size:.85rem}.dmg input{transform:translateY(2px)}
.result{margin-top:1.4rem;border-radius:14px;border:1px solid var(--line);overflow:hidden;display:none}
.verdict{padding:1.1rem 1.4rem;font-weight:800;font-size:1.1rem;display:flex;align-items:center;gap:.6rem}
.verdict.ok{background:rgba(34,197,94,.12);color:var(--ok)}.verdict.bad{background:rgba(239,68,68,.12);color:var(--bad)}
.body{padding:1rem 1.4rem}ol.chain{list-style:none;margin:0 0 1rem;padding:0}
ol.chain li{display:flex;justify-content:space-between;padding:.45rem 0;border-top:1px solid var(--line);font-size:.92rem}
ol.chain li:first-child{border-top:none}.who .r{color:var(--dim);font-size:.8rem;margin-left:.4rem}
.flag{font-size:.8rem;font-weight:700}.flag.ok{color:var(--ok)}.flag.bad{color:var(--bad)}
.escrow{border-top:1px solid var(--line);padding-top:.8rem;font-size:.95rem}.escrow b.rel{color:var(--ok)}.escrow b.blk{color:var(--bad)}
.reason{color:var(--dim);font-size:.86rem;margin-top:.3rem}.claim{margin-top:.7rem;background:#2a2410;border:1px solid #6b5518;color:var(--amber);border-radius:8px;padding:.6rem .8rem;font-size:.85rem}
</style></head><body><main>
<h1>Vehicle transport · escrow settlement</h1>
<div class=load>
  <h2>2022 Porsche 911 Carrera</h2>
  <div class=meta>VIN WP0AB2A99NS227614 · Scottsdale, AZ → Sun Valley, ID</div>
  <div class=book>
    <span>Carrier of record: <b>Sawtooth Hauling LLC</b></span>
    <span>Escrow: <b>$1,850.00</b> held · <b>$1,600.00</b> to carrier on delivery</span>
  </div>
</div>

<div class=choose>Who actually shows up to deliver?</div>
<div class=btns>
  <button class="act good" onclick="run('booked')"><b>Sawtooth delivers</b><span>the carrier that was booked</span></button>
  <button class="act bad" onclick="run('rebroker')"><b>A different truck delivers</b><span>Ghost Logistics — the load got re-brokered</span></button>
</div>
<label class=dmg><input type=checkbox id=dmg> deliver with a new scuff (show the damage claim)</label>

<div class=result id=result>
  <div class=verdict id=verdict></div>
  <div class=body>
    <ol class=chain id=chain></ol>
    <div class=escrow id=escrow></div>
    <div class=reason id=reason></div>
    <div id=claim></div>
  </div>
</div>

<script>
const RESULTS=__RESULTS__;   // precomputed so the page works standalone (no server needed)
const $=s=>document.querySelector(s);
async function run(carrier){
  const dmg=$('#dmg').checked?1:0;
  let r=RESULTS[carrier+'_'+dmg];
  if(!r){try{r=await (await fetch('/api/simulate?carrier='+carrier+'&damage='+dmg)).json();}catch(e){return;}}
  $('#result').style.display='block';
  const v=$('#verdict');
  v.className='verdict '+(r.verified?'ok':'bad');
  v.textContent=r.verified?'✓ VERIFIED — delivered by the booked carrier':'✕ REJECTED — double brokering detected';
  $('#chain').innerHTML=r.events.map(e=>{
    const bound=(e.type==='PICKUP'||e.type==='DELIVERY');
    const flag=bound?(e.is_bound?'<span class="flag ok">✓ booked carrier</span>':'<span class="flag bad">✕ NOT the booked carrier</span>'):'';
    return `<li><span class=who><b>${e.type}</b><span class=r>${e.role} · ${e.who}</span></span>${flag}</li>`;
  }).join('');
  const esc=$('#escrow');
  if(r.escrow.status==='RELEASED')
    esc.innerHTML=`Escrow: <b class=rel>RELEASED</b> — $${(r.escrow.amount_cents/100).toFixed(2)} paid to ${r.escrow.to.replace('acct:carrier:','')}`;
  else
    esc.innerHTML=`Escrow: <b class=blk>${r.escrow.status}</b> — no funds move. The delivering truck was never bound to this load, so it cannot be paid.`;
  $('#reason').textContent=r.reason;
  $('#claim').innerHTML=r.escrow.damage_claim?('<div class=claim>⚠ New damage at delivery, absent at pickup — an undeniable claim (both ends signed): '+r.escrow.damage_claim.new_damage.join(', ')+'</div>'):'';
}
</script></body></html>"""


def _results() -> dict:
    return {f"{c}_{1 if d else 0}": simulate(c, d)
            for c in ("booked", "rebroker") for d in (False, True)}


PAGE = _PAGE_TMPL.replace("__RESULTS__", json.dumps(_results()))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Live auto-transport double-broker demo")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8780)
    args = ap.parse_args(argv)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Transport demo on http://{args.host}:{args.port}  (screen-share this)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
