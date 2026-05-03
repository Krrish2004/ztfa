#!/usr/bin/env bash
# Export the auto-generated Solidity verifier for the aggregation circuit.
# Output: contracts/src/Verifier.sol
# DO NOT hand-edit the output.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

SNARKJS="node node_modules/snarkjs/cli.js"
OUT="../contracts/src/Verifier.sol"

mkdir -p "$(dirname "$OUT")"

if [[ ! -f build/aggregation_final.zkey ]]; then
    echo "ERROR: run setup.sh first to produce build/aggregation_final.zkey" >&2
    exit 1
fi

echo "[export_verifier.sh] Generating $OUT ..."
$SNARKJS zkey export solidityverifier \
    build/aggregation_final.zkey \
    "$OUT"

# Pin pragma to 0.8.20+ for compatibility with Foundry default
sed -i.bak -e 's|pragma solidity \^0\.6\.11|pragma solidity ^0.8.20|' "$OUT" && rm -f "$OUT.bak"

# Compute integrity hash
HASH=$(sha256sum "$OUT" | cut -d' ' -f1)
echo "[export_verifier.sh] Verifier.sol sha256 = $HASH"

# Header comment
HEADER="// SPDX-License-Identifier: GPL-3.0
// AUTO-GENERATED — DO NOT HAND-EDIT.
// Source: circuits/aggregation.circom + circuits/build/aggregation_final.zkey
// Regenerate with: bash circuits/scripts/export_verifier.sh
// Integrity hash (sha256): $HASH
"
TMP=$(mktemp)
printf '%s\n' "$HEADER" > "$TMP"
# strip the original SPDX line if present and append rest
sed -e '/^\/\/ SPDX-License-Identifier:/d' "$OUT" >> "$TMP"
mv "$TMP" "$OUT"

echo "[export_verifier.sh] OK"
wc -l "$OUT"
