"""Chain client — submits startRound and submitAggregateAndProof."""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from web3 import Web3

from .config import Settings
from .prover import Groth16Proof

# web3.py renamed the POA middleware between v6 and v7.
# v6: web3.middleware.geth_poa_middleware
# v7: web3.middleware.ExtraDataToPOAMiddleware
try:
    from web3.middleware import ExtraDataToPOAMiddleware as _PoaMiddleware  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover — fallback for web3 6.x
    from web3.middleware import geth_poa_middleware as _PoaMiddleware  # type: ignore[attr-defined,no-redef]

log = structlog.get_logger()

# ABI fragment — only the functions we call. Avoids vendoring Foundry artifacts.
FEDERATION_ROUND_ABI = json.loads(
    """[
    {"inputs":[{"internalType":"uint256","name":"t","type":"uint256"}],"name":"startRound","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[
        {"internalType":"uint256","name":"t","type":"uint256"},
        {"internalType":"bytes32","name":"H_agg","type":"bytes32"},
        {"internalType":"uint256[2]","name":"a","type":"uint256[2]"},
        {"internalType":"uint256[2][2]","name":"b","type":"uint256[2][2]"},
        {"internalType":"uint256[2]","name":"c","type":"uint256[2]"},
        {"internalType":"uint256[4]","name":"pubSignals","type":"uint256[4]"}
    ],"name":"submitAggregateAndProof","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"t","type":"uint256"}],"name":"isRoundVerified","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"t","type":"uint256"}],"name":"getRound","outputs":[
        {"internalType":"uint8","name":"state","type":"uint8"},
        {"internalType":"uint256","name":"deadline","type":"uint256"},
        {"internalType":"uint256","name":"clientCount","type":"uint256"},
        {"internalType":"bytes32","name":"aggregateCommit","type":"bytes32"},
        {"internalType":"uint256","name":"escrowed","type":"uint256"}
    ],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"t","type":"uint256"},{"internalType":"uint256","name":"idx","type":"uint256"}],"name":"getCommit","outputs":[
        {"internalType":"bytes32","name":"","type":"bytes32"},
        {"internalType":"address","name":"","type":"address"}
    ],"stateMutability":"view","type":"function"}
]"""
)


class ChainClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.w3 = Web3(Web3.HTTPProvider(settings.chain_rpc_url))
        # Anvil + Polygon zkEVM are POA-friendly chains
        self.w3.middleware_onion.inject(_PoaMiddleware, layer=0)
        self.account = self.w3.eth.account.from_key(settings.aggregator_private_key)
        if not settings.federation_round_address:
            raise RuntimeError("FEDERATION_ROUND_ADDRESS not set")
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(settings.federation_round_address),
            abi=FEDERATION_ROUND_ABI,
        )

    def start_round(self, t: int) -> str:
        tx = self.contract.functions.startRound(t).build_transaction(
            {
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "chainId": self.settings.chain_id,
                "gas": 200_000,
            }
        )
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        log.info("startRound", t=t, tx=tx_hash.hex(), gas_used=receipt.gasUsed)
        return tx_hash.hex()

    def submit_proof(self, t: int, h_agg_hex: str, proof: Groth16Proof) -> str:
        h_agg_bytes = bytes.fromhex(h_agg_hex.removeprefix("0x")).rjust(32, b"\0")
        a = [int(x, 16) for x in proof.a]
        b = [[int(x, 16) for x in row] for row in proof.b]
        c = [int(x, 16) for x in proof.c]
        public = [int(x, 16) for x in proof.public_signals]
        tx = self.contract.functions.submitAggregateAndProof(
            t, h_agg_bytes, a, b, c, public
        ).build_transaction(
            {
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "chainId": self.settings.chain_id,
                "gas": 1_000_000,
            }
        )
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError(f"submitAggregateAndProof reverted: {tx_hash.hex()}")
        log.info("submitAggregateAndProof", t=t, tx=tx_hash.hex(), gas_used=receipt.gasUsed)
        return tx_hash.hex()

    def is_round_verified(self, t: int) -> bool:
        return bool(self.contract.functions.isRoundVerified(t).call())

    def get_round(self, t: int) -> dict[str, object]:
        state, deadline, count, h_agg, escrowed = self.contract.functions.getRound(t).call()
        return {
            "state": state,
            "deadline": deadline,
            "client_count": count,
            "aggregate_commit": "0x" + h_agg.hex(),
            "escrowed": escrowed,
        }

    def get_client_commits(self, t: int, expected_count: int) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for i in range(expected_count):
            h, addr = self.contract.functions.getCommit(t, i).call()
            out.append(("0x" + h.hex(), addr))
        return out
