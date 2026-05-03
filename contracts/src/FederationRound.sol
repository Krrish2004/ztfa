// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IVerifier} from "./IVerifier.sol";

/// @title FederationRound — round registry for ZTFA federated aggregation
/// @notice
///   Implements HLD §7. Holds round state, escrows per-client fees, verifies
///   the aggregator's Groth16 proof on `submitAggregateAndProof`, releases
///   payment on successful verification, and refunds clients on timeout.
///
/// @dev Ciphertexts NEVER touch this contract. Only Poseidon commitments
///   (bytes32) and the SNARK proof.
contract FederationRound {
    // --- Types ---

    enum State {
        None,         // 0 — round t never opened
        Open,         // 1 — accepting client commitments
        Verified,     // 2 — proof accepted; aggregator paid
        Refundable    // 3 — deadline passed without verification; clients can refund
    }

    struct Round {
        uint256 startBlock;
        uint256 deadline;            // block.timestamp at which round expires
        bytes32[] clientCommits;     // H_i in submission order
        address[] participants;      // for refund + payout (parallel to clientCommits)
        bytes32 aggregateCommit;     // H_sum (set on verify)
        State state;
        uint256 escrowed;            // ΣperClientFee held in this round
        mapping(address => bool) hasCommitted;
        mapping(address => uint256) escrowOf;
    }

    // --- Immutable config ---

    uint256 public immutable perClientFee;
    uint256 public immutable aggregatorPayment;
    uint256 public immutable roundTimeoutSec;
    uint8 public immutable expectedClients;     // N — locked at deploy
    address public immutable aggregator;
    IVerifier public immutable verifier;

    // --- State ---

    mapping(uint256 => Round) private rounds;

    // --- Events ---

    event RoundStarted(uint256 indexed t, uint256 deadline);
    event ClientCommitted(uint256 indexed t, address indexed client, bytes32 H);
    event RoundVerified(uint256 indexed t, bytes32 H_agg);
    event RoundRefunded(uint256 indexed t, address indexed client, uint256 amount);
    event AggregatorPaid(uint256 indexed t, uint256 amount);

    // --- Errors ---

    error NotAggregator();
    error WrongFee();
    error RoundClosed();
    error AlreadyCommitted();
    error TooManyClients();
    error WrongClientCount();
    error ProofFailed();
    error NotRefundable();
    error AlreadyVerified();
    error NoEscrow();
    error PaymentFailed();
    error DeadlinePassed();
    error RoundDoesNotExist();

    // --- Modifiers ---

    modifier onlyAggregator() {
        if (msg.sender != aggregator) revert NotAggregator();
        _;
    }

    // --- Constructor ---

    constructor(
        address _aggregator,
        IVerifier _verifier,
        uint256 _perClientFee,
        uint256 _aggregatorPayment,
        uint256 _roundTimeoutSec,
        uint8 _expectedClients
    ) {
        aggregator = _aggregator;
        verifier = _verifier;
        perClientFee = _perClientFee;
        aggregatorPayment = _aggregatorPayment;
        roundTimeoutSec = _roundTimeoutSec;
        expectedClients = _expectedClients;
    }

    // --- External: aggregator ---

    /// @notice Open round t. Only the aggregator can do this.
    function startRound(uint256 t) external onlyAggregator {
        Round storage r = rounds[t];
        if (r.state != State.None) revert RoundClosed();
        r.startBlock = block.number;
        r.deadline = block.timestamp + roundTimeoutSec;
        r.state = State.Open;
        emit RoundStarted(t, r.deadline);
    }

    /// @notice Submit aggregate commitment + Groth16 proof. Verifies and pays
    ///   the aggregator on success.
    /// @param t        round index
    /// @param H_agg    Poseidon-chain commitment to c_sum
    /// @param a, b, c  Groth16 proof components
    /// @param pubSignals length must equal expectedClients + 1; ordered as
    ///                   [H_1, H_2, ..., H_N, H_agg]
    function submitAggregateAndProof(
        uint256 t,
        bytes32 H_agg,
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[4] calldata pubSignals
    ) external onlyAggregator {
        Round storage r = rounds[t];
        if (r.state != State.Open) revert RoundClosed();
        if (block.timestamp > r.deadline) revert DeadlinePassed();
        if (r.clientCommits.length != expectedClients) revert WrongClientCount();

        // Public signals MUST match the on-chain commitments in order.
        // Layout: pubSignals[0..N-1] = H_i,  pubSignals[N] = H_agg.
        uint8 n = expectedClients;
        for (uint256 i = 0; i < n; i++) {
            if (bytes32(pubSignals[i]) != r.clientCommits[i]) revert ProofFailed();
        }
        if (bytes32(pubSignals[n]) != H_agg) revert ProofFailed();

        bool ok = verifier.verifyProof(a, b, c, pubSignals);
        if (!ok) revert ProofFailed();

        r.aggregateCommit = H_agg;
        r.state = State.Verified;

        // Pay aggregator. Funded by the contract's balance (must be pre-funded
        // separately; v1 deploy script forwards initial value).
        (bool sent,) = payable(aggregator).call{value: aggregatorPayment}("");
        if (!sent) revert PaymentFailed();

        emit RoundVerified(t, H_agg);
        emit AggregatorPaid(t, aggregatorPayment);
    }

    // --- External: client ---

    /// @notice Submit Hᵢ for round t. Pays perClientFee into round escrow.
    function submitClientCommitment(uint256 t, bytes32 H) external payable {
        Round storage r = rounds[t];
        if (r.state != State.Open) revert RoundClosed();
        if (block.timestamp > r.deadline) revert DeadlinePassed();
        if (msg.value != perClientFee) revert WrongFee();
        if (r.hasCommitted[msg.sender]) revert AlreadyCommitted();
        if (r.clientCommits.length >= expectedClients) revert TooManyClients();

        r.hasCommitted[msg.sender] = true;
        r.escrowOf[msg.sender] = msg.value;
        r.escrowed += msg.value;
        r.clientCommits.push(H);
        r.participants.push(msg.sender);

        emit ClientCommitted(t, msg.sender, H);
    }

    /// @notice After deadline w/o verification, clients reclaim escrow.
    function claimRefund(uint256 t) external {
        Round storage r = rounds[t];
        if (r.state == State.Verified) revert AlreadyVerified();
        if (r.state == State.None) revert RoundDoesNotExist();
        if (block.timestamp <= r.deadline) revert NotRefundable();

        if (r.state == State.Open) {
            // First refund call after deadline transitions state.
            r.state = State.Refundable;
        }

        uint256 amt = r.escrowOf[msg.sender];
        if (amt == 0) revert NoEscrow();
        r.escrowOf[msg.sender] = 0;
        r.escrowed -= amt;

        (bool sent,) = payable(msg.sender).call{value: amt}("");
        if (!sent) revert PaymentFailed();

        emit RoundRefunded(t, msg.sender, amt);
    }

    // --- View ---

    function isRoundVerified(uint256 t) external view returns (bool) {
        return rounds[t].state == State.Verified;
    }

    function getRound(uint256 t)
        external
        view
        returns (
            State state,
            uint256 deadline,
            uint256 clientCount,
            bytes32 aggregateCommit,
            uint256 escrowed
        )
    {
        Round storage r = rounds[t];
        return (r.state, r.deadline, r.clientCommits.length, r.aggregateCommit, r.escrowed);
    }

    function getCommit(uint256 t, uint256 idx) external view returns (bytes32, address) {
        Round storage r = rounds[t];
        return (r.clientCommits[idx], r.participants[idx]);
    }

    /// @notice Required to receive aggregator-payment funding.
    receive() external payable {}
}
