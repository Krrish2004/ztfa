// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script, console2} from "forge-std/Script.sol";
import {FederationRound} from "../src/FederationRound.sol";
import {IVerifier} from "../src/IVerifier.sol";
import {Groth16Verifier} from "../src/Verifier.sol";

/// @notice Deploy Verifier + FederationRound to Anvil (or any chain).
///
/// Usage (from contracts/):
///   forge script script/Deploy.s.sol:Deploy \
///     --rpc-url http://localhost:8545 \
///     --private-key $DEPLOYER_PRIVATE_KEY \
///     --broadcast
///
/// Reads config from environment:
///   PER_CLIENT_FEE_WEI       (default: 5e14 wei = 0.0005 ETH)
///   AGGREGATOR_PAYMENT_WEI   (default: 1e15 wei = 0.001 ETH)
///   ROUND_TIMEOUT_SEC        (default: 600)
///   N_CLIENTS                (default: 3)
///   AGGREGATOR_ADDRESS       (default: 0x70997970C51812dc3A010C7d01b50e0d17dc79C8 — anvil[1])
///   PREFUND_ROUNDS           (default: 100 — set to 1 for cheap testnet deploys)
contract Deploy is Script {
    function run() external {
        uint256 perFee = vm.envOr("PER_CLIENT_FEE_WEI", uint256(5e14));
        uint256 aggPay = vm.envOr("AGGREGATOR_PAYMENT_WEI", uint256(1e15));
        uint256 timeout = vm.envOr("ROUND_TIMEOUT_SEC", uint256(600));
        uint8 n = uint8(vm.envOr("N_CLIENTS", uint256(3)));
        address aggregator = vm.envOr(
            "AGGREGATOR_ADDRESS", address(0x70997970C51812dc3A010C7d01b50e0d17dc79C8)
        );
        uint256 prefundRounds = vm.envOr("PREFUND_ROUNDS", uint256(100));

        vm.startBroadcast();

        Groth16Verifier verifier = new Groth16Verifier();
        FederationRound round = new FederationRound(
            aggregator,
            IVerifier(address(verifier)),
            perFee,
            aggPay,
            timeout,
            n
        );

        // Pre-fund the round contract so it can pay the aggregator on verify.
        // Default 100 rounds × aggPay; reduce via PREFUND_ROUNDS for testnets.
        if (prefundRounds > 0) {
            (bool sent,) = payable(address(round)).call{value: aggPay * prefundRounds}("");
            require(sent, "fund failed");
        }

        vm.stopBroadcast();

        console2.log("Verifier:        ", address(verifier));
        console2.log("FederationRound: ", address(round));
        console2.log("Aggregator:      ", aggregator);
        console2.log("perClientFee:    ", perFee);
        console2.log("aggregatorPayment:", aggPay);
        console2.log("expectedClients: ", n);
    }
}
