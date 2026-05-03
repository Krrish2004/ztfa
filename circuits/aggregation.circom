pragma circom 2.1.6;

// ZTFA — federated-aggregation correctness circuit (v1 demo).
//
// PROVES (per HLD §6.1, with v1 simplification documented in CLAUDE.md §5):
//   ∀i ∈ [0, N):  Hash(c_i) = H_i      // commitment binding
//   c_sum   = Σᵢ c_i                    // additive aggregation
//   Hash(c_sum) = H_sum                 // result binding
//
// The (1/N) scalar mult is moved to plaintext (post-threshold-decryption) in
// v1 — equivalent semantics, simpler circuit.
//
// Each ciphertext is represented as a K=8-element compressed digest (CLAUDE.md
// §5 simplification). The client computes the digest over its real CKKS
// ciphertext using `ztfa_crypto.snark_digest`; the aggregator does the same
// over c_agg. Off-circuit additive linkage of the digest to the underlying
// ciphertext is the v1 trust assumption.
//
// PARAMETERS (compile-time):
//   N  — number of clients (e.g. 3)
//   K  — digest length in BN254 Fr elements (locked at 8)
//
// PUBLIC INPUTS:
//   H[N]      — Poseidon-chain commitments to each client's digest
//   H_sum     — Poseidon-chain commitment to the sum digest
//
// PRIVATE WITNESS:
//   c[N][K]   — each client's compressed digest
//   c_sum[K]  — aggregate's compressed digest

include "circomlib/circuits/poseidon.circom";

// Hash a length-K array via left-fold pairwise Poseidon.
// h_0 = 0; h_{j+1} = Poseidon(h_j, x[j])  =>  result = h_K
template PoseidonChainK(K) {
    signal input in[K];
    signal output out;

    component p[K];
    signal acc[K + 1];
    acc[0] <== 0;
    for (var j = 0; j < K; j++) {
        p[j] = Poseidon(2);
        p[j].inputs[0] <== acc[j];
        p[j].inputs[1] <== in[j];
        acc[j + 1] <== p[j].out;
    }
    out <== acc[K];
}

// Sum N length-K vectors element-wise.
template VecSum(N, K) {
    signal input in[N][K];
    signal output out[K];

    signal acc[N + 1][K];
    for (var k = 0; k < K; k++) {
        acc[0][k] <== 0;
    }
    for (var i = 0; i < N; i++) {
        for (var k = 0; k < K; k++) {
            acc[i + 1][k] <== acc[i][k] + in[i][k];
        }
    }
    for (var k = 0; k < K; k++) {
        out[k] <== acc[N][k];
    }
}

template Aggregation(N, K) {
    // Public
    signal input H[N];
    signal input H_sum;

    // Private
    signal input c[N][K];
    signal input c_sum[K];

    // 1) Commitment binding: Hash(c_i) = H_i
    component hashClient[N];
    for (var i = 0; i < N; i++) {
        hashClient[i] = PoseidonChainK(K);
        for (var k = 0; k < K; k++) {
            hashClient[i].in[k] <== c[i][k];
        }
        hashClient[i].out === H[i];
    }

    // 2) Additive aggregation: c_sum = Σ c_i
    component sumGate = VecSum(N, K);
    for (var i = 0; i < N; i++) {
        for (var k = 0; k < K; k++) {
            sumGate.in[i][k] <== c[i][k];
        }
    }
    for (var k = 0; k < K; k++) {
        sumGate.out[k] === c_sum[k];
    }

    // 3) Result binding: Hash(c_sum) = H_sum
    component hashSum = PoseidonChainK(K);
    for (var k = 0; k < K; k++) {
        hashSum.in[k] <== c_sum[k];
    }
    hashSum.out === H_sum;
}

// Top-level instantiation: N=3 clients, K=8-element digests (locked for demo).
component main {public [H, H_sum]} = Aggregation(3, 8);
