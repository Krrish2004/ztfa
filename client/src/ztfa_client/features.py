"""Feature extraction + global normalization (CLAUDE.md G2)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# 15 sensor features (drop patient_id, timestamp, latitude, longitude,
# fall_detected, activity_type — see CLAUDE.md §12.F)
FEATURE_COLUMNS = [
    "heart_rate",
    "spo2_level",
    "ecg_signal",
    "respiration_rate",
    "body_temperature",
    "blood_pressure_sys",
    "blood_pressure_dia",
    "blood_glucose",
    "eeg_alpha_power",
    "eeg_beta_power",
    "emg_signal_strength",
    "step_count",
    "ambient_temperature",
    "stress_level_index",
]
# That's 14. Add a derived "pulse_pressure" (sys - dia) to make 15 — gives the
# MLP a non-linear-friendly engineered feature without changing the schema.

ACTIVITY_LABELS = ["sleeping", "walking", "resting", "running"]
LABEL_TO_INT = {a: i for i, a in enumerate(ACTIVITY_LABELS)}
NUM_FEATURES = 15  # FEATURE_COLUMNS + pulse_pressure
NUM_CLASSES = 4


@dataclass
class FeatureNormStats:
    mean: list[float]
    std: list[float]

    def to_json(self) -> str:
        return json.dumps({"mean": self.mean, "std": self.std}, indent=2)

    @classmethod
    def from_json(cls, s: str) -> "FeatureNormStats":
        d = json.loads(s)
        return cls(mean=d["mean"], std=d["std"])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())

    @classmethod
    def load(cls, path: Path) -> "FeatureNormStats":
        return cls.from_json(path.read_text())


def add_engineered(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["pulse_pressure"] = out["blood_pressure_sys"] - out["blood_pressure_dia"]
    return out


def feature_matrix(df: pd.DataFrame, norm: FeatureNormStats) -> np.ndarray:
    df = add_engineered(df)
    cols = FEATURE_COLUMNS + ["pulse_pressure"]
    X = df[cols].to_numpy(dtype=np.float32)
    mean = np.asarray(norm.mean, dtype=np.float32)
    std = np.asarray(norm.std, dtype=np.float32)
    std = np.where(std < 1e-6, 1.0, std)
    return (X - mean) / std


def label_vector(df: pd.DataFrame) -> np.ndarray:
    return df["activity_type"].map(LABEL_TO_INT).to_numpy(dtype=np.int64)


def compute_global_norm(df: pd.DataFrame) -> FeatureNormStats:
    df = add_engineered(df)
    cols = FEATURE_COLUMNS + ["pulse_pressure"]
    arr = df[cols].to_numpy(dtype=np.float64)
    return FeatureNormStats(
        mean=arr.mean(axis=0).tolist(),
        std=arr.std(axis=0).tolist(),
    )
