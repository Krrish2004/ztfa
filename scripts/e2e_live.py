#!/usr/bin/env python3
"""End-to-end LIVE test of the ZTFA v1 round protocol.

This is the cryptographic "money shot": exercises every layer of the stack
in one process against a freshly-spawned Anvil chain.

Sequence:
  1. Spawn Anvil on :8545
  2. Deploy Verifier + FederationRound contracts (via cast, no docker)
  3. Bootstrap CKKS keys + global feature norm + N=3 dataset shards
  4. Each of 3 clients:
     - load assigned patients' rows from the CSV directly (no MQTT)
     - train 5 epochs of MLP locally
     - encrypt weights under CKKS
     - compute H_i = commitment(t, cid, ct)
     - submit on chain {value: perClientFee}
  5. Aggregator:
     - homomorphic_sum over the 3 ciphertexts
     - build SNARK witness from per-client digests + sum digest
     - prove (snarkjs) → produce a, b, c, public[]
     - assemble H_sum = poseidon_chain(sum_digest); contract enforces
       this matches public[N] AND each H_i == clientCommits[i]
     - call submitAggregateAndProof
  6. Each client:
     - polls isRoundVerified
     - fetches c_sum, decrypts via sk, divides by N
     - measures held-out accuracy DELTA from round 0
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "client" / "src"))
sys.path.insert(0, str(ROOT / "iot-simulator"))


def log(msg: str, *, indent: int = 0) -> None:
    print("  " * indent + msg, flush=True)


def wait_port(port: int, timeout: float = 15.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        with socket.socket() as s:
            try:
                s.settimeout(0.3)
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.2)
    raise TimeoutError(f"port {port} never opened")


def main() -> int:
    log("=" * 60)
    log("ZTFA v1 — live E2E demonstration")
    log("=" * 60)

    # --- Step 1: anvil ---
    log("[1/6] starting anvil ...")
    anvil_log = open("/tmp/ztfa_anvil.log", "w")
    anvil = subprocess.Popen(
        [
            os.path.expanduser("~/.foundry/bin/anvil"),
            "--port", "8545",
            "--silent",
            "--mnemonic", "test test test test test test test test test test test junk",
        ],
        stdout=anvil_log,
        stderr=anvil_log,
    )
    try:
        wait_port(8545)
        log("anvil up", indent=1)

        # --- Step 2: deploy ---
        log("[2/6] deploying contracts ...")
        deploy_env = os.environ.copy()
        deploy_env["PATH"] = f"{os.path.expanduser('~/.foundry/bin')}:{deploy_env.get('PATH','')}"
        deploy = subprocess.run(
            [
                "forge", "script", "script/Deploy.s.sol:Deploy",
                "--rpc-url", "http://localhost:8545",
                "--private-key", "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
                "--broadcast",
                "-vv",
            ],
            cwd=str(ROOT / "contracts"),
            capture_output=True,
            text=True,
            env=deploy_env,
        )
        if deploy.returncode != 0:
            log("DEPLOY FAILED", indent=1)
            log(deploy.stdout[-2000:], indent=1)
            log(deploy.stderr[-1000:], indent=1)
            return 1

        round_addr = next(
            line.split(": ")[-1].strip()
            for line in deploy.stdout.splitlines()
            if "FederationRound:" in line
        )
        verifier_addr = next(
            line.split(": ")[-1].strip()
            for line in deploy.stdout.splitlines()
            if "Verifier:" in line
        )
        log(f"FederationRound: {round_addr}", indent=1)
        log(f"Verifier:        {verifier_addr}", indent=1)

        # --- Step 3: bootstrap crypto + dataset ---
        log("[3/6] bootstrap (keys + feature norm + dataset shards) ...")
        keys_dir = ROOT / ".tmp_e2e" / "keys"
        if keys_dir.exists():
            shutil.rmtree(keys_dir)
        keys_dir.mkdir(parents=True)

        from ztfa_crypto.keygen import run_keygen
        run_keygen(keys_dir)
        log("CKKS keys generated", indent=1)

        from ztfa_client.features import compute_global_norm
        import pandas as pd
        df_all = pd.read_csv(ROOT / "Multi-Sensor_Medical_IoT_Dataset.csv")
        norm = compute_global_norm(df_all)
        norm.save(keys_dir / "feature_norm.json")
        log("feature norm computed", indent=1)

        # Generate seed weights
        import torch
        from ztfa_client.trainer import HARMLP, make_seeded_model
        seed_model = make_seeded_model(seed=42)
        seed_path = keys_dir / "w_global_round_0.pt"
        torch.save(seed_model.state_dict(), seed_path)

        from split_config import patient_to_client
        N = 3
        per_client_df = {
            i: df_all[df_all["patient_id"].apply(lambda p, i=i: patient_to_client(p, N) == i)].reset_index(drop=True)
            for i in range(N)
        }
        for i, sub in per_client_df.items():
            log(f"client {i}: {len(sub)} rows, {sub['patient_id'].nunique()} patients", indent=1)

        # --- Step 4: each client trains, encrypts, submits ---
        log("[4/6] clients: train → encrypt → submit on chain ...")
        from ztfa_crypto.poseidon import commitment, to_bytes32
        from ztfa_client.ckks_engine import ClientCKKSEngine
        from ztfa_client.features import feature_matrix, label_vector
        from ztfa_client.trainer import (
            evaluate, flatten_state_dict, load_flat_into_model, train_one_round,
        )
        from ztfa_client.wallet import ClientWallet

        engine = ClientCKKSEngine(keys_dir / "ckks_full.bin")
        ROUND_T = 1

        # Anvil deterministic clients (same as portal mnemonic)
        client_pks = [
            "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
            "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
            "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
        ]

        client_state: list[dict] = []
        for cid in range(N):
            sub_df = per_client_df[cid]
            n_split = int(len(sub_df) * 0.8)
            train_df = sub_df.iloc[:n_split]
            eval_df = sub_df.iloc[n_split:]

            X_tr = feature_matrix(train_df, norm)
            y_tr = label_vector(train_df)
            X_ev = feature_matrix(eval_df, norm)
            y_ev = label_vector(eval_df)

            model = HARMLP()
            model.load_state_dict(torch.load(seed_path, weights_only=True))
            pre_acc = evaluate(model, X_ev, y_ev)

            tr_result = train_one_round(model, X_tr, y_tr, epochs=5, batch_size=32, lr=1e-2, seed=cid)
            log(
                f"client {cid}: pre_acc={pre_acc:.3f}  trained_loss={tr_result.final_loss:.3f}  M={tr_result.flat_weights.size}",
                indent=1,
            )

            ct_bytes = engine.encrypt_weights(tr_result.flat_weights)
            h_i = commitment(round_index=ROUND_T, client_id=cid, ciphertext_bytes=ct_bytes)
            h_bytes = to_bytes32(h_i)

            client_state.append({
                "id": cid,
                "X_ev": X_ev,
                "y_ev": y_ev,
                "pre_acc": pre_acc,
                "n_weights": tr_result.flat_weights.size,
                "ct_bytes": ct_bytes,
                "h_i": h_i,
            })

        # Aggregator: startRound BEFORE clients commit
        from ztfa_aggregator.config import Settings as AggSettings
        sys.path.insert(0, str(ROOT / "aggregator" / "src"))
        from ztfa_aggregator.chain import ChainClient

        os.environ["FEDERATION_ROUND_ADDRESS"] = round_addr
        os.environ["AGGREGATOR_PRIVATE_KEY"] = (
            "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
        )
        os.environ["CHAIN_RPC_URL"] = "http://localhost:8545"
        os.environ["CHAIN_ID"] = "31337"
        os.environ["KEYS_DIR"] = str(keys_dir)
        os.environ["CIRCUIT_BUILD_DIR"] = str(ROOT / "circuits" / "build")
        agg_settings = AggSettings(_env_file=None)  # don't load stale .env
        agg_chain = ChainClient(agg_settings)
        agg_chain.start_round(ROUND_T)
        log(f"aggregator: startRound({ROUND_T}) on chain", indent=1)

        # Each client commits IN ORDER (so getCommit indexes match)
        for cid, state in enumerate(client_state):
            wallet = ClientWallet(
                rpc_url="http://localhost:8545",
                chain_id=31337,
                private_key=client_pks[cid],
                contract_address=round_addr,
                per_client_fee_wei=int(5e14),
            )
            wallet.submit_commitment(ROUND_T, to_bytes32(state["h_i"]))
            log(f"client {cid}: submitClientCommitment OK", indent=1)

        # --- Step 5: aggregator: sum + prove + submit ---
        log("[5/6] aggregator: homomorphic-sum → prove → submit ...")
        from ztfa_aggregator.homomorphic import (
            homomorphic_sum,
            serialize_aggregate_for_snark,
            serialize_for_snark,
        )
        from ztfa_aggregator.prover import prove_round
        from ztfa_crypto.ckks_context import serialize_public_context
        import tenseal as ts

        ct_blobs = [s["ct_bytes"] for s in client_state]
        public_ctx = ts.context_from((keys_dir / "ckks_public.bin").read_bytes())
        public_blob = (keys_dir / "ckks_public.bin").read_bytes()

        c_sum_bytes = homomorphic_sum(ct_blobs, public_blob)
        log(f"c_sum produced ({len(c_sum_bytes)} bytes)", indent=1)

        client_digests = [
            serialize_for_snark(state["ct_bytes"], round_t=ROUND_T, client_id=state["id"])
            for state in client_state
        ]
        # The witness's c_sum MUST equal the element-wise sum of client digests
        # (that's what the SNARK enforces). The aggregator's separate
        # "digest of c_sum bytes" is for the H_sum that the client verifies
        # off-chain — for now the SNARK only checks `Σ digests == c_sum_witness`.

        work_dir = ROOT / ".tmp_e2e" / "proof"
        work_dir.mkdir(parents=True, exist_ok=True)
        snarkjs_cli = ROOT / "circuits" / "node_modules" / "snarkjs" / "cli.js"
        zkey = ROOT / "circuits" / "build" / "aggregation_final.zkey"

        proof, inputs = asyncio.run(
            prove_round(
                client_digests,
                zkey_path=zkey,
                work_dir=work_dir,
                snarkjs_cli=snarkjs_cli,
            )
        )
        log("Groth16 proof generated", indent=1)
        log(f"public[0..3] = {[p[:14]+'...' for p in proof.public_signals]}", indent=2)

        h_agg_bytes = to_bytes32(inputs.H_sum)
        agg_chain.submit_proof(ROUND_T, "0x" + h_agg_bytes.hex(), proof)

        verified = agg_chain.is_round_verified(ROUND_T)
        log(f"isRoundVerified({ROUND_T}) = {verified}", indent=1)
        if not verified:
            log("FAILED: round not verified on chain", indent=1)
            return 1

        # --- Step 6: clients fetch + decrypt + measure ---
        log("[6/6] clients: decrypt c_sum → average → eval ...")
        post_accs = []
        for state in client_state:
            avg_w = engine.decrypt_aggregate(
                c_sum_bytes,
                n_clients=N,
                n_weights=state["n_weights"],
            )
            model = HARMLP()
            load_flat_into_model(model, avg_w)
            post_acc = evaluate(model, state["X_ev"], state["y_ev"])
            delta = post_acc - state["pre_acc"]
            log(
                f"client {state['id']}: pre={state['pre_acc']:.3f} post={post_acc:.3f}  Δ={delta:+.3f}",
                indent=1,
            )
            post_accs.append(post_acc)

        log("=" * 60)
        log("E2E COMPLETE")
        log(f"  • {N} clients trained, encrypted, committed on chain")
        log(f"  • homomorphic FedAvg produced c_sum ({len(c_sum_bytes)} bytes)")
        log(f"  • Groth16 SNARK verified on chain (gas-paid)")
        log(f"  • all clients decrypted aggregate; mean post-acc = {sum(post_accs)/N:.3f}")
        log("=" * 60)
        return 0
    finally:
        anvil.send_signal(signal.SIGTERM)
        try:
            anvil.wait(timeout=3)
        except subprocess.TimeoutExpired:
            anvil.kill()
        anvil_log.close()


if __name__ == "__main__":
    sys.exit(main())
