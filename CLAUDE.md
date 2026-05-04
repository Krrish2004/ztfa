# ZTFA — Zero-Trust Federated Aggregation for Health IoT

> **Project codename:** `ztfa`
> **Source of truth:** `HLD_ZeroTrust_FedAgg_HealthIoT.pdf` (root). Implementation MUST follow the HLD literally for v1; any deviation requires an explicit note in this file.

---

## 1. One-paragraph elevator pitch

A privacy-preserving federated learning platform for healthcare-IoT data. **N healthcare clients** locally train a shared model on their private patient streams, encrypt model weights with **CKKS Fully Homomorphic Encryption client-side**, and submit only ciphertexts to an **untrusted aggregator**. The aggregator computes encrypted **FedAvg** (`c_agg = (1/N)·Σcᵢ`) over ciphertexts, generates a **Groth16 zk-SNARK** proving correctness, and a **smart contract on Polygon zkEVM** verifies the proof on-chain in ~250k gas. Clients fetch the verified `c_agg`, threshold-decrypt it locally, and run inference on their own unlabeled IoT stream. **The aggregator never holds a secret key. Ciphertexts never go on-chain.**

---

## 2. Project type & scope

| Property | Value |
|---|---|
| Project type | Academic / BTP-style v1 |
| Scope | Full v1 implementation across all 5 components |
| Target environment | **Local dev only** (Docker Compose; Anvil chain; MinIO; Mosquitto) |
| HLD adherence | **Literal** — no design changes in v1 |
| Known gaps | Tracked in §13 *Future Work*, not fixed in v1 |
| Demo task | **4-class Activity Recognition** on `Multi-Sensor_Medical_IoT_Dataset.csv` (sleeping / walking / resting / running) |
| Demo federation size | **N = 3 clients** for the local demo. The protocol has **no hard cap on N** — proving time scales linearly (~3s/client on a workstation), R1CS constraints scale as ~33k × N, gas scales linearly per client. Practical N is bounded only by wall-clock proving budget. |

---

## 3. The five components (locked)

```
┌────────────────────────┐    ┌─────────────────────────┐    ┌──────────────────────┐
│  TRUSTED ZONE (Client) │    │   UNTRUSTED (Server)    │    │   PUBLIC LEDGER       │
│                        │    │                         │    │                      │
│  IoT Sensor (MQTT) ─┐  │    │  Federated Aggregator   │    │  FederationRound.sol │
│                     ▼  │    │  (FastAPI)              │    │                      │
│  Client Node ──────────┼───►│  - Ciphertext intake    │───►│  Verifier.sol        │
│  • PyTorch trainer     │ ct │  - Homomorphic FedAvg   │ π  │  (Groth16, ~250k gas)│
│  • CKKS engine ★       │    │  - Groth16 prover       │    │                      │
│  • Inference runtime   │    │  - NO secret keys       │    │  Polygon zkEVM       │
│  • Wallet              │    │                         │    │  (Anvil for dev)     │
│                        │    │  Storage: Postgres+MinIO│    │                      │
│  Portal UI (Next.js) ──┼────┘                         │    │                      │
└────────────────────────┘    └─────────────────────────┘    └──────────────────────┘
                              ★ CKKS engine lives ONLY on the client node.
```

| # | Component | Tech | Location |
|---|---|---|---|
| 1 | **IoT Adapter** | Eclipse Mosquitto (MQTT 1883, TLS) + SQLite | Client node |
| 2 | **Client Node** | Python 3.11 + PyTorch + OpenFHE (CKKS) + ethers.js wallet | Client desktop/edge |
| 3 | **Federated Aggregator** | Python FastAPI + OpenFHE C++ runtime + rapidsnark (Rust binary) | Docker (server) |
| 4 | **Smart Contracts** | Solidity 0.8.x (Foundry/Hardhat) on Polygon zkEVM (Anvil for dev) | On-chain |
| 5 | **Portal** | Next.js (App Router) + wagmi v2 + viem + **RainbowKit** + @tanstack/react-query (WalletConnect via RainbowKit) | Browser |

---

## 4. Cryptographic stack (locked from HLD §4)

