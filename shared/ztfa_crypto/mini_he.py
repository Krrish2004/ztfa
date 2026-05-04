"""Minimal RLWE additive homomorphic encryption.

Replaces TenSEAL/CKKS in v1 to allow the SNARK to operate on full polynomial
coefficients. Semantically equivalent for FedAvg (additive over fixed-point
quantized weights).

Scheme:
    R_q = Z_q[X] / (X^N + 1)         negacyclic ring
    sk:  s ∈ R_q with small ternary coefficients (-1, 0, 1)
    pk:  (a, b) where a ← R_q uniform, b = -a*s + e (mod q), e small Gaussian
    Enc(m):  pick u ∈ R_q ternary, e1, e2 small Gaussian
             c0 = a*u + e1
             c1 = b*u + e2 + Δ * encode(m)
    Dec(c0, c1):  m̃ = (c1 + s*c0) / Δ ≈ encode(m)
    Add: (c0_a + c0_b, c1_a + c1_b) — homomorphic addition in R_q × R_q

Parameters (v1 locked):
    N = 256
    q = 2^60 - 2^52 + 1                     (60-bit prime; fits in BN254 Fr)
    Δ = 2^32                                (fixed-point scale)
    SLOTS = N (raw coefficient packing; no NTT)

Encoding of a real-valued vector w ∈ ℝ^k (k ≤ N) into a plaintext polynomial:
    pt[j] = round(w[j] * Δ) mod q   for j ∈ [0, k)
    pt[j] = 0                       for j ∈ [k, N)

This is "scaled-integer" packing — simpler than CKKS encode/decode and
sufficient for fixed-point FedAvg.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

# --- Locked v1 parameters ---
# RING_N=128 keeps the SNARK at ~245k constraints (ptau-18), provable in
# 30-60s. Big enough for a 15→4→4 MLP (84 weights) — still a real model.
RING_N: Final[int] = 128          # polynomial degree
PRIME_Q: Final[int] = (1 << 60) - (1 << 52) + 1  # ≈ 2^60, fits in BN254 Fr
SCALE_DELTA: Final[int] = 1 << 32  # fixed-point scale 2^32
ERR_BOUND: Final[int] = 8          # Gaussian error std bound (small)


def _ternary(rng: np.random.Generator, n: int = RING_N) -> np.ndarray:
    """Sample a uniformly random ternary polynomial in {-1, 0, +1}^n."""
    return rng.integers(-1, 2, size=n, dtype=np.int64)


def _small_gauss(rng: np.random.Generator, n: int = RING_N, sigma: int = 3) -> np.ndarray:
    """Centered discrete Gaussian-ish (clipped uniform) error for noise."""
    e = rng.integers(-sigma, sigma + 1, size=n, dtype=np.int64)
    return e


def _uniform_q(rng: np.random.Generator, n: int = RING_N) -> np.ndarray:
    """Uniformly random in Z_q^n."""
    return rng.integers(0, PRIME_Q, size=n, dtype=np.int64)


def _negacyclic_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Multiply two polynomials in R_q = Z_q[X] / (X^N + 1).

    Naive schoolbook implementation in O(N²); fine at N=256 for v1 demo.
    """
    n = RING_N
    out = np.zeros(n, dtype=np.int64)
    # Compute the full convolution then reduce X^n = -1
    a64 = a.astype(np.int64)
    b64 = b.astype(np.int64)
    for i in range(n):
        ai = int(a64[i])
        if ai == 0:
            continue
        for j in range(n):
            k = i + j
            term = (ai * int(b64[j])) % PRIME_Q
            if k < n:
                out[k] = (out[k] + term) % PRIME_Q
            else:
                # X^n = -1 ⇒ x^k = -x^(k-n)
                out[k - n] = (out[k - n] - term) % PRIME_Q
    return out % PRIME_Q


def _add_q(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a.astype(np.int64) + b.astype(np.int64)) % PRIME_Q


@dataclass(frozen=True)
class PublicKey:
    a: tuple[int, ...]   # length RING_N coefficients in [0, q)
    b: tuple[int, ...]

    def to_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        return np.array(self.a, dtype=np.int64), np.array(self.b, dtype=np.int64)

    def to_json(self) -> str:
        return json.dumps({"a": list(self.a), "b": list(self.b)})

    @classmethod
    def from_json(cls, s: str) -> "PublicKey":
        d = json.loads(s)
        return cls(a=tuple(d["a"]), b=tuple(d["b"]))


@dataclass(frozen=True)
class SecretKey:
    s: tuple[int, ...]   # ternary coefficients but stored mod q

    def to_array(self) -> np.ndarray:
        return np.array(self.s, dtype=np.int64)

    def to_json(self) -> str:
        return json.dumps({"s": list(self.s)})

    @classmethod
    def from_json(cls, s: str) -> "SecretKey":
        d = json.loads(s)
        return cls(s=tuple(d["s"]))


@dataclass(frozen=True)
class Ciphertext:
    c0: tuple[int, ...]   # length RING_N
    c1: tuple[int, ...]

    def to_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        return np.array(self.c0, dtype=np.int64), np.array(self.c1, dtype=np.int64)

    def serialize(self) -> bytes:
        """Deterministic 16-byte-per-coef serialization (big-endian)."""
        out = bytearray()
        for v in self.c0:
            out += int(v).to_bytes(16, "big")
        for v in self.c1:
            out += int(v).to_bytes(16, "big")
        return bytes(out)

    @classmethod
    def deserialize(cls, blob: bytes) -> "Ciphertext":
        n = RING_N
        if len(blob) != 16 * 2 * n:
            raise ValueError(f"expected {16 * 2 * n} bytes, got {len(blob)}")
        c0 = tuple(int.from_bytes(blob[i * 16 : (i + 1) * 16], "big") for i in range(n))
        c1 = tuple(
            int.from_bytes(blob[(n + i) * 16 : (n + i + 1) * 16], "big") for i in range(n)
        )
        return cls(c0=c0, c1=c1)


