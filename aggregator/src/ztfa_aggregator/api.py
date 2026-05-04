"""FastAPI app — aggregator REST surface (HLD §10.1)."""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Body, Depends, FastAPI, HTTPException, Path
from pydantic import BaseModel

from ztfa_crypto.poseidon import commitment, to_bytes32

from .chain import ChainClient
from .config import Settings
from .guards import load_public_only_context
from .orchestrator import Orchestrator
from .storage import StorageBackend, init_db, make_engine, make_sessionmaker

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    # Invariant: aggregator MUST hold no secret key (CLAUDE.md §8)
    # In cloud-stub mode the public CKKS context and the chain wiring are
    # bootstrapped out-of-band; we still preserve §8.1/§8.2 by never
    # constructing a context with a secret key here.
    public_ctx_blob: bytes = b""
    if settings.public_context_path.exists():
        load_public_only_context(settings.public_context_path)
        public_ctx_blob = settings.public_context_path.read_bytes()
    elif not settings.stub_mode:
        raise FileNotFoundError(
            f"public CKKS context missing at {settings.public_context_path} "
            "and STUB_MODE is not set"
        )
    else:
        log.warning(
            "ckks_public_ctx_missing_stub_mode",
            path=str(settings.public_context_path),
        )

    engine = make_engine(settings.database_url)
    await init_db(engine)
    session_factory = make_sessionmaker(engine)
    storage = StorageBackend(root=settings.keys_dir.parent / "aggregator" / "data" / "blobs")

    chain: ChainClient | None
    if settings.federation_round_address:
        chain = ChainClient(settings)
    elif settings.stub_mode:
        chain = None
        log.warning("chain_not_wired_stub_mode")
    else:
        raise RuntimeError(
            "FEDERATION_ROUND_ADDRESS not set and STUB_MODE is not enabled"
        )

    orchestrator = Orchestrator(settings, chain, storage, session_factory)

    app.state.settings = settings
    app.state.public_ctx_blob = public_ctx_blob
    app.state.orchestrator = orchestrator
    app.state.chain = chain
    log.info(
        "aggregator_started",
        n_clients=settings.n_clients,
        chain=settings.chain_rpc_url,
        contract=settings.federation_round_address,
        stub_mode=settings.stub_mode,
    )
    yield
    await engine.dispose()


app = FastAPI(title="ZTFA Aggregator", version="0.1.0", lifespan=lifespan)


def get_orchestrator() -> Orchestrator:
    return app.state.orchestrator


@app.get("/health")
def health() -> dict[str, object]:
    settings: Settings = app.state.settings if hasattr(app.state, "settings") else Settings()
    return {
        "status": "ok",
        "stub_mode": settings.stub_mode,
        "chain_wired": app.state.chain is not None if hasattr(app.state, "chain") else False,
        "n_clients": settings.n_clients,
    }


@app.get("/v1/round/{t}/status")
async def round_status(
    t: int = Path(ge=0),
    orch: Annotated[Orchestrator, Depends(get_orchestrator)] = ...,  # type: ignore[assignment]
) -> dict[str, object]:
    s = await orch.get_round_status(t)
    if s is None:
        raise HTTPException(status_code=404, detail="round not found")
    return s


class SubmitRequest(BaseModel):
    client_id: int
    ciphertext_b64: str  # base64-encoded serialized CKKS ciphertext


class SubmitResponse(BaseModel):
    receipt_id: str
    h_i: str  # 0x... bytes32 hex