| Layer | Choice | Parameters |
|---|---|---|
| FHE scheme | **CKKS (RNS variant)** via **TenSEAL** (Microsoft SEAL wrapper) — chosen over openfhe-python for pip-installability; HLD §11 lists SEAL as acceptable alternative | N=2¹⁵=32 768; log₂Q ≈ 438; modulus chain [60,40,60]; Δ=2⁴⁰; depth=1; 16 384 slots/ct |
| Hardness | Ring-LWE | post-quantum for FHE side |
| Algebraic ring | R = ℤ_q[X]/(X^N+1) | shared by FHE and ZK layers |
| ZK proof system | **Groth16** over BN254 | per-circuit trusted setup; ~200 byte proofs; 3-pairing verify |
| SNARK-friendly hash | **Poseidon** (circomlib) | ~250 R1CS constraints/hash |
| Circuit DSL | circom 2.x | |
| Prover binary | **rapidsnark** (Rust) | 5–10× faster than snarkjs |
| Settlement | EVM L2 — **Polygon zkEVM** in prod, **Anvil** for local dev | |

**Key management (v1 simplification, per HLD §4.2):** A **single trusted federation initiator** generates `(pk, sk)` once at federation launch, distributes `pk` to aggregator + chain + all clients, and distributes `sk` to clients via secure out-of-band channel. v2 will replace with multi-party threshold-DKG (Mouchet et al.) — see §13.

---

## 5. Federated round protocol (HLD §5.2 — 9 phases, locked)

```
[1] IoT stream ingestion        (continuous)        Client            trivial
[2] startRound(t)               (chain tx)          Aggregator → chain  ~50k gas
[3] Local training              (E epochs)          Client            seconds–minutes
[4] Encrypt cᵢ = CKKS.Enc(wᵢ); Hᵢ = Poseidon(cᵢ)   Client            ~100ms/ct
[5a] POST cᵢ to aggregator      (off-chain HTTPS)   Client → server   bandwidth
[5b] submitClientCommitment(t,Hᵢ){fee}              Client → chain    ~80k gas/client
[6] c_sum = Σcᵢ; c_agg = c_sum ⊗ (1/N)              Aggregator        ms/ct
[7] π ← Groth16.Prove(circuit, witness)             Aggregator        30–120s
[8] submitAggregateAndProof(t, H_agg, π)            Aggregator → chain ~280k gas
[9] Fetch c_agg, threshold-decrypt, update model    Client            seconds
```

**SNARK statement (HLD §6.1):**
- Public inputs: `{Hᵢ}ᵢ₌₁ᴺ`, `H_agg`, `N` (or `N⁻¹ mod q`)
- Private witness: `{cᵢ = (aᵢ, bᵢ)}`, `c_agg = (a_agg, b_agg)`
- Constraints:
  - `∀i : Hash(cᵢ) = Hᵢ` (commitment binding)
  - `c_sum = c₁ + c₂ + … + c_N` (coefficient-wise mod q)
  - `c_agg = c_sum ⊗ N⁻¹` (plaintext-scalar mult)
  - `Hash(c_agg) = H_agg`
- Estimated **~330k R1CS constraints** for N=10, 30–90s proving on Ryzen 7950X. For N=3 demo: ≈99k constraints, <30s proving.

**v1 SNARK design (locked):** The circuit operates on **full polynomial coefficients** of the encrypted polynomials — not a digest. To make this tractable in Groth16 over BN254, v1 uses a **hand-rolled minimal additive RLWE HE** (`ztfa_crypto.mini_he`) with ring degree N_ring = 256, single-prime modulus q ≈ 2⁶⁰. This replaces TenSEAL/CKKS for v1; semantically equivalent for FedAvg (additive over fixed-point quantized weights). The aggregator's `c_sum = Σ c_i` is computed by element-wise polynomial addition in BN254 Fr; the SNARK proves both the addition AND that each ciphertext's coefficients hash to its on-chain commitment. **No digest shortcut.** Constraint count: ~130k R1CS, <30s proving on a workstation, ptau power 18. Security level: ~80-bit (small ring), acceptable for academic v1 demo. Path to HLD's N_ring=2¹⁵ + 128-bit security: STARK migration (HLD §13.2) in v2.

---

## 6. Repository layout (target)

