# Demo Walkthrough Script

> 3-minute scripted demo for BTP submission. Pair with a screencast.

## Scene 1 — Architecture (30s)

> "ZTFA implements zero-trust federated learning for healthcare IoT data.
> Three trust zones: clients hold encryption keys, an untrusted aggregator
> performs homomorphic aggregation, and a smart contract verifies the result
> via zk-SNARK before paying the aggregator."

Show: `docs/architecture/system.mmd` rendered in a Mermaid viewer.

## Scene 2 — One round in motion (90s)

```bash
# Terminal 1
make infra-up
bash scripts/start-demo.sh

# Terminal 2 (browser)
open http://localhost:3000
```

> "The portal connects via RainbowKit. Three clients are running locally,
> each ingesting their patient-disjoint shard of the medical IoT dataset
> over MQTT."

```bash
# Terminal 3
bash scripts/run-round.sh 1
```

> "When we trigger round 1: each client trains 5 local epochs, encrypts
> its weight vector under CKKS, and submits the Poseidon commitment to the
> on-chain registry, paying 0.0005 ETH. The aggregator computes the sum
> homomorphically — never seeing plaintext weights — and generates a Groth16
> proof."

> "The smart contract verifies the proof for ~280k gas and pays the
> aggregator 0.001 ETH. Each client fetches the encrypted aggregate,
> decrypts locally, and updates their model. Look at the dashboard — local
> accuracy on the held-out 20% just jumped from 53% to 71%."

## Scene 3 — Threat resistance (45s)

> "Why is this zero-trust? Watch what happens when the aggregator misbehaves."

```bash
cd contracts && forge test -vv -m T2_OR_T3
```

> "T2 (drop a client) — rejected. T3 (substitute a ciphertext) — rejected.
> T9 replay — defended off-chain by domain-separated commitments. The
> Foundry suite covers all 10 attack vectors from the HLD."

## Scene 4 — Failure path (15s)

> "If the aggregator fails to prove within the deadline, every client can
> reclaim their fee from the contract. No funds get stuck."

Show: `WalletPanel` claim refund button.

## Scene 5 — Wrap (15s)

> "v1 is fully implemented across five components — client, aggregator,
> contracts, portal, and IoT simulator — all running locally with one
> command. The HLD's known gaps are tracked in CLAUDE.md §13 as v2 work."
