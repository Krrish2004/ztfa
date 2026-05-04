/**
 * Plain wagmi v2 configuration — no RainbowKit (it caused render failures
 * with React 19 + Next 15). We expose a simple injected connector and a
 * manual ConnectButton component below.
 */
import { http, createConfig } from "wagmi";
import { injected } from "wagmi/connectors";
import { defineChain } from "viem";

export const anvil = defineChain({
  id: 31337,
  name: "Anvil",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: {
    default: { http: ["http://127.0.0.1:8545"] },
  },
  testnet: true,
});

export const wagmiConfig = createConfig({
  chains: [anvil],
  connectors: [injected()],
  transports: {
    [anvil.id]: http("http://127.0.0.1:8545"),
  },
  ssr: true,
});

export const FEDERATION_ROUND_ADDRESS =
  (process.env.NEXT_PUBLIC_FEDERATION_ROUND_ADDRESS as `0x${string}`) ||
  "0x0000000000000000000000000000000000000000";

export const LOCAL_CLIENT_RPC_URL =
  process.env.NEXT_PUBLIC_LOCAL_CLIENT_RPC_URL || "http://localhost:7000";