```
ztfa/
├── HLD_ZeroTrust_FedAgg_HealthIoT.pdf      # source of truth — DO NOT EDIT
├── CLAUDE.md                                # this file
├── README.md
├── docker-compose.yml                       # local dev: aggregator + postgres + minio + mosquitto + anvil
├── Makefile                                 # one-command demo
│
├── docs/
│   ├── references/                          # FHE.pdf and other PDFs
│   ├── architecture/                        # diagrams (Mermaid + Excalidraw)
│   ├── crypto-protocol.md                   # CKKS + Groth16 spec elaboration
│   └── runbook.md                           # how to run the demo end-to-end
│
├── client/                                  # Python — client node
│   ├── pyproject.toml
│   ├── src/ztfa_client/
│   │   ├── iot_adapter.py                   # MQTT + SQLite (labeled/unlabeled topics)
│   │   ├── trainer.py                       # PyTorch local training (HAR MLP)
│   │   ├── ckks_engine.py                   # OpenFHE bindings: encrypt, decrypt, encode
│   │   ├── poseidon.py                      # Poseidon hash matching circuit hash
│   │   ├── inference.py                     # continuous inference on unlabeled stream
│   │   ├── wallet.py                        # ethers / web3.py wallet for chain calls
│   │   ├── round_client.py                  # orchestrates one round
│   │   └── main.py
│   └── tests/
│
├── aggregator/                              # Python — federated server (NO secret keys)
│   ├── pyproject.toml
│   ├── src/ztfa_aggregator/
│   │   ├── api.py                           # FastAPI: /v1/round/{t}/submit, /aggregate, etc.
│   │   ├── orchestrator.py                  # 9-phase state machine
│   │   ├── homomorphic.py                   # OpenFHE C++ wrapper for c_sum, c_agg
│   │   ├── prover_adapter.py                # subprocess wrapper around rapidsnark
│   │   ├── chain.py                         # service wallet for startRound + submitProof
│   │   ├── storage.py                       # Postgres (round metadata) + MinIO (ciphertexts)
│   │   └── main.py
│   └── tests/
│
├── circuits/                                # circom — SNARK circuit
│   ├── aggregation.circom                   # the ~330k-constraint circuit
│   ├── poseidon_check.circom
│   ├── package.json                         # circom + snarkjs + circomlib
│   ├── powers_of_tau/                       # ceremony artifacts (gitignored beyond pointers)
│   └── scripts/
│       ├── compile.sh                       # circom → r1cs + wasm
│       ├── setup.sh                         # phase1 + phase2 → .zkey
│       └── export_verifier.sh               # → contracts/Verifier.sol
│
├── prover/                                  # Rust — rapidsnark wrapper binary
│   ├── Cargo.toml
│   └── src/main.rs                          # reads witness + zkey → produces proof.json
│
├── contracts/                               # Solidity — on-chain layer
│   ├── foundry.toml
│   ├── src/
│   │   ├── FederationRound.sol              # round registry; ~250 LoC
│   │   └── Verifier.sol                     # auto-generated; DO NOT hand-edit
│   ├── script/Deploy.s.sol
│   └── test/                                # forge tests
│
├── portal/                                  # TypeScript — Next.js client UI
│   ├── package.json
│   ├── app/
│   │   ├── page.tsx                         # dashboard (round status, accuracy plot)
│   │   ├── login/                           # WalletConnect SSO
│   │   ├── round-history/
│   │   ├── wallet/
│   │   └── settings/                        # CKKS key import, threshold T config
│   └── lib/
│       └── localhost-rpc.ts                 # browser → local client node bridge
│
├── iot-simulator/                           # Python — replays the medical-IoT CSV as MQTT stream
│   ├── replay_medical_iot.py                # shards by patient_id mod N, publishes to hiot/labeled & hiot/unlabeled
│   └── split_config.py                      # deterministic patient → client mapping
│
└── scripts/
    ├── bootstrap.sh                         # generate CKKS keys, distribute to clients (v1 single-issuer)
    ├── start-demo.sh                        # spin up everything via docker compose
    └── run-round.sh                         # trigger one full FL round for the demo
```

---

## 7. Build / run / test commands (canonical — keep in sync)

```bash
# First-time setup
./scripts/bootstrap.sh                       # CKKS keygen + Phase1/2 ceremony + verifier export

# Local demo
docker compose up -d                         # starts aggregator, postgres, minio, mosquitto, anvil
./scripts/run-round.sh                       # runs a full FL round end-to-end

# Per-component
cd client       && pytest && ruff check .
cd aggregator   && pytest && ruff check .
cd circuits     && bash scripts/compile.sh && bash scripts/setup.sh
cd prover       && cargo test && cargo build --release
cd contracts    && forge test -vv && forge fmt --check
cd portal       && pnpm install && pnpm test && pnpm lint && pnpm build
```

