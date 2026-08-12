# The HTTP surface

_Status: implemented (`bingo/httpguard.py`), 41/41 suites. Written 2026-08-12._

## What was there

Three servers - `bingo/server.py`, `provenance/coin_server.py`,
`provenance/transport_server.py` - each carrying its own copy of the same twenty
lines:

```python
length = int(self.headers.get("Content-Length") or 0)
raw = self.rfile.read(length)
...
self.send_header("Access-Control-Allow-Origin", "*")
```

Read literally, that is:

- **An unbounded allocation controlled by the client.** `Content-Length:
  10000000000` and the process tries to allocate ten gigabytes. A non-numeric
  value raises `ValueError` straight out of the handler. A negative one reads
  until the socket closes.
- **No authentication on endpoints that move money.** `POST /api/orders`
  fabricates a part and settles payment. `POST /api/redeem` spends a $25 coin,
  once, forever.
- **`Access-Control-Allow-Origin: *` on those same endpoints**, so any web page
  a victim visited could drive them from the victim's browser.
- **No rate limiting and no socket timeout** - one slow client per thread, held
  open as long as it likes.

The memo listed this as Tier 2 and it was accurate, but "demo-grade" undersells
`/api/orders`: it is not a read-only demo, it fabricates and pays.

## Why a base class and not a checklist

Three copies of a thing is the specific way this codebase has been bitten. Red-
team rounds 7, 8 and 9 were each a sibling verifier that had drifted from its
twin, and the fuzzer's first real find was `verify_transport` missing a
`chain_head` check `verify_passport` had carried since round 5.

So the guards are not helper functions that each server remembers to call. They
are a base class that runs them before a subclass ever sees the request, and a
test asserts that all three servers still inherit it *and* that none of them has
re-declared `do_GET`/`do_POST`, which would route around the guards entirely.

## Fail closed, and refuse rather than degrade

Three refusals, two of which happen at **startup** - because a refusal at request
time still means the process spent its life in an unsafe configuration and nobody
found out.

| | Behaviour |
|---|---|
| mutating route, no token configured | **503**, never "open because no policy was set" |
| bind off-loopback, no token | **refuses to start** |
| bind off-loopback, token but no TLS | **refuses to start** |

The third one is the least obvious and the most important: **a bearer token sent
over plaintext is worse than no token.** It is a credential handed to anyone on
the path, reusable at leisure, and it buys the operator a feeling of security
they have not got. Either pass `--tls-cert/--tls-key`, or terminate TLS in a
proxy and bind `127.0.0.1` behind it. `""` and `0.0.0.0` count as off-loopback,
because "every interface" is the case most easily typed by accident.

Also refused: a `*` CORS origin, and any token under 16 characters. A guessable
token is decoration, and decoration that reads as security is worse than none.

## Reads open, writes closed - on purpose

The asymmetry is deliberate. Document-only public verifiability is the point of
this project; a passport check or a coin validation that needed a credential
would defeat it. So `GET` stays open and unauthenticated.

Writes are the opposite: they fabricate parts and spend coins. They need a bearer
token, compared with `hmac.compare_digest` - the comparison is reachable by an
anonymous client, so a plain `==` leaks the token one character at a time to
anyone who can measure.

## The rest of the floor

- **Body**: `Content-Length` must parse, be non-negative, and be within the cap,
  all checked *before a byte is read*. `Transfer-Encoding: chunked` is refused
  (411) rather than guessed at - guessing at a framing you do not parse is how
  request smuggling starts. A body that is valid JSON but not an object is
  refused, so a bare list cannot reach a route's `.get` and raise.
- **Rate limiting**: separate budgets for reads and writes, since a write costs
  far more to serve than a read. 429 with `Retry-After`.
- **CORS**: no header at all by default. Listed origins are echoed on reads only
  and never on a mutating response, which is the drive-by order placement this
  replaces. Preflight is answered only for listed origins.
- **Headers**: `nosniff`, `no-referrer`, `no-store`, and on HTML a CSP of
  `default-src 'none'` with `frame-ancestors 'none'` (the pages are entirely
  self-contained, so this costs nothing and stops an injected `<script src>`).
  The Python version is no longer advertised - that is free reconnaissance.
- **Errors**: a route that raises returns `500 {"error": "internal error"}` and
  the server survives. Previously the exception escaped: no status, no response,
  a traceback on the operator's stderr and a dropped connection.
- **Logs**: routine client disconnects are silent. `socketserver` prints a full
  traceback for every reset peer, which on a public surface is a denial-of-
  service against the operator's own logs - anyone can fill them from outside,
  which is a good way to bury the one line that mattered.

## What this is not

**Not a substitute for a reverse proxy.** In-memory per-IP rate limiting does
nothing against a distributed source, forgets everything on restart, and is
sidestepped by anyone holding a /64 of IPv6. It stops one script from trivially
exhausting a demo node and it makes the 429 path real and tested. Anything facing
the public internet puts nginx or equivalent in front.

**Not an authorization model.** There is one token and it is all-or-nothing:
whoever holds it can place any order or redeem any coin. Per-account identity,
scopes, and an audit trail of who authorized what are not here. For a single-
operator node that is the honest shape; for a multi-tenant service it is not
enough, and the seam to extend is `HardenedHandler._authorized`.

**Not audited.** Same caveat as everything else in this repo - see §7 of the
production-gap memo.

## Still open

- No per-account identity or scopes (above).
- No structured request logging, so there is no audit trail of who called what;
  that belongs with the Tier 2 monitoring work rather than here.
- TLS is supported but no certificate lifecycle exists - no renewal, no pinning,
  no story for rotation.
- Rate limiting is per-process, so two workers behind a load balancer each get
  the full budget.
