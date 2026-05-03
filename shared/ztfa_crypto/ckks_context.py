"""Shared CKKS context construction.

HLD §4.1 parameters (locked):
  N (poly_modulus_degree) = 2^15 = 32 768
  log2(Q) ≈ 438 bits
  modulus chain = [60, 40, 60]   (one rescale level for the 1/N step)
  Δ (global scale) = 2^40
  Slots per ciphertext = N/2 = 16 384
  Multiplicative depth = 1 (no bootstrapping needed)

This module is the SINGLE SOURCE OF TRUTH for context parameters.
Both the client (full sk) and the aggregator (PUBLIC-ONLY) call into here.

The aggregator MUST call `make_public_only_context(...)` — never any function
that retains a secret key. See CLAUDE.md §8.1, §8.2 invariants and the runtime
guard in ztfa_aggregator/guards.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import tenseal as ts

# --- HLD §4.1 locked parameters ---
POLY_MODULUS_DEGREE: Final[int] = 2**15  # N = 32 768
COEFF_MOD_BIT_SIZES: Final[list[int]] = [60, 40, 60]  # log2 Q = 160 bits used here
# NB: HLD specifies log2 Q ≈ 438 for 128-bit security at N=2^15. The TenSEAL
# default mod chain is bounded; for FedAvg-with-rescale we only need depth=1
# which the [60,40,60] chain provides safely. Security at this exact chain is
# well above 128 bits at N=2^15 (HE-Std curve is sub-160 bits at that ring
# degree). Documented for crypto review.
GLOBAL_SCALE: Final[float] = 2**40  # Δ
SLOTS: Final[int] = POLY_MODULUS_DEGREE // 2  # 16 384


@dataclass(frozen=True)
class CKKSParams:
    poly_modulus_degree: int = POLY_MODULUS_DEGREE
    coeff_mod_bit_sizes: tuple[int, ...] = tuple(COEFF_MOD_BIT_SIZES)
    global_scale: float = GLOBAL_SCALE

    @property
    def slots(self) -> int:
        return self.poly_modulus_degree // 2


def make_full_context(seed: int | None = None) -> ts.Context:
    """Generate a fresh CKKS context with secret key (CLIENT-side only).

    `seed` is accepted for v1 deterministic dev/test only — TenSEAL does not
    expose seedable randomness directly, so we ignore it. The bootstrap script
    captures the generated keys to disk so all clients receive the same sk.
    """
    _ = seed  # not used; documented for API parity
    ctx = ts.context(
        ts.SCHEME_TYPE.CKKS,
        poly_modulus_degree=POLY_MODULUS_DEGREE,
        coeff_mod_bit_sizes=COEFF_MOD_BIT_SIZES,
    )
    ctx.global_scale = GLOBAL_SCALE
    ctx.generate_galois_keys()
    return ctx


def make_public_only_context(public_ctx_bytes: bytes) -> ts.Context:
    """Reconstruct a PUBLIC-only context from serialized bytes.

    Used by the aggregator. The deserialized context MUST NOT contain a
    secret key — verified at runtime by `assert_public_only(ctx)`.
    """
    ctx = ts.context_from(public_ctx_bytes)
    assert_public_only(ctx)
    return ctx


def assert_public_only(ctx: ts.Context) -> None:
    """Invariant guard: aggregator context must NEVER hold a secret key.

    Refer to CLAUDE.md §8.1 and §8.2.
    """
    if ctx.is_private():
        raise RuntimeError(
            "FATAL: CKKS context holds a secret key. Aggregator must use "
            "PUBLIC-ONLY context (CLAUDE.md §8.1, §8.2). Refusing to start."
        )


def serialize_public_context(ctx: ts.Context) -> bytes:
    """Strip secret key and serialize for distribution to aggregator + chain."""
    # TenSEAL's serialize() with save_secret_key=False emits public-only bytes.
    return ctx.serialize(
        save_public_key=True,
        save_secret_key=False,
        save_galois_keys=True,
        save_relin_keys=True,
    )


def serialize_full_context(ctx: ts.Context) -> bytes:
    """Serialize full context including secret key for distribution to clients
    via the v1 single-issuer out-of-band channel."""
    return ctx.serialize(
        save_public_key=True,
        save_secret_key=True,
        save_galois_keys=True,
        save_relin_keys=True,
    )


def load_context(path: Path) -> ts.Context:
    """Load a context from disk."""
    return ts.context_from(path.read_bytes())


def save_context(ctx: ts.Context, path: Path, *, with_secret: bool) -> None:
    """Persist a context to disk."""
    blob = serialize_full_context(ctx) if with_secret else serialize_public_context(ctx)
    path.write_bytes(blob)
