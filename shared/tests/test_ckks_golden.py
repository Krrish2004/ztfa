"""CKKS golden-vector tests (CLAUDE.md §12.E).

Verifies the FedAvg-relevant invariants:
  1. encrypt → decrypt round-trip (within ε)
  2. Σ plaintexts == decrypt(Σ ciphertexts)        (homomorphic add)
  3. p × ct decrypts to p × pt                     (plaintext-scalar mult, depth=1)
  4. CKKS context can be serialized public-only and round-tripped
"""

from __future__ import annotations

import numpy as np
import pytest
import tenseal as ts

from ztfa_crypto.ckks_context import (
    assert_public_only,
    make_full_context,
    serialize_full_context,
    serialize_public_context,
)

EPS_DECRYPT = 1e-3   # CKKS approximation noise; very loose for float64
EPS_HOMO = 1e-2      # extra noise budget after homomorphic ops


def _vec(n: int, scale: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.uniform(-scale, scale, size=n).astype(np.float64)


def test_roundtrip() -> None:
    ctx = make_full_context()
    w = _vec(100)
    ct = ts.ckks_vector(ctx, w)
    out = np.array(ct.decrypt())
    assert out.shape == w.shape
    assert np.max(np.abs(out - w)) < EPS_DECRYPT


def test_homomorphic_addition() -> None:
    """Σ plaintexts == Dec(Σ ciphertexts)."""
    ctx = make_full_context()
    n_clients = 3
    weights = [_vec(50) for _ in range(n_clients)]
    cts = [ts.ckks_vector(ctx, w) for w in weights]
    csum = cts[0]
    for c in cts[1:]:
        csum = csum + c
    out = np.array(csum.decrypt())
    expected = np.sum(weights, axis=0)
    assert np.max(np.abs(out - expected)) < EPS_HOMO


def test_fedavg_with_scalar_mult() -> None:
    """c_agg = (Σ c_i) ⊗ (1/N); Dec(c_agg) ≈ mean(weights)."""
    ctx = make_full_context()
    n = 3
    weights = [_vec(50) for _ in range(n)]
    cts = [ts.ckks_vector(ctx, w) for w in weights]
    csum = cts[0]
    for c in cts[1:]:
        csum = csum + c
    cagg = csum * (1.0 / n)
    out = np.array(cagg.decrypt())
    expected = np.mean(weights, axis=0)
    assert np.max(np.abs(out - expected)) < EPS_HOMO


def test_public_context_serialize_roundtrip() -> None:
    """Strip secret, deserialize, ensure no sk leaked but homomorphic ops still work."""
    full_ctx = make_full_context()
    pub_blob = serialize_public_context(full_ctx)
    pub_ctx = ts.context_from(pub_blob)
    assert_public_only(pub_ctx)  # MUST NOT raise

    # The aggregator (with pub_ctx only) must still be able to add ciphertexts
    # encrypted by the client (with full_ctx).
    w1 = _vec(20)
    w2 = _vec(20)
    ct1 = ts.ckks_vector(full_ctx, w1)
    ct2 = ts.ckks_vector(full_ctx, w2)

    # Simulate over-the-wire: serialize with pk attached
    blob1 = ct1.serialize()
    blob2 = ct2.serialize()
    ct1_at_aggr = ts.ckks_vector_from(pub_ctx, blob1)
    ct2_at_aggr = ts.ckks_vector_from(pub_ctx, blob2)
    csum_at_aggr = ct1_at_aggr + ct2_at_aggr
    cagg_at_aggr = csum_at_aggr * 0.5

    # Aggregator returns to client; client decrypts
    cagg_blob = cagg_at_aggr.serialize()
    cagg_at_client = ts.ckks_vector_from(full_ctx, cagg_blob)
    out = np.array(cagg_at_client.decrypt())
    expected = (w1 + w2) / 2
    assert np.max(np.abs(out - expected)) < EPS_HOMO


def test_full_context_carries_secret_key() -> None:
    full_ctx = make_full_context()
    full_blob = serialize_full_context(full_ctx)
    rehydrated = ts.context_from(full_blob)
    assert rehydrated.is_private(), "full context must carry secret key"


def test_assert_public_only_raises_on_full_context() -> None:
    full_ctx = make_full_context()
    with pytest.raises(RuntimeError, match="FATAL"):
        assert_public_only(full_ctx)
