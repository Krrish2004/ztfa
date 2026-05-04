"use client";

import { useAccount, useConnect, useDisconnect } from "wagmi";

export function ConnectButton() {
  const { address, isConnected } = useAccount();
  const { connect, connectors, isPending } = useConnect();
  const { disconnect } = useDisconnect();

  if (!isConnected) {
    const c = connectors[0];
    return (
      <button onClick={() => connect({ connector: c })} disabled={isPending}>
        {isPending ? "Connecting…" : "Connect Wallet"}
      </button>
    );
  }

  const short = address ? `${address.slice(0, 6)}…${address.slice(-4)}` : "";
  return (
    <button onClick={() => disconnect()} title={address}>
      {short}  ⏏︎
    </button>
  );
}
