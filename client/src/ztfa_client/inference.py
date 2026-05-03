"""Continuous inference loop — runs the latest model over unlabeled records."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import structlog
import torch

from .config import Settings
from .features import (
    ACTIVITY_LABELS,
    FeatureNormStats,
    add_engineered,
    feature_matrix,
)
from .local_data import unlabeled_dataframe, write_prediction
from .trainer import HARMLP

log = structlog.get_logger()


def run_inference_once(settings: Settings) -> int:
    """Predict on every unlabeled record that doesn't yet have a prediction.
    Returns the number of new predictions written."""
    sqlite_path = settings.data_dir / f"client_{settings.client_id}.sqlite"
    if not sqlite_path.exists():
        return 0

    df = unlabeled_dataframe(sqlite_path)
    if df.empty:
        return 0

    # Load latest model
    model_dir = settings.data_dir / f"models_client_{settings.client_id}"
    rounds = sorted(int(p.stem.split("_")[-1]) for p in model_dir.glob("w_global_round_*.pt"))
    model = HARMLP()
    if rounds:
        sd = torch.load(model_dir / f"w_global_round_{rounds[-1]}.pt", weights_only=True)
        model.load_state_dict(sd)
    elif settings.initial_weights_path.exists():
        model.load_state_dict(torch.load(settings.initial_weights_path, weights_only=True))

    norm = FeatureNormStats.load(settings.feature_norm_path)
    X = feature_matrix(df, norm)
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor(X))
        probs = torch.softmax(logits, dim=1).numpy()
        preds = probs.argmax(axis=1)

    written = 0
    for i, rec_id in enumerate(df["id"].astype(int)):
        write_prediction(
            sqlite_path,
            int(rec_id),
            ACTIVITY_LABELS[int(preds[i])],
            float(probs[i, preds[i]]),
        )
        written += 1
    return written


def run_inference_forever(settings: Settings, interval_sec: float = 5.0) -> None:
    while True:
        try:
            n = run_inference_once(settings)
            if n:
                log.info("inference_batch", n=n)
        except Exception as e:
            log.error("inference_error", error=str(e))
        time.sleep(interval_sec)
