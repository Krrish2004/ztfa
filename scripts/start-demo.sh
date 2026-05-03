#!/usr/bin/env bash
# Bring up infra + spawn N client processes + IoT simulators.
# Aggregator runs in the foreground (use Ctrl-C to stop everything).

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ZTFA_ROOT="$(pwd)"
export ZTFA_ROOT
source scripts/env.sh

PYTHON="${PYTHON:-${ZTFA_ROOT}/.venv/bin/python}"
PIDS=()

cleanup() {
    echo "[start-demo] tearing down..."
    for pid in "${PIDS[@]:-}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    docker compose stop || true
}
trap cleanup EXIT INT TERM

echo "[start-demo] infra-up..."
docker compose up -d postgres minio minio-init mosquitto anvil
sleep 3

# Bootstrap (idempotent)
if [[ ! -f "$KEYS_DIR/ckks_full.bin" ]] || ! grep -q "^FEDERATION_ROUND_ADDRESS=0x" .env; then
    bash scripts/bootstrap.sh
    source scripts/env.sh
fi

echo "[start-demo] starting IoT simulators..."
for ((i=0; i<N_CLIENTS; i++)); do
    "$PYTHON" iot-simulator/replay_medical_iot.py \
        --csv "${ZTFA_ROOT}/Multi-Sensor_Medical_IoT_Dataset.csv" \
        --client-id "$i" \
        --n-clients "$N_CLIENTS" \
        --rate-hz 20 &
    PIDS+=($!)
done

echo "[start-demo] starting client nodes..."
for ((i=0; i<N_CLIENTS; i++)); do
    LOG="aggregator/data/client_${i}.log"
    mkdir -p "$(dirname "$LOG")"
    PRIVKEYS=(
        "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"
        "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"
        "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba"
    )
    PORT=$((7000 + i))
    PYTHONPATH=shared:client/src \
        ZTFA_CLIENT_ID="$i" \
        ZTFA_CLIENT_PRIVATE_KEY="${PRIVKEYS[$i]}" \
        ZTFA_LOCAL_RPC_PORT="$PORT" \
        "$PYTHON" -m ztfa_client.main local-rpc &> "$LOG" &
    PIDS+=($!)
    PYTHONPATH=shared:client/src \
        ZTFA_CLIENT_ID="$i" \
        ZTFA_CLIENT_PRIVATE_KEY="${PRIVKEYS[$i]}" \
        ZTFA_LOCAL_RPC_PORT="$PORT" \
        "$PYTHON" -m ztfa_client.main ingest &>> "$LOG" &
    PIDS+=($!)
    PYTHONPATH=shared:client/src \
        ZTFA_CLIENT_ID="$i" \
        ZTFA_CLIENT_PRIVATE_KEY="${PRIVKEYS[$i]}" \
        ZTFA_LOCAL_RPC_PORT="$PORT" \
        "$PYTHON" -m ztfa_client.main infer-loop &>> "$LOG" &
    PIDS+=($!)
done

echo "[start-demo] launching aggregator (foreground) on :8000 ..."
PYTHONPATH=shared:aggregator/src "$PYTHON" -m ztfa_aggregator.main
