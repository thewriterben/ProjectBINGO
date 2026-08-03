"""L5 — Web surface: browsable marketplace, live dashboard, agent-first API.

Stdlib only. Runs a live in-memory network (designs, nodes, ledger,
orchestrator) so you can browse it and place orders that really fabricate and
settle. The JSON API is the point: within a few years the modal buyer is
somebody's AI assistant ordering a part — this is the endpoint it calls.

  python -m bingo.server            # http://127.0.0.1:8760
  python -m bingo.server --port 9000 --host 0.0.0.0

API:
  GET  /api/health
  GET  /api/assets                designs + process packages, with royalty splits
  GET  /api/nodes                 nodes + grade-aware reputation
  GET  /api/dashboard             network totals + recent settlements
  POST /api/orders                {asset_id, qty, material?, grade?, buyer?}
                                  → places, fabricates, settles; returns the receipt
  GET  /api/orders/<id>           order status + per-job settlement
  GET  /api/creators/<account>    what a creator earned: total, units, per-design
  GET  /api/creators/<a>/statement  plain-text creator statement (the receipt)
  GET  /creator/<account>         a creator's earnings page (the payoff view)
  GET  /api/passport/<asset_id>   an RWA good's provenance passport + verification
  GET  /passport/<asset_id>       that good's printable provenance certificate
  GET  /api/tokens                tokenized claims on RWA goods (backed by provenance)
  GET  /api/token/<id>            one token's ownership ledger + replay verification
  GET  /api/verify/<job_id>       independently verify that job's persisted PoF
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import evidence
from .acceptance import Grade, GRADE_NAME
from .earnings import creator_earnings, statement_text
from .ledger import Ledger, NETWORK_ACCOUNT, CARRIER_ACCOUNT
from .models import (Derivation, License, LicenseTemplate, Machine, NodeInfo,
                    Split, SplitPayee)
from .node.agent import NodeAgent
from .orchestrator import Orchestrator, OrderRejected
from .registry import AssetRegistry
from .demo.make_design import bracket_stl, clip_stl
from provenance.register import register_rwa, passport_of
from provenance.passport import verify_passport, Actor
from provenance.demo import build as build_wagyu_passport, certificate_html
from provenance.token import AssetToken, verify_token, token_settlement

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "out")
_lock = threading.Lock()


def seed_network():
    reg, ledger = AssetRegistry(), Ledger()
    bracket = reg.register(
        kind="design", title="PB-001 shelf bracket", creator="acct:ben",
        content=bracket_stl(),
        license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=40),
        split=Split([SplitPayee("acct:ben", 8000), SplitPayee("acct:alex", 2000)]))
    reg.register(
        kind="design", title="PB-002 cable clip (remix of PB-001)", creator="acct:carol",
        content=clip_stl(),
        license=License(LicenseTemplate.COMMERCIAL_PER_UNIT, per_unit_cents=25),
        split=Split([SplitPayee("acct:carol", 10000)]),
        derives_from=[Derivation(bracket.asset_id, parent_share_bps=2000)])

    def fdm(mid, model, kw=0.12):
        return Machine(machine_id=mid, make_model=model, process="fdm",
                       envelope_mm=(250, 250, 250), materials=["PLA", "PETG"], kw=kw)

    nodes = [
        NodeInfo(node_id="n-slc", operator="acct:dana", name="Dana's spare-room Bambu (SLC)",
                 lat=40.76, lon=-111.89, tier=0, rate_cents_per_hour=250,
                 machines=[fdm("m-x1c", "Bambu X1C")], reputation=0.55),
        NodeInfo(node_id="n-abq", operator="acct:mia", name="Mia's print farm (ABQ)",
                 lat=35.08, lon=-106.65, tier=1, rate_cents_per_hour=400,
                 machines=[fdm("m-mk4", "Prusa MK4", 0.10)], reputation=0.72),
        NodeInfo(node_id="n-kc", operator="acct:ray", name="Ray's job shop (KC)",
                 lat=39.10, lon=-94.58, tier=2, rate_cents_per_hour=650,
                 machines=[fdm("m-x1e", "Bambu X1E", 0.14)], reputation=0.85),
    ]
    # A physical real-world good, registered as a first-class asset: its
    # content IS its signed provenance passport (content-addressed), its split
    # is the passport's value routing. A cow alongside the brackets.
    register_rwa(reg, build_wagyu_passport(), creator="acct:op:dgd-wagyu")

    agents = [NodeAgent(n) for n in nodes]
    orch = Orchestrator(reg, ledger, agents, evidence_dir=os.path.join(OUT_DIR, "evidence"))
    return reg, ledger, orch, agents


REG, LEDGER, ORCH, AGENTS = seed_network()


def seed_tokens() -> dict:
    """Issue a tokenized claim on the RWA good — 100 shares, pinned to its
    verified provenance — and do one primary transfer, so the network shows a
    real, verifiable ownership ledger sitting on top of a proven asset."""
    rwa = next((a for a in REG.all() if a.kind == "rwa"), None)
    if not rwa:
        return {}
    pp = passport_of(REG, rwa)
    value_split = next((e["data"]["split"]["payees"]
                        for e in pp["events"] if e["type"] == "SALE"), [])
    op = Actor.create("dgd-wagyu", "DGD Wagyu Co.", "operation", "acct:op:dgd-wagyu")
    chef = Actor.create("river-grill", "River Grill (Ketchum)", "buyer",
                        "acct:buyer:river-grill")
    tok = AssetToken(backing_asset_id=rwa.asset_id, passport_head=pp["chain_head"],
                     unit=f'1/100 of lot {pp["subject"]["lot"]}', total_supply=100,
                     issuer=op, value_split=value_split, ts="2026-07-31T18:00:00Z")
    # a primary sale routes proceeds through the provenance split (the rancher paid)
    tok.sell(op, chef.account, 40, price_cents=4000, ts="2026-07-31T18:05:00Z")
    return {tok.token_id: tok.to_dict()}


TOKENS = seed_tokens()


def _provenance_summary(asset) -> dict | None:
    """For an RWA asset, a compact, verified summary drawn from its passport."""
    if asset.kind != "rwa":
        return None
    pp = passport_of(REG, asset)
    ok, _ = verify_passport(pp)
    ev = {e["type"]: e["data"] for e in pp["events"]}
    lineage, harvest = ev.get("LINEAGE", {}), ev.get("HARVEST", {})
    return {
        "verified": ok,
        "grade": harvest.get("grade"),
        "origin": lineage.get("birth_ranch"),
        "tajima_pct": lineage.get("tajima_pct"),
        "links": len(pp["events"]),
        "signers": len(pp["signers"]),
        "chain_head": pp["chain_head"][:16],
        "price_cents": asset.license.flat_fee_cents,
        "certificate": f"/passport/{asset.asset_id}",
        "tokenized": _token_for_asset(asset.asset_id),
    }


def _assets():
    out = []
    for a in REG.all():
        out.append({"asset_id": a.asset_id, "title": a.title, "kind": a.kind,
                    "per_unit_cents": a.license.per_unit_cents,
                    "split": [{"account": p.account, "bps": p.bps}
                              for p in a.effective_split.payees],
                    "derived": bool(a.derives_from),
                    "provenance": _provenance_summary(a)})
    return out


def _passport(asset_id: str) -> dict:
    try:
        asset = REG.get(asset_id)
    except KeyError:
        return {"error": "not found"}
    if asset.kind != "rwa":
        return {"error": "asset has no provenance passport"}
    pp = passport_of(REG, asset)
    ok, notes = verify_passport(pp)
    return {"asset_id": asset_id, "verify": {"ok": ok, "notes": notes},
            "passport": pp}


def _verify_token(td: dict) -> tuple[bool, list]:
    """Verify a token, pulling its backing passport from the registry so the
    provenance pin is actually checked."""
    try:
        backing = passport_of(REG, REG.get(td["backing_asset_id"]))
    except (KeyError, Exception):
        backing = None
    return verify_token(td, backing_passport=backing)


def _tokens() -> list:
    out = []
    for tid, td in TOKENS.items():
        ok, _ = _verify_token(td)
        st = token_settlement(td)
        out.append({"token_id": tid, "unit": td["unit"],
                    "backing_asset_id": td["backing_asset_id"],
                    "total_supply": td["total_supply"],
                    "circulating": td["circulating"], "retired": td["retired"],
                    "holders": len(td["balances"]), "verified": ok,
                    "proceeds_cents": st["proceeds_cents"], "paid": st["paid"]})
    return out


def _token(token_id: str) -> dict:
    td = TOKENS.get(token_id)
    if not td:
        return {"error": "not found"}
    ok, notes = _verify_token(td)
    return {"token_id": token_id, "verify": {"ok": ok, "notes": notes},
            "settlement": token_settlement(td), "token": td}


def _token_for_asset(asset_id: str) -> dict | None:
    for tid, td in TOKENS.items():
        if td["backing_asset_id"] == asset_id:
            return {"token_id": tid, "circulating": td["circulating"],
                    "total_supply": td["total_supply"], "unit": td["unit"]}
    return None


def _certificate(asset_id: str) -> str | None:
    try:
        asset = REG.get(asset_id)
    except KeyError:
        return None
    if asset.kind != "rwa":
        return None
    return certificate_html(passport_of(REG, asset))


def _nodes():
    out = []
    for ag in AGENTS:
        n = ag.info
        out.append({"node_id": n.node_id, "name": n.name, "operator": n.operator,
                    "tier": n.tier, "process": n.machines[0].process,
                    "materials": n.machines[0].materials,
                    "reputation_F": ORCH.reputation.node_score(n.node_id, "F", "fdm", n.reputation),
                    "public_key": ag.public_key_hex[:16] + "…"})
    return out


def _dashboard():
    creators = sorted({p.account for a in REG.all() for p in a.effective_split.payees})
    orders = list(ORCH.orders.values())
    units = sum(o.qty for o in orders)
    return {
        "orders": len(orders),
        "units_fabricated": units,
        "creator_earnings": {c: LEDGER.balance(c) for c in creators if LEDGER.balance(c)},
        "node_earnings": {ag.info.operator: LEDGER.balance(f"acct:node:{ag.info.node_id}")
                          for ag in AGENTS},
        "network_fee_cents": LEDGER.balance(NETWORK_ACCOUNT),
        "carrier_cents": LEDGER.balance(CARRIER_ACCOUNT),
        "recent": [{"order_id": e.order_id, "job_id": e.job_id, "kind": e.kind,
                    "legs": len(e.legs)} for e in LEDGER.journal[-8:]],
    }


def _place_order(body: dict) -> dict:
    asset_id = body["asset_id"]
    qty = int(body.get("qty", 1))
    material = body.get("material", "PLA")
    grade = Grade(body.get("grade", "F"))
    buyer = body.get("buyer", "acct:api-buyer")
    lat = float(body.get("lat", 39.74))
    lon = float(body.get("lon", -104.99))
    with _lock:
        order, dfm = ORCH.place_order(buyer=buyer, asset_id=asset_id, qty=qty,
                                      material=material, buyer_lat=lat, buyer_lon=lon,
                                      grade=grade)
        settled = ORCH.execute_order(order, dfm)
    creators = sorted({p.account for j in settled for line in j.royalty_lines
                       for p in line.payees})
    return {
        "order_id": order.order_id, "grade": order.grade,
        "total_cents": order.total_cents, "units": order.qty,
        "jobs": [{"job_id": j.job_id, "node_id": j.node_id, "qty": j.qty,
                  "checklist_hash": j.checklist_hash[:12] + "…",
                  "pof_events": len(j.evidence),
                  "verify": f"/api/verify/{j.job_id}"} for j in settled],
        "royalties_paid": {c: LEDGER.balance(c) for c in creators},
    }


def _creator(account: str) -> dict:
    if not account.startswith("acct:"):
        account = "acct:" + account
    return creator_earnings(LEDGER, REG, account).to_dict()


def _creator_statement(account: str) -> str:
    if not account.startswith("acct:"):
        account = "acct:" + account
    return statement_text(creator_earnings(LEDGER, REG, account))


def _verify(job_id: str) -> dict:
    path = os.path.join(OUT_DIR, "evidence", f"{job_id}.json")
    if not os.path.exists(path):
        return {"ok": False, "notes": ["no persisted evidence for that job"]}
    ok, notes = evidence.verify(evidence.load(path))
    return {"ok": ok, "notes": notes}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200, ctype="application/json"):
        body = obj.encode() if isinstance(obj, str) else json.dumps(obj, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            return self._send(PAGE, ctype="text/html")
        if path == "/api/health":
            return self._send({"ok": True, "service": "bingo", "nodes": len(AGENTS)})
        if path == "/api/assets":
            return self._send(_assets())
        if path == "/api/nodes":
            return self._send(_nodes())
        if path == "/api/dashboard":
            return self._send(_dashboard())
        if path == "/api/tokens":
            return self._send(_tokens())
        if path.startswith("/api/token/"):
            return self._send(_token(path.rsplit("/", 1)[-1]))
        if path.startswith("/api/passport/"):
            return self._send(_passport(path.rsplit("/", 1)[-1]))
        if path.startswith("/passport/"):
            cert = _certificate(path.rsplit("/", 1)[-1])
            return self._send(cert, ctype="text/html") if cert else \
                self._send({"error": "no passport for that asset"}, 404)
        if path.startswith("/api/creators/"):
            rest = path[len("/api/creators/"):]
            if rest.endswith("/statement"):
                return self._send(_creator_statement(rest[:-len("/statement")]),
                                  ctype="text/plain; charset=utf-8")
            return self._send(_creator(rest))
        if path.startswith("/creator/"):
            return self._send(CREATOR_PAGE, ctype="text/html")
        if path.startswith("/api/verify/"):
            return self._send(_verify(path.rsplit("/", 1)[-1]))
        if path.startswith("/api/orders/"):
            oid = path.rsplit("/", 1)[-1]
            o = ORCH.orders.get(oid)
            return self._send(o.summary() if o else {"error": "not found"},
                              200 if o else 404)
        return self._send({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._send({"error": "invalid JSON"}, 400)
        if path == "/api/orders":
            try:
                return self._send(_place_order(body))
            except (OrderRejected, KeyError, ValueError) as e:
                return self._send({"error": str(e)}, 400)
        return self._send({"error": "not found"}, 404)


PAGE = """<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Project BINGO — network</title><style>
:root{--bg:#0e1116;--card:#161b22;--ink:#e6edf3;--dim:#8b949e;--acc:#4ade80;--line:#242b36}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 system-ui,sans-serif;padding:1.5rem 1rem 4rem}main{max-width:1000px;margin:0 auto}
h1{font-size:1.1rem;letter-spacing:.06em;color:var(--dim);text-transform:uppercase}
.hero{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1.5rem;margin:1rem 0;text-align:center}
.hero .big{font-size:2.2rem;font-weight:700;color:var(--acc)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1rem 1.2rem;margin-bottom:1.2rem}
h2{font-size:.9rem;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin:.2rem 0 .7rem}
table{width:100%;border-collapse:collapse;font-size:.86rem}td,th{padding:.4rem .5rem;border-top:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--dim);border-top:none}code{color:#79c0ff}.amt{text-align:right;color:var(--acc);font-variant-numeric:tabular-nums}
button{background:var(--acc);color:#06210f;border:0;border-radius:8px;padding:.5rem .9rem;font-weight:600;cursor:pointer}
select,input{background:#0d1117;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:.45rem;font:inherit}
.row{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center}#out{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:.8rem;color:var(--dim);margin-top:.6rem}
a{color:#79c0ff}</style></head><body><main>
<h1>Project BINGO · live network</h1>
<div class=hero><div class=big id=royalties>$0.00</div>
<p style="color:var(--dim)">paid to creators, atomically, at the moment of fabrication ·
<span id=units>0</span> units · <span id=orders>0</span> orders</p></div>

<section><h2>Place an order (this really fabricates & settles)</h2>
<div class=row>
<select id=asset></select>
<input id=qty type=number value=5 min=1 style=width:5rem>
<select id=grade><option value=F>F · Functional</option><option value=S>S · Standard</option><option value=P>P · Premium</option></select>
<button onclick=order()>Order</button></div>
<div id=out></div></section>

<section><h2>Assets (L1) — designs & provenance-verified real-world goods</h2><table id=assets></table></section>
<section><h2>Tokenized claims — ownership backed by verified provenance</h2><table id=tokens></table></section>
<section><h2>Nodes (L2)</h2><table id=nodes></table></section>
<section><h2>Recent settlements (L4)</h2><table id=recent></table></section>
<p style="color:var(--dim);font-size:.8rem">Agent-first API: <code>GET /api/assets</code>,
<code>POST /api/orders</code>, <code>GET /api/verify/&lt;job&gt;</code>. Every number here is derived from settled ledger entries.</p>
</main><script>
const $=s=>document.querySelector(s);
async function j(u,o){return (await fetch(u,o)).json()}
async function load(){
 const a=await j('/api/assets');
 $('#assets').innerHTML='<tr><th>title</th><th>kind / license</th><th>split</th></tr>'+a.map(x=>{
  const pv=x.provenance;
  let badge=pv?` <a href="${pv.certificate}" title="${pv.links} signed links · chain ${pv.chain_head}…" style="color:${pv.verified?'#4ade80':'#f85149'};text-decoration:none">✓ verified provenance</a>`:(x.derived?' <span style=color:#8b949e>· remix</span>':'');
  if(pv&&pv.tokenized)badge+=` <span style=color:#d2a8ff title="${pv.tokenized.circulating}/${pv.tokenized.total_supply} shares circulating">◆ tokenized</span>`;
  const kind=pv?`RWA · ${pv.grade} · ${pv.tajima_pct}% Tajima · $${(pv.price_cents/100).toFixed(2)}`:`${x.per_unit_cents}¢/unit`;
  return `<tr><td>${x.title}${badge}</td><td>${kind}</td><td>${x.split.map(s=>`<a href="/creator/${encodeURIComponent(s.account)}">${s.account.replace('acct:','')}</a> `+(s.bps/100)+'%').join(' · ')}</td></tr>`}).join('');
 const sel=$('#asset');sel.innerHTML=a.filter(x=>x.kind!=='rwa').map(x=>`<option value=${x.asset_id}>${x.title}</option>`).join('');
 const tk=await j('/api/tokens');
 const rancherPaid=t=>{const k=Object.keys(t.paid||{}).find(a=>a.includes('rancher'));return k?t.paid[k]:0};
 $('#tokens').innerHTML=tk.length?('<tr><th>token</th><th>unit</th><th>circulating</th><th>proceeds</th><th>→ rancher</th><th>verified</th></tr>'+tk.map(t=>
  `<tr><td><code>${t.token_id.slice(0,12)}…</code></td><td>${t.unit}</td><td>${t.circulating}/${t.total_supply}${t.retired?` <span style=color:#8b949e>(${t.retired} redeemed)</span>`:''}</td><td class=amt>$${((t.proceeds_cents||0)/100).toFixed(2)}</td><td class=amt>$${(rancherPaid(t)/100).toFixed(2)}</td><td style=color:${t.verified?'#4ade80':'#f85149'}>${t.verified?'✓ replayed':'✗'}</td></tr>`).join('')):'<tr><td>no tokens</td></tr>';
 const n=await j('/api/nodes');
 $('#nodes').innerHTML='<tr><th>node</th><th>tier</th><th>materials</th><th>rep(F)</th><th>key</th></tr>'+n.map(x=>
  `<tr><td>${x.name}</td><td>${x.tier}</td><td>${x.materials.join(', ')}</td><td>${x.reputation_F}</td><td><code>${x.public_key}</code></td></tr>`).join('');
 const d=await j('/api/dashboard');
 const cr=Object.values(d.creator_earnings).reduce((a,b)=>a+b,0);
 $('#royalties').textContent='$'+(cr/100).toFixed(2);
 $('#units').textContent=d.units_fabricated;$('#orders').textContent=d.orders;
 $('#recent').innerHTML='<tr><th>kind</th><th>order</th><th>job</th><th>legs</th></tr>'+d.recent.slice().reverse().map(r=>
  `<tr><td>${r.kind}</td><td><code>${r.order_id||''}</code></td><td><code>${r.job_id||''}</code></td><td>${r.legs}</td></tr>`).join('');
}
async function order(){
 $('#out').textContent='ordering…';
 const r=await j('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({asset_id:$('#asset').value,qty:+$('#qty').value,grade:$('#grade').value})});
 $('#out').textContent=JSON.stringify(r,null,2);load();
}
load();
</script></body></html>"""


CREATOR_PAGE = """<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>BINGO — creator earnings</title><style>
:root{--bg:#0e1116;--card:#161b22;--ink:#e6edf3;--dim:#8b949e;--acc:#4ade80;--line:#242b36}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 system-ui,sans-serif;padding:1.5rem 1rem 4rem}main{max-width:760px;margin:0 auto}
a{color:#79c0ff}h1{font-size:1.1rem;letter-spacing:.06em;color:var(--dim);text-transform:uppercase}
.hero{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1.8rem;margin:1rem 0;text-align:center}
.hero .who{color:var(--dim);font-size:.9rem}.hero .big{font-size:2.6rem;font-weight:700;color:var(--acc);margin:.2rem 0}
.hero .sub{color:var(--dim)}section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1rem 1.2rem;margin-bottom:1.2rem}
h2{font-size:.9rem;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;margin:.2rem 0 .7rem}
table{width:100%;border-collapse:collapse;font-size:.9rem}td,th{padding:.45rem .5rem;border-top:1px solid var(--line);text-align:left}
th{color:var(--dim);border-top:none}.amt{text-align:right;color:var(--acc);font-variant-numeric:tabular-nums}
.foot{color:var(--dim);font-size:.85rem;text-align:center;margin-top:1rem}</style></head><body><main>
<h1>Project BINGO · creator earnings</h1>
<div class=hero><div class=who id=who>—</div><div class=big id=total>$0.00</div>
<div class=sub id=sub></div></div>
<section><h2>By design</h2><table id=designs></table></section>
<p class=foot>Paid automatically, at the point of fabrication, on every unit —
no invoice, no platform's mercy. This is your money.<br>
<a href="/">← the whole network</a> · <a id=stmt href="#">plain-text statement</a></p>
</main><script>
const $=s=>document.querySelector(s);
const acct=decodeURIComponent(location.pathname.replace(/^\\/creator\\//,''));
$('#stmt').href='/api/creators/'+encodeURIComponent(acct)+'/statement';
(async()=>{
 const d=await (await fetch('/api/creators/'+encodeURIComponent(acct))).json();
 $('#who').textContent=d.account;
 $('#total').textContent='$'+(d.total_cents/100).toFixed(2);
 $('#sub').textContent=d.units+' units · '+d.designs.length+' design(s) · '+d.machines+' machine(s) · '+d.orders+' order(s)';
 $('#designs').innerHTML='<tr><th>design</th><th>units</th><th class=amt>earned</th></tr>'+
  (d.designs.length?d.designs.map(x=>`<tr><td>${x.title}</td><td>${x.units}</td><td class=amt>$${(x.cents/100).toFixed(2)}</td></tr>`).join('')
   :'<tr><td colspan=3 style=color:#8b949e>no royalties yet</td></tr>');
})();
</script></body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="BINGO web/API server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8760)
    args = ap.parse_args(argv)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"BINGO network on http://{args.host}:{args.port}  ({len(AGENTS)} nodes, "
          f"{len(REG.all())} designs seeded)")
    print("try:  curl -s localhost:%d/api/assets | head" % args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
