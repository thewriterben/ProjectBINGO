"""K2Driver — real driver for a Creality K2 Plus via Moonraker.

Stdlib-only (urllib), so the node agent runs anywhere without a venv.
Endpoint map and object model confirmed against the AdvancedStudio
diagnostics captures (diagnose_moonraker.py / diagnose_creality_9999.py,
2026-07-12): Moonraker on :7125, hostname K2Plus-BF81, standard
print_stats/virtual_sdcard objects present, webcam via /server/webcams/list.

Driver contract (same as MockDriver):
    prepare(gcode)              -> uploads file, returns {"gcode_sha256", ...}
    run_unit(serial, est_min)   -> yields raw observation dicts; the NodeAgent
                                   wraps each into the signed PoF chain.

Safety posture (matches AdvancedStudio's guard philosophy):
    * This driver only uploads + starts a file the OPERATOR supplied
      (a real sliced .gcode). It never generates or mutates gcode.
    * Multi-unit runs pause for operator bed-clear confirmation between units.
    * Any printer error/cancel state raises -> job FAILED, nothing settles.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Iterator

POLL_SECONDS = 5.0
FRAME_MILESTONES = (0.10, 0.35, 0.60, 0.85)
TELEMETRY_MIN_DELTA = 0.02          # emit TELEMETRY on >=2% progress movement


class K2Error(RuntimeError):
    pass


class K2Driver:
    def __init__(self, host: str, port: int = 7125, api_key: str = "",
                 max_hours: float = 12.0, confirm=input, say=print,
                 ui_port: int = 4408, webcam_url: str | None = None):
        self.host = host
        self.base = f"http://{host}:{port}"
        self.ui_port = ui_port            # Fluidd/Mainsail host that proxies /webcam/
        self.webcam_url = webcam_url      # explicit override; skips discovery
        self.headers = {"X-Api-Key": api_key} if api_key else {}
        self.max_hours = max_hours
        self.confirm = confirm            # injectable for tests/unattended
        self.say = say
        self._filename: str | None = None
        self._units_started = 0
        self._snap_url: str | None = None  # resolved + cached

    # ---------------- HTTP helpers (stdlib) ----------------

    def _request(self, path: str, data: bytes | None = None,
                 headers: dict | None = None, method: str | None = None) -> dict:
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={**self.headers, **(headers or {})},
                                     method=method or ("POST" if data is not None else "GET"))
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read()
        except urllib.error.URLError as e:
            raise K2Error(f"cannot reach printer at {self.base}: {e}") from e
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"raw": body[:200].decode(errors="replace")}

    def _get_bytes(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()

    def _post(self, path: str, **params) -> dict:
        qs = ("?" + urllib.parse.urlencode(params)) if params else ""
        return self._request(path + qs, data=b"", method="POST")

    # ---------------- printer surface ----------------

    def info(self) -> dict:
        return self._request("/printer/info").get("result", {})

    def query(self) -> dict:
        path = "/printer/objects/query?print_stats&virtual_sdcard&extruder&heater_bed"
        res = self._request(path).get("result", {})
        return res.get("status", {})

    def snapshot_url(self) -> str | None:
        """Resolve the snapshot URL Moonraker advertises. The K2 (Fluidd)
        advertises a RELATIVE path (/webcam/?action=snapshot) that is proxied
        by the UI host (:4408), NOT by Moonraker (:7125). Resolve against the
        UI host, cache the result."""
        if self._snap_url:
            return self._snap_url
        if self.webcam_url:
            self._snap_url = self.webcam_url
            return self._snap_url
        snap = ""
        try:
            res = self._request("/server/webcams/list").get("result", {})
            cams = res.get("webcams", [])
            if cams:
                snap = cams[0].get("snapshot_url", "")
        except K2Error:
            pass
        if snap.startswith("http"):
            self._snap_url = snap
        elif snap:
            # relative path → resolve against the UI proxy host, not Moonraker
            self._snap_url = f"http://{self.host}:{self.ui_port}{snap}"
        else:
            self._snap_url = None
        return self._snap_url

    def camera_preflight(self) -> tuple[bool, str]:
        """Check the camera BEFORE printing so a down streamer is a loud
        warning, not silent missing evidence. Returns (ok, detail)."""
        url = self.snapshot_url()
        if not url:
            return False, "no webcam advertised by Moonraker (no FRAME evidence)"
        try:
            with urllib.request.urlopen(url, timeout=6) as r:
                head = r.read(2)
            if head[:2] == b"\xff\xd8":
                return True, f"camera OK ({url})"
            return False, f"{url} responded but not JPEG (streamer misconfigured)"
        except urllib.error.HTTPError as e:
            if e.code == 502:
                return False, (f"camera streamer is DOWN (502 at {url}) — enable the "
                               f"camera in the K2 UI for FRAME evidence; proceeding "
                               f"telemetry-only")
            return False, f"camera error {e.code} at {url}"
        except Exception as e:
            return False, f"camera unreachable at {url}: {e}"

    def download_gcode(self, filename: str) -> bytes:
        """Fetch an existing file from the printer's gcodes root — used to
        register an already-proven print as a content-addressed asset."""
        return self._get_bytes(self.base + "/server/files/gcodes/"
                               + urllib.parse.quote(filename))

    def upload_gcode(self, gcode: bytes, filename: str) -> str:
        boundary = f"----bingo{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="root"\r\n\r\ngcodes\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + gcode + f"\r\n--{boundary}--\r\n".encode()
        self._request("/server/files/upload", data=body,
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return filename

    # ---------------- driver contract ----------------

    def prepare(self, gcode: bytes) -> dict:
        """Upload the operator-supplied sliced gcode; commit its hash."""
        info = self.info()
        state = info.get("state", "unknown")
        if state != "ready":
            raise K2Error(f"printer state is '{state}', need 'ready' "
                          f"({info.get('state_message', '')})")
        cam_ok, cam_detail = self.camera_preflight()
        self.say(f"    [k2] {cam_detail}")
        self._filename = f"bingo_{uuid.uuid4().hex[:8]}.gcode"
        self.upload_gcode(gcode, self._filename)
        self.say(f"    [k2] uploaded {self._filename} "
                 f"({len(gcode):,} bytes) to {info.get('hostname', self.base)}")
        return {"gcode_sha256": hashlib.sha256(gcode).hexdigest(),
                "machine_hostname": info.get("hostname", ""),
                "klipper_version": info.get("software_version", ""),
                "filename": self._filename,
                "camera_ok": cam_ok, "camera_detail": cam_detail}

    def run_unit(self, unit_serial: str, est_minutes: float) -> Iterator[dict]:
        assert self._filename, "prepare() must run first"
        self._units_started += 1
        if self._units_started > 1:
            self.confirm(f"    [k2] clear the bed, then press Enter to start "
                         f"unit {self._units_started} ({unit_serial})… ")

        self._post("/printer/print/start", filename=self._filename)
        self.say(f"    [k2] print started: {unit_serial}")
        started = time.time()
        milestones = list(FRAME_MILESTONES)
        last_reported = -1.0
        last_narrated = -1.0                  # throttle live progress prints
        snap = self.snapshot_url()

        while True:
            if time.time() - started > self.max_hours * 3600:
                raise K2Error(f"unit {unit_serial} exceeded {self.max_hours}h guard")
            time.sleep(POLL_SECONDS)
            status = self.query()
            ps = status.get("print_stats", {})
            vsd = status.get("virtual_sdcard", {})
            state = ps.get("state", "unknown")
            progress = float(vsd.get("progress") or 0.0)

            if state in ("error", "cancelled"):
                raise K2Error(f"printer reported {state}: {ps.get('message', '')}")

            if progress - last_reported >= TELEMETRY_MIN_DELTA or state == "complete":
                last_reported = progress
                nozzle = round(float(status.get("extruder", {}).get("temperature") or 0), 1)
                bed = round(float(status.get("heater_bed", {}).get("temperature") or 0), 1)
                yield {"type": "TELEMETRY", "stage": state,
                       "progress": round(progress, 4), "nozzle_c": nozzle, "bed_c": bed,
                       "print_duration_s": round(float(ps.get("print_duration") or 0), 1)}
                # live, throttled: one line per ~10% so a watcher sees motion
                if progress - last_narrated >= 0.10 or state == "complete":
                    last_narrated = progress
                    self.say(f"    [k2] {unit_serial} {state} {progress*100:4.0f}%  "
                             f"nozzle {nozzle}°C bed {bed}°C")

            while milestones and progress >= milestones[0]:
                pct = milestones.pop(0)
                frame_hash = self._capture(snap)
                if frame_hash:
                    yield {"type": "FRAME", "stage": f"progress-{int(pct * 100)}pct",
                           "frame_sha256": frame_hash}

            if state == "complete":
                final = self._capture(snap)
                if final:
                    yield {"type": "FRAME", "stage": "final", "frame_sha256": final}
                yield {"type": "UNIT_COMPLETE", "unit_serial": unit_serial,
                       "duration_min": round((time.time() - started) / 60.0, 1),
                       "filament_mm": round(float(ps.get("filament_used") or 0), 1)}
                return

    def _capture(self, snap_url: str | None) -> str | None:
        if not snap_url:
            return None
        try:
            return hashlib.sha256(self._get_bytes(snap_url)).hexdigest()
        except Exception:
            self.say("    [k2] webcam snapshot unavailable (continuing without frame)")
            return None
