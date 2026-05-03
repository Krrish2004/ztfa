"""Poseidon hash — BN254-Fr / circomlib-compatible.

The on-circuit `aggregation.circom`, the Solidity verifier, and this Python
module all use **circomlibjs's Poseidon** over the BN254 scalar field. The
Python side is a thin subprocess bridge to a Node REPL running circomlibjs —
this guarantees byte-for-byte parity with the in-circuit hash.

Single source of truth: `circuits/scripts/poseidon_cli.mjs`. Any change to
commitment construction must update Python (this file), the Node CLI, AND
`circuits/aggregation.circom`.

Performance: subprocess REPL stays alive across calls; one-time ~200ms cold
start, sub-millisecond per call. Round-level usage (~N+1 commits) is well
under 100ms total overhead.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Final

BN254_FR: Final[int] = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)


class _PoseidonRepl:
    """Long-lived Node subprocess running circomlibjs Poseidon."""

    _instance: "_PoseidonRepl | None" = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "_PoseidonRepl":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        cli_path = (
            Path(os.environ.get("ZTFA_ROOT", Path(__file__).resolve().parents[2]))
            / "circuits"
            / "scripts"
            / "poseidon_cli.mjs"
        )
        if not cli_path.exists():
            raise FileNotFoundError(
                f"poseidon_cli.mjs not found at {cli_path}. "
                "Run `npm install` in circuits/ first."
            )
        self._proc = subprocess.Popen(
            ["node", str(cli_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(cli_path.parent.parent),
        )
        self._call_lock = threading.Lock()
        # Wait for READY banner
        ready = self._proc.stdout.readline().strip()  # type: ignore[union-attr]
        if ready != "READY":
            raise RuntimeError(f"poseidon_cli failed to start; got: {ready!r}")

    def call(self, op: str, **kwargs: object) -> int:
        with self._call_lock:
            req = json.dumps({"op": op, **kwargs}) + "\n"
            assert self._proc.stdin is not None
            assert self._proc.stdout is not None
            self._proc.stdin.write(req)
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()
            if not line:
                stderr = self._proc.stderr.read() if self._proc.stderr else ""
                raise RuntimeError(f"poseidon_cli died: {stderr}")
            resp = json.loads(line)
            if "error" in resp:
                raise RuntimeError(f"poseidon_cli error: {resp}")
            return int(resp["result"])


def poseidon2(a: int, b: int) -> int:
    """Hash 2 BN254-Fr field elements → 1. Matches circomlib `Poseidon(2)`."""
    return _PoseidonRepl.get().call(
        "poseidon2", a=str(a % BN254_FR), b=str(b % BN254_FR)
    )


def poseidon_chain(elements: list[int]) -> int:
    """Left-fold pairwise Poseidon. Matches the in-circuit chain template."""
    if not elements:
        return 0
    return _PoseidonRepl.get().call(
        "chain", elements=[str(e % BN254_FR) for e in elements]
    )


def poseidon_bytes(data: bytes) -> int:
    """Hash arbitrary bytes by chunking into 31-byte field elements (iden3
    canonical convention) then folding via `poseidon_chain`. The matching
    circom template chunks identically."""
    return _PoseidonRepl.get().call("chain", elements=_chunk31(data))


def commitment(round_index: int, client_id: int, ciphertext_bytes: bytes) -> int:
    """Domain-separated commitment (CLAUDE.md §1.5; defends T9 replay).

    H_i = Poseidon( Poseidon(round_index, client_id),
                    Poseidon-chain( chunk31(ciphertext_bytes) ) )
    """
    return _PoseidonRepl.get().call(
        "commitment",
        round=str(round_index),
        clientId=str(client_id),
        ctHex=ciphertext_bytes.hex(),
    )


def to_bytes32(field_element: int) -> bytes:
    """Encode a BN254 Fr element as big-endian 32 bytes — matches Solidity
    `bytes32` event field."""
    return (field_element % BN254_FR).to_bytes(32, byteorder="big")


def from_bytes32(b: bytes) -> int:
    """Decode big-endian 32 bytes back to a BN254 Fr element."""
    return int.from_bytes(b, byteorder="big") % BN254_FR


def _chunk31(data: bytes) -> list[str]:
    """Internal: split bytes into 31-byte chunks, return as decimal strings."""
    out: list[str] = []
    for i in range(0, len(data), 31):
        chunk = data[i : i + 31]
        out.append(str(int.from_bytes(chunk, byteorder="big")))
    return out
