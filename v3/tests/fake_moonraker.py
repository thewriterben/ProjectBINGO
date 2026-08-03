"""A tiny Moonraker impostor for testing the K2 driver without a printer.

Mimics the endpoints K2Driver touches, with print progress advancing on a
clock. Response shapes match the AdvancedStudio diagnostics captures from
the real K2 Plus (hostname K2Plus-BF81).

Run the integration test:  python -m tests.test_k2_driver   (from v3/)
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _State:
    def __init__(self, print_seconds: float):
        self.print_seconds = print_seconds
        self.started_at: float | None = None
        self.filename: str | None = None

    def progress(self) -> float:
        if self.started_at is None:
            return 0.0
        return min(1.0, (time.time() - self.started_at) / self.print_seconds)

    def state(self) -> str:
        if self.started_at is None:
            return "standby"
        return "complete" if self.progress() >= 1.0 else "printing"


def make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):        # silence
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/printer/info"):
                self._json({"result": {"state": "ready", "hostname": "K2Plus-FAKE",
                                       "software_version": "test-1.0",
                                       "state_message": "Printer is ready"}})
            elif self.path.startswith("/printer/objects/query"):
                p = state.progress()
                self._json({"result": {"status": {
                    "print_stats": {"state": state.state(),
                                    "print_duration": p * state.print_seconds,
                                    "filament_used": p * 950.0, "message": ""},
                    "virtual_sdcard": {"progress": p},
                    "extruder": {"temperature": 209.7 + p, "target": 210.0},
                    "heater_bed": {"temperature": 60.1, "target": 60.0},
                }}})
            elif self.path.startswith("/server/webcams/list"):
                self._json({"result": {"webcams": [
                    {"name": "chamber", "snapshot_url": "/snapshot"}]}})
            elif self.path.startswith("/snapshot"):
                frame = f"jpegish-{time.time()}".encode()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            if self.path.startswith("/server/files/upload"):
                self._json({"result": {"item": {"path": "uploaded.gcode"}}})
            elif self.path.startswith("/printer/print/start"):
                state.started_at = time.time()
                self._json({"result": "ok"})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def start(port: int = 7125, print_seconds: float = 12.0) -> ThreadingHTTPServer:
    state = _State(print_seconds)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
