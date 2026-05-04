"use client";

import Link from "next/link";
import { ConnectButton } from "@/components/ConnectButton";
import WalletPanel from "@/components/WalletPanel";

export default function WalletPage() {
  return (
    <>
      <header>
        <h1>ZTFA · Wallet & Refunds</h1>
        <nav>
          <Link href="/">Dashboard</Link>
          <Link href="/rounds">Rounds</Link>
          <Link href="/wallet">Wallet</Link>
          <Link href="/settings">Settings</Link>
          <ConnectButton />
        </nav>
      </header>
      <main>
        <WalletPanel />
      </main>
    </>
  );
}
