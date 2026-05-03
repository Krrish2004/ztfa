// ABI fragment for the FederationRound contract — only the read functions
// and events the portal actually consumes.
export const federationRoundAbi = [
  {
    type: "function",
    name: "isRoundVerified",
    stateMutability: "view",
    inputs: [{ name: "t", type: "uint256" }],
    outputs: [{ name: "", type: "bool" }],
  },
  {
    type: "function",
    name: "getRound",
    stateMutability: "view",
    inputs: [{ name: "t", type: "uint256" }],
    outputs: [
      { name: "state", type: "uint8" },
      { name: "deadline", type: "uint256" },
      { name: "clientCount", type: "uint256" },
      { name: "aggregateCommit", type: "bytes32" },
      { name: "escrowed", type: "uint256" },
    ],
  },
  {
    type: "function",
    name: "claimRefund",
    stateMutability: "nonpayable",
    inputs: [{ name: "t", type: "uint256" }],
    outputs: [],
  },
  {
    type: "event",
    name: "RoundStarted",
    inputs: [
      { indexed: true, name: "t", type: "uint256" },
      { indexed: false, name: "deadline", type: "uint256" },
    ],
  },
  {
    type: "event",
    name: "RoundVerified",
    inputs: [
      { indexed: true, name: "t", type: "uint256" },
      { indexed: false, name: "H_agg", type: "bytes32" },
    ],
  },
  {
    type: "event",
    name: "ClientCommitted",
    inputs: [
      { indexed: true, name: "t", type: "uint256" },
      { indexed: true, name: "client", type: "address" },
      { indexed: false, name: "H", type: "bytes32" },
    ],
  },
  {
    type: "event",
    name: "RoundRefunded",
    inputs: [
      { indexed: true, name: "t", type: "uint256" },
      { indexed: true, name: "client", type: "address" },
      { indexed: false, name: "amt", type: "uint256" },
    ],
  },
] as const;
