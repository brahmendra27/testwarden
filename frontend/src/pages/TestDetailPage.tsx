import { useParams } from "react-router-dom";
import { useTestDetail } from "../api/hooks";
import { HistorySquares } from "../components/HistorySquares";
import { Reproducer } from "../components/Reproducer";
import { StatusBadge } from "../components/StatusBadge";
import { TrendChart } from "../components/TrendChart";
import { formatDate, formatDuration } from "../components/status";

function historyToken(status: string, flakyInRun: boolean): string {
  if (status === "passed") return flakyInRun ? "A" : "P";
  if (status === "failed") return "F";
  if (status === "error") return "E";
  return "K";
}

export function TestDetailPage() {
  const { slug = "", caseId } = useParams();
  const { data: test, isLoading } = useTestDetail(Number(caseId));
  if (isLoading || !test) return <p className="text-zinc-500">Loading test…</p>;

  const failures = test.history.filter((entry) => entry.status === "failed" || entry.status === "error");
  const byFingerprint = new Map<string, typeof failures>();
  for (const failure of failures) {
    const fingerprint = failure.failure_fingerprint ?? `result-${failure.result_id}`;
    byFingerprint.set(fingerprint, [...(byFingerprint.get(fingerprint) ?? []), failure]);
  }

  return (
    <div>
      <div className="mb-1 flex items-center gap-3">
        <h1 className="break-all font-mono text-lg font-semibold text-white">{test.node_id}</h1>
        {test.last_status && <StatusBadge status={test.last_status} />}
        {test.is_flaky && <StatusBadge status="flaky" />}
      </div>
      <p className="mb-6 text-sm text-zinc-500">{test.file_path}</p>

      {test.is_flaky && <Reproducer caseId={test.id} />}

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="card px-4 py-3">
          <div className={`text-xl font-semibold ${test.is_flaky ? "text-amber-400" : "text-zinc-100"}`}>
            {(test.flake_score * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-zinc-500">flake score</div>
        </div>
        <div className="card px-4 py-3">
          <div className="text-xl font-semibold text-zinc-100">{test.flip_count}</div>
          <div className="text-xs text-zinc-500">pass/fail flips (last {test.recent_statuses.length})</div>
        </div>
        <div className="card px-4 py-3">
          <div className="text-xl font-semibold text-zinc-100">{formatDuration(test.avg_duration_ms)}</div>
          <div className="text-xs text-zinc-500">avg duration</div>
        </div>
        <div className="card px-4 py-3">
          <div className="text-xl font-semibold text-zinc-100">{formatDuration(test.p95_duration_ms)}</div>
          <div className="text-xs text-zinc-500">p95 duration</div>
        </div>
      </div>

      <h2 className="mb-2 text-sm font-medium uppercase text-zinc-500">History (oldest → newest)</h2>
      <div className="mb-6 card p-4">
        <HistorySquares
          entries={test.history.map((entry) => ({
            token: historyToken(entry.status, entry.is_flaky_in_run),
            label: `Run #${entry.run_id} · ${formatDate(entry.run_started_at)}`,
            href: `/p/${slug}/runs/${entry.run_id}`,
          }))}
        />
      </div>

      <h2 className="mb-2 text-sm font-medium uppercase text-zinc-500">Duration trend</h2>
      <div className="mb-6 card p-4">
        <TrendChart
          points={test.history.map((entry) => ({
            label: `#${entry.run_id}`,
            duration_ms: entry.duration_ms,
            status: entry.status,
          }))}
        />
      </div>

      {byFingerprint.size > 0 && (
        <>
          <h2 className="mb-2 text-sm font-medium uppercase text-zinc-500">
            Recent failures ({failures.length}, grouped by fingerprint)
          </h2>
          <div className="space-y-3">
            {[...byFingerprint.entries()].map(([fingerprint, group]) => {
              const latest = group[group.length - 1];
              return (
                <div key={fingerprint} className="card p-4">
                  <div className="mb-1 flex items-center gap-3 text-sm">
                    <span className="rounded bg-red-500/10 px-2 py-0.5 text-xs text-red-400">
                      ×{group.length} occurrence{group.length > 1 ? "s" : ""}
                    </span>
                    <span className="font-mono text-xs text-zinc-600">{fingerprint.slice(0, 12)}</span>
                    <span className="ml-auto text-xs text-zinc-500">
                      last: {formatDate(latest.run_started_at)}
                    </span>
                  </div>
                  <p className="text-sm text-red-300">
                    {latest.error_type && <strong>{latest.error_type}: </strong>}
                    {latest.error_message}
                  </p>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
