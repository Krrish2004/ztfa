"use client";

import { useState } from "react";
import {
  useAccount,
  useBalance,
  useWaitForTransactionReceipt,
  useWriteContract,
} from "wagmi";
import { federationRoundAbi } from "@/lib/abi";
import { parseError } from "@/lib/errors";
import { FEDERATION_ROUND_ADDRESS } from "@/lib/wagmi";

export default function WalletPanel() {
  const { address, isConnected } = useAccount();
  const { data: balance } = useBalance({ address });
  const [t, setT] = useState("1");
  const { writeContract, data: hash, isPending, error } = useWriteContract();
  const { isLoading, isSuccess } = useWaitForTransactionReceipt({ hash });

  const onClaim = () => {
    writeContract({
      address: FEDERATION_ROUND_ADDRESS,
      abi: federationRoundAbi,
      functionName: "claimRefund",
      args: [BigInt(t)],
    });
  };

  return (
    <>
      <div className="panel">
        <h2>Account</h2>
        <p style={{ marginBottom: 8 }}>
          <code>{isConnected ? address : "Not connected"}</code>
        </p>
        <p>
          Balance:{" "}
          <strong>
            {balance
              ? `${Number(balance.value) / 1e18} ${balance.symbol}`
              : "—"}
          </strong>
        </p>
      </div>

      <div className="panel">
        <h2>Claim Refund</h2>
        <p style={{ color: "var(--muted)", marginTop: 0 }}>
          If a round did not verify before its deadline, the per-client fee can
          be reclaimed.
        </p>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <input
            type="number"
            value={t}
            onChange={(e) => setT(e.target.value)}
            placeholder="round t"
            style={{
              padding: "10px 12px",
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "transparent",
              color: "var(--text)",
              width: 100,
            }}
          />
          <button onClick={onClaim} disabled={!isConnected || isPending || isLoading}>
            {isPending ? "Confirm in wallet…" : isLoading ? "Refunding…" : "Claim"}
          </button>
        </div>
        {error && <p style={{ color: "salmon" }}>{parseError(error)}</p>}
        {isSuccess && <p style={{ color: "#7bd88f" }}>Refund successful — tx: {hash}</p>}
      </div>
    </>
  );
}
