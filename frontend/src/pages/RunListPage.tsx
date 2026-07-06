import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useBranches, useRuns, useRunStrip } from "../api/hooks";
import type { RunSummary } from "../api/types";
import { RunStrip } from "../components/RunStrip";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate, formatDuration } from "../components/status";

function RunRow({ run, slug }: { run: RunSummary; slug: string }) {
  const { data: strip } = useRunStrip(run.id);
  return (
    <Link
      to={`/p/${slug}/runs/${run.id}`}
      className="block rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 transition hover:border-zinc-600"
    >
      <div className="mb-2 flex flex-wrap items-center gap-3 text-sm">
        <StatusBadge status={run.status === "completed" ? (run.failed + run.error_count > 0 ? "failed" : "passed") : run.status} />
        <span className="font-medium text-zinc-200">Run #{run.id}</span>
        {run.branch && <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">{run.branch}</span>}
        {run.commit_sha && <span className="font-mono text-xs text-zinc-500">{run.commit_sha.slice(0, 8)}</span>}
        <span className="ml-auto text-zinc-500">{formatDate(run.started_at)}</span>
      </div>
      <div className="mb-2">{strip && <RunStrip entries={strip} slug={slug} />}</div>
      <div className="flex gap-4 text-xs text-zinc-400">
        <span className="text-emerald-400">{run.passed} passed</span>
        {run.failed > 0 && <span className="text-red-400">{run.failed} failed</span>}
        {run.error_count > 0 && <span className="text-rose-400">{run.error_count} errors</span>}
        {run.flaky_count > 0 && <span className="text-amber-400">{run.flaky_count} flaky</span>}
        {run.skipped > 0 && <span>{run.skipped} skipped</span>}
        <span className="ml-auto">{formatDuration(run.duration_ms)}</span>
      </div>
    </Link>
  );
}

export function RunListPage() {
  const { slug = "" } = useParams();
  const [branch, setBranch] = useState<string>("");
  const { data: runs, isLoading, error } = useRuns(slug, branch || undefined);
  const { data: branches } = useBranches(slug);

  return (
    <div>
      <div className="mb-6 flex items-center gap-4">
        <h1 className="text-2xl font-semibold text-zinc-100">Runs</h1>
        <select
          value={branch}
          onChange={(event) => setBranch(event.target.value)}
          className="ml-auto rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-300"
        >
          <option value="">All branches</option>
          {branches?.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>
      {isLoading && <p className="text-zinc-500">Loading runs…</p>}
      {error && <p className="text-red-400">Failed to load runs: {String(error)}</p>}
      <div className="space-y-3">
        {runs?.map((run) => (
          <RunRow key={run.id} run={run} slug={slug} />
        ))}
      </div>
    </div>
  );
}
