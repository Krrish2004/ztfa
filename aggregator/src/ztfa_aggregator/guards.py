"""Runtime invariant guards. Refer to CLAUDE.md §8."""

from __future__ import annotations

from pathlib import Path

import tenseal as ts

from ztfa_crypto.ckks_context import assert_public_only


def load_public_only_context(public_ctx_path: Path) -> ts.Context:
    """Load the CKKS context and ASSERT no secret key.

    Failure here means the deployment is misconfigured and the aggregator
    must not start. CLAUDE.md §8.1, §8.2.
    """
    if not public_ctx_path.exists():
        raise FileNotFoundError(
            f"public CKKS context missing at {public_ctx_path}. "
            "Run scripts/bootstrap.sh to generate it."
        )
    blob = public_ctx_path.read_bytes()
    ctx = ts.context_from(blob)
    assert_public_only(ctx)  # raises if sk is present
    return ctx
