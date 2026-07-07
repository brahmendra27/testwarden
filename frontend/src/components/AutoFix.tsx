import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

interface AgentJob {
  id: number;
  status: "queued" | "running" | "completed" | "failed";
  model: string;
  log: string;
  diff: string | null;
  summary: string | null;
  branch: string | null;
  pr_url: string | null;
  error: string | null;
}

interface AutofixState {
  available: boolean;
  job: AgentJob | null;
}

function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 text-xs leading-5">
      {diff.split("\n").map((line, index) => {
        let cls = "text-zinc-400";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "text-emerald-400";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "text-red-400";
        else if (line.startsWith("@@")) cls = "text-sky-400";
        else if (line.startsWith("diff ") || line.startsWith("index ")) cls = "text-zinc-600";
        return (
          <div key={index} className={cls}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}

function LogView({ log, live }: { log: string; live: boolean }) {
  const ref = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (live && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [log, live]);
  return (
    <pre
      ref={ref}
      className="max-h-48 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 text-xs leading-5 text-zinc-400"
    >
      {log || "…"}
    </pre>
  );
}

export function AutoFix({ resultId }: { resultId: number }) {
  const queryClient = useQueryClient();
  const { data: state } = useQuery({
    queryKey: ["autofix", resultId],
    queryFn: async (): Promise<AutofixState> => {
      const response = await fetch(`/api/v1/results/${resultId}/autofix`);
      if (!response.ok) throw new Error(`${response.status}`);
      return response.json();
    },
    refetchInterval: (query) => {
      const status = query.state.data?.job?.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });

  const start = useMutation({
    mutationFn: async () => {
      const response = await fetch(`/api/v1/results/${resultId}/autofix`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `${response.status}`);
      return body as AgentJob;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["autofix", resultId] }),
  });

  const job = state?.job;
  const active = job?.status === "queued" || job?.status === "running";

  return (
    <div className="rounded-xl border border-violet-400/25 bg-violet-500/[0.06] p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-base">🔧</span>
        <h3 className="text-sm font-semibold text-violet-200">Auto-fix agent</h3>
        {job && (
          <span
            className={`ml-auto rounded px-2 py-0.5 text-xs font-medium ${
              job.status === "completed"
                ? "bg-emerald-500/15 text-emerald-400"
                : job.status === "failed"
                  ? "bg-red-500/15 text-red-400"
                  : "bg-sky-500/15 text-sky-400"
            }`}
          >
            {active && <span className="glow-dot mr-1.5 align-middle" />}
            {job.status}
          </span>
        )}
      </div>

      {!job && (
        <>
          <p className="mb-3 text-sm text-zinc-400">
            Launch an autonomous agent that clones the repo, finds the root cause, applies a
            minimal fix, re-runs the failing test to verify, and opens a pull request for review.
          </p>
          <button onClick={() => start.mutate()} className="btn-grad" disabled={!state}>
            🔧 Launch auto-fix agent
          </button>
          {!state?.available && state && (
            <p className="mt-2 text-xs text-zinc-500">
              Requires <code className="rounded bg-white/10 px-1">ANTHROPIC_API_KEY</code> on the
              backend (and <code className="rounded bg-white/10 px-1">GITHUB_TOKEN</code> to open
              PRs). The project also needs a <code className="rounded bg-white/10 px-1">repo_url</code>.
            </p>
          )}
        </>
      )}

      {job && (
        <div className="space-y-3">
          <LogView log={job.log} live={active} />
          {job.summary && (
            <div>
              <h4 className="mb-1 text-xs font-medium uppercase text-zinc-500">Agent summary</h4>
              <p className="whitespace-pre-wrap text-sm text-zinc-300">{job.summary}</p>
            </div>
          )}
          {job.error && <p className="text-sm text-red-400">{job.error}</p>}
          {job.diff && (
            <div>
              <h4 className="mb-1 text-xs font-medium uppercase text-zinc-500">
                Proposed change {job.branch && <span className="normal-case">· branch <code>{job.branch}</code></span>}
              </h4>
              <DiffView diff={job.diff} />
            </div>
          )}
          <div className="flex items-center gap-3">
            {job.pr_url && (
              <a href={job.pr_url} target="_blank" rel="noreferrer" className="btn-grad">
                View pull request →
              </a>
            )}
            {!active && (
              <button onClick={() => start.mutate()} className="text-xs text-sky-400 hover:underline">
                run again
              </button>
            )}
          </div>
        </div>
      )}
      {start.isError && <p className="mt-2 text-xs text-red-400">{String(start.error.message)}</p>}
    </div>
  );
}
