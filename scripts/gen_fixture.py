#!/usr/bin/env python3
"""Generate test/fixture.json — a real Groth16 proof for the FederationRound
Foundry tests. Uses snarkjs's `groth16 exportsoliditycalldata` to emit
proof components in the EXACT format the auto-generated Verifier.sol expects
(this is non-trivial because of Fq2 element ordering).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Make the local shared/ package importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))

from ztfa_crypto.snark_digest import project  # noqa: E402
from ztfa_crypto.witness import build_inputs, write_witness_simple  # noqa: E402


def main() -> None:
    fake_cts = [
        b"client_0_test_ciphertext_padding_to_make_it_long",
        b"client_1_test_ciphertext_padding_to_make_it_long",
        b"client_2_test_ciphertext_padding_to_make_it_long",
    ]
    digests = [project(ct) for ct in fake_cts]
    inputs = build_inputs(digests)

    build_dir = ROOT / "circuits" / "build"
    wtns = build_dir / "fixture_witness.wtns"
    write_witness_simple(inputs, wtns)

    proof_path = build_dir / "fixture_proof.json"
    public_path = build_dir / "fixture_public.json"
    snarkjs = ROOT / "circuits" / "node_modules" / "snarkjs" / "cli.js"

    subprocess.run(
        [
            "node",
            str(snarkjs),
            "groth16",
            "prove",
            str(build_dir / "aggregation_final.zkey"),
            str(wtns),
            str(proof_path),
            str(public_path),
        ],
        check=True,
        capture_output=True,
    )

    # Use snarkjs `groth16 exportsoliditycalldata` for the EXACT format the
    # generated Verifier.sol expects.
    proc = subprocess.run(
        [
            "node",
            str(snarkjs),
            "zkey",
            "export",
            "soliditycalldata",
            str(public_path),
            str(proof_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    calldata = proc.stdout.strip()

    # snarkjs emits e.g.:
    #   ["0x...", "0x..."],[["0x...","0x..."],["0x...","0x..."]],["0x...","0x..."],["0x...","0x...","0x...","0x..."]
    # We parse it as: a, b, c, pubSignals
    parts = _split_top_level(calldata)
    if len(parts) != 4:
        raise RuntimeError(f"unexpected calldata shape: got {len(parts)} parts")

    a = json.loads(parts[0])
    b = json.loads(parts[1])
    c = json.loads(parts[2])
    pub = json.loads(parts[3])

    # Convert hex strings to decimal strings (Foundry parseJsonUint expects
    # decimal or hex; vm.parseJsonUint accepts hex with 0x prefix too)
    fixture = {
        "a": a,
        "b": b,
        "c": c,
        "pubSignals": pub,
        "H": [hex(h) for h in inputs.H],
        "H_sum": hex(inputs.H_sum),
        "ciphertexts_hex": [ct.hex() for ct in fake_cts],
    }
    out = ROOT / "contracts" / "test" / "fixture.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture, indent=2))
    print(f"  ✓ fixture written → {out}")
    print(f"  pubSignals count: {len(pub)}")


def _split_top_level(s: str) -> list[str]:
    """Split a comma-separated list of JSON arrays at the top level (depth 0)."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(s):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(s[start:i].strip())
            start = i + 1
    parts.append(s[start:].strip())
    return parts


if __name__ == "__main__":
    main()
