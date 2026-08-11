"""A faithful, offline Stripe stand-in for the Transfers API — enough of the real
contract that `bingo.payout.StripeConnectRail` runs against it UNCHANGED and the
only thing that differs between this and live Stripe is the base URL and the key.

What it honors (the parts the payout safety machinery actually depends on):

  * `POST /v1/transfers`, `application/x-www-form-urlencoded`, requires
    `Authorization: Bearer <key>` (401 without it — proves fail-closed).
  * The **`Idempotency-Key` header**: the same key replays the SAME transfer id
    and never creates a second transfer — exactly Stripe's guarantee, and the
    reason a retry (ours or Stripe's) can't double-pay. A DIFFERENT amount reused
    under the same key is a 400 (Stripe rejects idempotent-key/param mismatch).
  * `GET /v1/transfers/<id>` for reconciliation against the provider's own record.
  * A validation 400 for a non-positive/absent amount (terminal, like Stripe).
  * A `fail_times=N` knob that returns HTTP 500 the first N calls to a given key
    before succeeding — to exercise the 5xx→PENDING→retry path with a REAL server,
    proving the retry lands on the same idempotency key and still moves money once.

This is stdlib `http.server` only. It is a TEST DOUBLE — no real money, no real
auth — but it is faithful where faithfulness is load-bearing for the money proof.
"""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _State:
    """Shared, lock-guarded server state: the idempotency store and the flaky knob."""
    def __init__(self, fail_times: int = 0):
        self.lock = threading.Lock()
        self.by_idem: dict[str, dict] = {}     # Idempotency-Key -> transfer object
        self.by_id: dict[str, dict] = {}       # transfer id      -> transfer object
        self.transfers_created = 0             # how many REAL transfer objects exist
        self.fail_times = fail_times           # 500 the first N calls per idem key
        self.fail_seen: dict[str, int] = {}    # idem key -> #times we've 500'd it


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):                 # silence the default stderr spam
        pass

    # -- helpers ---------------------------------------------------------------
    def _json(self, status: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, status: int, message: str, typ: str = "invalid_request_error"):
        self._json(status, {"error": {"message": message, "type": typ}})

    def _authed(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return auth.startswith("Bearer ") and len(auth) > len("Bearer ")

    # -- POST /v1/transfers ----------------------------------------------------
    def do_POST(self):
        if self.path != "/v1/transfers":
            return self._err(404, f"Unrecognized request URL: POST {self.path}")
        if not self._authed():
            return self._err(401, "You did not provide a valid API key.",
                             "authentication_error")
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode() if length else ""
        form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
        idem = self.headers.get("Idempotency-Key", "")

        try:
            amount = int(form.get("amount", ""))
        except ValueError:
            amount = 0
        if amount <= 0:
            return self._err(400, "Invalid integer: amount must be a positive integer.")

        st: _State = self.server.state          # type: ignore[attr-defined]
        with st.lock:
            # flaky knob: 500 the first N times we see this idem key (transport-ish)
            if idem and st.fail_seen.get(idem, 0) < st.fail_times:
                st.fail_seen[idem] = st.fail_seen.get(idem, 0) + 1
                return self._err(500, "Stripe test-double: injected transient error.",
                                 "api_error")
            # idempotency: same key -> same transfer, never a second one
            if idem and idem in st.by_idem:
                prior = st.by_idem[idem]
                if prior["amount"] != amount:
                    return self._err(
                        400, "Keys for idempotent requests can only be used with the "
                        "same parameters they were first used with.",
                        "idempotency_error")
                return self._json(200, prior)   # replay: identical object, no new transfer
            st.transfers_created += 1
            tid = f"tr_test_{st.transfers_created:08d}"
            obj = {"id": tid, "object": "transfer", "amount": amount,
                   "currency": form.get("currency", "usd"),
                   "destination": form.get("destination", ""),
                   "metadata": {"memo": form.get("metadata[memo]", ""),
                                "idem": form.get("metadata[idem]", "")}}
            if idem:
                st.by_idem[idem] = obj
            st.by_id[tid] = obj
            return self._json(200, obj)

    # -- GET /v1/transfers/<id> ------------------------------------------------
    def do_GET(self):
        if not self._authed():
            return self._err(401, "You did not provide a valid API key.",
                             "authentication_error")
        prefix = "/v1/transfers/"
        if not self.path.startswith(prefix):
            return self._err(404, f"Unrecognized request URL: GET {self.path}")
        tid = self.path[len(prefix):]
        st: _State = self.server.state          # type: ignore[attr-defined]
        with st.lock:
            obj = st.by_id.get(tid)
        if obj is None:
            return self._err(404, f"No such transfer: {tid}", "invalid_request_error")
        return self._json(200, obj)


class FakeStripe:
    """A context-managed local Stripe double. `with FakeStripe() as fs:` starts the
    server on an ephemeral port; `fs.base_url` is what you pass to
    `StripeConnectRail(base_url=...)`. `fs.transfers_created` is the ground truth
    for "how many real transfers happened" — the number a double-pay would inflate.
    """
    def __init__(self, fail_times: int = 0):
        self._state = _State(fail_times=fail_times)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.state = self._state         # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def transfers_created(self) -> int:
        with self._state.lock:
            return self._state.transfers_created

    def start(self) -> "FakeStripe":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def __enter__(self) -> "FakeStripe":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
