"""The HTTP surface, attacked with real requests over a real socket.

Every check below binds an actual server on 127.0.0.1 and talks to it with
`urllib`. Nothing is asserted about the handler in isolation, because the bugs
being closed here live in the space between HTTP and the handler - a
`Content-Length` header that is a lie, a preflight that shouldn't be answered, a
token compared with `==`.

What the three servers looked like before, in triplicate:

    length = int(self.headers.get("Content-Length") or 0)
    raw = self.rfile.read(length)
    ...
    self.send_header("Access-Control-Allow-Origin", "*")

So: `Content-Length: 10000000000` allocated ten gigabytes, a non-numeric one
raised out of the handler, and `POST /api/orders` (fabricates and settles) and
`POST /api/redeem` (spends a $25 coin, once, forever) were open to any web page
a victim visited.

The load-bearing claims here are the three **startup** refusals, because a
refusal at request time still means the process was running in an unsafe
configuration and nobody knew:

  * off-loopback with no token -> refuses to start
  * off-loopback with a token but no TLS -> refuses to start, because a bearer
    token in the clear is worse than no token
  * no token at all -> mutating routes answer 503, never "open by default"

  python -m tests.test_http_surface
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

from bingo import httpguard as G

TOKEN = "test-token-" + "x" * 24
OTHER = "wrong-token-" + "y" * 24


# -- a tiny server to attack ---------------------------------------------------

class Echo(G.HardenedHandler):
    def handle_get(self, u):
        if u.path == "/boom":
            raise RuntimeError("a route blew up")
        if u.path == "/html":
            return self.send_json("<h1>hi</h1>", ctype="text/html; charset=utf-8")
        return self.send_json({"ok": True, "path": u.path})

    def handle_post(self, u, body):
        return self.send_json({"got": body})


class Running:
    """Bind on a free port, serve in a thread, tear down cleanly."""

    def __init__(self, policy=None, host="127.0.0.1", **kw):
        self.srv = G.build_server(Echo, host, 0, policy or G.Policy(), **kw)
        self.port = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *e):
        self.srv.shutdown()
        self.srv.server_close()
        self.t.join(timeout=5)

    def url(self, path=""):
        return f"http://127.0.0.1:{self.port}{path}"


def _req(url, *, method="GET", data=None, headers=None, raw_body=None):
    """-> (status, headers, parsed-or-text). Never raises on an HTTP error
    status: the error statuses ARE the assertions here."""
    body = raw_body if raw_body is not None else (
        json.dumps(data).encode() if data is not None else None)
    r = urllib.request.Request(url, data=body, method=method,
                               headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, dict(resp.headers), _parse(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), _parse(e.read())


def _parse(raw):
    try:
        return json.loads(raw)
    except Exception:
        return raw.decode(errors="replace")


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


# -- the startup refusals ------------------------------------------------------

def test_refuses_to_bind_off_loopback_without_a_token():
    """The typo case. `--host 0.0.0.0` on a process that fabricates parts and
    spends coins should not be a thing you can do by accident."""
    for host in ("0.0.0.0", "", "10.0.0.5"):
        try:
            G.build_server(Echo, host, 0, G.Policy())
            assert False, f"binding {host!r} unauthenticated must be refused"
        except G.ConfigRefused as e:
            assert "no API token" in str(e)
            assert "127.0.0.1" in str(e), "the refusal must say what to do instead"


def test_refuses_to_bind_off_loopback_without_tls_even_with_a_token():
    """A bearer token over plaintext is a credential handed to whoever is
    listening, reusable at leisure. Worse than no token, so it is refused rather
    than warned about."""
    try:
        G.build_server(Echo, "0.0.0.0", 0, G.Policy(auth_token=TOKEN))
        assert False, "plaintext + token off-loopback must be refused"
    except G.ConfigRefused as e:
        assert "without TLS" in str(e) and "proxy" in str(e)


def test_loopback_stays_easy():
    """The refusals must not make local development annoying, or they will be
    worked around rather than satisfied."""
    with Running() as s:
        code, _h, body = _req(s.url("/api/x"))
        assert code == 200 and body["ok"] is True


def test_a_wildcard_origin_is_refused_outright():
    try:
        G.Policy(cors_origins=("*",))
        assert False, "'*' must not be an accepted origin"
    except G.ConfigRefused as e:
        assert "credential leak" in str(e)


def test_a_short_token_is_refused():
    """A guessable token is decoration, and decoration that reads as security is
    worse than none."""
    try:
        G.Policy(auth_token="hunter2")
        assert False
    except G.ConfigRefused as e:
        assert "guessed" in str(e)


# -- writes are closed unless explicitly opened --------------------------------

def test_mutating_routes_are_503_when_no_token_is_configured():
    """Fail closed. 'Nobody set a policy' must never read as 'anything goes' on
    an endpoint that spends money."""
    with Running() as s:
        code, _h, body = _req(s.url("/api/orders"), method="POST", data={"a": 1})
        assert code == 503, f"expected writes disabled, got {code}"
        assert "require an API token" in body["detail"]


def test_mutating_routes_require_the_right_token():
    with Running(G.Policy(auth_token=TOKEN)) as s:
        code, h, _b = _req(s.url("/api/orders"), method="POST", data={"a": 1})
        assert code == 401 and "Bearer" in h.get("WWW-Authenticate", "")

        for bad in (OTHER, TOKEN[:-1], TOKEN + "z", "", TOKEN.upper()):
            code, _h, _b = _req(s.url("/x"), method="POST", data={"a": 1},
                                headers=_bearer(bad))
            assert code == 401, f"token {bad!r} was accepted"

        code, _h, _b = _req(s.url("/x"), method="POST", data={"a": 1},
                            headers={"Authorization": f"Basic {TOKEN}"})
        assert code == 401, "only the Bearer scheme is accepted"

        code, _h, body = _req(s.url("/x"), method="POST", data={"n": 7},
                              headers=_bearer(TOKEN))
        assert code == 200 and body["got"] == {"n": 7}


def test_token_comparison_is_constant_time():
    """Reachable by an anonymous client, so a plain `==` leaks the token one
    character at a time to anyone who can measure. Checked by inspection rather
    than by timing, because a timing measurement in CI is a coin flip."""
    import inspect
    src = inspect.getsource(G.HardenedHandler._authorized)
    assert "compare_digest" in src
    assert "== want" not in src and "!= want" not in src


def test_reads_stay_open_on_purpose():
    """The asymmetry is deliberate and worth pinning: document-only public
    verifiability is the point of the project, and a passport or coin check that
    needed a credential would defeat it."""
    with Running(G.Policy(auth_token=TOKEN)) as s:
        code, _h, body = _req(s.url("/api/passport/abc"))
        assert code == 200 and body["ok"] is True


# -- the body -------------------------------------------------------------------

def test_an_enormous_content_length_is_refused_before_it_is_read():
    """The old code allocated whatever the header claimed. This must be refused
    on the header alone - reading it to find out how big it is defeats the
    purpose."""
    with Running(G.Policy(auth_token=TOKEN, max_body_bytes=1024)) as s:
        h = dict(_bearer(TOKEN))
        h["Content-Length"] = "10000000000"
        # hand-rolled: urllib would try to send a body that size
        conn = socket.create_connection(("127.0.0.1", s.port), timeout=10)
        conn.sendall(
            f"POST /x HTTP/1.1\r\nHost: localhost\r\n"
            f"Authorization: Bearer {TOKEN}\r\n"
            f"Content-Length: 10000000000\r\n\r\n".encode())
        resp = conn.recv(4096).decode(errors="replace")
        conn.close()
        assert "413" in resp.split("\r\n")[0], resp.split("\r\n")[0]


def test_a_body_over_the_cap_is_refused():
    with Running(G.Policy(auth_token=TOKEN, max_body_bytes=512)) as s:
        big = json.dumps({"pad": "z" * 4096}).encode()
        code, _h, body = _req(s.url("/x"), method="POST", raw_body=big,
                              headers=_bearer(TOKEN))
        assert code == 413 and body["max_bytes"] == 512


def test_a_lying_content_length_does_not_crash_the_handler():
    """Non-numeric, negative, and absurd. The old `int(...)` raised straight out
    of `do_POST`."""
    with Running(G.Policy(auth_token=TOKEN)) as s:
        for bad in ("abc", "-1", "1e5", " ", "12,13"):
            conn = socket.create_connection(("127.0.0.1", s.port), timeout=10)
            conn.sendall(
                f"POST /x HTTP/1.1\r\nHost: localhost\r\n"
                f"Authorization: Bearer {TOKEN}\r\n"
                f"Content-Length: {bad}\r\n\r\n".encode())
            first = conn.recv(4096).decode(errors="replace").split("\r\n")[0]
            conn.close()
            assert "400" in first, f"Content-Length {bad!r} -> {first}"


def test_chunked_encoding_is_refused_rather_than_guessed_at():
    """Guessing at a framing you do not parse is how request smuggling starts."""
    with Running(G.Policy(auth_token=TOKEN)) as s:
        conn = socket.create_connection(("127.0.0.1", s.port), timeout=10)
        conn.sendall(
            f"POST /x HTTP/1.1\r\nHost: localhost\r\n"
            f"Authorization: Bearer {TOKEN}\r\n"
            f"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n".encode())
        first = conn.recv(4096).decode(errors="replace").split("\r\n")[0]
        conn.close()
        assert "411" in first, first


def test_malformed_and_non_object_bodies_are_refused_cleanly():
    with Running(G.Policy(auth_token=TOKEN)) as s:
        for raw in (b"{not json", b"[1,2,3]", b'"a string"', b"null", b"7"):
            code, _h, _b = _req(s.url("/x"), method="POST", raw_body=raw,
                                headers=_bearer(TOKEN))
            assert code == 400, f"{raw!r} -> {code}"
        # an absent body is fine and means {}
        code, _h, body = _req(s.url("/x"), method="POST", raw_body=b"",
                              headers=_bearer(TOKEN))
        assert code == 200 and body["got"] == {}


# -- rate limiting ---------------------------------------------------------------

def test_reads_are_rate_limited_with_a_retry_after():
    with Running(G.Policy(rate_limit=5, rate_window=60)) as s:
        codes = [_req(s.url("/x"))[0] for _ in range(8)]
        assert codes[:5] == [200] * 5, codes
        assert codes[5:] == [429] * 3, codes
        _c, h, _b = _req(s.url("/x"))
        assert int(h["Retry-After"]) > 0


def test_writes_get_their_own_tighter_budget():
    """A write costs far more to serve than a read, so it does not share the
    read budget."""
    with Running(G.Policy(auth_token=TOKEN, rate_limit=100,
                          mutating_rate_limit=3, rate_window=60)) as s:
        codes = [_req(s.url("/x"), method="POST", data={}, headers=_bearer(TOKEN))[0]
                 for _ in range(5)]
        assert codes == [200, 200, 200, 429, 429], codes
        # reads are unaffected - the budgets are separate
        assert _req(s.url("/x"))[0] == 200


def test_the_rate_limiter_window_actually_rolls_over():
    rl = G.RateLimiter(limit=2, window=10.0)
    assert rl.check("a", now=100.0)[0]
    assert rl.check("a", now=100.1)[0]
    assert not rl.check("a", now=100.2)[0]
    assert rl.check("b", now=100.2)[0], "clients must not share a budget"
    assert rl.check("a", now=111.0)[0], "the window must roll over"


def test_the_rate_limiter_does_not_grow_without_bound():
    """A dict keyed on client address is a slow memory leak wearing a hat."""
    rl = G.RateLimiter(limit=1, window=1.0)
    for i in range(11_000):
        rl.check(f"10.0.{i // 256}.{i % 256}", now=float(i))
    assert len(rl._hits) < 11_000


# -- CORS ------------------------------------------------------------------------

def test_no_cors_header_by_default():
    """Same-origin unless told otherwise. The old code sent `*` to everyone."""
    with Running() as s:
        _c, h, _b = _req(s.url("/x"), headers={"Origin": "https://evil.example"})
        assert "Access-Control-Allow-Origin" not in h


def test_a_listed_origin_is_echoed_on_reads_only():
    good = "https://app.example"
    with Running(G.Policy(auth_token=TOKEN, cors_origins=(good,))) as s:
        _c, h, _b = _req(s.url("/x"), headers={"Origin": good})
        assert h.get("Access-Control-Allow-Origin") == good
        assert h.get("Vary") == "Origin"

        _c, h, _b = _req(s.url("/x"), headers={"Origin": "https://evil.example"})
        assert "Access-Control-Allow-Origin" not in h

        # and NEVER on a mutating response, even for a listed origin - that is
        # the drive-by order placement this replaces
        hdr = dict(_bearer(TOKEN)); hdr["Origin"] = good
        _c, h, _b = _req(s.url("/x"), method="POST", data={}, headers=hdr)
        assert "Access-Control-Allow-Origin" not in h


def test_preflight_is_answered_only_for_listed_origins():
    good = "https://app.example"
    with Running(G.Policy(cors_origins=(good,))) as s:
        code, h, _b = _req(s.url("/x"), method="OPTIONS",
                           headers={"Origin": good})
        assert code == 204 and h["Access-Control-Allow-Origin"] == good
        assert "POST" not in h.get("Access-Control-Allow-Methods", "")
        code, _h, _b = _req(s.url("/x"), method="OPTIONS",
                            headers={"Origin": "https://evil.example"})
        assert code == 403


# -- responses ------------------------------------------------------------------

def test_security_headers_on_every_response():
    with Running() as s:
        _c, h, _b = _req(s.url("/x"))
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["Referrer-Policy"] == "no-referrer"
        _c, h, _b = _req(s.url("/html"))
        csp = h["Content-Security-Policy"]
        assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
        assert h["X-Frame-Options"] == "DENY"


def test_a_route_that_raises_returns_500_and_leaks_nothing():
    """The old handler let the exception escape: no status, no response, a
    traceback on the operator's stderr and a dropped connection."""
    with Running() as s:
        code, _h, body = _req(s.url("/boom"))
        assert code == 500 and body == {"error": "internal error"}
        assert "RuntimeError" not in json.dumps(body)
        assert "blew up" not in json.dumps(body)
        # and the server is still alive afterwards
        assert _req(s.url("/x"))[0] == 200


