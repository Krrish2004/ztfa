"use client";

import Link from "next/link";
import { ConnectButton } from "@/components/ConnectButton";
import RoundHistory from "@/components/RoundHistory";

export default function RoundsPage() {
  return (
    <>
      <header>
        <h1>ZTFA · Round History</h1>
        <nav>
          <Link href="/">Dashboard</Link>
          <Link href="/rounds">Rounds</Link>
          <Link href="/wallet">Wallet</Link>
          <Link href="/settings">Settings</Link>
          <ConnectButton />
        </nav>
      </header>
      <main>
        <RoundHistory />
      </main>
    </>
  );
}
