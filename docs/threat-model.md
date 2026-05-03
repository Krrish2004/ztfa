# ZTFA Threat Model — v1

Mapping HLD §9.2 (T1..T10) to where each defense lives in the codebase.

| ID | Attack | Adversary | Defense | Code reference |
|---|---|---|---|---|
| T1 | Model-inversion / gradient-leakage on raw weights | Aggregator (passive) | Weights only leave client encrypted under CKKS; RLWE hardness | `client/src/ztfa_client/ckks_engine.py:encrypt_weights` |
| T2 | Aggregator silently drops a client's contribution | Aggregator (active) | Contract enforces `clientCommits.length == expectedClients` before allowing proof | `contracts/src/FederationRound.sol:submitAggregateAndProof` (`WrongClientCount`) |
| T3 | Aggregator substitutes wrong ciphertext for one client | Aggregator (active) | SNARK statement requires `Hash(c_i) == H_i` for the on-chain H_i; pubSignals linkage check at the contract level rejects mismatch | `circuits/aggregation.circom` (PoseidonChainK constraint), `contracts/src/FederationRound.sol` (`pubSignals[i] != clientCommits[i]` check) |
| T4 | Aggregator lies about the result | Aggregator (active) | `Hash(c_sum) == H_sum` enforced inside circuit; client re-derives H_sum from fetched c_sum and refuses to accept on mismatch | `circuits/aggregation.circom`, `client/src/ztfa_client/round_client.py` |
| T5 | Network eavesdropper | Network attacker | TLS at transport (Mosquitto + HTTPS in prod) + CKKS at app layer; defense-in-depth | `scripts/mosquitto.conf` (TLS slot), encryption mandatory before submit |
| T6 | Coalition of T-1 dishonest clients tries to decrypt | Insider clients | Threshold (T,N) sharing — no info leaks below T shares (v2 — single-issuer in v1) | v2: `ztfa_crypto.keygen` (DKG ceremony) |
| T7 | Server colludes with ≤T-1 clients | Server + clients | Same threshold guarantee (v2) | v2 |
| T8 | Chain operator censors transactions | Chain validators | Use a permissionless L2 (Polygon zkEVM in prod; Anvil in dev). Refund mechanism caps client harm at one round's perClientFee | `contracts/src/FederationRound.sol:claimRefund` |
| T9 | Replay of stale ciphertexts (round-t commit → round t+1) | Aggregator | Round index baked into commitment domain: `H_i = Poseidon(t || cid || c_i)`. Same ciphertext → different commit per round | `shared/ztfa_crypto/poseidon.py:commitment` |
| T10 | Quantum adversary recovers sk from public traffic | Future quantum | CKKS is post-quantum (RLWE) ✓; Groth16/BN254 is NOT — flagged for v2 STARK migration | v2 — see `docs/crypto-protocol.md` §3 |

## Out of scope for v1 (HLD §9.3, §13.1)

- Defense against **malicious clients submitting poisoned weights** (Krum, Trimmed-Mean, FLTrust, ZK range-proofs over weights)
- **Differential privacy** noise injection
- **Side-channel** defense on client device
- **Sybil resistance** (assumed handled by KYC at portal registration)

## Verifying defenses

The Foundry test suite runs adversarial scenarios that try each attack:

```bash
cd contracts && forge test -vv
```

- `test_T2_DroppedClient_RejectedByProofMismatch` — verifies T2 rejection
- `test_T3_SubstitutedCommit_FailsProof` — verifies T3 rejection
- `test_T9_ReplayAcrossRounds_DefendedByDomainSeparation` — documents T9
- `testInvalidProofRejected` — verifies T4 rejection
- `testClaimRefund_AfterDeadline` — verifies T8 escape hatch

All 13 tests pass.
