"""Localhost RPC server — bridge from the portal (Next.js) to the client node.

The portal NEVER does crypto in the browser; it talks to this server which
runs alongside the client process. CORS is locked to localhost.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .local_data import accuracy_history, recent_predictions


def make_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="ZTFA Client Local-RPC", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    sqlite_path = settings.data_dir / f"client_{settings.client_id}.sqlite"

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "client_id": settings.client_id}

    @app.get("/round-status")
    def round_status() -> dict[str, object]:
        from .wallet import ClientWallet

        wallet = ClientWallet(
            rpc_url=settings.chain_rpc_url,
            chain_id=settings.chain_id,
            private_key=settings.client_private_key,
            contract_address=settings.federation_round_address,
            per_client_fee_wei=settings.per_client_fee_wei,
        )
        # We probe the last few rounds' verification status
        latest = sorted(
            int(p.stem.split("_")[-1])
            for p in (settings.data_dir / f"models_client_{settings.client_id}").glob(
                "w_global_round_*.pt"
            )
        )
        last_round = latest[-1] if latest else -1
        return {
            "client_id": settings.client_id,
            "last_completed_round": last_round,
            "wallet_address": wallet.address,
        }

    @app.get("/accuracy-history")
    def accuracy() -> list[dict[str, object]]:
        return accuracy_history(sqlite_path)

    @app.get("/recent-predictions")
    def predictions() -> list[dict[str, object]]:
        return recent_predictions(sqlite_path, limit=50)

    return app


def main() -> None:
    import uvicorn

    settings = Settings()
    uvicorn.run(make_app(settings), host="127.0.0.1", port=settings.local_rpc_port)


if __name__ == "__main__":
    main()
