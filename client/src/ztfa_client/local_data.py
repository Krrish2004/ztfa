"""Read labeled / unlabeled records from the client's SQLite DB."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd


def labeled_dataframe(sqlite_path: Path) -> pd.DataFrame:
    if not sqlite_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(sqlite_path) as conn:
        rows = conn.execute("SELECT payload FROM labeled_records").fetchall()
    docs = [json.loads(r[0]) for r in rows]
    return pd.DataFrame(docs)


def unlabeled_dataframe(sqlite_path: Path) -> pd.DataFrame:
    if not sqlite_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(sqlite_path) as conn:
        rows = conn.execute("SELECT id, payload FROM unlabeled_records").fetchall()
    docs = [{"id": rid, **json.loads(p)} for rid, p in rows]
    return pd.DataFrame(docs)


def write_accuracy(sqlite_path: Path, round_t: int, accuracy: float, n_samples: int) -> None:
    from datetime import datetime
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO accuracy_history(round_t, accuracy, n_samples, measured_at) VALUES(?,?,?,?)",
            (round_t, float(accuracy), n_samples, datetime.utcnow().isoformat()),
        )
        conn.commit()


def write_prediction(
    sqlite_path: Path, record_id: int, predicted: str, confidence: float
) -> None:
    from datetime import datetime
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "INSERT INTO predictions(record_id, predicted_activity, confidence, predicted_at) VALUES(?,?,?,?)",
            (record_id, predicted, float(confidence), datetime.utcnow().isoformat()),
        )
        conn.commit()


def accuracy_history(sqlite_path: Path) -> list[dict[str, object]]:
    if not sqlite_path.exists():
        return []
    with sqlite3.connect(sqlite_path) as conn:
        rows = conn.execute(
            "SELECT round_t, accuracy, n_samples, measured_at FROM accuracy_history ORDER BY round_t"
        ).fetchall()
    return [
        {"round_t": r[0], "accuracy": r[1], "n_samples": r[2], "measured_at": r[3]}
        for r in rows
    ]


def recent_predictions(sqlite_path: Path, limit: int = 50) -> list[dict[str, object]]:
    if not sqlite_path.exists():
        return []
    with sqlite3.connect(sqlite_path) as conn:
        rows = conn.execute(
            "SELECT record_id, predicted_activity, confidence, predicted_at "
            "FROM predictions ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"record_id": r[0], "activity": r[1], "confidence": r[2], "at": r[3]}
        for r in rows
    ]
