"""9-phase round orchestrator. State machine driving each round through:

  1. open       — startRound on chain; accept client commits off-chain
  2. aggregate  — homomorphic FedAvg over received ciphertexts
  3. prove      — generate Groth16 proof (digest-level)
  4. submit     — submitAggregateAndProof on chain
  5. verified   — clients can fetch c_sum

If fewer than N clients submit by deadline → state = failed; clients refund.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ztfa_crypto.poseidon import to_bytes32

from .chain import ChainClient
from .config import Settings
from .homomorphic import homomorphic_sum, serialize_for_snark, write_aggregate_blob
from .prover import prove_round
from .storage import ClientCommit, Round, RoundState, StorageBackend

log = structlog.get_logger()


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        chain: ChainClient,
        storage: StorageBackend,
        session_factory,
    ) -> None:
        self.settings = settings
        self.chain = chain
        self.storage = storage
        self.session_factory = session_factory

    async def open_round(self, t: int) -> None:
        """Phase 1 — start round on chain + create DB row."""
        async with self.session_factory() as session:
            existing = await session.get(Round, t)
            if existing is not None:
                raise ValueError(f"round {t} already exists")
            deadline = datetime.now(UTC) + timedelta(seconds=self.settings.round_period_sec)
            session.add(Round(t=t, state=RoundState.OPEN.value, deadline_ts=deadline))
            await session.commit()
        await asyncio.to_thread(self.chain.start_round, t)
        log.info("round_opened", t=t)

    async def record_client_commit(
        self,
        round_t: int,
        client_id: int,
        h_i_hex: str,
        ciphertext: bytes,
    ) -> str:
        async with self.session_factory() as session:
            blob_uri = await self.storage.put_ciphertext(round_t, client_id, ciphertext)
            session.add(
                ClientCommit(
                    round_t=round_t,
                    client_id=client_id,
                    h_i_hex=h_i_hex,
                    blob_uri=blob_uri,
                )
            )
            await session.commit()
            log.info("client_committed", t=round_t, client=client_id, h=h_i_hex[:14])
            return blob_uri

    async def finalize_round(self, t: int, public_ctx_blob: bytes) -> None:
        """Run phases 2-4: aggregate, prove, submit on chain."""
        async with self.session_factory() as session:
            r = await session.get(Round, t)
            if r is None:
                raise RuntimeError(f"round {t} not found")
            if r.state != RoundState.OPEN.value:
                raise RuntimeError(f"round {t} not open (state={r.state})")
            commits = (
                await session.execute(
                    select(ClientCommit)
                    .where(ClientCommit.round_t == t)
                    .order_by(ClientCommit.created_at)
                )
            ).scalars().all()
            if len(commits) != self.settings.n_clients:
                r.state = RoundState.FAILED.value
                await session.commit()
                raise RuntimeError(
                    f"round {t}: expected {self.settings.n_clients} commits, got {len(commits)}"
                )

            # Phase 2 — homomorphic sum
            r.state = RoundState.AGGREGATING.value
            await session.commit()

            cts = [await self.storage.get_ciphertext(c.blob_uri) for c in commits]
            c_sum = await asyncio.to_thread(homomorphic_sum, cts, public_ctx_blob)
            agg_uri = await self.storage.put_aggregate(t, c_sum)

            # Build digests for the SNARK
            client_digests = [serialize_for_snark(ct) for ct in cts]

            # Phase 3 — prove
            r.state = RoundState.PROVING.value
            await session.commit()

            work_dir = Path("./aggregator/data/proofs") / f"round_{t}"
            snarkjs_cli = (
                Path(self.settings.circuit_build_dir).parent
                / "node_modules"
                / "snarkjs"
                / "cli.js"
            )
            proof, inputs = await prove_round(
                client_digests,
                zkey_path=self.settings.zkey_path,
                work_dir=work_dir,
                snarkjs_cli=snarkjs_cli,
            )

            # h_agg in our v1 spec is computed by the aggregator over c_sum
            # via the digest projection (same as client side). NOTE this is
            # the H_sum in the circuit; we name it H_agg in the contract.
            h_agg_bytes = to_bytes32(inputs.H_sum)

            # Phase 4 — submit on chain
            r.state = RoundState.AWAITING_CHAIN.value
            r.h_agg_hex = "0x" + h_agg_bytes.hex()
            r.aggregate_blob_uri = agg_uri
            await session.commit()

            await asyncio.to_thread(
                self.chain.submit_proof, t, r.h_agg_hex, proof
            )

            # Confirm via on-chain view
            verified = await asyncio.to_thread(self.chain.is_round_verified, t)
            r.state = (
                RoundState.VERIFIED.value if verified else RoundState.FAILED.value
            )
            await session.commit()
            log.info("round_finalized", t=t, verified=verified)

    async def get_round_status(self, t: int) -> dict[str, object] | None:
        async with self.session_factory() as session:
            r = await session.get(Round, t)
            if r is None:
                return None
            commits = (
                await session.execute(select(ClientCommit).where(ClientCommit.round_t == t))
            ).scalars().all()
            return {
                "t": t,
                "state": r.state,
                "clients_submitted": len(commits),
                "deadline": r.deadline_ts.isoformat(),
                "h_agg": r.h_agg_hex,
            }
