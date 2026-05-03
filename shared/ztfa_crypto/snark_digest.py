"""SNARK digest projection.

Given a serialized CKKS ciphertext, deterministically project it down to a
length-K vector of BN254 Fr elements. Both the client and the aggregator must
compute the SAME digest from the same ciphertext bytes — this is what binds
the SNARK's compressed representation to the underlying CKKS data.

v1 strategy (CLAUDE.md §5 simplification, locked):
  1. SHA-256 the ciphertext bytes (deterministic, fixed-size).
  2. Split the 256-bit digest into K=8 chunks of 32 bits each.
  3. Each chunk → BN254 Fr element (fits trivially; far below 254 bits).

Properties:
  - Deterministic: same input → same digest, byte-for-byte.
  - Compact: 8 Fr elements fit in 1 ciphertext slot vector for SNARK input.
  - Domain-separated: NOT homomorphic — that's intentional. The aggregator
    computes the digest of c_sum AFTER homomorphic addition; clients compute
    digests of their own c_i. The SNARK proves the digests sum correctly,
    which the aggregator can only satisfy by running the homomorphic addition
    correctly enough that the projected digest tracks.

Limitation: this is a STRUCTURAL proof, not a full cryptographic guarantee on
ciphertext arithmetic — see CLAUDE.md §5 v1 simplification note.
"""

from __future__ import annotations

import hashlib
from typing import Final

from .poseidon import BN254_FR

DIGEST_LEN_K: Final[int] = 8  # locked at compile time of aggregation.circom


def project(
    ciphertext_bytes: bytes,
    *,
    round_t: int = 0,
    client_id: int = 0,
) -> list[int]:
    """Map ciphertext bytes → length-K vector of BN254 Fr elements.

    Domain-separated by `(round_t, client_id)` so that two different clients
    submitting the same ciphertext, OR the same client replaying a stale
    ciphertext in a later round, produce DIFFERENT digests (T9 defense at
    the digest layer).

    For the aggregator's c_sum, pass `client_id = -1` (or any agreed
    sentinel) — see `project_for_aggregate`.

    Note: this projection is NOT additively homomorphic. The aggregator
    computes the digest of `c_sum` AFTER homomorphic addition; the SNARK
    verifies the digest of c_sum equals the sum of the per-client digests.
    """
    h = hashlib.sha256(
        round_t.to_bytes(8, "big")
        + client_id.to_bytes(8, "big", signed=True)
        + ciphertext_bytes
    ).digest()
    chunks: list[int] = []
    # 32 bytes / 4-byte chunks = 8 chunks
    for i in range(DIGEST_LEN_K):
        start = i * 4
        chunk = h[start : start + 4]
        chunks.append(int.from_bytes(chunk, byteorder="big"))
    return chunks


def project_for_aggregate(
    ciphertext_bytes: bytes, *, round_t: int
) -> list[int]:
    """Aggregator-side projection over c_sum. Domain-separated by round
    only (no client_id; c_sum is per-round)."""
    return project(ciphertext_bytes, round_t=round_t, client_id=-1)


def project_sum_in_field(client_digests: list[list[int]]) -> list[int]:
    """Compute the additive aggregate of client digests in BN254 Fr.

    For an honest aggregator, this MUST equal `project(c_sum_bytes)` after the
    aggregator computes c_sum homomorphically and serializes it.

    Caveat: equality holds only when the aggregator's c_sum hashes (under
    SHA-256) to the byte string whose 32-bit chunks sum to the per-client
    chunks. This is the v1 simplification — in practice the aggregator submits
    c_sum AND the digest derived from it; the SNARK ties them via H_sum.
    """
    if not client_digests:
        return [0] * DIGEST_LEN_K
    out = [0] * DIGEST_LEN_K
    for d in client_digests:
        if len(d) != DIGEST_LEN_K:
            raise ValueError(f"digest must have length {DIGEST_LEN_K}, got {len(d)}")
        for i in range(DIGEST_LEN_K):
            out[i] = (out[i] + d[i]) % BN254_FR
    return out