@app.post("/v1/round/{t}/submit")
async def submit_ciphertext(
    t: int,
    req: SubmitRequest,
    orch: Annotated[Orchestrator, Depends(get_orchestrator)] = ...,  # type: ignore[assignment]
) -> SubmitResponse:
    """Client submits their CKKS ciphertext off-chain.

    Sanity check: H_i computed locally from `commitment(t, client_id, ct)`
    should match the H_i the client published on chain (the SNARK is the
    real enforcement; this is a fail-fast hint).
    """
    try:
        ct = base64.b64decode(req.ciphertext_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad base64: {e}") from e

    expected_h = commitment(t, req.client_id, ct)
    expected_h_hex = "0x" + to_bytes32(expected_h).hex()

    blob_uri = await orch.record_client_commit(t, req.client_id, expected_h_hex, ct)
    return SubmitResponse(receipt_id=blob_uri, h_i=expected_h_hex)


@app.get("/v1/round/{t}/aggregate")
async def get_aggregate(
    t: int,
    orch: Annotated[Orchestrator, Depends(get_orchestrator)] = ...,  # type: ignore[assignment]
) -> dict[str, object]:
    """Returns the aggregated ciphertext c_sum (base64) — but only after the
    SNARK has verified on chain. Clients verify on-chain status before
    accepting the blob."""
    chain: ChainClient | None = app.state.chain
    if chain is None:
        raise HTTPException(
            status_code=503, detail="chain not wired (cloud-stub mode)"
        )
    if not chain.is_round_verified(t):
        raise HTTPException(status_code=409, detail="round not verified yet")
    s = await orch.get_round_status(t)
    if s is None or s["h_agg"] is None:
        raise HTTPException(status_code=404, detail="aggregate not available")
    # Pull blob
    from .storage import Round

    async with orch.session_factory() as session:
        r = await session.get(Round, t)
        if r is None or r.aggregate_blob_uri is None:
            raise HTTPException(status_code=404, detail="aggregate blob missing")
        blob = await orch.storage.get_aggregate(r.aggregate_blob_uri)
    return {
        "ct_sum_b64": base64.b64encode(blob).decode(),
        "h_agg": s["h_agg"],
        "n_clients": app.state.settings.n_clients,
    }


@app.get("/v1/keys/joint-public")
def joint_public() -> dict[str, str]:
    """v1: returns the pre-distributed CKKS public context, base64-encoded."""
    blob: bytes = app.state.public_ctx_blob
    if not blob:
        raise HTTPException(
            status_code=503,
            detail="public CKKS context not yet bootstrapped (cloud-stub mode)",
        )
    return {"public_context_b64": base64.b64encode(blob).decode()}


class StartRoundRequest(BaseModel):
    t: int


@app.post("/v1/round/start")
async def start_round_endpoint(
    body: StartRoundRequest,
    orch: Annotated[Orchestrator, Depends(get_orchestrator)] = ...,  # type: ignore[assignment]
) -> dict[str, str]:
    if app.state.chain is None:
        raise HTTPException(
            status_code=503,
            detail="chain not wired (cloud-stub mode); deploy contracts and set FEDERATION_ROUND_ADDRESS",
        )
    await orch.open_round(body.t)
    return {"status": "started", "t": str(body.t)}


@app.post("/v1/round/{t}/finalize")
async def finalize_round_endpoint(
    t: int,
    orch: Annotated[Orchestrator, Depends(get_orchestrator)] = ...,  # type: ignore[assignment]
) -> dict[str, str]:
    """Triggers homomorphic-sum + proof + chain-submit (phases 2-4)."""
    if app.state.chain is None or not app.state.public_ctx_blob:
        raise HTTPException(
            status_code=503,
            detail="cloud-stub mode: chain or CKKS public context not wired",
        )
    await orch.finalize_round(t, app.state.public_ctx_blob)
    return {"status": "finalized", "t": str(t)}


@app.post("/v1/keys/dkg/contribute")
def dkg_contribute_stub() -> dict[str, str]:
    """v1 stub. v2 implements multi-party threshold-DKG."""
    raise HTTPException(
        status_code=501,
        detail="threshold-DKG not implemented in v1 (single-issuer key model — see HLD §13.1)",
    )


def main() -> None:
    import os
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("ztfa_aggregator.api:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
