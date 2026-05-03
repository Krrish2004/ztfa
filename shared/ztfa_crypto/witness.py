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
from .snark_digest import DIGEST_LEN_K, project_sum_in_field


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


def build_inputs(client_digests: list[list[int]]) -> CircuitInputs:
    """Compute the full witness from a list of per-client digests.

    Each `client_digests[i]` is a length-K list of BN254 Fr elements (computed
    via `snark_digest.project` over that client's serialized ciphertext).
    """
    n = len(client_digests)
    if n == 0:
        raise ValueError("at least 1 client digest required")
    for i, d in enumerate(client_digests):
        if len(d) != DIGEST_LEN_K:
            raise ValueError(f"client {i} digest length {len(d)} != {DIGEST_LEN_K}")

    H = [poseidon_chain(d) for d in client_digests]
    c_sum = project_sum_in_field(client_digests)
    H_sum = poseidon_chain(c_sum)

    return CircuitInputs(H=H, H_sum=H_sum, c=client_digests, c_sum=c_sum)


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