---

## 8. v1 invariants (MUST NOT be violated)

These are the **non-negotiable architectural constraints** from the HLD. Any code that breaks any of these must be rejected:

1. **CKKS engine runs ONLY on the client node.** Never instantiate `CryptoContext` with a secret key on the aggregator. Aggregator uses public-key-only context.
2. **Aggregator holds NO secret keys** — only `pk` and the SNARK proving key.
3. **Ciphertexts NEVER go on-chain.** Only Poseidon hashes (32 bytes) and the Groth16 proof (~200 bytes).
4. **The aggregator's payment is gated on successful proof verification.** No proof → no payout → client refund via `claimRound`.
5. **Round index `t` is part of the commitment domain separation** — prevents replay of stale ciphertexts (T9 in HLD §9.2).
6. **Hash inside circuit = Poseidon. Hash outside circuit = Poseidon.** Never SHA-256 inside the SNARK.
7. **No bootstrapping in v1.** Multiplicative depth budget = 1 (one ct×pt rescale for the 1/N step). Adding any extra ct×ct multiplication breaks the parameter set.
8. **Inference is purely local.** No inference traffic crosses the network. The model decrypted at end of round t serves the client's local unlabeled stream until round t+1.

---

## 9. Threat model (v1, HLD §9.2 — defended)

| ID | Attack | Defense |
|---|---|---|
| T1 | Aggregator inversion on raw weights | Weights only leave client encrypted under CKKS; RLWE hardness |
| T2 | Aggregator drops a client | All `Hᵢ` are public on chain; SNARK requires all of them as inputs |
| T3 | Aggregator substitutes wrong ciphertext | `Hash(cᵢ) = Hᵢ` enforced inside SNARK |
| T4 | Aggregator lies about result | `Hash(c_agg) = H_agg` on-chain; client re-checks before accepting |
| T5 | Network eavesdropper | TLS at transport + CKKS at app layer (defense in depth) |
| T6 | Coalition of T-1 clients tries to decrypt | Threshold (T,N) sharing — no info leaks below T shares |
| T7 | Server colludes with ≤T-1 clients | Same threshold guarantee |
| T8 | Chain operator censors txs | Public L2 (Polygon zkEVM); refund mechanism bounds harm |
| T9 | Replay of stale ciphertexts | Round index `t` baked into commitment domain |
| T10 | Quantum adversary recovers `sk` | CKKS is post-quantum (RLWE); Groth16/BN254 is **not** — flagged for v2 |

---

## 10. Out of scope for v1 (HLD §9.3, §13.1) — DO NOT implement

These are **deferred to future work** by explicit decision. If you find yourself wanting to add any of these, stop and ask first:

- ❌ Defense against **malicious clients submitting poisoned weights** (Krum, Trimmed-Mean, FLTrust, ZK range-proofs over weights)
- ❌ **Differential privacy** noise injection
- ❌ **Side-channel** defense on client device
- ❌ **Sybil resistance** (assumed handled by KYC at portal registration)
- ❌ **Multi-tenant** isolation across orgs (single federation per deployment)
- ❌ **Decentralized aggregator** (single coordinator)
- ❌ **Threshold-DKG** ceremony — v1 uses single-issuer key bootstrap
- ❌ **STARK / post-quantum SNARK** — Groth16 over BN254 for v1
- ❌ **GPU-accelerated CKKS** (HEonGPU)
- ❌ **Sparse-update FedAvg** (top-k weight changes)

---

## 11. Key references

