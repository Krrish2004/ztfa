pragma circom 2.1.6;

// ZTFA — federated-aggregation correctness circuit (v1, full polynomial arithmetic).
//
// PROVES (HLD §6.1):
//   ∀i ∈ [0, N):  Hash(c_i) = H_i           // commitment binding
//                 c_sum[k] = Σ_i c_i[k]      // additive aggregation
//                                            // (over BN254 Fr, NO mod q;
//                                            //  decrypt-side reduces)
//                 Hash(c_sum) = H_sum        // result binding
//
// Each ciphertext c_i is a pair of polynomials (a, b) ∈ R_q × R_q with
// R_q = Z_q[X]/(X^N_RING + 1), N_RING = 256, q ≈ 2^60. Flattened into a
// length-M = 2·N_RING = 512 vector of Fr elements (each coefficient is
// < q < 2^60, well below BN254 Fr's ~2^254).
//
// The aggregator's `mini_he.add` does NOT reduce mod q, so the on-chain
// commit's preimage IS the unreduced sum and the BN254 constraint
// `c_sum[k] = Σ c_i[k]` holds without any in-circuit modular reduction.
//
// PARAMETERS (compile-time):
//   N — number of clients (3 for v1 demo)
//   M — coefficients per ciphertext (= 2·N_RING = 512)
//
// PUBLIC INPUTS:  H[N], H_sum
// PRIVATE WITNESS: c[N][M], c_sum[M]

include "circomlib/circuits/poseidon.circom";

// Length-M Poseidon-chain hash: h_0 = 0; h_{j+1} = Poseidon(h_j, in[j]).
template PoseidonChain(M) {
    signal input in[M];
    signal output out;

    component p[M];
    signal acc[M + 1];
    acc[0] <== 0;
    for (var j = 0; j < M; j++) {
        p[j] = Poseidon(2);
        p[j].inputs[0] <== acc[j];
        p[j].inputs[1] <== in[j];
        acc[j + 1] <== p[j].out;
    }
    out <== acc[M];
}

// Sum N length-M vectors element-wise (in Fr; no modular reduction).
template VecSum(N, M) {
    signal input in[N][M];
    signal output out[M];

    signal acc[N + 1][M];
    for (var k = 0; k < M; k++) {
        acc[0][k] <== 0;
    }
    for (var i = 0; i < N; i++) {
        for (var k = 0; k < M; k++) {
            acc[i + 1][k] <== acc[i][k] + in[i][k];
        }
    }
    for (var k = 0; k < M; k++) {
        out[k] <== acc[N][k];
    }
}

template Aggregation(N, M) {
    signal input H[N];
    signal input H_sum;

    signal input c[N][M];
    signal input c_sum[M];

    // 1) Commitment binding: PoseidonChain(c_i) = H_i
    component hashC[N];
    for (var i = 0; i < N; i++) {
        hashC[i] = PoseidonChain(M);
        for (var k = 0; k < M; k++) {
            hashC[i].in[k] <== c[i][k];
        }
        hashC[i].out === H[i];
    }

    // 2) Additive aggregation: c_sum = Σ c_i (in Fr; no mod q).
    component sumGate = VecSum(N, M);
    for (var i = 0; i < N; i++) {
        for (var k = 0; k < M; k++) {
            sumGate.in[i][k] <== c[i][k];
        }
    }
    for (var k = 0; k < M; k++) {
        sumGate.out[k] === c_sum[k];
    }

    // 3) Result binding: PoseidonChain(c_sum) = H_sum
    component hashS = PoseidonChain(M);
    for (var k = 0; k < M; k++) {
        hashS.in[k] <== c_sum[k];
    }
    hashS.out === H_sum;
}

// Top-level: N=3 clients, M=256 coefs per ciphertext (128 ring degree × 2 polys)
component main {public [H, H_sum]} = Aggregation(3, 256);
