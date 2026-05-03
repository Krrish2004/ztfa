/**
 * Bridge to the local client node's FastAPI server (run by the Python
 * ZTFA client at 127.0.0.1:7000+i). The browser NEVER talks crypto directly;
 * everything goes through the local client.
 */
import { LOCAL_CLIENT_RPC_URL } from "./wagmi";

export type AccuracyHistoryRow = {
  round_t: number;
  accuracy: number;
  n_samples: number;
  measured_at: string;
};

export type RoundStatusDoc = {
  client_id: number;
  last_completed_round: number;
  wallet_address: string;
};

export type PredictionDoc = {
  record_id: number;
  activity: string;
  confidence: number;
  at: string;
};

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${LOCAL_CLIENT_RPC_URL}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`local RPC ${path} → ${r.status}`);
  return (await r.json()) as T;
}

export const localRpc = {
  health: () => get<{ status: string; client_id: number }>("/health"),
  roundStatus: () => get<RoundStatusDoc>("/round-status"),
  accuracyHistory: () => get<AccuracyHistoryRow[]>("/accuracy-history"),
  recentPredictions: () => get<PredictionDoc[]>("/recent-predictions"),
};
