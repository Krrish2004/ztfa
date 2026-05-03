"""Tests for the deterministic patient → client split."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from split_config import build_manifest, patient_to_client


@pytest.fixture
def csv_path() -> Path:
    return Path(__file__).resolve().parent.parent / "Multi-Sensor_Medical_IoT_Dataset.csv"


def test_deterministic(csv_path: Path) -> None:
    """Same patient_id maps to same client every call."""
    assert patient_to_client("P001", 3) == patient_to_client("P001", 3)
    assert patient_to_client("P099", 5) == patient_to_client("P099", 5)


def test_disjoint(csv_path: Path) -> None:
    m = build_manifest(csv_path, 3)
    seen: set[str] = set()
    for patients in m.values():
        for p in patients:
            assert p not in seen, f"patient {p} appears in multiple shards"
            seen.add(p)


def test_covers_all_patients(csv_path: Path) -> None:
    df = pd.read_csv(csv_path)
    m = build_manifest(csv_path, 3)
    flat = [p for ps in m.values() for p in ps]
    assert set(flat) == set(df["patient_id"].unique())


def test_balanced_split(csv_path: Path) -> None:
    """For ~100 patients into 3 clients, each gets between ~25 and ~45."""
    m = build_manifest(csv_path, 3)
    for c, patients in m.items():
        assert 20 <= len(patients) <= 50, f"client {c} got {len(patients)} patients"
