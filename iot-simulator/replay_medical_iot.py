"""Replay the Multi-Sensor Medical IoT CSV as MQTT stream.

For client `i`, we publish only that client's assigned patients' rows.
80% of each client's rows go to `hiot/labeled` (with activity_type kept);
20% go to `hiot/unlabeled` (activity_type stripped).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pandas as pd

from split_config import patient_to_client


def replay(
    csv_path: Path,
    client_id: int,
    n_clients: int,
    *,
    mqtt_host: str = "localhost",
    mqtt_port: int = 1883,
    rate_hz: float = 5.0,
    repeat: bool = True,
) -> None:
    df = pd.read_csv(csv_path)
    df = df[df["patient_id"].apply(lambda p: patient_to_client(p, n_clients) == client_id)]
    if df.empty:
        print(f"  ⚠ no rows assigned to client {client_id}")
        return

    df = df.reset_index(drop=True)
    n_train = int(len(df) * 0.8)
    print(f"  client {client_id}: {len(df)} rows → {n_train} labeled, {len(df) - n_train} unlabeled")

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(mqtt_host, mqtt_port)
    client.loop_start()

    period = 1.0 / max(rate_hz, 0.01)

    while True:
        for i in range(len(df)):
            row = df.iloc[i].to_dict()
            doc = {k: (None if pd.isna(v) else v) for k, v in row.items()}
            if i < n_train:
                client.publish("hiot/labeled", json.dumps(doc, default=str))
            else:
                doc.pop("activity_type", None)
                client.publish("hiot/unlabeled", json.dumps(doc, default=str))
            time.sleep(period)
        if not repeat:
            break

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--client-id", type=int, required=True)
    parser.add_argument("--n-clients", type=int, default=3)
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--rate-hz", type=float, default=20.0)
    parser.add_argument("--once", action="store_true", help="don't loop")
    args = parser.parse_args()
    replay(
        args.csv,
        args.client_id,
        args.n_clients,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        rate_hz=args.rate_hz,
        repeat=not args.once,
    )