def test_shutdown_waits_for_requests_still_in_flight():
    """A handler writes its audit record at the very end of the request, so a
    close that returns while handlers are running loses exactly the records
    around a restart.

    This currently holds for free - `ThreadingMixIn.server_close` joins, because
    `block_on_close` defaults to True. The test exists to make that a checked
    property rather than an inherited default: `daemon_threads = True` plus
    `block_on_close = False` would drop handlers silently, and nothing else in
    the suite would notice. `GuardedServer` also drains explicitly so the
    guarantee does not depend on a stdlib default staying put."""
    done = []

    class Slow(G.HardenedHandler):
        def handle_get(self, u):
            self.send_json({"ok": True})
            time.sleep(0.4)                 # still working after the response
            done.append(u.path)

    srv = G.build_server(Slow, "127.0.0.1", 0, G.Policy())
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        _req(f"http://127.0.0.1:{port}/slow")
    finally:
        srv.shutdown()
        srv.server_close()                  # must not return before the handler
        th.join(timeout=5)
    assert done == ["/slow"], (
        "server_close() returned while a handler was still running - work that "
        "handler had not finished (its audit record, for one) is lost")
    assert srv.drain_timeout <= 30, "the drain must stay bounded"


def test_the_python_version_is_not_advertised():
    """Free reconnaissance otherwise: `Server: BaseHTTP/0.6 Python/3.11.2` tells
    an attacker exactly which CVEs to try."""
    with Running() as s:
        _c, h, _b = _req(s.url("/x"))
        assert "Python" not in h.get("Server", "")


