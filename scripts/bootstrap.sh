#!/usr/bin/env bash
# One-time setup for the ZTFA project.
#
# Steps:
#   1. CKKS keygen (single-issuer for v1)
#   2. Compile circuit
#   3. Powers-of-Tau + Phase-2 ceremony (local for v1)
#   4. Export Verifier.sol
#   5. Compute global feature mean/std from the dataset
#   6. Generate seed initial weights w_global^(0)
#   7. Build IoT-simulator manifests (deterministic patient split)
#   8. Deploy contracts on Anvil and update .env files

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ZTFA_ROOT="$(pwd)"
export ZTFA_ROOT

# shellcheck source=scripts/env.sh
source scripts/env.sh

PYTHON="${PYTHON:-${ZTFA_ROOT}/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
    echo "[bootstrap] FATAL: $PYTHON missing. Create .venv first." >&2
    exit 1
fi

export PATH="$HOME/.foundry/bin:$HOME/.local/bin:$PATH"

# --- 1. CKKS keygen ---
echo "[bootstrap] 1/8  CKKS keygen ..."
PYTHONPATH=shared "$PYTHON" -m ztfa_crypto.keygen "$KEYS_DIR"

# --- 2. Compile circuit ---
echo "[bootstrap] 2/8  Compile circuit ..."
( cd circuits && bash scripts/compile.sh )

# --- 3. Trusted setup ---
echo "[bootstrap] 3/8  Trusted setup ..."
( cd circuits && bash scripts/setup.sh )

# --- 4. Export Verifier.sol ---
echo "[bootstrap] 4/8  Export Verifier.sol ..."
( cd circuits && bash scripts/export_verifier.sh )

# --- 5. Feature normalisation stats ---
echo "[bootstrap] 5/8  Compute global feature norm stats ..."
PYTHONPATH=shared:client/src "$PYTHON" - <<'PYEOF'
import json
from pathlib import Path
import os, sys
sys.path.insert(0, "client/src")
from ztfa_client.features import compute_global_norm
import pandas as pd

csv_path = Path(os.environ["ZTFA_ROOT"]) / "Multi-Sensor_Medical_IoT_Dataset.csv"
keys_dir = Path(os.environ["KEYS_DIR"])
df = pd.read_csv(csv_path)
norm = compute_global_norm(df)
norm.save(keys_dir / "feature_norm.json")
print(f"   norm stats → {keys_dir / 'feature_norm.json'}")
PYEOF

# --- 6. Seed initial weights ---
echo "[bootstrap] 6/8  Generate w_global^(0) seed weights ..."
PYTHONPATH=shared:client/src "$PYTHON" - <<'PYEOF'
import os, torch
from pathlib import Path
import sys
sys.path.insert(0, "client/src")
from ztfa_client.trainer import make_seeded_model

model = make_seeded_model(seed=42)
out = Path(os.environ["KEYS_DIR"]) / "w_global_round_0.pt"
torch.save(model.state_dict(), out)
print(f"   seed weights → {out}")
PYEOF

# --- 7. IoT-simulator manifests ---
echo "[bootstrap] 7/8  Build IoT-simulator manifests ..."
"$PYTHON" iot-simulator/split_config.py \
    --csv "${ZTFA_ROOT}/Multi-Sensor_Medical_IoT_Dataset.csv" \
    --n-clients "${N_CLIENTS}" \
    --out-dir iot-simulator/manifests

# --- 8. Deploy contracts ---
echo "[bootstrap] 8/8  Deploy contracts on $CHAIN_RPC_URL ..."
if ! cast block-number --rpc-url "$CHAIN_RPC_URL" >/dev/null 2>&1; then
    echo "  ⚠ chain not reachable at $CHAIN_RPC_URL; skipping deploy." \
         "Run \`make infra-up\` first or set CHAIN_RPC_URL." >&2
    echo "[bootstrap] DONE (deploy skipped)."
    exit 0
fi

# anvil[1] is the aggregator service wallet; clients are anvil[2..4]
AGGREGATOR_ADDRESS="${AGGREGATOR_ADDRESS:-0x70997970C51812dc3A010C7d01b50e0d17dc79C8}"
DEPLOYER_PK="${DEPLOYER_PRIVATE_KEY}"

OUTPUT=$(cd contracts && forge script script/Deploy.s.sol:Deploy \
    --rpc-url "$CHAIN_RPC_URL" \
    --private-key "$DEPLOYER_PK" \
    --broadcast \
    -vv 2>&1)
echo "$OUTPUT" | tail -20

VERIFIER_ADDR=$(echo "$OUTPUT" | grep -oP 'Verifier:\s+\K0x[0-9a-fA-F]+' | head -1)
ROUND_ADDR=$(echo "$OUTPUT" | grep -oP 'FederationRound:\s+\K0x[0-9a-fA-F]+' | head -1)
echo "  ✓ Verifier:        $VERIFIER_ADDR"
echo "  ✓ FederationRound: $ROUND_ADDR"

# Persist addresses to .env
grep -v '^FEDERATION_ROUND_ADDRESS=' .env | grep -v '^VERIFIER_ADDRESS=' \
  | grep -v '^NEXT_PUBLIC_FEDERATION_ROUND_ADDRESS=' > .env.tmp
{
    cat .env.tmp
    echo "FEDERATION_ROUND_ADDRESS=$ROUND_ADDR"
    echo "VERIFIER_ADDRESS=$VERIFIER_ADDR"
    echo "NEXT_PUBLIC_FEDERATION_ROUND_ADDRESS=$ROUND_ADDR"
} > .env
rm -f .env.tmp

echo
echo "[bootstrap] ALL DONE. .env updated with contract addresses."