# --- Keygen / Enc / Dec / Add ---


def keygen(seed: int | None = None) -> tuple[PublicKey, SecretKey]:
    rng = np.random.default_rng(seed if seed is not None else secrets.randbelow(1 << 64))
    s = _ternary(rng)
    a = _uniform_q(rng)
    e = _small_gauss(rng)
    # b = -a*s + e
    a_s = _negacyclic_mul(a, s)
    b = ((-a_s + e) % PRIME_Q + PRIME_Q) % PRIME_Q
    return (
        PublicKey(a=tuple(int(x) for x in a), b=tuple(int(x) for x in b)),
        SecretKey(s=tuple(int(x) for x in (s % PRIME_Q + PRIME_Q) % PRIME_Q)),
    )


def encode(weights: np.ndarray) -> np.ndarray:
    """Real vector → integer plaintext polynomial mod q.

    Pads to RING_N with zeros. Quantizes via Δ.
    """
    if weights.ndim != 1:
        raise ValueError("expected 1-D vector")
    if weights.size > RING_N:
        raise ValueError(f"vector length {weights.size} > RING_N {RING_N}")
    pt = np.zeros(RING_N, dtype=np.int64)
    scaled = np.round(weights.astype(np.float64) * SCALE_DELTA).astype(np.int64)
    pt[: weights.size] = scaled % PRIME_Q
    return pt


def decode(pt: np.ndarray, n_real: int) -> np.ndarray:
    """Inverse of `encode` — integer plaintext → real vector."""
    # Recenter mod q (negative numbers wrap)
    half = PRIME_Q // 2
    centered = np.where(pt > half, pt - PRIME_Q, pt)
    return (centered[:n_real].astype(np.float64) / SCALE_DELTA)


def encrypt(pk: PublicKey, weights: np.ndarray, *, seed: int | None = None) -> Ciphertext:
    """Encrypt a real-valued weight vector (length ≤ RING_N) → Ciphertext."""
    rng = np.random.default_rng(seed if seed is not None else secrets.randbelow(1 << 64))
    a, b = pk.to_arrays()
    pt = encode(weights)

    u = _ternary(rng)
    e1 = _small_gauss(rng)
    e2 = _small_gauss(rng)

    # c0 = a*u + e1
    c0 = (_negacyclic_mul(a, u) + e1) % PRIME_Q
    # c1 = b*u + e2 + pt   (no extra Δ — pt already scaled by Δ in encode())
    c1 = (_negacyclic_mul(b, u) + e2 + pt) % PRIME_Q

    return Ciphertext(
        c0=tuple(int(x) for x in (c0 % PRIME_Q + PRIME_Q) % PRIME_Q),
        c1=tuple(int(x) for x in (c1 % PRIME_Q + PRIME_Q) % PRIME_Q),
    )


def decrypt(sk: SecretKey, ct: Ciphertext, *, n_real: int) -> np.ndarray:
    """Decrypt → real vector of length `n_real`."""
    s = sk.to_array()
    c0, c1 = ct.to_arrays()
    # m̃ = c1 + s*c0
    m_scaled = (c1 + _negacyclic_mul(c0, s)) % PRIME_Q
    return decode(m_scaled, n_real)


def add(ct1: Ciphertext, ct2: Ciphertext) -> Ciphertext:
    """Homomorphic addition WITHOUT mod-q reduction.

    Coefficients accumulate into [0, k·q) for k clients. This is essential
    so that the SNARK constraint `c_sum[k] = Σ c[i][k]` holds in BN254 Fr
    arithmetic — with mod-q reduction on the aggregator side, the witness
    sum would not equal the on-chain commit's preimage.

    Decryption (`decrypt`) handles the mod-q reduction at the final stage,
    so this is semantically equivalent.
    """
    a1, b1 = ct1.to_arrays()
    a2, b2 = ct2.to_arrays()
    c0 = a1 + a2
    c1 = b1 + b2
    return Ciphertext(
        c0=tuple(int(x) for x in c0),
        c1=tuple(int(x) for x in c1),
    )


def add_many(cts: list[Ciphertext]) -> Ciphertext:
    if not cts:
        raise ValueError("empty list")
    acc = cts[0]
    for c in cts[1:]:
        acc = add(acc, c)
    return acc


def coefficients_for_snark(ct: Ciphertext) -> list[int]:
    """Flatten (c0, c1) into a single 2N-length vector of BN254-Fr-compatible
    integers (each coef is < q < 2^60 < BN254 Fr).
    """
    return list(ct.c0) + list(ct.c1)


# --- Persistence ---


def save_keys(pk: PublicKey, sk: SecretKey, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "minihe_pk.json").write_text(pk.to_json())
    (out_dir / "minihe_sk.json").write_text(sk.to_json())


def load_pk(path: Path) -> PublicKey:
    return PublicKey.from_json(path.read_text())


def load_sk(path: Path) -> SecretKey:
    return SecretKey.from_json(path.read_text())
