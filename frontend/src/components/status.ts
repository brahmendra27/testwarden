export const TOKEN_COLORS: Record<string, string> = {
  P: "#10b981", // passed
  A: "#f59e0b", // passed after retry (flaky)
  F: "#ef4444", // failed
  E: "#e11d48", // error
  K: "#52525b", // skipped
};

export const TOKEN_LABELS: Record<string, string> = {
  P: "passed",
  A: "flaky pass",
  F: "failed",
  E: "error",
  K: "skipped",
};

export const STATUS_STYLES: Record<string, string> = {
  passed: "bg-emerald-500/15 text-emerald-400",
  failed: "bg-red-500/15 text-red-400",
  error: "bg-rose-600/15 text-rose-400",
  skipped: "bg-zinc-500/15 text-zinc-400",
  xfailed: "bg-zinc-500/15 text-zinc-400",
  xpassed: "bg-purple-500/15 text-purple-400",
  flaky: "bg-amber-500/15 text-amber-400",
  running: "bg-sky-500/15 text-sky-400",
  completed: "bg-emerald-500/15 text-emerald-400",
  interrupted: "bg-zinc-500/15 text-zinc-400",
};

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
