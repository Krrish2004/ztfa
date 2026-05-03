"use client";

import { ConnectButton } from "@rainbow-me/rainbowkit";
import dynamic from "next/dynamic";
import Link from "next/link";

const RoundHistory = dynamic(() => import("@/components/RoundHistory"), { ssr: false });

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
          <ConnectButton accountStatus="address" chainStatus="icon" />
        </nav>
      </header>
      <main>
        <RoundHistory />
      </main>
    </>
  );
}
