#!/usr/bin/env python3
"""ZTFA v1 — live E2E with FULL polynomial-arithmetic SNARK.

The SNARK now operates on the actual (a, b) polynomial coefficients of each
ciphertext (mini_he RLWE additive HE), not on a SHA-256 digest. Every
encrypted weight participates in the proof.

Sequence:
  1. Spawn Anvil on :8545
  2. Deploy Verifier + FederationRound contracts
  3. Bootstrap mini_he keys + global feature norm + N=3 dataset shards
  4. Each of 3 clients:
       - load assigned patients' rows
       - train MLP (15→8→4) locally for 5 epochs
       - encrypt weights with mini_he (RLWE additive HE, N_RING=256, q≈2^60)
       - H_i = poseidon_chain(c.c0 || c.c1)         ; 512 BN254-Fr coefs
       - submitClientCommitment on chain {value: perClientFee}
  5. Aggregator:
       - mini_he.add_many over the 3 ciphertexts (NO mod-q reduction)
       - build SNARK witness from raw coefficient arrays
       - prove with snarkjs (~30-90s at 491k constraints, ptau-19)
       - submitAggregateAndProof on chain
  6. Each client:
       - poll isRoundVerified
       - decrypt c_sum, divide by N (post-decryption averaging)
       - measure held-out accuracy delta
"""

from __future__ import annotations

