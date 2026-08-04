"""DGD coin validation & redemption — the scan-to-redeem front end + API.

For https://digitalgold.co/. Serves the page a recipient lands on when they scan
a coin's QR, and the API behind it:

  GET  /                    the redemption page (or /redeem?c=<payload>)
  GET  /redeem              same page (QR points here with ?c=<credential>)
  GET  /api/coin?c=<pl>     validate: authentic? what's the credit? redeemed yet?
  POST /api/redeem          {c, account} → redeem the $25 once

  python -m provenance.coin_server        # http://127.0.0.1:8770

Authenticity is checked BOTH client-side (Ed25519 in the browser, instant and
offline) and server-side at redemption (authoritative). Single-use is enforced
server-side by the RedemptionRegistry — a copied QR can pass authenticity and
still be refused because the serial is already spent.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from bingo.models import now_iso
from .passport import Actor, CutPassport
from .coin import (mint_coin, qr_payload, qr_url, parse_qr, verify_credential,
                   RedemptionRegistry, CoinError, new_secret)

_lock = threading.Lock()
CREDIT = 2500


def _coin_passport(serial, issuer):
    p = CutPassport(subject={"product": "DGD promo coin", "serial": serial})
    p.attest(issuer, "FINISH", {"serial": serial, "credit_cents": CREDIT},
             ts="2026-08-03T22:00:00Z")
    return p.to_dict()["chain_head"]


# In production these keys live in DGD's custody; here they're deterministic so
# the demo is reproducible. THE ISSUER PUBKEY BELOW is what the page trusts.
ISSUER = Actor.create("dgd", "Digital Gold Foundation", "issuer", "acct:dgd:foundation")
VALIDATOR = Actor.create("dgd-validator", "DGD Validation", "validator", "acct:dgd:validator")
REGISTRY = RedemptionRegistry(VALIDATOR, trusted_issuer_pubkey=ISSUER.pubkey_hex)

# genuine samples + one counterfeit, for the demo buttons. 0001 is code-less so
# the standalone page preview is clickable end-to-end; 0002 carries a scratch-off
# code (its code is printed at startup) so the physical anti-copy is testable too.
_SAMPLES = {}
_SECRETS = {}
_SAMPLES["DGD-2026-0001"] = mint_coin(
    ISSUER, serial="DGD-2026-0001",
    passport_head=_coin_passport("DGD-2026-0001", ISSUER), credit_cents=CREDIT)
_SECRETS["DGD-2026-0002"] = new_secret()
_SAMPLES["DGD-2026-0002"] = mint_coin(
    ISSUER, serial="DGD-2026-0002",
    passport_head=_coin_passport("DGD-2026-0002", ISSUER), credit_cents=CREDIT,
    secret=_SECRETS["DGD-2026-0002"])
_FAKE = Actor.create("counterfeiter", "Counterfeiter", "issuer", "acct:dgd:foundation")
_SAMPLE_COUNTERFEIT = mint_coin(_FAKE, serial="DGD-2026-9999",
                                passport_head=_coin_passport("DGD-2026-9999", _FAKE))


def _validate(payload: str) -> dict:
    try:
        cred = parse_qr(payload)
    except CoinError as e:
        return {"genuine": False, "why": str(e)}
    ok, why = verify_credential(cred, ISSUER.pubkey_hex)
    return {"genuine": ok, "why": why, "serial": cred["serial"],
            "credit_cents": cred["credit_cents"], "passport_head": cred["passport_head"],
            "needs_code": bool(cred.get("secret_hash")),
            "status": REGISTRY.status(cred["serial"])}


def _redeem(payload: str, account: str, secret: str = "") -> dict:
    account = account or "acct:holder:web"
    try:
        cred = parse_qr(payload)
    except CoinError as e:
        return {"ok": False, "reason": str(e)}
    with _lock:
        try:
            rec = REGISTRY.redeem(cred, account, ts=now_iso(), secret=secret or None)
        except CoinError as e:
            return {"ok": False, "reason": str(e),
                    "status": REGISTRY.status(cred["serial"])}
    return {"ok": True, "credited_cents": rec["credit_cents"], "to": rec["to"],
            "status": "REDEEMED",
            "balance_cents": REGISTRY.credits.get(account, 0)}


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
        if u.path in ("/", "/redeem", "/index.html"):
            return self._send(PAGE, ctype="text/html; charset=utf-8")
        if u.path == "/api/coin":
            c = (parse_qs(u.query).get("c") or [""])[0]
            return self._send(_validate(c))
        return self._send({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send({"error": "invalid JSON"}, 400)
        if u.path == "/api/redeem":
            return self._send(_redeem(body.get("c", ""), body.get("account", ""),
                                      body.get("secret", "")))
        return self._send({"error": "not found"}, 404)


def _page() -> str:
    return _PAGE_TMPL.format(
        issuer_pubkey=ISSUER.pubkey_hex,
        sample_ok=qr_payload(_SAMPLES["DGD-2026-0001"]),
        sample_bad=qr_payload(_SAMPLE_COUNTERFEIT))


_PAGE_TMPL = """<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Digital Gold — validate & redeem</title><style>
:root{{--bg:#0b0c0f;--card:#15171d;--ink:#f4efe3;--dim:#9a927f;--gold:#d4af37;--line:#262a33;--ok:#4ade80;--bad:#f8686f}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#1a1710,#0b0c0f);color:var(--ink);
font:16px/1.55 system-ui,sans-serif;padding:1.5rem 1rem 4rem;min-height:100vh}}
main{{max-width:440px;margin:0 auto}}
.brand{{text-align:center;letter-spacing:.28em;text-transform:uppercase;font-size:.72rem;color:var(--gold);font-weight:700}}
.brand b{{display:block;font-size:1.5rem;letter-spacing:.12em;color:var(--ink);margin-top:.2rem}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:1.6rem;margin:1.2rem 0;box-shadow:0 20px 60px rgba(0,0,0,.4)}}
.coin{{text-align:center}}.disc{{width:120px;height:120px;border-radius:50%;margin:.2rem auto 1rem;
background:radial-gradient(circle at 38% 32%,#f5e2a0,#d4af37 55%,#9c7c1e);box-shadow:0 6px 24px rgba(212,175,55,.35),inset 0 0 0 6px rgba(0,0,0,.08);
display:flex;align-items:center;justify-content:center;color:#5a4713;font-weight:800;letter-spacing:.1em}}
.amt{{font-size:2.4rem;font-weight:800;color:var(--gold)}}.amt small{{font-size:1rem;color:var(--dim);font-weight:600}}
.serial{{color:var(--dim);font-family:ui-monospace,monospace;font-size:.82rem;margin-top:.2rem}}
.badge{{display:inline-flex;gap:.4rem;align-items:center;margin:.8rem 0;padding:.35rem .8rem;border-radius:99px;font-weight:700;font-size:.85rem}}
.badge.ok{{background:rgba(74,222,128,.12);color:var(--ok);border:1px solid rgba(74,222,128,.35)}}
.badge.bad{{background:rgba(248,104,111,.12);color:var(--bad);border:1px solid rgba(248,104,111,.4)}}
.badge.spent{{background:rgba(154,146,127,.12);color:var(--dim);border:1px solid var(--line)}}
button{{width:100%;background:linear-gradient(180deg,#e6c14e,#c99a24);color:#2a2107;border:0;border-radius:12px;padding:.9rem;font-weight:800;font-size:1rem;cursor:pointer;letter-spacing:.02em}}
button:disabled{{filter:grayscale(1);opacity:.5;cursor:not-allowed}}
.muted{{color:var(--dim);font-size:.82rem;text-align:center;margin-top:.8rem;line-height:1.5}}
input{{width:100%;background:#0d0f13;color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:.7rem;font:inherit;margin:.4rem 0}}
.row{{display:flex;gap:.5rem}}.row button{{background:#22252d;color:var(--ink);font-weight:600;font-size:.82rem}}
.result{{text-align:center;margin-top:1rem;font-weight:700}}.result.ok{{color:var(--ok)}}.result.bad{{color:var(--bad)}}
a{{color:var(--gold)}}.chain{{font-family:ui-monospace,monospace;font-size:.68rem;color:var(--dim);word-break:break-all;margin-top:.3rem}}
.demo{{background:#221c0c;border:1px dashed var(--gold);border-radius:10px;padding:.5rem .7rem;font-size:.74rem;color:var(--gold);text-align:center;margin-bottom:1rem}}
</style></head><body><main>
<div class=brand>Digital Gold<b>Coin Validation</b></div>
<div id=demo class=demo style=display:none>DEMO — no backend reachable; redemption is simulated (resets on reload)</div>

<div class=card id=card>
  <div class=coin>
    <div class=disc>DGD</div>
    <div class=amt>$<span id=amt>25</span> <small>validation credits</small></div>
    <div class=serial id=serial>—</div>
    <div id=badge class="badge spent">awaiting a coin…</div>
    <div class=chain id=chain></div>
  </div>
  <input id=code placeholder="scratch-off code from the coin" style=display:none autocomplete=off oninput="$('#redeem').disabled=!(GENUINE&&(!NEEDS_CODE||this.value.trim()))">
  <button id=redeem disabled onclick=redeem()>Redeem $25</button>
  <div class=result id=result></div>
</div>

<div class=card>
  <div class=muted>Scan a coin's QR with your phone camera — it opens this page.
  Or paste the code from the coin:</div>
  <input id=paste placeholder="DGD1:… (paste coin code)">
  <div class=row><button onclick=useInput()>Validate</button>
  <button onclick="load(SAMPLE_OK)">Try a genuine coin</button>
  <button onclick="load(SAMPLE_BAD)">Try a fake</button></div>
</div>
<div class=muted>Each coin is worth $25 once. Authenticity is checked in your browser
with the issuer's public key; the credit can only be redeemed a single time.</div>

<script>
const ISSUER_PUBKEY="{issuer_pubkey}";
const SAMPLE_OK="{sample_ok}", SAMPLE_BAD="{sample_bad}";
const $=s=>document.querySelector(s);
let CURRENT=null, GENUINE=false, NEEDS_CODE=false, DEMO=false, demoSpent={{}};

function hexToBytes(h){{const a=new Uint8Array(h.length/2);for(let i=0;i<a.length;i++)a[i]=parseInt(h.substr(i*2,2),16);return a;}}
function b64urlToStr(b){{b=b.replace(/-/g,'+').replace(/_/g,'/');return atob(b);}}
function parsePayload(p){{if(!p.startsWith('DGD1:'))throw'not a DGD coin';const c=JSON.parse(b64urlToStr(p.slice(5)));
  return {{serial:c.s,passport_head:c.p,credit_cents:c.c,issuer:c.i,secret_hash:c.h||'',sig:c.sig,pubkey:c.k}};}}
function credBody(c){{return JSON.stringify({{credit_cents:c.credit_cents,issuer:c.issuer,passport_head:c.passport_head,schema:"bingo/coin-credential/0.1",secret_hash:c.secret_hash||'',serial:c.serial}});}}

async function verifyClient(c){{
  try{{
    const key=await crypto.subtle.importKey("raw",hexToBytes(ISSUER_PUBKEY),{{name:"Ed25519"}},false,["verify"]);
    return await crypto.subtle.verify({{name:"Ed25519"}},key,hexToBytes(c.sig),new TextEncoder().encode(credBody(c)));
  }}catch(e){{return null;}}   // WebCrypto Ed25519 unavailable → fall back to server
}}

async function load(payload){{
  let c; try{{c=parsePayload(payload);}}catch(e){{show(null,false,'unreadable code');return;}}
  CURRENT=payload; NEEDS_CODE=!!c.secret_hash;
  $('#amt').textContent=(c.credit_cents/100).toFixed(0);
  $('#serial').textContent=c.serial;
  $('#chain').textContent='provenance '+c.passport_head.slice(0,24)+'…';
  let ok=await verifyClient(c);
  let status='VALID';
  // confirm with server (authoritative) + get redemption status
  try{{
    const r=await fetch(API('/api/coin?c='+encodeURIComponent(payload)));
    const j=await r.json(); if(ok===null)ok=j.genuine; status=j.status||'VALID';
  }}catch(e){{DEMO=true;$('#demo').style.display='block'; if(ok===null)ok=false; if(demoSpent[c.serial])status='REDEEMED';}}
  GENUINE=!!ok;
  show(c,GENUINE,status);
}}
function show(c,genuine,status){{
  const b=$('#badge'), rd=$('#redeem'); $('#result').textContent='';
  if(!c){{b.className='badge bad';b.textContent='✕ '+status;rd.disabled=true;return;}}
  if(!genuine){{b.className='badge bad';b.textContent='✕ Counterfeit — not issued by DGD';rd.disabled=true;return;}}
  if(status==='REDEEMED'){{b.className='badge spent';b.textContent='● Already redeemed';rd.disabled=true;$('#code').style.display='none';return;}}
  b.className='badge ok';b.textContent='✓ Genuine DGD coin';
  const codeEl=$('#code');
  if(NEEDS_CODE){{codeEl.style.display='block';rd.disabled=!codeEl.value.trim();}}
  else{{codeEl.style.display='none';rd.disabled=false;}}
}}
async function redeem(){{
  if(!CURRENT||!GENUINE)return; $('#redeem').disabled=true; $('#result').textContent='Redeeming…';
  const code=$('#code').value.trim();
  if(DEMO){{const c=parsePayload(CURRENT); if(demoSpent[c.serial]){{done(false,'already redeemed — copied QR');}}
    else if(NEEDS_CODE&&!code){{done(false,'enter the scratch-off code');}}
    else{{demoSpent[c.serial]=1;done(true,25);}} return;}}
  try{{
    const r=await fetch(API('/api/redeem'),{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{c:CURRENT,account:'acct:holder:web',secret:code}})}});
    const j=await r.json();
    if(j.ok)done(true,j.credited_cents/100); else done(false,j.reason||'refused');
  }}catch(e){{done(false,'network error');}}
}}
function done(ok,v){{
  const r=$('#result'),b=$('#badge');
  if(ok){{r.className='result ok';r.textContent='✓ $'+Number(v).toFixed(0)+' in validation credits redeemed';
    b.className='badge spent';b.textContent='● Redeemed';}}
  else{{r.className='result bad';r.textContent='✕ '+v;$('#redeem').disabled=true;
    b.className='badge spent';b.textContent='● '+String(v).includes('redeemed')?'● Already redeemed':'● Not redeemable';}}
}}
function API(p){{return p;}}   // same-origin; point at digitalgold.co's API in prod
function useInput(){{const v=$('#paste').value.trim(); if(v)load(v);}}
// auto-load from ?c= (what the QR opens)
const q=new URLSearchParams(location.search).get('c');
if(q)load(decodeURIComponent(q));
</script></body></html>"""

PAGE = _page()


def main(argv=None):
    ap = argparse.ArgumentParser(description="DGD coin validation/redemption server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args(argv)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"DGD coin validation on http://{args.host}:{args.port}")
    print(f"  issuer pubkey: {ISSUER.pubkey_hex[:16]}…")
    print(f"  demo coin (no code): /redeem?c={qr_payload(_SAMPLES['DGD-2026-0001'])[:36]}…")
    print(f"  demo coin (scratch-off): serial DGD-2026-0002, code {_SECRETS['DGD-2026-0002']}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
