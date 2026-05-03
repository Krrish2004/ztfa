"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { localRpc } from "@/lib/localhost-rpc";

export default function Dashboard() {
  const status = useQuery({
    queryKey: ["round-status"],
    queryFn: () => localRpc.roundStatus(),
    refetchInterval: 4000,
  });

  const accuracy = useQuery({
    queryKey: ["accuracy-history"],
    queryFn: () => localRpc.accuracyHistory(),
    refetchInterval: 4000,
  });

  const predictions = useQuery({
    queryKey: ["predictions"],
    queryFn: () => localRpc.recentPredictions(),
    refetchInterval: 4000,
  });

  const localOnline = !status.isError;

  return (
    <>
      <div className="row">
        <div className="panel">
          <h2>Local Client</h2>
          <div className="metric">
            {localOnline ? `#${status.data?.client_id ?? "?"}` : "offline"}
          </div>
          <code>{status.data?.wallet_address ?? "—"}</code>
        </div>
        <div className="panel">
          <h2>Last Completed Round</h2>
          <div className="metric">
            {status.data?.last_completed_round ?? "—"}
          </div>
        </div>
        <div className="panel">
          <h2>Latest Local Accuracy</h2>
          <div className="metric">
            {accuracy.data && accuracy.data.length > 0
              ? `${(accuracy.data[accuracy.data.length - 1].accuracy * 100).toFixed(1)}%`
              : "—"}
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>Federated Accuracy Over Time</h2>
        {accuracy.data && accuracy.data.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={accuracy.data}>
              <XAxis dataKey="round_t" stroke="#8a93a6" />
              <YAxis domain={[0, 1]} stroke="#8a93a6" />
              <Tooltip
                contentStyle={{ background: "#131a2e", border: "1px solid #1f2940" }}
              />
              <Line
                type="monotone"
                dataKey="accuracy"
                stroke="#6c8eff"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p style={{ color: "var(--muted)" }}>
            No completed rounds yet. Run <code>./scripts/run-round.sh 1</code>.
          </p>
        )}
      </div>

      <div className="panel">
        <h2>Recent Inferences (unlabeled stream)</h2>
        {predictions.data && predictions.data.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>record id</th>
                <th>predicted activity</th>
                <th>confidence</th>
                <th>at</th>
              </tr>
            </thead>
            <tbody>
              {predictions.data.slice(0, 10).map((p) => (
                <tr key={p.record_id}>
                  <td>{p.record_id}</td>
                  <td>{p.activity}</td>
                  <td>{(p.confidence * 100).toFixed(1)}%</td>
                  <td style={{ color: "var(--muted)" }}>{p.at.slice(11, 19)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ color: "var(--muted)" }}>No inferences yet.</p>
        )}
      </div>
    </>
  );
}
