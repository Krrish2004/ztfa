"""Homomorphic engine. Operates on PUBLIC-only CKKS context."""

from __future__ import annotations

from pathlib import Path

import tenseal as ts

from ztfa_crypto.snark_digest import project, project_for_aggregate


def homomorphic_sum(ciphertext_blobs: list[bytes], public_ctx_blob: bytes) -> bytes:
    """Compute c_sum = Σ c_i homomorphically.

    The (1/N) scalar mult is moved to plaintext-side (post-decryption) per
    the v1 simplification — see CLAUDE.md §5.

    Returns the serialized c_sum ciphertext.
    """
    if not ciphertext_blobs:
        raise ValueError("no ciphertexts to aggregate")

    pub_ctx = ts.context_from(public_ctx_blob)
    cts: list[ts.CKKSVector] = [ts.ckks_vector_from(pub_ctx, blob) for blob in ciphertext_blobs]

    csum = cts[0]
    for c in cts[1:]:
        csum = csum + c

    return csum.serialize()


def serialize_for_snark(
    ct_blob: bytes, *, round_t: int, client_id: int
) -> list[int]:
    """Project a serialized ciphertext to its 8-element BN254 Fr digest
    (the SNARK input representation), domain-separated by (round_t, client_id)."""
    return project(ct_blob, round_t=round_t, client_id=client_id)


def serialize_aggregate_for_snark(ct_blob: bytes, *, round_t: int) -> list[int]:
    """Aggregator-side projection of c_sum."""
    return project_for_aggregate(ct_blob, round_t=round_t)


def write_aggregate_blob(out_path: Path, ct_blob: bytes) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(ct_blob)
