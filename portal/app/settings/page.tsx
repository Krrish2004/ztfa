"use client";

import { ConnectButton } from "@rainbow-me/rainbowkit";
import Link from "next/link";

export default function Settings() {
  return (
    <>
      <header>
        <h1>ZTFA · Settings</h1>
        <nav>
          <Link href="/">Dashboard</Link>
          <Link href="/rounds">Rounds</Link>
          <Link href="/wallet">Wallet</Link>
          <Link href="/settings">Settings</Link>
          <ConnectButton accountStatus="address" chainStatus="icon" />
        </nav>
      </header>
      <main>
        <div className="panel">
          <h2>CKKS Key Import</h2>
          <p style={{ color: "var(--muted)" }}>
            v1: keys are distributed offline by the federation initiator
            (single-issuer model — see HLD §4.2). v2 will support multi-party
            DKG ceremony import here.
          </p>
        </div>
        <div className="panel">
          <h2>Threshold T</h2>
          <p style={{ color: "var(--muted)" }}>
            v1: T is implicit (single-issuer keygen sets T=1). v2 will expose a
            slider for ceremony participants.
          </p>
        </div>
      </main>
    </>
  );
}
