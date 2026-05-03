"""Client CLI entry points."""

from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="ztfa-client")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest", help="Run MQTT subscriber → SQLite")
    p_round = sub.add_parser("run-round", help="Run a single FL round")
    p_round.add_argument("--t", type=int, required=True)
    sub.add_parser("local-rpc", help="Run the localhost RPC for the portal")
    sub.add_parser("infer-loop", help="Continuously infer over unlabeled records")
    args = parser.parse_args()

    if args.cmd == "ingest":
        from .config import Settings
        from .iot_adapter import IoTAdapter

        settings = Settings()
        adapter = IoTAdapter(
            sqlite_path=settings.data_dir / f"client_{settings.client_id}.sqlite",
            mqtt_host=settings.mqtt_host,
            mqtt_port=settings.mqtt_port,
        )
        adapter.start()
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            adapter.stop()

    elif args.cmd == "run-round":
        from .config import Settings
        from .round_client import ClientRoundOrchestrator

        settings = Settings()
        orch = ClientRoundOrchestrator(settings)
        outcome = asyncio.run(orch.run_round(args.t))
        print(outcome)
        sys.exit(0 if outcome.succeeded else 1)

    elif args.cmd == "local-rpc":
        from .local_rpc import main as rpc_main
        rpc_main()

    elif args.cmd == "infer-loop":
        from .config import Settings
        from .inference import run_inference_forever

        run_inference_forever(Settings())


if __name__ == "__main__":
    main()
