"use client";

import { useEffect, useState } from "react";
import { parseAbiItem } from "viem";
import { usePublicClient } from "wagmi";
import { FEDERATION_ROUND_ADDRESS } from "@/lib/wagmi";

const startedSig = parseAbiItem("event RoundStarted(uint256 indexed t, uint256 deadline)");
const verifiedSig = parseAbiItem("event RoundVerified(uint256 indexed t, bytes32 H_agg)");

type Row = {
  t: bigint;
  started: boolean;
  verified: boolean;
  hAgg?: string;
  deadline?: bigint;
};

export default function RoundHistory() {
  const publicClient = usePublicClient();
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!publicClient) return;
    if (
      FEDERATION_ROUND_ADDRESS ===
      "0x0000000000000000000000000000000000000000"
    ) {
      setError("FederationRound not deployed yet — run bootstrap.sh / e2e_live.py.");
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const fromBlock = 0n;
        const startedLogs = await publicClient!.getLogs({
          address: FEDERATION_ROUND_ADDRESS,
          event: startedSig,
          fromBlock,
        });
        const verifiedLogs = await publicClient!.getLogs({
          address: FEDERATION_ROUND_ADDRESS,
          event: verifiedSig,
          fromBlock,
        });
        if (cancelled) return;

        const map = new Map<string, Row>();
        for (const log of startedLogs) {
          const t = log.args.t!;
          map.set(t.toString(), {
            t,
            started: true,
            verified: false,
            deadline: log.args.deadline,
          });
        }
        for (const log of verifiedLogs) {
          const t = log.args.t!;
          const r = map.get(t.toString()) ?? { t, started: true, verified: false };
          r.verified = true;
          r.hAgg = log.args.H_agg as string;
          map.set(t.toString(), r);
        }
        setRows([...map.values()].sort((a, b) => Number(a.t - b.t)));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [publicClient]);

  return (
    <div className="panel">
      <h2>Federated Rounds</h2>
      {error && <p style={{ color: "salmon" }}>{error}</p>}
      {rows.length === 0 ? (
        <p style={{ color: "var(--muted)" }}>No rounds yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>t</th>
              <th>state</th>
              <th>H_agg</th>
              <th>deadline</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.t.toString()}>
                <td>{r.t.toString()}</td>
                <td>
                  {r.verified ? (
                    <span style={{ color: "#7bd88f" }}>verified</span>
                  ) : (
                    <span style={{ color: "var(--accent-warm)" }}>open</span>
                  )}
                </td>
                <td>
                  {r.hAgg ? <code>{r.hAgg.slice(0, 18)}…</code> : "—"}
                </td>
                <td style={{ color: "var(--muted)" }}>
                  {r.deadline
                    ? new Date(Number(r.deadline) * 1000).toLocaleTimeString()
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
