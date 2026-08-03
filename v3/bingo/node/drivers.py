"""L2 — Machine drivers.

Driver contract: prepare(job_ctx) -> iterate run(unit_serial) yielding raw
telemetry dicts. The node agent wraps every yield into a signed, hash-chained
PoF event; drivers only produce observations.

- MockDriver: full simulation for the demo/prototype.
- MoonrakerDriver: Klipper via Moonraker HTTP (correct endpoints, untested stub).
- BambuDriver: Bambu LAN/Developer Mode (MQTT; stub documenting the interface).
"""

from __future__ import annotations

import hashlib
import random
from typing import Iterator


class MockDriver:
    """Simulates an FDM printer deterministically enough to demo, randomly
    enough to look alive. Frame 'captures' are hashes of synthetic frames —
    the PoF commitment structure is identical to a real camera's."""

    def __init__(self, machine_id: str, seed: int | None = None):
        self.machine_id = machine_id
        self.rng = random.Random(seed)

    def prepare(self, gcode: bytes) -> dict:
        return {"gcode_sha256": hashlib.sha256(gcode).hexdigest(),
                "machine_id": self.machine_id}

    def run_unit(self, unit_serial: str, est_minutes: float) -> Iterator[dict]:
        nozzle = 210 + self.rng.uniform(-2, 2)
        bed = 60 + self.rng.uniform(-1, 1)
        yield {"type": "TELEMETRY", "stage": "heating",
               "nozzle_c": round(nozzle, 1), "bed_c": round(bed, 1), "progress": 0.0}
        for pct in (10, 35, 60, 85):
            yield {"type": "TELEMETRY", "stage": "printing",
                   "nozzle_c": round(nozzle + self.rng.uniform(-1.5, 1.5), 1),
                   "bed_c": round(bed + self.rng.uniform(-0.5, 0.5), 1),
                   "progress": pct / 100.0}
            frame = f"{self.machine_id}:{unit_serial}:{pct}:{self.rng.random()}".encode()
            yield {"type": "FRAME", "stage": f"layer-{pct}pct",
                   "frame_sha256": hashlib.sha256(frame).hexdigest()}
        yield {"type": "UNIT_COMPLETE", "unit_serial": unit_serial,
               "duration_min": round(est_minutes * self.rng.uniform(0.92, 1.12), 1)}


class MoonrakerDriver:
    """Klipper via Moonraker. Untested stub with the real endpoints:
      POST {base}/server/files/upload            (multipart gcode)
      POST {base}/printer/print/start?filename=  (start job)
      GET  {base}/printer/objects/query?extruder&heater_bed&virtual_sdcard
                                                  (telemetry: temps + progress)
      GET  {webcam}/snapshot                      (frame capture -> sha256)
    Wire with urllib/httpx when pointing at a real Klipper machine."""

    def __init__(self, base_url: str, webcam_url: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.webcam_url = webcam_url

    def prepare(self, gcode: bytes) -> dict:
        raise NotImplementedError("connect to a real Moonraker instance to use this driver")

    def run_unit(self, unit_serial: str, est_minutes: float):
        raise NotImplementedError


class BambuDriver:
    """Bambu Lab over LAN/Developer Mode: MQTT on port 8883 (topic
    device/{serial}/report for telemetry; chamber camera via LAN liveview).
    Requires Developer Mode enabled on the printer. Stub."""

    def __init__(self, host: str, serial: str, access_code: str):
        self.host, self.serial, self.access_code = host, serial, access_code

    def prepare(self, gcode: bytes) -> dict:
        raise NotImplementedError("requires a LAN-mode Bambu printer")

    def run_unit(self, unit_serial: str, est_minutes: float):
        raise NotImplementedError
