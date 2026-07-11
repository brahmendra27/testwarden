import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

function useSlug() {
  const { slug = "" } = useParams();
  return slug;
}
import { useResultDetail, useRun, useRunResults, useRunStrip } from "../api/hooks";
import type { ResultRow } from "../api/types";
import { AiAnalysis } from "../components/AiAnalysis";
import { AutoFix } from "../components/AutoFix";
import { ArtifactViewer } from "../components/ArtifactViewer";
import { RunStrip } from "../components/RunStrip";
import { StackTrace } from "../components/StackTrace";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate, formatDuration } from "../components/status";

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="card px-4 py-3">
      <div className={`text-xl font-semibold ${tone ?? "text-zinc-100"}`}>{value}</div>
      <div className="text-xs text-zinc-500">{label}</div>
    </div>
  );
}

function ResultDetailPanel({ resultId, onClose }: { resultId: number; onClose: () => void }) {
  const slug = useSlug();
  const { data: detail } = useResultDetail(resultId);
  const [tab, setTab] = useState(0);
  if (!detail) return null;
  const attempt = detail.attempts[Math.min(tab, detail.attempts.length - 1)];
  return (
    <div className="fixed inset-y-0 right-0 z-20 w-full max-w-2xl overflow-y-auto border-l border-white/10 bg-black/90 p-6 shadow-2xl backdrop-blur-xl">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <StatusBadge status={detail.status} flaky={detail.is_flaky_in_run} />
            <span className="text-sm text-zinc-500">{formatDuration(detail.duration_ms)}</span>
          </div>
          <h2 className="break-all font-mono text-sm text-zinc-200">{detail.node_id}</h2>
        </div>
        <button onClick={onClose} className="rounded-md px-2 py-1 text-zinc-400 hover:bg-white/10">
          ✕
        </button>
      </div>
      <Link to={`/p/${slug}/tests/${detail.test_case_id}`} className="text-sm text-sky-400 hover:underline">
        View test history →
      </Link>
      <div className="mt-4 flex gap-1 border-b border-white/10">
        {detail.attempts.map((item, index) => (
          <button
            key={item.id}
            onClick={() => setTab(index)}
            className={`rounded-t-md px-3 py-1.5 text-sm ${
              index === tab ? "bg-white/10 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Attempt {index + 1}
            <span className={`ml-1.5 ${item.status === "passed" ? "text-emerald-400" : "text-red-400"}`}>●</span>
          </button>
        ))}
      </div>
      {attempt && (
        <div className="mt-4 space-y-5">
          {(detail.status === "failed" || detail.status === "error" || detail.is_flaky_in_run) && (
            <>
              <AiAnalysis resultId={detail.result_id} />
              <AutoFix resultId={detail.result_id} />
            </>
          )}
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
              <pre className="max-h-48 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 text-xs text-zinc-400">
                {attempt.stdout}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MergeVerdict({ runId }: { runId: number }) {
  const { data } = useQuery({
    queryKey: ["verdict", runId],
    queryFn: async () => {
      const r = await fetch(`/api/v1/runs/${runId}/verdict`);
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json() as Promise<{ conclusion: string; title: string }>;
    },
  });
  if (!data) return null;
  const style =
    data.conclusion === "success" ? "bg-emerald-500/15 text-emerald-400"
      : data.conclusion === "neutral" ? "bg-amber-500/15 text-amber-400"
      : "bg-red-500/15 text-red-400";
  const icon = data.conclusion === "success" ? "✓ merge-ready" : data.conclusion === "neutral" ? "⚠ flaky only" : "✕ blocked";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${style}`} title={data.title}>
      {icon}
    </span>
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
        <h1 className="grad-text text-3xl font-bold">Run #{run.id}</h1>
        <StatusBadge status={run.status} />
        <MergeVerdict runId={run.id} />
        {run.branch && <span className="rounded bg-white/10 px-2 py-0.5 text-xs text-zinc-400">{run.branch}</span>}
        <span className="text-sm text-zinc-500">{formatDate(run.started_at)}</span>
        {run.previous_run_id && (
          <Link to={`/p/${slug}/compare?base=${run.previous_run_id}&head=${run.id}`} className="btn-grad ml-auto">
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
            className={`rounded-full px-3 py-1 text-sm transition ${
              filter === item.value
                ? "border border-blue-400/40 bg-blue-500/15 text-blue-200 shadow-[0_0_14px_rgba(61,106,254,0.25)]"
                : "border border-white/10 text-zinc-400 hover:bg-white/5"
            }`}
          >
            {item.label}
          </button>
        ))}
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search tests…"
          className="field ml-auto w-64"
        />
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-left text-xs uppercase text-zinc-500">
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
                className="cursor-pointer border-t border-white/5 hover:bg-white/5"
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
