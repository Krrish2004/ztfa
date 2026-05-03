# ZTFA — Zero-Trust Federated Aggregation for Health IoT

> Privacy-preserving federated learning for healthcare-IoT data, secured by
> client-side **CKKS Fully Homomorphic Encryption**, **Groth16 zk-SNARKs**,
> and an EVM smart contract that pays the aggregator only after on-chain
> proof verification.

The aggregator never holds a secret key. Ciphertexts never go on-chain.

## Architecture (3 trust zones)

```
┌─ TRUSTED (Client) ────┐  ┌─ UNTRUSTED (Aggregator) ─┐  ┌─ PUBLIC LEDGER ──┐
│ IoT  →  PyTorch       │  │ FastAPI                  │  │ FederationRound  │
│        ↓ + CKKS sk    │→ │ Homomorphic FedAvg       │→ │  + Verifier.sol  │
│ Inference + Portal    │  │ Groth16 prover (no sk)   │  │ (Polygon zkEVM)  │
└───────────────────────┘  └──────────────────────────┘  └──────────────────┘
```

See `docs/architecture/system.mmd` (full diagram) and `HLD_ZeroTrust_FedAgg_HealthIoT.pdf`
for the formal design.

## Quick start

```bash
make infra-up
bash scripts/bootstrap.sh
bash scripts/start-demo.sh    # terminal 1
cd portal && npm run dev      # terminal 2
bash scripts/run-round.sh 1   # terminal 3
```

Visit http://localhost:3000 and connect with the deterministic Anvil
mnemonic (`test test test test test test test test test test test junk`).

## Live end-to-end demo (one command)

```bash
PYTHONPATH=shared:client/src:aggregator/src:iot-simulator ZTFA_ROOT=$PWD \
    .venv/bin/python scripts/e2e_live.py
```

Spins up Anvil, deploys contracts, runs the full v1 protocol (3 clients
train → CKKS-encrypt → on-chain commit → homomorphic sum → Groth16
proof → on-chain verify → decrypt → update model) in one process. Output
includes pre/post accuracy delta per client. Real chain. Real proof.
Real gas. Real CKKS arithmetic.

## Tests

```bash
make test
```

Across all components:
- 20 Python crypto golden vector tests (CKKS + Poseidon parity)
- 5 circom circuit unit tests
- 13 Foundry tests (happy path + T2/T3/T9 adversarial + refund flow)
- 4 IoT-simulator split tests
- 1 Rust prover smoke test

## Stack (HLD §11)

| Layer | Choice |
|---|---|
| FHE | TenSEAL (CKKS over BN254-friendly RLWE) |
| FL framework | Custom orchestration (single-coordinator) |
| ML | PyTorch — small MLP (15→32→16→4) for activity classification |
| Circuit | circom 2 + circomlib (Poseidon) |
| Prover | snarkjs (v1); rapidsnark slot ready (v2) |
| Smart contract | Solidity 0.8.20 + Foundry |
| Chain | Polygon zkEVM (prod) / Anvil (local dev) |
| Aggregator | Python FastAPI + web3.py |
| Frontend | Next.js 15 + wagmi v2 + viem + RainbowKit + Tanstack Query |
| IoT broker | Eclipse Mosquitto |
| Storage | Postgres + MinIO (S3-compatible) |

## v1 scope

Full v1 implementation across **5 components** (client / aggregator / contracts / portal / iot-simulator). Local-dev only; the protocol literally follows the HLD; known gaps documented as v2 work — see `CLAUDE.md` §13.

## Documentation

- `HLD_ZeroTrust_FedAgg_HealthIoT.pdf` — original HLD (source of truth)
- `CLAUDE.md` — living project contract: scope, invariants, decisions
- `docs/runbook.md` — operational guide
- `docs/crypto-protocol.md` — cryptographic primitive reference
- `docs/threat-model.md` — T1..T10 mapping to code

## License

MIT — see `LICENSE`.
