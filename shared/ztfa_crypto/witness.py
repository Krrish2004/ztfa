"""Witness builder + WASM-driven witness generator wrapper.

Builds the JSON inputs for `circuits/aggregation.circom`, invokes the
auto-generated WASM witness calculator, and emits a `.wtns` file consumable
by rapidsnark / snarkjs.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .poseidon import poseidon_chain


@dataclass(frozen=True)
class CircuitInputs:
    """Public + private witness for `aggregation.circom`."""

    H: list[int]                     # public — N commitments
    H_sum: int                       # public — aggregate commitment
    c: list[list[int]]               # private — per-client digests, shape [N][K]
    c_sum: list[int]                 # private — sum digest, length K

    def to_json(self) -> dict[str, object]:
        return {
            "H": [str(x) for x in self.H],
            "H_sum": str(self.H_sum),
            "c": [[str(x) for x in row] for row in self.c],
            "c_sum": [str(x) for x in self.c_sum],
        }


def build_inputs(client_coefficients: list[list[int]]) -> CircuitInputs:
    """Compute the full witness from per-client ciphertext coefficient vectors.

    Each `client_coefficients[i]` is a length-M list of BN254 Fr-compatible
    integers (coefficients of the (a, b) polynomial pair, flattened in order).
    For mini_he with N_RING=256, M = 2*256 = 512.

    The aggregator's c_sum is computed by element-wise addition in BN254 Fr
    (matching mini_he.add which intentionally does NOT reduce mod q so the
    constraint Σ c_i = c_sum holds exactly).
    """
    n = len(client_coefficients)
    if n == 0:
        raise ValueError("at least 1 client coefficient vector required")
    m = len(client_coefficients[0])
    for i, d in enumerate(client_coefficients):
        if len(d) != m:
            raise ValueError(f"client {i} length {len(d)} != {m}")

    H = [poseidon_chain(d) for d in client_coefficients]
    c_sum = [0] * m
    for d in client_coefficients:
        for k in range(m):
            c_sum[k] += d[k]
    H_sum = poseidon_chain(c_sum)

    return CircuitInputs(H=H, H_sum=H_sum, c=client_coefficients, c_sum=c_sum)


def write_witness(
    inputs: CircuitInputs,
    output_wtns: Path,
    *,
    wasm_path: Path | None = None,
    witness_calculator_js: Path | None = None,
) -> None:
    """Run the WASM witness calculator → emit `.wtns` to `output_wtns`."""
    ztfa_root = Path(os.environ.get("ZTFA_ROOT", Path(__file__).resolve().parents[2]))
    if wasm_path is None:
        wasm_path = ztfa_root / "circuits" / "build" / "aggregation_js" / "aggregation.wasm"
    if witness_calculator_js is None:
        witness_calculator_js = (
            ztfa_root / "circuits" / "build" / "aggregation_js" / "generate_witness.js"
        )

    if not wasm_path.exists():
        raise FileNotFoundError(f"missing {wasm_path} (run circuits/scripts/compile.sh)")
    if not witness_calculator_js.exists():
        raise FileNotFoundError(f"missing {witness_calculator_js}")

    # snarkjs `generate_witness.js` signature: <wasm> <input.json> <output.wtns>
    import tempfile
    output_wtns.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
        json.dump(inputs.to_json(), tmp)
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(
            [
                "node",
                str(witness_calculator_js),
                str(wasm_path),
                str(tmp_path),
                str(output_wtns),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def write_witness_simple(
    inputs: CircuitInputs,
    output_wtns: Path,
) -> None:
    """Simpler entry: subprocess-call snarkjs CLI (more portable)."""
    import tempfile

    ztfa_root = Path(os.environ.get("ZTFA_ROOT", Path(__file__).resolve().parents[2]))
    wasm_path = ztfa_root / "circuits" / "build" / "aggregation_js" / "aggregation.wasm"
    if not wasm_path.exists():
        raise FileNotFoundError(f"missing {wasm_path} (run circuits/scripts/compile.sh)")

    output_wtns.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
        json.dump(inputs.to_json(), tmp)
        tmp_path = Path(tmp.name)

    try:
        subprocess.run(
            [
                "node",
                str(ztfa_root / "circuits" / "node_modules" / "snarkjs" / "cli.js"),
                "wtns",
                "calculate",
                str(wasm_path),
                str(tmp_path),
                str(output_wtns),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
