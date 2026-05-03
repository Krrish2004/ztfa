"use client";

import { ConnectButton } from "@rainbow-me/rainbowkit";
import dynamic from "next/dynamic";
import Link from "next/link";

const Dashboard = dynamic(() => import("@/components/Dashboard"), { ssr: false });

export default function Home() {
  return (
    <>
      <header>
        <h1>ZTFA · Zero-Trust Federated Aggregation</h1>
        <nav>
          <Link href="/">Dashboard</Link>
          <Link href="/rounds">Rounds</Link>
          <Link href="/wallet">Wallet</Link>
          <Link href="/settings">Settings</Link>
          <ConnectButton accountStatus="address" chainStatus="icon" />
        </nav>
      </header>
      <main>
        <Dashboard />
      </main>
    </>
  );
}
