#!/usr/bin/env bash
# Tear down all infra + drop volumes + reset all generated state.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "[clean] docker compose down -v ..."
docker compose down -v 2>/dev/null || true

echo "[clean] removing local data ..."
rm -rf \
    aggregator/data \
    aggregator/aggregator.sqlite \
    client/data \
    circuits/build/* \
    circuits/powers_of_tau/*.ptau \
    contracts/out contracts/cache contracts/broadcast \
    keys/ckks_*.bin keys/keygen_metadata.json keys/feature_norm.json keys/w_global_round_0.pt \
    iot-simulator/manifests \
    .gas-snapshot

# Reset .env to .env.example defaults
cp .env.example .env

echo "[clean] done. Run \`bash scripts/bootstrap.sh\` to rebuild."
