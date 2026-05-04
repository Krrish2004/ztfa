"use client";

import Link from "next/link";
import { ConnectButton } from "@/components/ConnectButton";
import Dashboard from "@/components/Dashboard";

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
          <ConnectButton />
        </nav>
      </header>
      <main>
        <Dashboard />
      </main>
    </>
  );
}
