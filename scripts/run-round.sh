#!/usr/bin/env bash
# Trigger one full FL round end-to-end (assumes start-demo.sh is already running
# in another terminal).
#
# Sequence:
#   1. Aggregator: open round t (POST /v1/round/start)
#   2. Each client: run-round t  (trains, encrypts, commits, uploads, decrypts)
#   3. Aggregator: finalize (POST /v1/round/{t}/finalize)
#   4. Print accuracy from each client's local-RPC

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
source scripts/env.sh

PYTHON="${PYTHON:-${ZTFA_ROOT:-$(pwd)}/.venv/bin/python}"
T="${1:-1}"
AGGR="${ZTFA_AGGREGATOR_URL:-http://localhost:8000}"

echo "[run-round] open round $T ..."
curl -fSs -X POST "${AGGR}/v1/round/start" \
    -H 'Content-Type: application/json' \
    -d "{\"t\": ${T}}" | python3 -m json.tool

echo "[run-round] launching ${N_CLIENTS} clients ..."
PIDS=()
PRIVKEYS=(
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba"
)
for ((i=0; i<N_CLIENTS; i++)); do
    PYTHONPATH=shared:client/src \
        ZTFA_CLIENT_ID="$i" \
        ZTFA_CLIENT_PRIVATE_KEY="${PRIVKEYS[$i]}" \
        "$PYTHON" -m ztfa_client.main run-round --t "$T" &
    PIDS+=($!)
done

# Stagger: clients submit + the aggregator finalizes once 3 commits arrive.
sleep 5
echo "[run-round] finalize round $T ..."
curl -fSs -X POST "${AGGR}/v1/round/${T}/finalize" | python3 -m json.tool

# Wait for all client processes
for pid in "${PIDS[@]}"; do
    wait "$pid" || echo "  ⚠ client pid $pid failed"
done

echo "[run-round] verification status:"
curl -fSs "${AGGR}/v1/round/${T}/status" | python3 -m json.tool || true

echo "[run-round] accuracy per client:"
for ((i=0; i<N_CLIENTS; i++)); do
    PORT=$((7000 + i))
    echo "  client $i:"
    curl -fSs "http://localhost:${PORT}/accuracy-history" | python3 -m json.tool || true
done
