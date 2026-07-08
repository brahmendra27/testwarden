import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { HistorySquares } from "../components/HistorySquares";

interface QJob {
  id: number;
  kind: string;
  status: string;
  branch: string | null;
  pr_url: string | null;
  error: string | null;
  summary: string | null;
}

interface QCase {
  id: number;
  node_id: string;
  flake_score: number;
  is_flaky: boolean;
  recent_statuses: { t: string; r: number }[];
  quarantined_at: string | null;
  quarantine_branch: string | null;
  quarantine_pr_url: string | null;
  release_ready: boolean;
  latest_job: QJob | null;
}

interface Board {
  available: boolean;
  suggestions: QCase[];
  quarantined: QCase[];
}

function JobChip({ job }: { job: QJob | null }) {
  if (!job) return null;
  const active = job.status === "queued" || job.status === "running";
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${
        job.status === "completed"
          ? "bg-emerald-500/15 text-emerald-400"
          : job.status === "failed"
            ? "bg-red-500/15 text-red-400"
            : "bg-sky-500/15 text-sky-400"
      }`}
      title={job.error ?? job.summary ?? undefined}
    >
      {active && <span className="glow-dot mr-1.5 align-middle" />}
      {job.kind} · {job.status}
    </span>
  );
}

function CaseRow({
  item,
  slug,
  actions,
}: {
  item: QCase;
  slug: string;
  actions: React.ReactNode;
}) {
  return (
    <div className="card p-4">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <span className="rounded bg-amber-500/15 px-2 py-0.5 text-sm font-semibold text-amber-400">
          {(item.flake_score * 100).toFixed(0)}%
        </span>
        <Link to={`/p/${slug}/tests/${item.id}`} className="break-all font-mono text-sm text-zinc-200 hover:text-sky-400">
          {item.node_id}
        </Link>
        {item.release_ready && (
          <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-400">
            ✓ ready to release
          </span>
        )}
        <JobChip job={item.latest_job} />
        {(item.quarantine_pr_url || item.latest_job?.pr_url) && (
          <a
            href={item.quarantine_pr_url ?? item.latest_job?.pr_url ?? "#"}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-sky-400 hover:underline"
          >
            PR ↗
          </a>
        )}
        <div className="ml-auto flex gap-2">{actions}</div>
      </div>
      <HistorySquares
        size={11}
        entries={item.recent_statuses.map((entry) => ({ token: entry.t, label: `run #${entry.r}` }))}
      />
    </div>
  );
}

export function QuarantinePage() {
  const { slug = "" } = useParams();
  const queryClient = useQueryClient();

  const { data: board } = useQuery({
    queryKey: ["quarantine", slug],
    queryFn: async (): Promise<Board> => {
      const response = await fetch(`/api/v1/projects/${slug}/quarantine`);
      if (!response.ok) throw new Error(`${response.status}`);
      return response.json();
    },
    refetchInterval: (query) => {
      const data = query.state.data;
      const active = [...(data?.suggestions ?? []), ...(data?.quarantined ?? [])].some(
        (c) => c.latest_job && (c.latest_job.status === "queued" || c.latest_job.status === "running")
      );
      return active ? 2500 : false;
    },
  });

  const act = useMutation({
    mutationFn: async ({ caseId, action }: { caseId: number; action: string }) => {
      const response = await fetch(`/api/v1/tests/${caseId}/${action}`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `${response.status}`);
      return body;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["quarantine", slug] }),
  });

  const button = (caseId: number, action: string, label: string, primary = false) => (
    <button
      onClick={() => act.mutate({ caseId, action })}
      disabled={act.isPending}
      className={primary ? "btn-grad text-xs" : "rounded-lg border border-white/10 px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/5"}
    >
      {label}
    </button>
  );

  return (
    <div className="max-w-5xl">
      <h1 className="grad-text mb-2 text-3xl font-bold">Quarantine</h1>
      <p className="mb-6 text-sm text-zinc-500">
        The closed loop: quarantine a flaky test (it keeps running, but stops failing CI), let
        SelfHeal fix it in the background, then release it once it's proven healthy.
      </p>
      {board && !board.available && (
        <p className="mb-4 text-xs text-zinc-500">
          Agent actions require <code className="rounded bg-white/10 px-1">ANTHROPIC_API_KEY</code> on the backend.
        </p>
      )}
      {act.isError && <p className="mb-4 text-xs text-red-400">{String(act.error.message)}</p>}

      <h2 className="mb-2 text-sm font-medium uppercase text-zinc-500">
        Suggested for quarantine ({board?.suggestions.length ?? 0})
      </h2>
      <div className="mb-8 space-y-3">
        {board?.suggestions.length === 0 && (
          <div className="card p-6 text-center text-sm text-zinc-500">
            No flaky tests awaiting quarantine. 🎉
          </div>
        )}
        {board?.suggestions.map((item) => (
          <CaseRow
            key={item.id}
            item={item}
            slug={slug}
            actions={<>{button(item.id, "quarantine", "🛡 Quarantine", true)}</>}
          />
        ))}
      </div>

      <h2 className="mb-2 text-sm font-medium uppercase text-zinc-500">
        In quarantine ({board?.quarantined.length ?? 0})
      </h2>
      <div className="space-y-3">
        {board?.quarantined.length === 0 && (
          <div className="card p-6 text-center text-sm text-zinc-500">Nothing in quarantine.</div>
        )}
        {board?.quarantined.map((item) => (
          <CaseRow
            key={item.id}
            item={item}
            slug={slug}
            actions={
              <>
                {button(item.id, "heal", "🩹 Heal")}
                {button(item.id, "release", "Release", item.release_ready)}
              </>
            }
          />
        ))}
      </div>
    </div>
  );
}
