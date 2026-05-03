"""MQTT subscriber → SQLite. Receives sensor stream from iot-simulator."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
import structlog

log = structlog.get_logger()

LABELED_TOPIC = "hiot/labeled"
UNLABELED_TOPIC = "hiot/unlabeled"

SCHEMA = """
CREATE TABLE IF NOT EXISTS labeled_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL,
    activity TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS unlabeled_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    predicted_activity TEXT NOT NULL,
    confidence REAL NOT NULL,
    predicted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accuracy_history (
    round_t INTEGER PRIMARY KEY,
    accuracy REAL NOT NULL,
    n_samples INTEGER NOT NULL,
    measured_at TEXT NOT NULL
);
"""


class IoTAdapter:
    def __init__(self, sqlite_path: Path, mqtt_host: str = "localhost", mqtt_port: int = 1883) -> None:
        self.sqlite_path = sqlite_path
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self._init_schema()
        self._client: mqtt.Client | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        log.info("mqtt_connected", rc=rc, host=self.mqtt_host)
        client.subscribe([(LABELED_TOPIC, 0), (UNLABELED_TOPIC, 0)])

    def _on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode()
            doc = json.loads(payload)
            now = datetime.utcnow().isoformat()
            with sqlite3.connect(self.sqlite_path) as conn:
                if msg.topic == LABELED_TOPIC:
                    conn.execute(
                        "INSERT INTO labeled_records(received_at, timestamp, payload, activity) VALUES(?,?,?,?)",
                        (now, doc.get("timestamp", ""), payload, doc.get("activity_type", "")),
                    )
                elif msg.topic == UNLABELED_TOPIC:
                    conn.execute(
                        "INSERT INTO unlabeled_records(received_at, timestamp, payload) VALUES(?,?,?)",
                        (now, doc.get("timestamp", ""), payload),
                    )
                conn.commit()
        except Exception as e:
            log.error("mqtt_msg_error", error=str(e))

    def start(self) -> None:
        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self.mqtt_host, self.mqtt_port)

        self._thread = threading.Thread(target=self._client.loop_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._client is not None:
            self._client.disconnect()
        self._stop.set()