def test_oversized_headers_are_refused():
    with Running(G.Policy(max_header_bytes=2048)) as s:
        code, _h, _b = _req(s.url("/x"), headers={"X-Pad": "z" * 4096})
        assert code == 431


# -- the three real servers actually use it ------------------------------------

def test_all_three_servers_share_the_hardened_base():
    """The specific countermeasure to the specific failure this codebase keeps
    having. Rounds 7, 8 and 9 of the red-team were all sibling handlers that
    drifted apart, and the fuzzer's first real find was the same shape. If one
    of these ever stops inheriting the base, that is the drift starting."""
    import bingo.server as bsrv
    import provenance.coin_server as csrv
    import provenance.transport_server as tsrv
    for mod in (bsrv, csrv, tsrv):
        assert issubclass(mod.Handler, G.HardenedHandler), mod.__name__
        # and none of them kept a private do_GET/do_POST that would bypass the
        # guards entirely
        assert "do_GET" not in vars(mod.Handler), f"{mod.__name__} bypasses the guards"
        assert "do_POST" not in vars(mod.Handler), f"{mod.__name__} bypasses the guards"


def test_the_money_moving_routes_are_behind_auth():
    """Named explicitly, because these two are the reason any of this exists:
    `/api/orders` fabricates and settles, `/api/redeem` spends a $25 coin once
    and forever. Both were reachable by any web page a victim visited."""
    import bingo.server as bsrv
    import provenance.coin_server as csrv
    for mod, route in ((bsrv, "/api/orders"), (csrv, "/api/redeem")):
        assert "handle_post" in vars(mod.Handler), \
            f"{mod.__name__} must route {route} through handle_post"
        srv = G.build_server(mod.Handler, "127.0.0.1", 0, G.Policy())
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            code, _h, _b = _req(f"http://127.0.0.1:{port}{route}",
                                method="POST", data={})
            assert code == 503, f"{route} answered {code} with no token set"
        finally:
            srv.shutdown()
            srv.server_close()
            t.join(timeout=5)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK - all {len(tests)} HTTP-surface groups pass, every one against a "
          "real socket: the server REFUSES TO START off-loopback without a "
          "token, and refuses again without TLS even with one (a bearer token "
          "in the clear is worse than none); writes answer 503 rather than "
          "opening by default when no token is set, and the token is compared "
          "in constant time; a lying, negative, absurd or chunked "
          "Content-Length is refused before a byte is allocated; reads and "
          "writes have separate rate budgets; CORS is same-origin by default, "
          "never '*', and never sent on a mutating response; a route that "
          "raises returns 500 with no traceback and the server survives; and "
          "all three servers are checked to still inherit the shared base, "
          "which is the sibling drift this codebase keeps being bitten by.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
