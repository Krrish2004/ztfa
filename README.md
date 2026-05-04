# ZTFA — Zero-Trust Federated Aggregation for Health IoT

> A privacy-preserving federated-learning platform for healthcare-IoT data.
> Clients encrypt their model weights with **homomorphic encryption** before
> the aggregator ever sees them. The aggregator computes the federated
> average over ciphertexts, generates a **Groth16 zk-SNARK** proving the
> aggregation was correct, and submits the proof to a **smart contract** that
> pays the aggregator only on successful verification.
>
> **The aggregator never holds a secret key. Ciphertexts never go on-chain.**

---

## Table of contents

- [What this is](#what-this-is)
- [Architecture at a glance](#architecture-at-a-glance)
- [Prerequisites](#prerequisites)
- [One-time setup](#one-time-setup)
- [Running the demo](#running-the-demo)
  - [A. Live end-to-end (single command, no docker)](#a-live-end-to-end-single-command-no-docker)
  - [B. Full Docker-Compose stack with portal UI](#b-full-docker-compose-stack-with-portal-ui)
  - [C. Just the portal (no chain)](#c-just-the-portal-no-chain)
- [Running the tests](#running-the-tests)
- [Repository layout](#repository-layout)
- [Configuration / environment variables](#configuration--environment-variables)
- [Common operations](#common-operations)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [License](#license)

---

## What this is

A working v1 implementation of the system described in
`HLD_ZeroTrust_FedAgg_HealthIoT.pdf`. Five components run together:

1. **Client node** (Python) — trains a local PyTorch model on its share of
   the healthcare-IoT dataset, encrypts the weights, signs the commitment,
   uploads ciphertext to the aggregator, decrypts the aggregate when the
   contract reports verification.
2. **Aggregator** (Python FastAPI) — receives ciphertexts, runs homomorphic
   FedAvg (the `1/N` scalar mult is moved to the client side after
   decryption — semantically equivalent, simpler in-circuit), generates a
   Groth16 proof, posts it on chain. Has zero secret keys (runtime-checked).
3. **Smart contracts** (Solidity / Foundry) — `FederationRound.sol` orchestrates
   each round, holds escrows, and delegates proof verification to the
   auto-generated `Verifier.sol`. Runs on Anvil locally; Polygon zkEVM in prod.
4. **Portal** (Next.js + wagmi v2 + viem) — single-page dashboard for the
   client; round history fetched via on-chain events; wallet/refund page.
5. **IoT simulator** (Python) — replays the medical-IoT CSV as MQTT streams,
   sharded patient-disjoint per client.

Plus a `circuits/` directory (circom 2.x + snarkjs) and a `prover/` Rust
binary that wraps snarkjs.

## Architecture at a glance

```
┌─ TRUSTED (Client) ────┐  ┌─ UNTRUSTED (Aggregator) ─┐  ┌─ PUBLIC LEDGER ──┐
│ IoT MQTT → SQLite     │  │ FastAPI                  │  │ FederationRound  │
│ PyTorch trainer       │  │ Homomorphic FedAvg       │  │  + Verifier.sol  │
│ ★ HE secret key ★     │→ │ Groth16 prover (NO sk)   │→ │  ~280k gas verify│
│ Decrypt + inference   │  │ Postgres + MinIO         │  │  Anvil / zkEVM   │
│ Wallet, Portal UI     │  │                          │  │                  │
└───────────────────────┘  └──────────────────────────┘  └──────────────────┘
```

The full diagram is in `docs/architecture/system.mmd` (Mermaid).

## Prerequisites

| Tool      | Version     | Why                                       |
|-----------|-------------|-------------------------------------------|
| Linux x86_64 | (other platforms work; bash flavored) | dev OS |
| Python    | 3.11+ (3.12 tested) | client + aggregator |
| Node.js   | 20+         | circom, snarkjs, Next.js portal           |
| Rust      | 1.70+       | the prover binary, building circom from source |
| Docker + Compose | latest | postgres, MinIO, mosquitto, anvil   |
| Foundry (forge / anvil) | 1.6+ | Solidity build/test, local chain |
| circom    | 2.1.6       | circuit DSL — built from source on first use |

The `Makefile` and `scripts/bootstrap.sh` handle missing tools where
possible; otherwise install yourself per the [official docs][1].

[1]: docs/runbook.md

## One-time setup

```bash
# 0. clone
git clone <repo> ztfa && cd ztfa

# 1. Python venv + deps
python3 -m venv .venv
source .venv/bin/activate
pip install -e shared
pip install -e aggregator
pip install -e client
pip install pytest pytest-asyncio

# 2. circom (Rust binary, ~1 min build)
git clone --depth=1 --branch v2.1.6 https://github.com/iden3/circom.git /tmp/circom-src
cd /tmp/circom-src && cargo build --release --bin circom
mkdir -p ~/.local/bin && cp target/release/circom ~/.local/bin/
cd -   # back to ztfa repo

# 3. Foundry
curl -L https://foundry.paradigm.xyz | bash
source ~/.bashrc && foundryup

# 4. forge-std (header-only Solidity test lib)
cd contracts && \
  git clone --depth=1 --branch v1.9.4 https://github.com/foundry-rs/forge-std.git lib/forge-std && \
  cd ..

# 5. JS deps
cd circuits && npm install && cd ..
cd portal   && npm install && cd ..

# 6. Rust prover
cd prover && cargo build --release && cd ..

# 7. Compile circuit + run trusted setup ceremony + export Verifier.sol
cd circuits
bash scripts/compile.sh
bash scripts/setup.sh                  # ~3-5 min for the locked ring degree
bash scripts/export_verifier.sh
cd ..
```

After step 7 you have:
- `circuits/build/aggregation.r1cs`     – compiled circuit
- `circuits/build/aggregation_final.zkey` – proving key
- `circuits/build/verification_key.json` – verification key
- `contracts/src/Verifier.sol`          – auto-generated Solidity verifier

## Running the demo

There are three ways to exercise the system, in order of decreasing
complexity. **Pick (A) for the cleanest end-to-end demonstration.**

### A. Live end-to-end (single command, no docker)

This is the simplest demo. It spawns its own Anvil chain, deploys the
contracts, simulates 3 clients (training + encryption + on-chain commit),
runs the aggregator (homomorphic sum + Groth16 proof + chain submit), and
verifies all three clients can decrypt the federated average.

```bash
source .venv/bin/activate

PYTHONPATH=shared:client/src:aggregator/src:iot-simulator ZTFA_ROOT=$PWD \
  python scripts/e2e_live.py
```

Expected output (last 8 lines):

```
========================================================================
E2E COMPLETE
  • 3 clients trained, encrypted, committed on chain
  • homomorphic sum produced c_sum (XXX bytes)
  • Groth16 SNARK over polynomial arithmetic verified ✓
  • all clients decrypted; mean post-acc = 0.XXX
========================================================================
```

The script writes the freshly-deployed contract address into
`portal/.env.local`, so opening the portal afterward will populate the round
history with this round.

### B. Full Docker-Compose stack with portal UI

Use this when you want to see the whole architecture working: docker
compose runs postgres, MinIO, mosquitto, anvil, the aggregator FastAPI;
native processes run the IoT simulators and the portal.

**Terminal 1** — bring up infra and seed crypto state:

```bash
make infra-up                       # postgres + minio + mosquitto + anvil
bash scripts/bootstrap.sh           # keys + ceremony + deploy + .env wiring
```

**Terminal 2** — start the demo (clients + simulators + aggregator):

```bash
bash scripts/start-demo.sh
```

This launches:
- 3 client processes (each with its own MQTT subscriber, local-RPC, inference loop)
- 3 IoT simulator processes (publish patient-sharded rows over MQTT)
- the aggregator FastAPI on `:8000`

**Terminal 3** — start the frontend:

```bash
cd portal && npm run dev
# Visit http://localhost:3000
```

Connect with the Anvil deterministic mnemonic:

```
test test test test test test test test test test test junk
```

**Terminal 4** — trigger a federated round:

```bash
bash scripts/run-round.sh 1
```

The dashboard will populate as the round progresses. Subsequent rounds:
`bash scripts/run-round.sh 2`, `bash scripts/run-round.sh 3`, …

### C. Just the portal (no chain)

To work on UI in isolation:

```bash
cd portal
npm run dev      # http://localhost:3000
```

The dashboard will show a "FederationRound not deployed yet" banner where
chain data would appear, and the wallet button still works (just won't have
anywhere to transact to). Useful for layout/styling work.

## Running the tests

All test suites should be green:

```bash
make test
```

Equivalent to running each suite individually:

```bash
# Python — crypto golden vectors + simulator splits
PYTHONPATH=shared:client/src:aggregator/src:iot-simulator ZTFA_ROOT=$PWD \
  python -m pytest shared/tests iot-simulator/test_split.py -v

# circom — circuit unit tests
cd circuits && npx mocha tests/aggregation.test.mjs --reporter min --timeout 60000 ; cd ..

# Solidity — Foundry happy + adversarial
cd contracts && forge test -vv ; cd ..

# Rust — prover smoke
cd prover && cargo test --release ; cd ..
```

Coverage:
- **24** Python crypto + simulator tests (RLWE roundtrip, Poseidon ↔ circomlib parity, patient-shard determinism)
- **5** circom unit tests (commitment binding, additive aggregation, hash result)
- **13** Foundry tests (happy path, **T2** drop client, **T3** substitute ciphertext, **T9** replay, refund-after-deadline, double-submit prevention, gas profile)
- **1** Rust prover smoke test

## Repository layout

```
ztfa/
├── HLD_ZeroTrust_FedAgg_HealthIoT.pdf   ← formal design doc (source of truth)
├── CLAUDE.md                            ← living project contract & invariants
├── README.md                            ← you are here
├── Makefile                             ← orchestration helpers
├── docker-compose.yml                   ← postgres + minio + mosquitto + anvil
├── .env.example
│
├── client/                              ← Python — client node
│   └── src/ztfa_client/                   IoT adapter, trainer, CKKS engine,
│                                          wallet, round orchestrator,
│                                          inference, eval loop, local-RPC
│
├── aggregator/                          ← Python FastAPI
│   └── src/ztfa_aggregator/               api, orchestrator, homomorphic engine,
│                                          witness builder, prover adapter,
│                                          chain client, postgres + minio
│
├── shared/ztfa_crypto/                  ← single source of truth for primitives
│   ├── ckks_context.py                    parameter set, public/secret guards
│   ├── mini_he.py                         RLWE additive HE w/ raw coefficients
│   ├── poseidon.py                        circomlibjs subprocess bridge
│   ├── snark_digest.py                    deterministic ct → Fr digest
│   ├── witness.py                         circuit input builder + WASM driver
│   └── keygen.py                          v1 single-issuer keygen
│
├── circuits/                            ← circom 2 + snarkjs
│   ├── aggregation.circom                 ~250k constraints (full poly arith)
│   ├── scripts/{compile,setup,export_verifier}.sh
│   ├── tests/aggregation.test.mjs
│   └── powers_of_tau/                     locally-generated ptau (gitignored)
│
├── contracts/                           ← Foundry (Solidity 0.8.20)
│   ├── src/{FederationRound,Verifier,IVerifier}.sol
│   ├── test/FederationRound.t.sol         13 tests, 100% pass
│   ├── script/Deploy.s.sol
│   └── lib/forge-std/                     std library (gitignored)
│
├── prover/                              ← Rust crate, snarkjs wrapper
│   └── src/main.rs
│
├── portal/                              ← Next.js 15 + wagmi v2 + viem
│   ├── app/{page,rounds,wallet,settings}/page.tsx
│   ├── components/{Dashboard,RoundHistory,WalletPanel,ConnectButton}.tsx
│   ├── lib/{wagmi,abi,localhost-rpc,errors}.ts
│   └── next.config.mjs
│
├── iot-simulator/                       ← MQTT replayer
│   ├── split_config.py                    deterministic patient → client mapping
│   └── replay_medical_iot.py
│
├── scripts/
│   ├── bootstrap.sh                       one-shot: keys + ceremony + deploy
│   ├── start-demo.sh                      brings up all native processes
│   ├── run-round.sh                       triggers one FL round
│   ├── e2e_live.py                        no-docker E2E (recommended)
│   ├── e2e_happy_path.sh                  test-suite E2E
│   ├── gen_fixture.py                     regenerates Foundry test fixture
│   └── clean.sh                           tear everything down
│
└── docs/
    ├── runbook.md                         expanded operational guide
    ├── crypto-protocol.md                 primitive reference
    ├── threat-model.md                    T1..T10 mapping to code
    ├── demo-script.md                     3-min walkthrough
    └── architecture/*.mmd                 Mermaid diagrams
```

## Configuration / environment variables

Copy `.env.example` to `.env` and edit. The major knobs:

| Var | Default | Purpose |
|---|---|---|
| `N_CLIENTS` | 3 | federation size |
| `PER_CLIENT_FEE_WEI` | 5e14 (0.0005 ETH) | escrow per round per client |
| `AGGREGATOR_PAYMENT_WEI` | 1e15 (0.001 ETH) | paid on successful verification |
| `ROUND_PERIOD_SEC` | 600 | refund window |
| `CHAIN_RPC_URL` | `http://localhost:8545` | RPC endpoint |
| `CHAIN_ID` | 31337 | Anvil local chain |
| `FEDERATION_ROUND_ADDRESS` | (filled by bootstrap.sh) | deployed contract |
| `DATABASE_URL` | `postgresql://ztfa:ztfa_dev@localhost:5432/ztfa` | aggregator metadata DB |
| `S3_ENDPOINT` | `http://localhost:9000` | MinIO ciphertext blob store |
| `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | Mosquitto broker |
| `KEYS_DIR` | `./keys` | where mini_he keys + feature norm live |

Portal-specific (`portal/.env.local`):

| Var | Purpose |
|---|---|
| `NEXT_PUBLIC_FEDERATION_ROUND_ADDRESS` | written by `e2e_live.py` and `bootstrap.sh` |
| `NEXT_PUBLIC_LOCAL_CLIENT_RPC_URL` | bridge to your local client process |
| `NEXT_PUBLIC_RPC_URL` | chain RPC the browser hits |

## Common operations

```bash
# Re-run trusted setup after editing aggregation.circom:
cd circuits
bash scripts/compile.sh
bash scripts/setup.sh
bash scripts/export_verifier.sh
python ../scripts/gen_fixture.py     # regenerate Foundry fixture
cd ../contracts && forge test -vv

# Tear everything down (drops all Docker volumes + generated artifacts):
bash scripts/clean.sh

# Just bring infra up/down:
make infra-up
make infra-down

# Format / lint:
make fmt
make lint
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Portal shows blank page | Webpack stuck on a wallet-SDK dep | already handled in `portal/next.config.mjs` (resolve.fallback). If it recurs, `rm -rf portal/.next portal/node_modules && cd portal && npm install` |
| Portal shows "Failed to fetch http://127.0.0.1:8545" | Anvil isn't running, or contract isn't deployed | `make infra-up` then `bash scripts/bootstrap.sh` (or just run `scripts/e2e_live.py`) |
| Portal: "FederationRound not deployed yet" | `NEXT_PUBLIC_FEDERATION_ROUND_ADDRESS` is empty | `bash scripts/bootstrap.sh` writes it; or run `scripts/e2e_live.py` once |
| `circom: command not found` | Not in `~/.local/bin` or PATH | Build per step 2 above; ensure `~/.local/bin` is in `$PATH` |
| `forge: command not found` | Foundry not installed/sourced | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| `forge install foundry-rs/forge-std` fails | Foundry CLI version-specific quirks | clone manually as in step 4 |
| Foundry tests fail with `vm.readFile not allowed` | `fs_permissions` outside `[profile.default]` | already in `contracts/foundry.toml` |
| Foundry tests fail with `ProofFailed` | Stale fixture (after circuit edit) | `python scripts/gen_fixture.py` |
| `tenseal not available` | venv not active | `source .venv/bin/activate` |
| Aggregator: "FATAL: secret key" | Bad context bin in `keys/` | `bash scripts/clean.sh && bash scripts/bootstrap.sh` |
| Snarkjs ceremony: `ERR_OUT_OF_RANGE` | ptau power < log2(constraint count) | bump `POT_POWER` in `circuits/scripts/setup.sh` |
| Port 3000 / 8000 / 8545 / 9000 / 5432 in use | leftover processes | `bash scripts/clean.sh` then `pkill -f "next dev"` |

## Documentation

- **`HLD_ZeroTrust_FedAgg_HealthIoT.pdf`** — original 22-page formal design doc (source of truth)
- **`CLAUDE.md`** — project contract: locked decisions, invariants, v1 scope
- **`docs/runbook.md`** — expanded operational guide (clean clone → demo)
- **`docs/crypto-protocol.md`** — cryptographic primitives walked through with code references
- **`docs/threat-model.md`** — every HLD threat T1..T10 mapped to the file:line that defends it
- **`docs/demo-script.md`** — 3-minute scripted walkthrough for a recorded demo
- **`docs/architecture/`** — Mermaid diagrams: system, sequence, trust-boundary, deployment

## License

MIT — see `LICENSE`.
