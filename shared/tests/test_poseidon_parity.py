"""Poseidon Python ↔ circomlib parity tests.

Verifies the Python bridge produces byte-for-byte identical output to the
circomlib reference (already verified live during development; this locks
the result down as a regression test).
"""

from __future__ import annotations

import pytest

from ztfa_crypto.poseidon import (
    BN254_FR,
    commitment,
    poseidon2,
    poseidon_bytes,
    poseidon_chain,
    to_bytes32,
)

# Reference vectors from circomlibjs (verified by independent calls).
REFERENCE_POSEIDON_1_2 = (
    0x115CC0F5E7D690413DF64C6B9662E9CF2A3617F2743245519E19607A4417189A
)


def test_circomlib_reference_vector() -> None:
    """The single most important test: Poseidon(1, 2) must equal the
    well-known circomlibjs reference. If this fails, Python ↔ circuit
    parity is broken and ALL commits will mismatch."""
    assert poseidon2(1, 2) == REFERENCE_POSEIDON_1_2


def test_poseidon2_modular_reduction() -> None:
    """Inputs > BN254 prime are reduced modulo Fr."""
    assert poseidon2(1, 2) == poseidon2(1 + BN254_FR, 2)
    assert poseidon2(1, 2) == poseidon2(1, 2 + 2 * BN254_FR)


def test_chain_zero_element() -> None:
    """chain([]) = 0 by convention."""
    assert poseidon_chain([]) == 0


def test_chain_singleton() -> None:
    """chain([x]) = Poseidon(0, x)."""
    assert poseidon_chain([42]) == poseidon2(0, 42)


def test_chain_associativity_via_left_fold() -> None:
    """chain([a, b, c]) = Poseidon(Poseidon(Poseidon(0, a), b), c)."""
    a, b, c = 11, 22, 33
    expected = poseidon2(poseidon2(poseidon2(0, a), b), c)
    assert poseidon_chain([a, b, c]) == expected


def test_poseidon_bytes_31byte_chunking() -> None:
    """≤31-byte input fits in one field element."""
    data = b"hello"
    one_chunk = int.from_bytes(data, "big")
    assert poseidon_bytes(data) == poseidon_chain([one_chunk])


def test_poseidon_bytes_multi_chunk() -> None:
    """A 62-byte input splits into 2 chunks of 31 bytes each."""
    data = bytes(range(62))
    chunk1 = int.from_bytes(data[:31], "big")
    chunk2 = int.from_bytes(data[31:62], "big")
    assert poseidon_bytes(data) == poseidon_chain([chunk1, chunk2])


def test_commitment_domain_separation_against_replay() -> None:
    """T9 defense: same ciphertext in different rounds → different commits."""
    ct = b"some ciphertext bytes"
    h_t1 = commitment(round_index=1, client_id=2, ciphertext_bytes=ct)
    h_t2 = commitment(round_index=2, client_id=2, ciphertext_bytes=ct)
    assert h_t1 != h_t2, "domain separation by round index broken"


def test_commitment_domain_separation_by_client_id() -> None:
    """Same ct, same round, different client → different commit."""
    ct = b"some ciphertext bytes"
    h_a = commitment(round_index=1, client_id=1, ciphertext_bytes=ct)
    h_b = commitment(round_index=1, client_id=2, ciphertext_bytes=ct)
    assert h_a != h_b


def test_commitment_deterministic() -> None:
    """Same inputs → same commit (any failure here means the bridge is leaking
    state across calls)."""
    ct = b"x" * 200
    assert commitment(7, 3, ct) == commitment(7, 3, ct)


def test_to_bytes32_length_and_endianness() -> None:
    h = poseidon2(1, 2)
    b = to_bytes32(h)
    assert len(b) == 32
    assert int.from_bytes(b, "big") == h


@pytest.mark.parametrize("value", [0, 1, BN254_FR - 1])
def test_to_bytes32_edge_values(value: int) -> None:
    out = to_bytes32(value)
    assert len(out) == 32