Primary (read these before doing crypto work):
- **HLD** — `HLD_ZeroTrust_FedAgg_HealthIoT.pdf` (root) — full system spec
- **FHE textbook** — `docs/references/FHE.pdf` (Ko 2025, *Beginner's Textbook for Fully Homomorphic Encryption*, arXiv:2503.05136) — cyclotomic rings → RLWE → CKKS in full
- **CKKS** — Cheon, Kim, Kim, Song. *Homomorphic Encryption for Arithmetic of Approximate Numbers*. ASIACRYPT 2017
- **Groth16** — Groth, J. *On the Size of Pairing-Based Non-interactive Arguments*. EUROCRYPT 2016

Online primers (zk-SNARKs):
- Reitwießner, C. *zkSNARKs in a Nutshell* (2016) — http://chriseth.github.io/notes/articles/zksnarks/zksnarks.pdf
- Buterin, V. *zkSNARKs in a Nutshell* — https://blog.ethereum.org/2016/12/05/zksnarks-in-a-nutshell
- Thaler, J. *Proofs, Arguments, and Zero-Knowledge* — https://people.cs.georgetown.edu/jthaler/ProofsArgsAndZK.pdf

Number theory background:
- Belk. *Cyclotomic Polynomials* — https://e.math.cornell.edu/people/belk/numbertheory/CyclotomicPolynomials.pdf

FL / threshold-CKKS prior art:
- McMahan et al. *Communication-Efficient Learning of Deep Networks from Decentralized Data*. AISTATS 2017 — original FedAvg
- Khan et al. *EAH-FL*. 2025 — prior art for CKKS-based health-IoT FL
- Mouchet et al. *Multiparty Homomorphic Encryption from Ring-LWE*. PETS 2021 — threshold-CKKS DKG (v2)

---

## 12. Working agreements with Claude (project-specific)

> These extend the global rules in `~/.claude/rules/` for this project.

**A. HLD is the source of truth.** When the HLD and intuition disagree, follow the HLD. If the HLD seems wrong, surface it as a question — do not silently redesign.

**B. Crypto is non-negotiable.** Do not "simplify" CKKS parameters, swap Poseidon for SHA-256 inside the circuit, or change the modulus chain to "make tests pass". Crypto-correctness comes before convenience.

**C. Local-dev only.** No AWS/Vercel/cloud config. Anvil for chain, MinIO for object store, Mosquitto in Docker, Postgres in Docker. Production wiring is out of scope.

**C.1. Render demo exception (added 2026-05-04).** A parallel cloud target exists for demo purposes: a free-tier Render deployment of `ztfa-aggregator` and `ztfa-portal` plus a free Render Postgres. Substitutions vs. C: chain → Polygon zkEVM Cardona public RPC (chainId 2442); object store → ephemeral filesystem (no R2/MinIO); MQTT → omitted in cloud demo. The aggregator boots in `STUB_MODE` until contracts and the CKKS public context are bootstrapped out-of-band — `/health` and `/v1/round/{t}/status` are live; `start`/`finalize` return 503 until wired. **Local-dev remains primary.** All §8 invariants still hold: aggregator never holds `sk`, ciphertexts never go on-chain, Poseidon for commitments. Cloud blueprint lives in `render.yaml` at repo root.

**D. Languages locked:** Python (client + aggregator), Rust (rapidsnark wrapper), Solidity (contracts), TypeScript+Next.js (portal), circom (circuit DSL). Do not introduce additional languages.

**E. Test discipline.** Per global rules: 80% coverage, TDD for new features. **Crypto modules MUST have golden-vector tests** (encrypt → decrypt round-trip; sum of plaintexts == decrypt(sum of ciphertexts) within ε).

**F. Demo dataset locked:** `Multi-Sensor_Medical_IoT_Dataset.csv` (root) — 670 rows, 100 unique patients (P001–P100), 17 sensor features (heart_rate, spo2_level, ecg_signal, respiration_rate, body_temperature, blood_pressure_sys/dia, blood_glucose, eeg_alpha_power, eeg_beta_power, emg_signal_strength, step_count, latitude, longitude, ambient_temperature, stress_level_index, fall_detected) + timestamp + patient_id. **Primary v1 task = 4-class activity classification** (sleeping=185, walking=163, resting=163, running=159 — balanced). **Fall detection (28/670 = 4%) is too imbalanced for v1; deferred to v2.** Model: small MLP, 15 input features (drop `latitude`/`longitude` to avoid location leakage; drop `fall_detected` since it's a separate label) → 32 → 16 → 4. ~600 weights — fits in **1 CKKS ciphertext** (16 384 slots). N=3 clients for demo; **federation split is patient-disjoint** (shard by `patient_id` hash mod N → ~33 patients / ~220 rows per client when N=3; realistic non-IID FL setup). N is a runtime parameter — change it in `split_config.py` and `bootstrap.sh` without touching the protocol.

**G. Circuit changes require ceremony re-run.** If any constraint of `aggregation.circom` is modified, Phase-2 must be re-run and `Verifier.sol` re-exported. Document this in the PR.

**H. Never commit:** `.zkey` files >100MB, secret-key shares, signed wallet keys, `node_modules/`, `target/`, `__pycache__/`, MinIO data dirs, generated `Verifier.sol` (it's deterministic — regenerate from circuit).

**I. When in doubt about a cryptographic primitive, read `docs/references/FHE.pdf` first**, then ask. Do not guess RLWE / cyclotomic ring math from memory.

---

## 13. Future work (v2+ — tracked, NOT implemented in v1)

| Item | Source | Notes |
|---|---|---|
| **Fall detection** secondary task | dataset | 28/670 positives — too imbalanced for v1; needs SMOTE/focal-loss + larger dataset |
| Threshold-DKG (Mouchet et al.) | HLD §4.2, §13.1 | Replaces single-issuer key bootstrap |
| Multi-Key CKKS | HLD §13.1 | Each client uses own keypair; eliminates inter-client trust |
| Robust aggregation under FHE | HLD §13.1 | Krum/Trimmed-Mean as depth ≤3 FHE circuit |
| Client-side ZK range proofs | HLD §13.1 | Bulletproofs over `‖wᵢ − w_global‖∞ ≤ B` |
| Differential privacy | HLD §13.1 | Gaussian noise on `wᵢ` pre-encryption |
| STARK proof system | HLD §13.2 | Post-quantum, ~10× higher verify cost |
| GPU-accelerated CKKS | HLD §13.2 | Sub-100ms encryption for 100M-parameter models |
| Sparse-update FedAvg | HLD §13.2 | Only top-k weight changes encrypted; ~10× bandwidth reduction |
| Aggregator replication for HA | HLD §13.3 | Open question: how to coordinate proving across replicas |
| KYC / identity layer | HLD §13.3 | Open: HIPAA-covered entity? GDPR controller? |

---

## 14. Open questions still being resolved

- [ ] Round period: minutes (online learning) or hours (batch retraining)? — **default to on-demand for demo**
- [ ] Exact threshold T for (T,N) decryption — **v1 uses single-issuer so T=1 trivially; revisit at v2**
- [ ] Should we ship a Tauri-wrapped client binary in v1 or only a Python CLI? — **Python CLI for v1; Tauri deferred**
- [ ] Labeled vs unlabeled split — dataset is fully labeled. For demo: **80% of each client's rows → labeled (training), 20% → unlabeled (inference stream after stripping `activity_type`)**. Realistic enough for v1.

---

---

## 15. Execution mode (autonomous)

> **Active directive — issued 2026-05-03**: Complete all 82 tasks (loaded into the task system) **non-stop, autonomously, taking all decisions yourself**. Do not pause for confirmation between tasks. If something is missing from the task list, **add it via TaskCreate** and keep going.

**Decision framework when ambiguous:**
1. **HLD wins** over intuition. Follow the document literally.
2. **Invariants in §8 are inviolable** — if a "shortcut" breaks one, find another path.
3. **Local-dev only** — pick the simplest tool that works on a laptop with Docker.
4. **TDD for crypto modules** (golden vectors before implementation). For glue/IO code, tests-after is acceptable.
5. **When two reasonable choices exist, pick the one that matches the HLD's recommended tech stack (§11)** and move on. Document the call inline; do not deliberate.
6. **If a task is genuinely blocked** (missing dependency only the user can provide — e.g. a WalletConnect cloud projectId, an API key, sudo access), **stub it with a clear TODO marker** and continue. Surface blockers in a single end-of-run summary.

**Discipline rules during the run:**
- Mark each task `in_progress` when starting and `completed` when done — no batching.
- Verify before claiming success (run the test, read the diff, check the output).
- Commit logical chunks of work (per-phase or per-component) with conventional-commits messages. Do not push.
- Keep the running narrative terse — one sentence per task, not paragraphs.
- If a phase exceeds expected time, push through; do not abandon.

**Do NOT do during the autonomous run:**
- Do not ask for clarification on choices the user already locked (N=3, dataset, languages, frontend stack).
- Do not redesign past the HLD.
- Do not implement out-of-scope items (§10) under any circumstance.
- Do not push to remote, force-push, or modify global git config.
- Do not skip tests "to save time."

*End of CLAUDE.md. This file is the living contract for the project. Update it when the HLD, scope, or invariants change — and only then.*
