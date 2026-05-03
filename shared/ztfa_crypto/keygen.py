"""v1 single-issuer keygen.

INSECURE FOR PRODUCTION. v1 simplification per HLD §4.2:
  - Federation initiator generates (pk, sk) once at federation launch
  - pk is published to aggregator + smart contract + all clients
  - sk is distributed to clients over a secure out-of-band channel
    (here: local file copy on the dev machine)

For v2: replace with multi-party threshold-DKG ceremony (Mouchet et al. 2021),
producing (pk, {sk_share_i}) such that no party ever holds the full sk.
See HLD §13.1 and CLAUDE.md §13.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .ckks_context import (
    CKKSParams,
    make_full_context,
    save_context,
)


@dataclass(frozen=True)
class KeyArtifacts:
    """Files written by run_keygen()."""

    public_context_path: Path  # to aggregator + chain
    full_context_path: Path  # to clients (sk-bearing)
    metadata_path: Path  # human-readable params + provenance


def run_keygen(out_dir: Path) -> KeyArtifacts:
    """Generate CKKS context and split into public + full artifacts."""
    out_dir.mkdir(parents=True, exist_ok=True)

    ctx = make_full_context()

    public_path = out_dir / "ckks_public.bin"
    full_path = out_dir / "ckks_full.bin"
    save_context(ctx, public_path, with_secret=False)
    save_context(ctx, full_path, with_secret=True)

    metadata = {
        "scheme": "CKKS",
        "version": "v1-single-issuer",
        "params": {
            "poly_modulus_degree": CKKSParams().poly_modulus_degree,
            "coeff_mod_bit_sizes": list(CKKSParams().coeff_mod_bit_sizes),
            "global_scale_log2": 40,
            "slots": CKKSParams().slots,
            "multiplicative_depth": 1,
        },
        "files": {
            "public_context": public_path.name,
            "full_context": full_path.name,
        },
        "warning": (
            "INSECURE FOR PRODUCTION. v1 single-issuer key model. "
            "v2 replaces with threshold-DKG (HLD §13.1)."
        ),
    }
    metadata_path = out_dir / "keygen_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    return KeyArtifacts(
        public_context_path=public_path,
        full_context_path=full_path,
        metadata_path=metadata_path,
    )


def main() -> None:
    """CLI: python -m ztfa_crypto.keygen [out_dir]."""
    import sys

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "./keys")
    artifacts = run_keygen(out)
    print(f"  ✓ public context  → {artifacts.public_context_path}")
    print(f"  ✓ full context    → {artifacts.full_context_path}")
    print(f"  ✓ metadata        → {artifacts.metadata_path}")
    print()
    print("  ⚠ INSECURE: v1 single-issuer key model. See HLD §4.2 / §13.1.")


if __name__ == "__main__":
    main()
