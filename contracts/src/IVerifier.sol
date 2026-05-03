// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Interface matching the auto-generated Groth16 verifier from snarkjs.
/// Public signal count is locked to 4 = N (=3) commitments + H_sum.
interface IVerifier {
    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[4] calldata _pubSignals
    ) external view returns (bool);
}
