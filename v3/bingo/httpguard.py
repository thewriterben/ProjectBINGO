"""The hardened HTTP base the three BINGO servers share.

`bingo/server.py`, `provenance/coin_server.py` and `provenance/transport_server.py`
each had their own copy of the same twenty lines: the same `_send`, the same
`Access-Control-Allow-Origin: *`, the same

    length = int(self.headers.get("Content-Length") or 0)
    raw = self.rfile.read(length)

Three copies of a thing is how this codebase has been bitten before - rounds 7,
8 and 9 of the red-team were all sibling verifiers that drifted apart, and the
fuzzer's first real find was `verify_transport` missing a check `verify_passport`
had carried since round 5. A shared base is not tidiness here; it is the specific
countermeasure to the specific failure this project keeps having.

What those twenty lines were actually exposing:

  * **Unbounded body read.** `Content-Length: 10000000000` and the process
    allocates ten gigabytes. A non-numeric one raises `ValueError` out of the
    handler. A negative one reads until the socket closes.
  * **No authentication on endpoints that move money.** `POST /api/orders`
    fabricates and settles. `POST /api/redeem` spends a $25 coin, once, forever.
  * **`Access-Control-Allow-Origin: *` on those same endpoints**, so any web page
    a victim visits could drive them from the victim's browser.
  * **No rate limiting, no socket timeout** - one slow client per thread, held
    open indefinitely.

The design rule everywhere below is the one the rest of the kernel already
follows: **fail closed, and refuse rather than degrade.** Concretely, three
refusals that happen at startup rather than at exploitation time:

  1. a mutating request with no token configured is **503**, not "allowed
     because no policy was set"
  2. binding to a non-loopback address with no token configured **refuses to
     start** - a money-moving endpoint should not reach the network by a typo
     in a `--host` flag
  3. binding off-loopback with a token but **no TLS** also refuses to start,
     because a bearer token sent in the clear is worse than no token: it is a
     credential handed to whoever is listening

What this is NOT: a substitute for a reverse proxy. In-memory per-IP rate
limiting does nothing against a botnet and forgets everything on restart. It is
the floor that makes the surface defensible, not a WAF.

Spec: `specs/HTTP-SURFACE.md`.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import ssl
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

__all__ = ["Policy", "HardenedHandler", "RateLimiter", "serve", "build_server",
           "is_loopback", "policy_from_env", "ConfigRefused"]

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class ConfigRefused(RuntimeError):
    """Raised at startup when a configuration would expose something. Deliberately
    a startup error and not a warning: a warning is a thing you scroll past."""


def is_loopback(host: str) -> bool:
    """`""` and `0.0.0.0` are NOT loopback - they are every interface, which is
    the case that matters most and the one most easily typed by accident."""
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "localhost.localdomain")


# -- policy --------------------------------------------------------------------

@dataclass
class Policy:
    """Everything adjustable, with defaults that are safe rather than convenient.

    `auth_token` gates **mutating** methods only. Reads stay open on purpose:
    document-only public verifiability is the point of this project, and a
    passport or a coin check that needed a credential would defeat it. The
    asymmetry is deliberate and worth stating - reads expose signed documents
    anyone is meant to be able to check; writes fabricate parts and spend coins.
    """
    max_body_bytes: int = 256 * 1024
    max_header_bytes: int = 16 * 1024
    read_timeout: float = 15.0            # slowloris: a thread is not free
    rate_limit: int = 120                 # requests per window, per client
    rate_window: float = 60.0
    mutating_rate_limit: int = 12         # writes are cheap to send, costly to serve
    auth_token: str | None = None
    cors_origins: tuple[str, ...] = ()    # never "*"; empty = same-origin only
    server_token: str = "bingo"           # what goes in the Server: header

    def __post_init__(self):
        if "*" in self.cors_origins:
            raise ConfigRefused(
                "cors_origins may not contain '*'. A wildcard origin plus a "
                "bearer token is a credential leak, and a wildcard origin on a "
                "mutating endpoint lets any page a victim visits drive it. "
                "List the origins you actually serve.")
        if self.auth_token is not None and len(self.auth_token) < 16:
            raise ConfigRefused(
                "auth_token is shorter than 16 characters. A token that can be "
                "guessed is decoration; generate one with "
                "`python -c \"import secrets;print(secrets.token_urlsafe(32))\"`.")


def policy_from_env(**overrides) -> Policy:
    """`$BINGO_API_TOKEN` is the supported way in. Absent means absent - it is
    never defaulted to something, because a default token is a published one."""
    tok = os.environ.get("BINGO_API_TOKEN") or None
    origins = tuple(o.strip() for o in
                    (os.environ.get("BINGO_CORS_ORIGINS") or "").split(",")
                    if o.strip())
    kw = {"auth_token": tok, "cors_origins": origins}
    kw.update(overrides)
    return Policy(**kw)


# -- rate limiting -------------------------------------------------------------

@dataclass
class RateLimiter:
    """A per-client fixed-window counter, in memory.

    Honest about its ceiling: it is per-process, forgets on restart, and keys on
    the peer address, so it is useless against a distributed source and trivially
    sidestepped by anyone with a /64 of IPv6. It exists to stop one script from
    trivially exhausting a demo node, and to make the 429 path real and tested.
    Anything facing the public internet puts a proxy in front of this.
    """
    limit: int
    window: float
    _hits: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """-> (allowed, seconds_until_reset)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            count += 1
            self._hits[key] = (start, count)
            if len(self._hits) > 10_000:          # unbounded dict = a slow leak
                cutoff = now - self.window
                for k in [k for k, (s, _) in self._hits.items() if s < cutoff]:
                    self._hits.pop(k, None)
            return count <= self.limit, max(0.0, self.window - (now - start))


