#!/usr/bin/env python3
"""Run the whole BINGO + Sentinel test suite. Stdlib only, no pytest needed.

    python run_tests.py

Exits non-zero if anything fails — this is what CI runs.
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
V3 = os.path.join(ROOT, "v3")

# (label, module, cwd)
SUITE = [
    ("ed25519 self-test", "bingo.crypto", V3),
    ("thin-vertical demo", "bingo.demo.run", V3),
    ("multi-asset royalty", "tests.test_multi_royalty", V3),
    ("acceptance grades", "tests.test_grades", V3),
    ("reputation", "tests.test_reputation", V3),
    ("persisted evidence + verifier", "tests.test_verifier", V3),
    ("settlement adapter", "tests.test_settlement_adapter", V3),
    ("creator earnings", "tests.test_earnings", V3),
    ("k2 driver (fake moonraker)", "tests.test_k2_driver", V3),
    ("sentinel classifier", "sentinel.test_sentinel", ROOT),
]


def main() -> int:
    results = []
    for label, module, cwd in SUITE:
        print(f"▶ {label} …", flush=True)
        env = dict(os.environ, PYTHONUTF8="1")
        proc = subprocess.run([sys.executable, "-m", module], cwd=cwd, env=env,
                              capture_output=True, text=True)
        ok = proc.returncode == 0
        results.append((label, ok))
        tail = (proc.stdout.strip().splitlines() or [""])[-1]
        print(f"  {'✓' if ok else '✗'} {tail}")
        if not ok:
            print(proc.stdout[-1500:])
            print(proc.stderr[-1500:])
    passed = sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{len(results)} suites passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
