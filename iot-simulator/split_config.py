"""Deterministic patient_id → client mapping.

For N clients, hash(patient_id) mod N → client index.
Writes per-client manifest JSON listing assigned patient_ids.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def patient_to_client(patient_id: str, n_clients: int) -> int:
    """Stable mapping from patient_id (e.g., 'P075') to client index in [0, N).

    Uses SHA-256 mod N rather than Python `hash()` to be deterministic across
    runs and across processes (Python's randomized hash would not be).
    """
    h = hashlib.sha256(patient_id.encode("utf-8")).digest()
    return int.from_bytes(h, "big") % n_clients


def build_manifest(csv_path: Path, n_clients: int) -> dict[int, list[str]]:
    """Return {client_idx: [patient_ids...]}."""
    df = pd.read_csv(csv_path)
    if "patient_id" not in df.columns:
        raise ValueError("CSV missing patient_id column")
    patients = sorted(df["patient_id"].unique())
    manifest: dict[int, list[str]] = {i: [] for i in range(n_clients)}
    for p in patients:
        manifest[patient_to_client(p, n_clients)].append(p)
    return manifest


def write_manifests(csv_path: Path, n_clients: int, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(csv_path, n_clients)
    for client_idx, patients in manifest.items():
        path = out_dir / f"client_{client_idx}_manifest.json"
        path.write_text(json.dumps({"client_id": client_idx, "patients": patients}, indent=2))
    summary = {
        "n_clients": n_clients,
        "total_patients": sum(len(v) for v in manifest.values()),
        "per_client_count": {k: len(v) for k, v in manifest.items()},
    }
    (out_dir / "split_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--n-clients", type=int, default=3)
    parser.add_argument("--out-dir", type=Path, default=Path("./iot-simulator/manifests"))
    args = parser.parse_args()
    write_manifests(args.csv, args.n_clients, args.out_dir)
    print(f"  ✓ wrote {args.n_clients} client manifests to {args.out_dir}")