# -- the handler ---------------------------------------------------------------

class HardenedHandler(BaseHTTPRequestHandler):
    """Subclass and implement `handle_get(u)` / `handle_post(u, body)`.

    Every request passes the guards below before a subclass sees it, so a new
    route cannot forget them - which is the whole reason this is a base class
    and not a set of helper functions someone remembers to call.
    """

    policy: Policy = Policy()
    reader: RateLimiter | None = None
    writer: RateLimiter | None = None
    protocol_version = "HTTP/1.1"          # so Content-Length is honoured
    server_version = "bingo"
    sys_version = ""                       # do not advertise the Python version

    # -- subclass surface --
    def handle_get(self, u):
        return self.send_json({"error": "not found"}, 404)

    def handle_post(self, u, body):
        return self.send_json({"error": "not found"}, 404)

    # -- sending --
    def _security_headers(self, ctype: str) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if ctype.startswith("text/html"):
            # the pages are self-contained: inline styles/scripts, no third-party
            # anything. Say so, so an injected <script src> cannot run.
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; img-src data:; connect-src 'self'; "
                "form-action 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("X-Frame-Options", "DENY")

    def _cors_headers(self, mutating: bool) -> None:
        """Never on a mutating response, and never a wildcard.

        A cross-origin POST that the browser is willing to send is exactly the
        drive-by order-placement this replaces. Reads are safe to share because
        they return signed documents anyone is entitled to verify."""
        if mutating or not self.policy.cors_origins:
            return
        origin = self.headers.get("Origin")
        if origin and origin in self.policy.cors_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def send_json(self, obj, code: int = 200,
                  ctype: str = "application/json", extra: dict | None = None):
        body = obj.encode() if isinstance(obj, str) else \
            json.dumps(obj, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers(ctype)
        self._cors_headers(self.command in MUTATING_METHODS)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # back-compat with the three servers' existing call sites
    _send = send_json

    # -- guards --
    def _client_key(self) -> str:
        return self.client_address[0] if self.client_address else "?"

    def _rate_ok(self, mutating: bool) -> bool:
        rl = self.writer if mutating else self.reader
        if rl is None:
            return True
        ok, reset = rl.check(self._client_key())
        if not ok:
            self.send_json({"error": "rate limited"}, 429,
                           extra={"Retry-After": str(int(reset) + 1)})
        return ok

    def _authorized(self) -> bool:
        """Fail closed: no token configured means mutating routes are CLOSED,
        not open. 'Nobody set a policy' must never read as 'anything goes' on an
        endpoint that spends money."""
        want = self.policy.auth_token
        if not want:
            self.send_json(
                {"error": "this endpoint is disabled",
                 "detail": "mutating endpoints require an API token. Set "
                           "$BINGO_API_TOKEN to enable them. Refusing to serve "
                           "a money-moving endpoint unauthenticated."}, 503)
            return False
        header = self.headers.get("Authorization") or ""
        scheme, _, given = header.partition(" ")
        if scheme.lower() != "bearer" or not given:
            self.send_json({"error": "unauthorized"}, 401,
                           extra={"WWW-Authenticate": 'Bearer realm="bingo"'})
            return False
        # constant-time: a plain == leaks the token one character at a time to
        # anyone who can measure, and this is reachable by an anonymous client
        if not hmac.compare_digest(given.strip(), want):
            self.send_json({"error": "unauthorized"}, 401)
            return False
        return True

    def _read_body(self) -> tuple[bool, dict]:
        if self.headers.get("Transfer-Encoding", "").lower().find("chunked") >= 0:
            # not implemented here, and guessing at a framing you do not parse is
            # how request smuggling starts
            self.send_json({"error": "chunked encoding not supported"}, 411)
            return False, {}
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            return True, {}
        try:
            length = int(raw_len)
        except (TypeError, ValueError):
            self.send_json({"error": "bad Content-Length"}, 400)
            return False, {}
        if length < 0:
            self.send_json({"error": "bad Content-Length"}, 400)
            return False, {}
        if length > self.policy.max_body_bytes:
            # refused BEFORE reading: the point is not to allocate it
            self.send_json({"error": "payload too large",
                            "max_bytes": self.policy.max_body_bytes}, 413)
            return False, {}
        raw = self.rfile.read(length) if length else b""
        if len(raw) != length:
            self.send_json({"error": "incomplete body"}, 400)
            return False, {}
        try:
            body = json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json({"error": "invalid JSON"}, 400)
            return False, {}
        if not isinstance(body, dict):
            # every route here expects an object; a bare list or string would
            # reach `.get` and raise inside the route instead of being refused
            self.send_json({"error": "body must be a JSON object"}, 400)
            return False, {}
        return True, body

    def _headers_sane(self) -> bool:
        total = sum(len(k) + len(v) + 4 for k, v in self.headers.items())
        if total > self.policy.max_header_bytes:
            self.send_json({"error": "headers too large"}, 431)
            return False
        return True

    # -- dispatch --
    def _dispatch(self, mutating: bool):
        if not self._headers_sane() or not self._rate_ok(mutating):
            return
        u = urlparse(self.path)
        if mutating:
            if not self._authorized():
                return
            ok, body = self._read_body()
            if not ok:
                return
            return self.handle_post(u, body)
        return self.handle_get(u)

    def _guarded(self, mutating: bool):
        try:
            self._dispatch(mutating)
        except Exception:
            # never let a traceback reach the client, and never let one kill the
            # connection silently with no status at all
            try:
                self.send_json({"error": "internal error"}, 500)
            except Exception:
                pass

    def do_GET(self):
        self._guarded(False)

    def do_HEAD(self):
        self._guarded(False)

    def do_POST(self):
        self._guarded(True)

    def do_OPTIONS(self):
        """Preflight. Answered without ever consulting auth, and without ACAO
        unless the Origin is one we actually listed."""
        origin = self.headers.get("Origin")
        allowed = bool(origin and origin in self.policy.cors_origins)
        self.send_response(204 if allowed else 403)
        if allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *a):
        pass                                  # the servers stay quiet by default

    def setup(self):
        # `self.timeout` must be set BEFORE super().setup(), which is where
        # StreamRequestHandler creates self.connection and applies it. Touching
        # self.connection first raises AttributeError inside setup(), and the
        # only symptom a client sees is the connection dropping with no response
        # at all - which is exactly how it presented.
        self.timeout = self.policy.read_timeout
        super().setup()


