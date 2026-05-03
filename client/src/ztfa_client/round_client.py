"""Per-round orchestrator on the client side.

Drives the 9-phase protocol from the client's POV:
  1. wait for round t to be open on chain
  2. local train E epochs from latest decrypted w_global
  3. encrypt → c_i, compute commitment H_i
  4. submit H_i on chain (paid: per_client_fee)
  5. POST c_i to aggregator off-chain
  6. wait until isRoundVerified(t) on chain
  7. fetch c_sum from aggregator, decrypt, divide by N
  8. update local model + record per-round accuracy
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import structlog
import torch

from .ckks_engine import ClientCKKSEngine
from .config import Settings
from .features import FeatureNormStats, feature_matrix, label_vector
from .local_data import labeled_dataframe, write_accuracy
from .trainer import HARMLP, evaluate, flatten_state_dict, load_flat_into_model, train_one_round
from .wallet import ClientWallet

log = structlog.get_logger()


@dataclass
class RoundOutcome:
    round_t: int
    succeeded: bool
    pre_train_accuracy: float | None
    post_round_accuracy: float | None
    final_loss: float | None
    note: str = ""


class ClientRoundOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = ClientCKKSEngine(settings.full_context_path)
        self.wallet = ClientWallet(
            rpc_url=settings.chain_rpc_url,
            chain_id=settings.chain_id,
            private_key=settings.client_private_key,
            contract_address=settings.federation_round_address,
            per_client_fee_wei=settings.per_client_fee_wei,
        )
        self.norm = FeatureNormStats.load(settings.feature_norm_path)
        self.sqlite_path = settings.data_dir / f"client_{settings.client_id}.sqlite"
        self.model_dir = settings.data_dir / f"models_client_{settings.client_id}"
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def _model_path(self, round_t: int) -> Path:
        return self.model_dir / f"w_global_round_{round_t}.pt"

    def load_latest_model(self) -> tuple[HARMLP, int]:
        """Return (model, last_round). For round 0, loads the seed weights."""
        # Find the highest round_t we've stored
        rounds = sorted(int(p.stem.split("_")[-1]) for p in self.model_dir.glob("w_global_round_*.pt"))
        model = HARMLP()
        if rounds:
            last_t = rounds[-1]
            sd = torch.load(self._model_path(last_t), weights_only=True)
            model.load_state_dict(sd)
            return model, last_t
        # Cold start: load seed
        seed_path = self.settings.initial_weights_path
        if seed_path.exists():
            sd = torch.load(seed_path, weights_only=True)
            model.load_state_dict(sd)
            return model, -1
        return model, -1

    def _split_local_data(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        df = labeled_dataframe(self.sqlite_path)
        if len(df) < 10:
            raise RuntimeError(
                f"insufficient labeled data: {len(df)} rows. Run iot-simulator longer."
            )
        # 80/20 train/eval split (deterministic by row order)
        n_train = int(len(df) * 0.8)
        train_df = df.iloc[:n_train]
        eval_df = df.iloc[n_train:]
        return (
            feature_matrix(train_df, self.norm),
            label_vector(train_df),
            feature_matrix(eval_df, self.norm),
            label_vector(eval_df),
        )

    async def run_round(self, round_t: int, *, n_weights: int | None = None) -> RoundOutcome:
        log.info("round_start", t=round_t, client_id=self.settings.client_id)
        model, last_t = self.load_latest_model()

        try:
            X_tr, y_tr, X_ev, y_ev = self._split_local_data()
        except RuntimeError as e:
            return RoundOutcome(round_t, False, None, None, None, note=str(e))

        pre_acc = evaluate(model, X_ev, y_ev)
        result = train_one_round(
            model,
            X_tr,
            y_tr,
            epochs=5,
            batch_size=32,
            lr=1e-2,
            seed=round_t * 100 + self.settings.client_id,
        )
        if n_weights is not None and result.flat_weights.size != n_weights:
            log.warning(
                "weight_count_mismatch",
                expected=n_weights,
                actual=result.flat_weights.size,
            )

        # Encrypt + commit
        ct_bytes = self.engine.encrypt_weights(result.flat_weights)
        h_i_bytes = self.engine.commit(
            round_t=round_t, client_id=self.settings.client_id, ciphertext_bytes=ct_bytes
        )

        # Submit on chain
        await asyncio.to_thread(self.wallet.submit_commitment, round_t, h_i_bytes)

        # POST ciphertext off-chain
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.settings.aggregator_url}/v1/round/{round_t}/submit",
                json={
                    "client_id": self.settings.client_id,
                    "ciphertext_b64": base64.b64encode(ct_bytes).decode(),
                },
            )
            resp.raise_for_status()

        # Wait for on-chain verify
        for _ in range(120):
            if await asyncio.to_thread(self.wallet.is_round_verified, round_t):
                break
            await asyncio.sleep(2)
        else:
            return RoundOutcome(
                round_t, False, pre_acc, None, result.final_loss, note="timeout waiting for verify"
            )

        # Fetch aggregate
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.settings.aggregator_url}/v1/round/{round_t}/aggregate"
            )
            resp.raise_for_status()
            doc = resp.json()
            ct_sum_blob = base64.b64decode(doc["ct_sum_b64"])

        avg_weights = self.engine.decrypt_aggregate(
            ct_sum_blob,
            n_clients=self.settings.n_clients,
            n_weights=result.flat_weights.size,
        )

        # Update local model with the federated aggregate
        load_flat_into_model(model, avg_weights)
        post_acc = evaluate(model, X_ev, y_ev)

        # Persist
        torch.save(model.state_dict(), self._model_path(round_t))
        write_accuracy(self.sqlite_path, round_t, post_acc, len(y_ev))

        log.info(
            "round_complete",
            t=round_t,
            pre=pre_acc,
            post=post_acc,
            loss=result.final_loss,
        )
        return RoundOutcome(round_t, True, pre_acc, post_acc, result.final_loss)
