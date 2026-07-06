import { STATUS_STYLES } from "./status";

export function StatusBadge({ status, flaky }: { status: string; flaky?: boolean }) {
  const label = flaky ? "flaky" : status;
  const style = STATUS_STYLES[label] ?? "bg-zinc-500/15 text-zinc-400";
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${style}`}>
      {label}
    </span>
  );
}
