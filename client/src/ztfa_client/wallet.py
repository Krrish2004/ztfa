"""Client wallet — submits commitments + claims refunds on chain."""

from __future__ import annotations

import json

import structlog
from web3 import Web3
from web3.middleware import geth_poa_middleware

log = structlog.get_logger()

ABI = json.loads(
    """[
    {"inputs":[
        {"internalType":"uint256","name":"t","type":"uint256"},
        {"internalType":"bytes32","name":"H","type":"bytes32"}
    ],"name":"submitClientCommitment","outputs":[],"stateMutability":"payable","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"t","type":"uint256"}],"name":"claimRefund","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"t","type":"uint256"}],"name":"isRoundVerified","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}
]"""
)


class ClientWallet:
    def __init__(
        self,
        rpc_url: str,
        chain_id: int,
        private_key: str,
        contract_address: str,
        per_client_fee_wei: int,
    ) -> None:
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self.account = self.w3.eth.account.from_key(private_key)
        self.chain_id = chain_id
        self.fee = per_client_fee_wei
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(contract_address), abi=ABI
        )

    @property
    def address(self) -> str:
        return self.account.address

    def submit_commitment(self, t: int, h_i_bytes: bytes) -> str:
        tx = self.contract.functions.submitClientCommitment(t, h_i_bytes).build_transaction(
            {
                "from": self.account.address,
                "value": self.fee,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "chainId": self.chain_id,
                "gas": 250_000,
            }
        )
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError(f"submitClientCommitment reverted: {tx_hash.hex()}")
        log.info("client_commit_tx", t=t, gas=receipt.gasUsed, tx=tx_hash.hex())
        return tx_hash.hex()

    def claim_refund(self, t: int) -> str:
        tx = self.contract.functions.claimRefund(t).build_transaction(
            {
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "chainId": self.chain_id,
                "gas": 200_000,
            }
        )
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError(f"claimRefund reverted: {tx_hash.hex()}")
        log.info("client_refund_tx", t=t, gas=receipt.gasUsed)
        return tx_hash.hex()

    def is_round_verified(self, t: int) -> bool:
        return bool(self.contract.functions.isRoundVerified(t).call())
