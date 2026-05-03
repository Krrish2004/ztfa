#!/usr/bin/env bash
# Shared env loader. Source from any script: `source scripts/env.sh`
# Loads .env if present, falls back to .env.example.

set -e

ZTFA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ZTFA_ROOT

if [[ -f "$ZTFA_ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    . "$ZTFA_ROOT/.env"
    set +a
elif [[ -f "$ZTFA_ROOT/.env.example" ]]; then
    echo "[env.sh] WARNING: .env not found, using .env.example defaults"
    set -a
    # shellcheck source=/dev/null
    . "$ZTFA_ROOT/.env.example"
    set +a
else
    echo "[env.sh] FATAL: no .env or .env.example found in $ZTFA_ROOT" >&2
    exit 1
fi

: "${N_CLIENTS:?N_CLIENTS not set}"
: "${CHAIN_RPC_URL:?CHAIN_RPC_URL not set}"
