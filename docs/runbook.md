# ZTFA Runbook

> How to go from a clean clone to a running end-to-end federated round.

## 0. Prerequisites

- Linux x86_64 (other platforms work but commands are bash-flavored)
- Docker + Docker Compose
- Node 20+ (for circom/snarkjs/Next.js)
- Python 3.11+ (3.12 tested)
- Rust 1.80+ (for the prover binary)
- Foundry (auto-installed by `setup` step below if missing)

## 1. One-time setup

```bash
git clone <this-repo> ztfa && cd ztfa

# Python venv
python3 -m venv .venv && source .venv/bin/activate
pip install -e shared
pip install -e aggregator
pip install -e client
pip install pytest pytest-asyncio

# circom (Rust build)
git clone --depth=1 --branch v2.1.6 https://github.com/iden3/circom.git /tmp/circom-src
cd /tmp/circom-src && cargo build --release --bin circom
cp target/release/circom ~/.local/bin/   # ensure ~/.local/bin is in $PATH
cd -

# Foundry
curl -L https://foundry.paradigm.xyz | bash
source ~/.bashrc && foundryup

# Forge std lib
cd contracts && git clone --depth=1 --branch v1.9.4 \
    https://github.com/foundry-rs/forge-std.git lib/forge-std && cd -

# Circuit + portal deps
cd circuits && npm install && cd -
cd portal && npm install && cd -

# Rust prover
cd prover && cargo build --release && cd -

# Bootstrap (CKKS keygen + ceremony + deploy)
make infra-up
bash scripts/bootstrap.sh
```

## 2. Verify everything works

```bash
# Crypto + circuit + contracts + simulator: ~30 seconds total
make test
```

Expected:
- 20 passing crypto golden tests
- 5 passing circuit tests
- 13 passing Foundry tests (happy + T2/T3/T9/refund)
- 4 passing simulator tests

## 3. Run the demo

```bash
# Terminal 1 — start everything
bash scripts/start-demo.sh

# Terminal 2 — open portal
cd portal && npm run dev
# Visit http://localhost:3000 and connect with the deterministic Anvil mnemonic
# "test test test test test test test test test test test junk"

# Terminal 3 — trigger one federated round
bash scripts/run-round.sh 1
```

Expected outcome:
- Aggregator opens round 1 on chain (`startRound`)
- Each client reads ~30s of MQTT data, trains 5 epochs locally
- Clients submit on-chain commits with 0.0005 ETH fee
- Aggregator computes `c_sum`, generates SNARK proof, calls `submitAggregateAndProof`
- Verifier passes; aggregator paid 0.001 ETH
- Each client fetches `c_sum`, decrypts, divides by N, updates local model
- Per-client accuracy displayed on dashboard

## 4. Trigger more rounds

```bash
bash scripts/run-round.sh 2
bash scripts/run-round.sh 3
# ... watch /accuracy-history monotonically improve
```

## 5. Tear down

```bash
bash scripts/clean.sh   # drops all volumes, regenerable artifacts, .env
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `circom not found` | `cargo build` it from /tmp/circom-src and put in `~/.local/bin/circom` |
| `forge install` fails | clone `forge-std` manually (above) |
| port 8545/8000/3000 in use | `docker compose down -v` |
| ProofFailed on chain | Regenerate fixture: `python3 scripts/gen_fixture.py` |
| TenSEAL import error | Ensure venv: `source .venv/bin/activate` |
| Aggregator fails with "FATAL: secret key" | A bad context bin is in `keys/`; re-run bootstrap |
