import { Link, useParams } from "react-router-dom";
import { useFlaky } from "../api/hooks";
import { HistorySquares } from "../components/HistorySquares";
import { InfoTip } from "../components/InfoTip";
import { formatDuration } from "../components/status";

export function FlakyTestsPage() {
  const { slug = "" } = useParams();
  const { data: flaky, isLoading } = useFlaky(slug);
  if (isLoading) return <p className="text-zinc-500">Loading flaky tests…</p>;
  return (
    <div>
      <h1 className="grad-text mb-2 text-3xl font-bold">Flaky tests</h1>
      <p className="mb-6 text-sm text-zinc-500">
        Tests that flip between pass and fail across runs, or that regularly need retries to pass.
        Sorted by <InfoTip term="flake score" />.
      </p>
      {!flaky?.length && (
        <div className="card p-8 text-center text-zinc-500">
          No flaky tests detected. 🎉
        </div>
      )}
      <div className="space-y-3">
        {flaky?.map((testCase) => (
          <Link
            key={testCase.id}
            to={`/p/${slug}/tests/${testCase.id}`}
            className="card card-hover block p-4"
          >
            <div className="mb-2 flex flex-wrap items-center gap-3">
              <span className="rounded bg-amber-500/15 px-2 py-0.5 text-sm font-semibold text-amber-400">
                {(testCase.flake_score * 100).toFixed(0)}%
              </span>
              <span className="break-all font-mono text-sm text-zinc-200">{testCase.node_id}</span>
              <span className="ml-auto text-xs text-zinc-500">
                {testCase.flip_count} flips · avg {formatDuration(testCase.avg_duration_ms)}
              </span>
            </div>
            <HistorySquares
              size={11}
              entries={testCase.recent_statuses.map((entry) => ({
                token: entry.t,
                label: `run #${entry.r}`,
              }))}
            />
          </Link>
        ))}
      </div>
    </div>
  );
}
