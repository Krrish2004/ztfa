/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // wagmi/viem use ESM-only deps; Next 15 handles this natively.
  experimental: {},
};
export default nextConfig;
