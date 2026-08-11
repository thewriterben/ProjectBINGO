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
    ("key custody: generation, at-rest, rotation/revocation/recovery", "tests.test_key_custody", V3),
    ("signing path: audited constant-time vs pure-python kernel", "tests.test_signing_path", V3),
    ("external anchor: merkle transparency log + ordering proofs", "tests.test_anchor", V3),
    ("coin rollback closed by the external anchor", "tests.test_coin_anchor", V3),
    ("thin-vertical demo", "bingo.demo.run", V3),
    ("multi-asset royalty", "tests.test_multi_royalty", V3),
    ("acceptance grades", "tests.test_grades", V3),
    ("reputation", "tests.test_reputation", V3),
    ("persisted evidence + verifier", "tests.test_verifier", V3),
    ("settlement adapter", "tests.test_settlement_adapter", V3),
    ("payout execution (idempotent money movement)", "tests.test_payout", V3),
    ("real stripe rail end-to-end (faithful local double)", "tests.test_payout_stripe", V3),
    ("creator earnings", "tests.test_earnings", V3),
    ("training-material royalties", "tests.test_training", V3),
    ("provenance passport (RWA)", "tests.test_passport", V3),
    ("rwa as first-class asset", "tests.test_rwa_asset", V3),
    ("rwa tokenization (ownership ledger)", "tests.test_token", V3),
    ("machine rwa / node financing", "tests.test_machine_rwa", V3),
    ("machine-rwa raise readiness (fail-closed)", "tests.test_raise_readiness", V3),
    ("unified network earnings", "tests.test_network_earnings", V3),
    ("provenance/token verifier CLI", "tests.test_verify_cli", V3),
    ("auto-transport custody + anti-double-broker", "tests.test_transport", V3),
    ("dgd coin $25 QR credential + redemption", "tests.test_coin", V3),
    ("coin redemption: persistence + backend", "tests.test_redemption", V3),
    ("k2 driver (fake moonraker)", "tests.test_k2_driver", V3),
    ("architecture thesis (one-kernel conformance)", "tests.test_kernel_thesis", V3),
    ("property-based fuzz over the kernel invariants", "tests.test_fuzz_invariants", V3),
    ("red-team regressions (19 confirmed breaks, all fixed)", "tests.test_redteam_regressions", V3),
    ("red-team round-2 regressions (15 confirmed breaks, all fixed)", "tests.test_redteam_r2_regressions", V3),
    ("red-team round-3 regressions (9 confirmed breaks, all fixed)", "tests.test_redteam_r3_regressions", V3),
    ("red-team round-4 regressions (7 confirmed breaks, all fixed)", "tests.test_redteam_r4_regressions", V3),
    ("red-team round-5 regressions (11 confirmed breaks, all fixed)", "tests.test_redteam_r5_regressions", V3),
    ("red-team round-6 regressions (5 confirmed breaks, all fixed)", "tests.test_redteam_r6_regressions", V3),
    ("red-team round-7 regressions (2 confirmed breaks, all fixed)", "tests.test_redteam_r7_regressions", V3),
    ("red-team round-8 regressions (1 confirmed break, all fixed)", "tests.test_redteam_r8_regressions", V3),
    ("red-team round-9 regressions (1 confirmed break, all fixed)", "tests.test_redteam_r9_regressions", V3),
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
