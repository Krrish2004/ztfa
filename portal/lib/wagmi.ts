/**
 * wagmi v2 + RainbowKit configuration.
 *
 * Local dev uses Anvil (chainId 31337). Production wiring for Polygon zkEVM
 * Cardona is left commented for v2.
 */
import { getDefaultConfig } from "@rainbow-me/rainbowkit";
import { defineChain } from "viem";

const anvil = defineChain({
  id: 31337,
  name: "Anvil",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: {
    default: { http: ["http://127.0.0.1:8545"] },
  },
  testnet: true,
});

export const wagmiConfig = getDefaultConfig({
  appName: "ZTFA Portal",
  projectId: process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID || "stub_for_local_dev",
  chains: [anvil],
  ssr: true,
});

export const FEDERATION_ROUND_ADDRESS =
  (process.env.NEXT_PUBLIC_FEDERATION_ROUND_ADDRESS as `0x${string}`) ||
  "0x0000000000000000000000000000000000000000";

export const LOCAL_CLIENT_RPC_URL =
  process.env.NEXT_PUBLIC_LOCAL_CLIENT_RPC_URL || "http://localhost:7000";
