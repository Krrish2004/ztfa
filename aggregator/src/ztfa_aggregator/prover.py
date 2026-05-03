"""Prover adapter: builds witness, invokes ztfa-prove (rust binary), returns proof."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ztfa_crypto.witness import CircuitInputs, build_inputs, write_witness_simple


@dataclass(frozen=True)
class Groth16Proof:
    a: list[str]                 # length 2 (uint256 hex strings)
    b: list[list[str]]           # 2x2
    c: list[str]                 # length 2
    public_signals: list[str]    # length N+1


async def prove_round(
    client_digests: list[list[int]],
    *,
    zkey_path: Path,
    work_dir: Path,
    snarkjs_cli: Path,
) -> tuple[Groth16Proof, CircuitInputs]:
    """Run the SNARK prover for a single round."""
    work_dir.mkdir(parents=True, exist_ok=True)
    inputs = build_inputs(client_digests)

    wtns = work_dir / "witness.wtns"
    proof_path = work_dir / "proof.json"
    public_path = work_dir / "public.json"

    await asyncio.to_thread(write_witness_simple, inputs, wtns)

    # Prove
    proc = await asyncio.create_subprocess_exec(
        "node",
        str(snarkjs_cli),
        "groth16",
        "prove",
        str(zkey_path),
        str(wtns),
        str(proof_path),
        str(public_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"snarkjs prove failed: {err.decode()}")

    # Get the calldata-format output (handles Fq2 ordering automatically)
    proc = await asyncio.create_subprocess_exec(
        "node",
        str(snarkjs_cli),
        "zkey",
        "export",
        "soliditycalldata",
        str(public_path),
        str(proof_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"snarkjs soliditycalldata failed: {err.decode()}")

    parts = _split_top_level(out.decode().strip())
    if len(parts) != 4:
        raise RuntimeError(f"unexpected calldata parts: {len(parts)}")
    a = json.loads(parts[0])
    b = json.loads(parts[1])
    c = json.loads(parts[2])
    public = json.loads(parts[3])
    return (
        Groth16Proof(a=a, b=b, c=c, public_signals=public),
        inputs,
    )


def _split_top_level(s: str) -> list[str]:
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
