#!/usr/bin/env bash
# Trusted-setup ceremony for the aggregation circuit.
#
# Phase 1 (Powers of Tau) — generated locally for v1 demo. PRODUCTION SHOULD
# REUSE THE HERMEZ CEREMONY (powersOfTau28_hez_final_<N>.ptau). For local-dev
# BTP demo at power 14 (16k constraints), local generation is tractable
# (~30-60 seconds) and removes external dependencies. Documented in CLAUDE.md.
#
# Phase 2 — single-party contribution for v1; v2 must run multi-party.
#
# Idempotent: re-running skips steps whose outputs already exist.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

POT_POWER="${POT_POWER:-14}"  # 2^14 = 16 384 ≥ 7 668 constraints
POT_DIR="powers_of_tau"
POT_NEW="$POT_DIR/pot${POT_POWER}_0000.ptau"
POT_CONTRIB="$POT_DIR/pot${POT_POWER}_0001.ptau"
POT_PREP="$POT_DIR/pot${POT_POWER}_final.ptau"
SNARKJS="node node_modules/snarkjs/cli.js"

mkdir -p "$POT_DIR" build

# --- Phase 1: Powers of Tau ---
if [[ ! -f "$POT_NEW" ]]; then
    echo "[setup.sh] Phase 1: new ptau (power $POT_POWER) ..."
    $SNARKJS powersoftau new bn128 "$POT_POWER" "$POT_NEW" -v
fi

if [[ ! -f "$POT_CONTRIB" ]]; then
    echo "[setup.sh] Phase 1: contribute (single-party for v1 demo) ..."
    $SNARKJS powersoftau contribute "$POT_NEW" "$POT_CONTRIB" \
        --name="ZTFA v1 phase1 contribution" \
        -e="$(date +%s%N)$RANDOM"
fi

if [[ ! -f "$POT_PREP" ]]; then
    echo "[setup.sh] Phase 1: prepare for phase 2 ..."
    $SNARKJS powersoftau prepare phase2 "$POT_CONTRIB" "$POT_PREP" -v
fi

# --- Phase 2: circuit-specific ---
if [[ ! -f build/aggregation_0000.zkey ]]; then
    echo "[setup.sh] Phase 2: initial zkey ..."
    $SNARKJS groth16 setup \
        build/aggregation.r1cs \
        "$POT_PREP" \
        build/aggregation_0000.zkey
fi

if [[ ! -f build/aggregation_final.zkey ]]; then
    echo "[setup.sh] Phase 2: contribute ..."
    $SNARKJS zkey contribute \
        build/aggregation_0000.zkey \
        build/aggregation_final.zkey \
        --name="ZTFA v1 phase2 contribution" \
        -e="$(date +%s%N)$RANDOM"
fi

echo "[setup.sh] Exporting verification key ..."
$SNARKJS zkey export verificationkey \
    build/aggregation_final.zkey \
    build/verification_key.json

echo "[setup.sh] OK"
ls -lh build/aggregation_final.zkey build/verification_key.json
