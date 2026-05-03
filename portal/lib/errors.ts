// User-friendly wallet/tx error message formatter.
// Per /web3-frontend skill recipe.
export function parseError(error: unknown): string {
  const msg = error instanceof Error ? error.message : String(error);
  if (msg.includes("user rejected") || msg.includes("User rejected")) return "Transaction cancelled";
  if (msg.includes("insufficient funds")) return "Insufficient balance";
  if (msg.includes("execution reverted")) {
    const m = msg.match(/reason="([^"]+)"/);
    if (m) return m[1];
    const sel = msg.match(/0x[0-9a-fA-F]{8}/);
    if (sel) return `Reverted (selector ${sel[0]})`;
    return "Transaction would fail";
  }
  return msg.length > 200 ? msg.slice(0, 200) + "…" : msg;
}
