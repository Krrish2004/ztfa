#!/usr/bin/env node
// Poseidon CLI bridging circomlibjs to Python.
//
// Reads JSON commands from stdin (one JSON object per line):
//   { "op": "poseidon2", "a": "<dec>", "b": "<dec>" }      → { "result": "<dec>" }
//   { "op": "chain", "elements": ["<dec>", ...] }            → { "result": "<dec>" }
//   { "op": "commitment", "round": "<dec>",
//     "clientId": "<dec>", "ctHex": "<hex>" }                → { "result": "<dec>" }
//
// Stays alive across requests for low-overhead reuse from Python.
//
// Single source of truth: this binds the on-circuit Poseidon (which uses
// circomlibjs/circomlib internally) to the off-chain commitment. Any change
// to commitment construction MUST update this file AND aggregation.circom AND
// any contract that emits commits.

import { buildPoseidon } from "circomlibjs";
import readline from "node:readline";

const FR = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;

function chunk31(hex) {
  // Strip 0x and pair-pad to even length; treat as raw bytes
  const clean = hex.replace(/^0x/i, "").padStart(hex.length % 2 ? hex.length + 1 : hex.length, "0");
  const buf = Buffer.from(clean, "hex");
  const out = [];
  for (let i = 0; i < buf.length; i += 31) {
    const slice = buf.subarray(i, i + 31);
    let n = 0n;
    for (const b of slice) n = (n << 8n) | BigInt(b);
    out.push(n);
  }
  return out;
}

async function main() {
  const poseidon = await buildPoseidon();
  const F = poseidon.F;
  const toDec = (x) => F.toObject(x).toString();

  function p2(a, b) {
    return toDec(poseidon([BigInt(a), BigInt(b)]));
  }
  function chain(elements) {
    let h = 0n;
    for (const e of elements) {
      h = BigInt(p2(h, BigInt(e) % FR));
    }
    return h.toString();
  }
  function commitment(round, clientId, ctHex) {
    const domain = p2(BigInt(round), BigInt(clientId));
    const payload = chain(chunk31(ctHex));
    return p2(BigInt(domain), BigInt(payload));
  }

  const rl = readline.createInterface({ input: process.stdin });
  process.stdout.write("READY\n");
  for await (const line of rl) {
    if (!line.trim()) continue;
    let req;
    try {
      req = JSON.parse(line);
    } catch (e) {
      process.stdout.write(JSON.stringify({ error: "bad_json", detail: String(e) }) + "\n");
      continue;
    }
    try {
      let result;
      if (req.op === "poseidon2") {
        result = p2(BigInt(req.a), BigInt(req.b));
      } else if (req.op === "chain") {
        result = chain(req.elements.map((x) => BigInt(x)));
      } else if (req.op === "commitment") {
        result = commitment(BigInt(req.round), BigInt(req.clientId), req.ctHex);
      } else {
        throw new Error(`unknown op: ${req.op}`);
      }
      process.stdout.write(JSON.stringify({ result }) + "\n");
    } catch (e) {
      process.stdout.write(JSON.stringify({ error: "exec", detail: String(e) }) + "\n");
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
