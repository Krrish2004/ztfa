/**
 * Plain wagmi v2 configuration — no RainbowKit (it caused render failures
 * with React 19 + Next 15). We expose a simple injected connector and a
 * manual ConnectButton component below.
 *
 * Chain is selected via NEXT_PUBLIC_CHAIN_ID:
 *   31337     → local Anvil                 (default for `pnpm dev`)
 *   11155111  → Sepolia L1 testnet          (cloud demo)
 *   2442      → Polygon zkEVM Cardona       (HLD prod target; faucet unreliable in 2026)
 */
import { http, createConfig } from "wagmi";
import { injected } from "wagmi/connectors";
import { defineChain } from "viem";
import { sepolia } from "viem/chains";

const CHAIN_ID = Number(process.env.NEXT_PUBLIC_CHAIN_ID || "31337");
const RPC_URL =
  process.env.NEXT_PUBLIC_RPC_URL ||
  (CHAIN_ID === 11155111
    ? "https://ethereum-sepolia-rpc.publicnode.com"
    : CHAIN_ID === 2442
      ? "https://rpc.cardona.zkevm-rpc.com"
      : "http://127.0.0.1:8545");

export const anvil = defineChain({
  id: 31337,
  name: "Anvil",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: { default: { http: ["http://127.0.0.1:8545"] } },
  testnet: true,
});

export const cardona = defineChain({
  id: 2442,
  name: "Polygon zkEVM Cardona",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: { default: { http: ["https://rpc.cardona.zkevm-rpc.com"] } },
  blockExplorers: {
    default: {
      name: "PolygonScan zkEVM Cardona",
      url: "https://cardona-zkevm.polygonscan.com",
    },
  },
  testnet: true,
});

export { sepolia };

export const activeChain =
  CHAIN_ID === 11155111 ? sepolia : CHAIN_ID === 2442 ? cardona : anvil;

// Literal chain IDs so TS keeps the union key type intact.
export const wagmiConfig = createConfig({
  chains: [anvil, cardona, sepolia] as const,
  connectors: [injected()],
  transports: {
    31337: http(CHAIN_ID === 31337 ? RPC_URL : "http://127.0.0.1:8545"),
    2442: http(CHAIN_ID === 2442 ? RPC_URL : "https://rpc.cardona.zkevm-rpc.com"),
    11155111: http(
      CHAIN_ID === 11155111 ? RPC_URL : "https://ethereum-sepolia-rpc.publicnode.com",
    ),
  },
  ssr: true,
});

export const FEDERATION_ROUND_ADDRESS =
  (process.env.NEXT_PUBLIC_FEDERATION_ROUND_ADDRESS as `0x${string}`) ||
  "0x0000000000000000000000000000000000000000";

export const LOCAL_CLIENT_RPC_URL =
  process.env.NEXT_PUBLIC_LOCAL_CLIENT_RPC_URL || "http://localhost:7000";

export const AGGREGATOR_API_URL =
  process.env.NEXT_PUBLIC_AGGREGATOR_API_URL || "http://localhost:8000";
