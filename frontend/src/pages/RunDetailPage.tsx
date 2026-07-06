import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useResultDetail, useRun, useRunResults, useRunStrip } from "../api/hooks";
import type { ResultRow } from "../api/types";
import { ArtifactViewer } from "../components/ArtifactViewer";
import { RunStrip } from "../components/RunStrip";
import { StackTrace } from "../components/StackTrace";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate, formatDuration } from "../components/status";

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-3">
      <div className={`text-xl font-semibold ${tone ?? "text-zinc-100"}`}>{value}</div>
      <div className="text-xs text-zinc-500">{label}</div>
    </div>
  );
}

function ResultDetailPanel({ resultId, onClose }: { resultId: number; onClose: () => void }) {
  const { data: detail } = useResultDetail(resultId);
  const [tab, setTab] = useState(0);
  if (!detail) return null;
  const attempt = detail.attempts[Math.min(tab, detail.attempts.length - 1)];
  return (
    <div className="fixed inset-y-0 right-0 z-20 w-full max-w-2xl overflow-y-auto border-l border-zinc-700 bg-zinc-950 p-6 shadow-2xl">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <StatusBadge status={detail.status} flaky={detail.is_flaky_in_run} />
            <span className="text-sm text-zinc-500">{formatDuration(detail.duration_ms)}</span>
          </div>
          <h2 className="break-all font-mono text-sm text-zinc-200">{detail.node_id}</h2>
        </div>
        <button onClick={onClose} className="rounded-md px-2 py-1 text-zinc-400 hover:bg-zinc-800">
          ✕
        </button>
      </div>
      <Link to={`../tests/${detail.test_case_id}`} relative="path" className="text-sm text-sky-400 hover:underline">
        View test history →
      </Link>
      <div className="mt-4 flex gap-1 border-b border-zinc-800">
        {detail.attempts.map((item, index) => (
          <button
            key={item.id}
            onClick={() => setTab(index)}
            className={`rounded-t-md px-3 py-1.5 text-sm ${
              index === tab ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Attempt {index + 1}
            <span className={`ml-1.5 ${item.status === "passed" ? "text-emerald-400" : "text-red-400"}`}>●</span>
          </button>
        ))}
      </div>
      {attempt && (
        <div className="mt-4 space-y-5">
          {attempt.error_message && (
            <div>
              <h3 className="mb-1 text-xs font-medium uppercase text-zinc-500">Error</h3>
              <p className="rounded-md bg-red-500/10 p-3 text-sm text-red-300">
                {attempt.error_type && <strong>{attempt.error_type}: </strong>}
                {attempt.error_message}
              </p>
            </div>
          )}
          {attempt.stack_trace && (
            <div>
              <h3 className="mb-1 text-xs font-medium uppercase text-zinc-500">Stack trace</h3>
              <StackTrace trace={attempt.stack_trace} />
            </div>
          )}
          <div>
            <h3 className="mb-1 text-xs font-medium uppercase text-zinc-500">Artifacts</h3>
            <ArtifactViewer artifacts={attempt.artifacts} />
          </div>
          {attempt.stdout && (
            <div>
              <h3 className="mb-1 text-xs font-medium uppercase text-zinc-500">Stdout</h3>
              <pre className="max-h-48 overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-400">
                {attempt.stdout}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const FILTERS = [
  { value: "", label: "All" },
  { value: "failed", label: "Failed" },
  { value: "flaky", label: "Flaky" },
  { value: "passed", label: "Passed" },
  { value: "skipped", label: "Skipped" },
];

export function RunDetailPage() {
  const { slug = "", runId } = useParams();
  const id = Number(runId);
  const { data: run } = useRun(id);
  const { data: strip } = useRunStrip(id);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
  const { data: results } = useRunResults(id, filter || undefined, search || undefined);
  const [selected, setSelected] = useState<number | null>(null);

  if (!run) return <p className="text-zinc-500">Loading run…</p>;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-zinc-100">Run #{run.id}</h1>
        <StatusBadge status={run.status} />
        {run.branch && <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">{run.branch}</span>}
        <span className="text-sm text-zinc-500">{formatDate(run.started_at)}</span>
        {run.previous_run_id && (
          <Link
            to={`/p/${slug}/compare?base=${run.previous_run_id}&head=${run.id}`}
            className="ml-auto rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-sky-400 hover:bg-zinc-900"
          >
            Compare with previous
          </Link>
        )}
      </div>
      <div className="mb-4 grid grid-cols-3 gap-3 md:grid-cols-6">
        <Stat label="total" value={run.total} />
        <Stat label="passed" value={run.passed} tone="text-emerald-400" />
        <Stat label="failed" value={run.failed} tone={run.failed ? "text-red-400" : undefined} />
        <Stat label="errors" value={run.error_count} tone={run.error_count ? "text-rose-400" : undefined} />
        <Stat label="flaky" value={run.flaky_count} tone={run.flaky_count ? "text-amber-400" : undefined} />
        <Stat label="duration" value={formatDuration(run.duration_ms)} />
      </div>
      {strip && (
        <div className="mb-6">
          <RunStrip entries={strip} slug={slug} height={18} />
        </div>
      )}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {FILTERS.map((item) => (
          <button
            key={item.value}
            onClick={() => setFilter(item.value)}
            className={`rounded-full px-3 py-1 text-sm ${
              filter === item.value
                ? "bg-zinc-200 text-zinc-900"
                : "border border-zinc-700 text-zinc-400 hover:bg-zinc-900"
            }`}
          >
            {item.label}
          </button>
        ))}
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search tests…"
          className="ml-auto w-64 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-300 placeholder:text-zinc-600"
        />
      </div>
      <div className="overflow-hidden rounded-lg border border-zinc-800">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 text-left text-xs uppercase text-zinc-500">
            <tr>
              <th className="px-4 py-2">Test</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Attempts</th>
              <th className="px-4 py-2 text-right">Duration</th>
            </tr>
          </thead>
          <tbody>
            {results?.map((row: ResultRow) => (
              <tr
                key={row.result_id}
                onClick={() => setSelected(row.result_id)}
                className="cursor-pointer border-t border-zinc-800/60 hover:bg-zinc-900/60"
              >
                <td className="px-4 py-2">
                  <div className="font-mono text-xs text-zinc-300">{row.node_id}</div>
                  {row.error_message && (
                    <div className="mt-0.5 line-clamp-1 text-xs text-red-400/80">{row.error_message}</div>
                  )}
                </td>
                <td className="px-4 py-2">
                  <StatusBadge status={row.status} flaky={row.is_flaky_in_run} />
                </td>
                <td className="px-4 py-2 text-zinc-400">{row.attempt_count}</td>
                <td className="px-4 py-2 text-right text-zinc-400">{formatDuration(row.duration_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected != null && <ResultDetailPanel resultId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
