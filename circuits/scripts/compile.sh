#!/usr/bin/env bash
# Compile aggregation.circom → R1CS + WASM + sym.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

CIRCOM="${CIRCOM:-circom}"
if ! command -v "$CIRCOM" &>/dev/null; then
    if [[ -x "$HOME/.local/bin/circom" ]]; then
        CIRCOM="$HOME/.local/bin/circom"
    else
        echo "circom not found. Build with: cd /tmp && git clone --depth=1 --branch v2.1.6 https://github.com/iden3/circom.git && cd circom && cargo build --release --bin circom && cp target/release/circom ~/.local/bin/" >&2
        exit 1
    fi
fi

mkdir -p build

echo "[compile.sh] Compiling aggregation.circom ..."
"$CIRCOM" aggregation.circom \
    --r1cs --wasm --sym \
    -l node_modules \
    -o build

echo "[compile.sh] Constraint count:"
"$CIRCOM" aggregation.circom -l node_modules --r1cs -o build 2>&1 | grep -E "non-linear|linear constraints|constraints:" || true

ls -lh build/
echo "[compile.sh] OK"
