// Circuit unit tests for aggregation.circom — verifies the constraint set
// against witness vectors built in JS using circomlibjs Poseidon.
import { wasm as wasm_tester } from "circom_tester";
import { buildPoseidon } from "circomlibjs";
import { strict as assert } from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

let circuit;
let poseidon;
let F;

function chainHashK(K, vec) {
  let h = 0n;
  for (let j = 0; j < K; j++) {
    h = F.toObject(poseidon([h, vec[j]]));
  }
  return h;
}

function vecSum(vecs) {
  const K = vecs[0].length;
  const out = Array(K).fill(0n);
  for (const v of vecs) for (let k = 0; k < K; k++) out[k] += v[k];
  return out;
}

before(async function () {
  this.timeout(60_000);
  circuit = await wasm_tester(path.join(__dirname, "..", "aggregation.circom"), {
    include: [path.join(__dirname, "..", "node_modules")],
  });
  poseidon = await buildPoseidon();
  F = poseidon.F;
});

describe("aggregation circuit", function () {
  this.timeout(60_000);

  it("accepts a valid witness", async () => {
    const c = [
      [1n, 2n, 3n, 4n, 5n, 6n, 7n, 8n],
      [10n, 11n, 12n, 13n, 14n, 15n, 16n, 17n],
      [100n, 200n, 300n, 400n, 500n, 600n, 700n, 800n],
    ];
    const c_sum = vecSum(c);
    const H = c.map((row) => chainHashK(8, row));
    const H_sum = chainHashK(8, c_sum);
    const w = await circuit.calculateWitness({ H, H_sum, c, c_sum }, true);
    await circuit.checkConstraints(w);
  });

  it("rejects when c_sum is wrong", async () => {
    const c = [
      [1n, 2n, 3n, 4n, 5n, 6n, 7n, 8n],
      [10n, 11n, 12n, 13n, 14n, 15n, 16n, 17n],
      [100n, 200n, 300n, 400n, 500n, 600n, 700n, 800n],
    ];
    const correct_sum = vecSum(c);
    const wrong_sum = correct_sum.slice();
    wrong_sum[0] += 1n;
    const H = c.map((row) => chainHashK(8, row));
    const H_sum = chainHashK(8, wrong_sum);
    let threw = false;
    try {
      await circuit.calculateWitness({ H, H_sum, c, c_sum: wrong_sum }, true);
    } catch (e) {
      threw = true;
    }
    assert.ok(threw, "expected witness calculation to fail with wrong c_sum");
  });

  it("rejects when an H_i does not match c_i", async () => {
    const c = [
      [1n, 2n, 3n, 4n, 5n, 6n, 7n, 8n],
      [10n, 11n, 12n, 13n, 14n, 15n, 16n, 17n],
      [100n, 200n, 300n, 400n, 500n, 600n, 700n, 800n],
    ];
    const c_sum = vecSum(c);
    const H = c.map((row) => chainHashK(8, row));
    H[1] += 1n; // tamper
    const H_sum = chainHashK(8, c_sum);
    let threw = false;
    try {
      await circuit.calculateWitness({ H, H_sum, c, c_sum }, true);
    } catch (e) {
      threw = true;
    }
    assert.ok(threw, "expected witness to fail when H[1] doesn't match c[1]");
  });

  it("rejects when H_sum doesn't match c_sum", async () => {
    const c = [
      [1n, 2n, 3n, 4n, 5n, 6n, 7n, 8n],
      [10n, 11n, 12n, 13n, 14n, 15n, 16n, 17n],
      [100n, 200n, 300n, 400n, 500n, 600n, 700n, 800n],
    ];
    const c_sum = vecSum(c);
    const H = c.map((row) => chainHashK(8, row));
    const H_sum = chainHashK(8, c_sum) + 7n;
    let threw = false;
    try {
      await circuit.calculateWitness({ H, H_sum, c, c_sum }, true);
    } catch (e) {
      threw = true;
    }
    assert.ok(threw, "expected witness to fail with bad H_sum");
  });

  it("constraint count is ~8000 (sanity)", async () => {
    const stats = await circuit.getDecoratedOutput
      ? null
      : null;
    // circuit.constraints is exposed by circom_tester
    const n = circuit.constraints?.length ?? 0;
    assert.ok(n > 7000 && n < 9000, `constraint count = ${n}, expected ~8000`);
  });
});
