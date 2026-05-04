#!/usr/bin/env bash
# Render build hook for ztfa-aggregator.
# Installs the shared ztfa_crypto package first, then the aggregator itself.
# Run from repo root by Render's build command.
set -euo pipefail

echo "[render-build] python: $(python --version)"
echo "[render-build] pip: $(pip --version)"

echo "[render-build] installing ztfa-crypto (shared)..."
pip install -e ./shared

echo "[render-build] installing ztfa-aggregator..."
pip install -e ./aggregator

echo "[render-build] done."
