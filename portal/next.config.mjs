/** @type {import('next').NextConfig} */
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const nextConfig = {
  reactStrictMode: true,

  // Silence the multi-lockfile warning by anchoring to the portal directory.
  outputFileTracingRoot: __dirname,

  // wagmi + RainbowKit pull a deep tree of wallet SDKs that need transpiling
  // through Next's bundler (otherwise their ESM-only/Node-only artifacts
  // bail out at compile time).
  transpilePackages: [
    "@rainbow-me/rainbowkit",
    "@walletconnect/sign-client",
    "@walletconnect/universal-provider",
    "@walletconnect/ethereum-provider",
    "@walletconnect/utils",
  ],

  webpack: (config, { isServer }) => {
    // Optional Node-only deps that browser builds of the wallet SDKs reach
    // for; we don't ship them, so resolve to false and silence the warnings.
    config.resolve.fallback = {
      ...(config.resolve.fallback ?? {}),
      fs: false,
      net: false,
      tls: false,
      "pino-pretty": false,
      lokijs: false,
      encoding: false,
      "@react-native-async-storage/async-storage": false,
    };
    // The MetaMask SDK ships a CommonJS-with-named-exports artifact that
    // Next's bundler can't statically analyse — mark it external on the
    // server build (it's only used in the browser anyway).
    if (isServer) {
      config.externals = [
        ...(config.externals ?? []),
        "@metamask/sdk",
        "pino-pretty",
        "lokijs",
        "encoding",
      ];
    }
    return config;
  },
};

export default nextConfig;