import asyncio
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
    log("=" * 72)
    log("ZTFA v1 — full polynomial arithmetic SNARK · live E2E")
    log("=" * 72)

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
        stdout=anvil_log, stderr=anvil_log,
    )
    try:
        wait_port(8545)
        log("anvil up", indent=1)

        # --- Step 2: deploy ---
        log("[2/6] deploying contracts ...")
        deploy_env = os.environ.copy()
        deploy_env["PATH"] = (
            f"{os.path.expanduser('~/.foundry/bin')}:{deploy_env.get('PATH','')}"
        )
        deploy = subprocess.run(
            [
                "forge", "script", "script/Deploy.s.sol:Deploy",
                "--rpc-url", "http://localhost:8545",
                "--private-key",
                "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
                "--broadcast", "-vv",
            ],
            cwd=str(ROOT / "contracts"),
            capture_output=True, text=True, env=deploy_env,
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

        # Wire the address into the portal
        portal_env = ROOT / "portal" / ".env.local"
        portal_env.write_text(
            f"NEXT_PUBLIC_CHAIN_ID=31337\n"
            f"NEXT_PUBLIC_RPC_URL=http://localhost:8545\n"
            f"NEXT_PUBLIC_FEDERATION_ROUND_ADDRESS={round_addr}\n"
            f"NEXT_PUBLIC_LOCAL_CLIENT_RPC_URL=http://localhost:7000\n"
        )
        log(f"portal/.env.local updated", indent=1)

        # --- Step 3: bootstrap ---
        log("[3/6] bootstrap (mini_he keys, feature norm, dataset shards) ...")
        from ztfa_crypto import mini_he

        keys_dir = ROOT / ".tmp_e2e" / "keys"
        if keys_dir.exists():
            shutil.rmtree(keys_dir)
        keys_dir.mkdir(parents=True)

        pk, sk = mini_he.keygen(seed=42)
        mini_he.save_keys(pk, sk, keys_dir)
        log("mini_he keys (RLWE additive HE, N_RING=256, q≈2^60) generated", indent=1)

        from ztfa_client.features import (
            NUM_CLASSES, NUM_FEATURES, compute_global_norm,
            feature_matrix, label_vector,
        )
        import pandas as pd
        df_all = pd.read_csv(ROOT / "Multi-Sensor_Medical_IoT_Dataset.csv")
        norm = compute_global_norm(df_all)
        norm.save(keys_dir / "feature_norm.json")
        log("feature norm computed", indent=1)

        # MLP fits in N_RING=128 mini_he slots:
        # 15 → 4 → 4 ⇒ (15·4 + 4) + (4·4 + 4) = 64 + 20 = 84 weights ≤ 128
        import numpy as np
        import torch
        import torch.nn as nn

        class SmallMLP(nn.Module):
            def __init__(self):
                super().__init__()
                self.net = nn.Sequential(
                    nn.Linear(NUM_FEATURES, 4), nn.ReLU(),
                    nn.Linear(4, NUM_CLASSES),
                )
            def forward(self, x): return self.net(x)

        torch.manual_seed(42)
        seed_model = SmallMLP()
        seed_path = keys_dir / "w_global_round_0.pt"
        torch.save(seed_model.state_dict(), seed_path)

        from split_config import patient_to_client
        N = 3
        per_client_df = {
            i: df_all[
                df_all["patient_id"].apply(
                    lambda p, i=i: patient_to_client(p, N) == i
                )
            ].reset_index(drop=True)
            for i in range(N)
        }
        for i, sub in per_client_df.items():
            log(
                f"client {i}: {len(sub)} rows, {sub['patient_id'].nunique()} patients",
                indent=1,
            )

        # --- Aggregator chain client (set up env first) ---
        os.environ["FEDERATION_ROUND_ADDRESS"] = round_addr
        os.environ["AGGREGATOR_PRIVATE_KEY"] = (
            "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
        )
        os.environ["CHAIN_RPC_URL"] = "http://localhost:8545"
        os.environ["CHAIN_ID"] = "31337"
        os.environ["KEYS_DIR"] = str(keys_dir)
        os.environ["CIRCUIT_BUILD_DIR"] = str(ROOT / "circuits" / "build")

        sys.path.insert(0, str(ROOT / "aggregator" / "src"))
        from ztfa_aggregator.config import Settings as AggSettings
        from ztfa_aggregator.chain import ChainClient

        agg_settings = AggSettings(_env_file=None)
        agg_chain = ChainClient(agg_settings)
        agg_chain.start_round(1)
        log("aggregator: startRound(1) on chain", indent=1)

        # --- Step 4: train + encrypt + submit ---
        log("[4/6] clients: train → encrypt (mini_he) → submit on chain ...")
        from ztfa_crypto.poseidon import poseidon_chain, to_bytes32
        from ztfa_client.wallet import ClientWallet

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

            torch.manual_seed(42)
            model = SmallMLP()
            model.load_state_dict(torch.load(seed_path, weights_only=True))

            model.eval()
            with torch.no_grad():
                pre_acc = float(
                    (model(torch.tensor(X_ev)).argmax(dim=1).numpy() == y_ev).mean()
                )

            optim = torch.optim.SGD(model.parameters(), lr=1e-2, momentum=0.9)
            crit = nn.CrossEntropyLoss()
            rng = np.random.default_rng(cid)
            model.train()
            for _ in range(5):
                idx = rng.permutation(len(y_tr))
                for s in range(0, len(idx), 32):
                    b = idx[s:s+32]
                    xb = torch.tensor(X_tr[b]); yb = torch.tensor(y_tr[b])
                    optim.zero_grad()
                    loss = crit(model(xb), yb); loss.backward(); optim.step()

            flat = np.concatenate(
                [p.detach().cpu().numpy().ravel() for p in model.parameters()]
            ).astype(np.float64)
            log(f"client {cid}: pre_acc={pre_acc:.3f}  M={flat.size}", indent=1)

            ct = mini_he.encrypt(pk, flat, seed=10 + cid)
            coefs = mini_he.coefficients_for_snark(ct)  # length 512
            h_i = poseidon_chain(coefs)
            h_bytes = to_bytes32(h_i)

            wallet = ClientWallet(
                rpc_url="http://localhost:8545",
                chain_id=31337,
                private_key=client_pks[cid],
                contract_address=round_addr,
                per_client_fee_wei=int(5e14),
            )
            wallet.submit_commitment(1, h_bytes)
            log(
                f"client {cid}: submitClientCommitment OK (H_i={h_bytes.hex()[:14]}…)",
                indent=1,
            )

            client_state.append({
                "id": cid, "X_ev": X_ev, "y_ev": y_ev, "pre_acc": pre_acc,
                "n_weights": flat.size, "ct": ct, "coefs": coefs, "h_i": h_i,
                "model_init_state": model.state_dict(),
            })

        # --- Step 5: aggregator: sum + prove + submit ---
        log("[5/6] aggregator: homomorphic-sum → prove (~30-90s) → submit ...")
        cts = [s["ct"] for s in client_state]
        c_sum = mini_he.add_many(cts)
        log(f"c_sum produced ({len(c_sum.serialize())} bytes)", indent=1)

        from ztfa_aggregator.prover import prove_round
        client_coefs = [s["coefs"] for s in client_state]

        work_dir = ROOT / ".tmp_e2e" / "proof"
        work_dir.mkdir(parents=True, exist_ok=True)
        snarkjs_cli = ROOT / "circuits" / "node_modules" / "snarkjs" / "cli.js"
        zkey = ROOT / "circuits" / "build" / "aggregation_final.zkey"

        if not zkey.exists():
            log(f"ERROR: zkey missing at {zkey}", indent=1)
            log("       run: cd circuits && POT_POWER=19 bash scripts/setup.sh", indent=1)
            return 1

        t0 = time.time()
        proof, inputs = asyncio.run(
            prove_round(
                client_coefs,
                zkey_path=zkey,
                work_dir=work_dir,
                snarkjs_cli=snarkjs_cli,
            )
        )
        log(f"Groth16 proof generated in {time.time()-t0:.1f}s", indent=1)

        h_agg_bytes = to_bytes32(inputs.H_sum)
        agg_chain.submit_proof(1, "0x" + h_agg_bytes.hex(), proof)

        verified = agg_chain.is_round_verified(1)
        log(f"isRoundVerified(1) = {verified}", indent=1)
        if not verified:
            log("FAILED: round not verified on chain", indent=1)
            return 1

        # --- Step 6: clients fetch + decrypt + measure ---
        log("[6/6] clients: decrypt c_sum → divide by N → eval ...")
        post_accs = []
        for state in client_state:
            avg_w = mini_he.decrypt(sk, c_sum, n_real=state["n_weights"]) / N

            model = SmallMLP()
            model.load_state_dict(state["model_init_state"])
            idx = 0
            with torch.no_grad():
                for p in model.parameters():
                    n = p.numel()
                    p.copy_(torch.tensor(
                        avg_w[idx:idx+n].reshape(p.shape), dtype=p.dtype
                    ))
                    idx += n

            model.eval()
            with torch.no_grad():
                logits = model(torch.tensor(state["X_ev"]))
                preds = logits.argmax(dim=1).numpy()
                post_acc = float((preds == state["y_ev"]).mean())
            delta = post_acc - state["pre_acc"]
            log(
                f"client {state['id']}: pre={state['pre_acc']:.3f}  "
                f"post={post_acc:.3f}  Δ={delta:+.3f}",
                indent=1,
            )
            post_accs.append(post_acc)

        log("=" * 72)
        log("E2E COMPLETE")
        log(f"  • {N} clients trained, encrypted (mini_he RLWE), committed on chain")
        log(f"  • homomorphic sum: c_sum = {len(c_sum.serialize())} bytes / 512 coefs")
        log(f"  • Groth16 SNARK over FULL polynomial arithmetic verified ✓")
        log(f"  • all clients decrypted; mean post-acc = {sum(post_accs)/N:.3f}")
        log("=" * 72)
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
