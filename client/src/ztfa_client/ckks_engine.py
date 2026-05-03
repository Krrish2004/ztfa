"""Client-side CKKS engine: encrypt local weights, compute Poseidon
commitment, decrypt the aggregate."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import tenseal as ts

from ztfa_crypto.poseidon import commitment, to_bytes32


class ClientCKKSEngine:
    def __init__(self, full_context_path: Path) -> None:
        if not full_context_path.exists():
            raise FileNotFoundError(f"missing CKKS full context: {full_context_path}")
        self.ctx = ts.context_from(full_context_path.read_bytes())
        if not self.ctx.is_private():
            raise RuntimeError("client requires PRIVATE (sk-bearing) context")

    def encrypt_weights(self, weights: np.ndarray) -> bytes:
        """Encrypt a 1-D weight vector → serialized CKKS ciphertext bytes."""
        if weights.ndim != 1:
            raise ValueError("weights must be 1-D")
        ct = ts.ckks_vector(self.ctx, weights.tolist())
        return ct.serialize()

    def commit(self, *, round_t: int, client_id: int, ciphertext_bytes: bytes) -> bytes:
        """H_i = Poseidon(t || client_id || serialize(c_i)). 32-byte big-endian."""
        h = commitment(round_t, client_id, ciphertext_bytes)
        return to_bytes32(h)

    def decrypt_aggregate(
        self, ct_blob: bytes, *, n_clients: int, n_weights: int
    ) -> np.ndarray:
        """Decrypt c_sum and divide by N (the v1 plaintext-side average step)."""
        ct = ts.ckks_vector_from(self.ctx, ct_blob)
        plain = np.array(ct.decrypt(), dtype=np.float64)
        plain = plain[:n_weights]  # strip padding
        return plain / float(n_clients)