# -- construction --------------------------------------------------------------

class GuardedServer(ThreadingHTTPServer):
    """A client hanging up is not an incident.

    `socketserver` prints a full traceback for every dropped connection, reset
    peer and read timeout. On a public surface that is not diagnostics, it is a
    denial-of-service against the operator's own logs: anyone can fill them from
    the outside, which is a good way to bury the one line that mattered. Routine
    disconnects are silent; anything else gets one line, and still no traceback,
    because tracebacks in logs have a way of ending up in tickets.
    """

    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        import sys as _sys
        exc = _sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                            ConnectionAbortedError, TimeoutError, OSError)):
            return
        print(f"! handler error from {client_address[0]}: "
              f"{type(exc).__name__}", file=_sys.stderr)


def build_server(handler_cls, host: str, port: int, policy: Policy,
                 *, tls_cert: str | None = None, tls_key: str | None = None):
    """Bind, with the startup refusals that are the point of this module.

    These are checked here rather than at request time on purpose: an operator
    should find out that a configuration is unsafe when they start the process,
    not when someone finds it.
    """
    loopback = is_loopback(host)
    tls = bool(tls_cert and tls_key)

    if not loopback and not policy.auth_token:
        raise ConfigRefused(
            f"refusing to bind {host!r} with no API token.\n"
            f"This process exposes endpoints that fabricate parts and spend "
            f"coins. Off the loopback interface that is a public, "
            f"unauthenticated money-moving surface.\n"
            f"Set $BINGO_API_TOKEN, or bind 127.0.0.1.")
    if not loopback and not tls:
        raise ConfigRefused(
            f"refusing to bind {host!r} without TLS.\n"
            f"A bearer token sent over plaintext is worse than no token - it is "
            f"a credential handed to anyone on the path, reusable at leisure.\n"
            f"Pass --tls-cert and --tls-key, or terminate TLS in a proxy and "
            f"bind 127.0.0.1 behind it.")

    cls = type(handler_cls.__name__, (handler_cls,), {
        "policy": policy,
        "reader": RateLimiter(policy.rate_limit, policy.rate_window),
        "writer": RateLimiter(policy.mutating_rate_limit, policy.rate_window),
    })
    srv = GuardedServer((host, port), cls)
    if tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(tls_cert, tls_key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    return srv


def add_server_args(ap, *, default_port: int) -> None:
    """The same flags on all three servers, so one is never hardened and another
    left behind."""
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=default_port)
    ap.add_argument("--tls-cert", default=None,
                    help="PEM certificate; required to bind off loopback")
    ap.add_argument("--tls-key", default=None, help="PEM private key")
    ap.add_argument("--cors-origin", action="append", default=[],
                    help="allow this exact origin on READ endpoints (repeatable). "
                         "'*' is refused.")
    ap.add_argument("--max-body-kb", type=int, default=256)
    ap.add_argument("--rate-limit", type=int, default=120,
                    help="reads per minute per client")


def serve(handler_cls, args, *, name: str) -> int:
    policy = policy_from_env(
        cors_origins=tuple(args.cors_origin),
        max_body_bytes=args.max_body_kb * 1024,
        rate_limit=args.rate_limit)
    try:
        srv = build_server(handler_cls, args.host, args.port, policy,
                           tls_cert=args.tls_cert, tls_key=args.tls_key)
    except ConfigRefused as e:
        print(f"x refusing to start:\n{e}")
        return 2
    scheme = "https" if (args.tls_cert and args.tls_key) else "http"
    auth = "token required for writes" if policy.auth_token else \
        "WRITES DISABLED (no $BINGO_API_TOKEN)"
    print(f"-> {name} on {scheme}://{args.host}:{args.port}  [{auth}]")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        srv.server_close()
    return 0
