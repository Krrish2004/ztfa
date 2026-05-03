"""Local PyTorch trainer. MLP 15→32→16→4."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn

from .features import NUM_CLASSES, NUM_FEATURES


class HARMLP(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(NUM_FEATURES, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, NUM_CLASSES),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def make_seeded_model(seed: int = 42) -> HARMLP:
    torch.manual_seed(seed)
    return HARMLP()


def flatten_state_dict(model: nn.Module) -> np.ndarray:
    """Concat all parameters into a single float32 vector. Order is fixed by
    Python dict insertion order, which `nn.Module.state_dict()` preserves."""
    parts = [p.detach().cpu().numpy().reshape(-1) for p in model.parameters()]
    return np.concatenate(parts).astype(np.float64)  # float64 for CKKS precision


def load_flat_into_model(model: nn.Module, flat: np.ndarray) -> None:
    """Inverse of `flatten_state_dict` — copies a flat vector back into the
    model's parameter tensors in order."""
    idx = 0
    for p in model.parameters():
        n = p.numel()
        chunk = flat[idx : idx + n].reshape(p.shape)
        with torch.no_grad():
            p.copy_(torch.tensor(chunk, dtype=p.dtype))
        idx += n
    if idx != flat.size:
        raise ValueError(f"flat size mismatch: had {flat.size}, model expected {idx}")


@dataclass
class TrainResult:
    flat_weights: np.ndarray
    final_loss: float


def train_one_round(
    model: HARMLP,
    X: np.ndarray,
    y: np.ndarray,
    *,
    epochs: int = 5,
    batch_size: int = 32,
    lr: float = 1e-2,
    seed: int = 0,
) -> TrainResult:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)

    optim = torch.optim.SGD(model.parameters(), lr=lr, momentum=0.9)
    crit = nn.CrossEntropyLoss()
    n = X.shape[0]
    last_loss = float("inf")

    model.train()
    for _ in range(epochs):
        idx = rng.permutation(n)
        for s in range(0, n, batch_size):
            b = idx[s : s + batch_size]
            xb = torch.tensor(X[b])
            yb = torch.tensor(y[b])
            optim.zero_grad()
            logits = model(xb)
            loss = crit(logits, yb)
            loss.backward()
            optim.step()
            last_loss = float(loss.item())
    return TrainResult(flat_weights=flatten_state_dict(model), final_loss=last_loss)


def evaluate(model: HARMLP, X: np.ndarray, y: np.ndarray) -> float:
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor(X))
        preds = logits.argmax(dim=1).numpy()
    return float((preds == y).mean())
