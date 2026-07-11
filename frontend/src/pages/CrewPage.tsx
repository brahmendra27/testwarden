import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { formatDate } from "../components/status";

interface Incident {
  node_ids: string[];
  count: number;
  classification: string;
  error_type: string | null;
  error_message: string | null;
  case_ids: number[];
  action?: { kind: string; status: string; branch?: string; pr_url?: string };
  action_reason?: string;
}

interface CrewRun {
  id: number;
  trigger: string;
  status: "queued" | "running" | "completed" | "failed";
  log: string;
  incidents: Incident[];
  digest: string | null;
  error: string | null;
  window_start: string | null;
  created_at: string | null;
}

const CLASS_STYLE: Record<string, string> = {
  APP_BUG: "bg-red-500/15 text-red-400",
  TEST_BUG: "bg-amber-500/15 text-amber-400",
  FLAKY_TIMING: "bg-violet-500/15 text-violet-300",
  ENVIRONMENT: "bg-sky-500/15 text-sky-400",
  UNKNOWN: "bg-zinc-500/15 text-zinc-400",
  UNANALYZED: "bg-zinc-500/15 text-zinc-500",
};

function IncidentCard({ incident, slug }: { incident: Incident; slug: string }) {
  const primary = incident.node_ids[0] ?? "unknown";
  const action = incident.action;
  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.03] p-3">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${CLASS_STYLE[incident.classification] ?? CLASS_STYLE.UNKNOWN}`}>
          {incident.classification}
        </span>
        <span className="text-xs text-zinc-500">{incident.count} failure{incident.count > 1 ? "s" : ""}</span>
        {incident.case_ids[0] && (
          <Link to={`/p/${slug}/tests/${incident.case_ids[0]}`} className="min-w-0 flex-1 truncate font-mono text-xs text-zinc-300 hover:text-sky-400">
            {primary}
          </Link>
        )}
        {incident.node_ids.length > 1 && (
          <span className="text-xs text-zinc-500">+{incident.node_ids.length - 1} more</span>
        )}
      </div>
      {incident.error_message && (
        <p className="mb-1 line-clamp-1 text-xs text-red-400/80">
          {incident.error_type}: {incident.error_message}
        </p>
      )}
      {action?.kind ? (
        <div className="flex items-center gap-2 text-xs">
          <span className="rounded bg-blue-500/15 px-2 py-0.5 text-blue-300">
            🤖 {action.kind} · {action.status}
          </span>
          {action.pr_url && (
            <a href={action.pr_url} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">
              PR ↗
            </a>
          )}
          {!action.pr_url && action.branch && (
            <span className="font-mono text-zinc-500">{action.branch}</span>
          )}
        </div>
      ) : (
        <p className="text-xs text-zinc-500">No action — {incident.action_reason ?? "report only"}</p>
      )}
    </div>
  );
}

export function CrewPage() {
  const { slug = "" } = useParams();
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["crew", slug],
    queryFn: async (): Promise<{ runs: CrewRun[] }> => {
      const response = await fetch(`/api/v1/projects/${slug}/crew`);
      if (!response.ok) throw new Error(`${response.status}`);
      return response.json();
    },
    refetchInterval: (query) => {
      const latest = query.state.data?.runs?.[0];
      return latest && (latest.status === "queued" || latest.status === "running") ? 2500 : false;
    },
  });

  const run = useMutation({
    mutationFn: async () => {
      const response = await fetch(`/api/v1/projects/${slug}/crew`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `${response.status}`);
      return body;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["crew", slug] }),
  });

  const latest = data?.runs?.[0];
  const active = latest?.status === "queued" || latest?.status === "running";

  return (
    <div className="max-w-4xl">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="grad-text text-3xl font-bold">Maintenance crew</h1>
        <button onClick={() => run.mutate()} disabled={active} className="btn-grad ml-auto">
          🌙 {active ? "Running…" : "Run crew now"}
        </button>
      </div>
      <p className="mb-6 text-sm text-zinc-500">
        An autonomous nightly pass: cluster new failures into incidents, classify each with AI,
        then act — SelfHeal test bugs, quarantine chronic flakes, flag app bugs for humans. Set{" "}
        <code className="rounded bg-white/10 px-1">FLAKELENS_CREW_HOUR</code> (0–23) to schedule it.
      </p>
      {run.isError && <p className="mb-4 text-xs text-red-400">{String(run.error.message)}</p>}

      {!latest && (
        <div className="card p-8 text-center text-sm text-zinc-500">
          No crew runs yet. Click "Run crew now" to do the first pass.
        </div>
      )}

      {latest && (
        <div className="card mb-6 p-5">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
                latest.status === "completed"
                  ? "bg-emerald-500/15 text-emerald-400"
                  : latest.status === "failed"
                    ? "bg-red-500/15 text-red-400"
                    : "bg-sky-500/15 text-sky-400"
              }`}
            >
              {active && <span className="glow-dot mr-1.5 align-middle" />}
              {latest.status}
            </span>
            <span className="text-sm text-zinc-400">
              {latest.trigger} pass · {formatDate(latest.created_at)}
            </span>
            <span className="ml-auto text-xs text-zinc-500">
              {latest.incidents.length} incident{latest.incidents.length === 1 ? "" : "s"}
            </span>
          </div>

          {latest.error && <p className="mb-3 text-sm text-red-400">{latest.error}</p>}

          {active && (
            <pre className="mb-3 max-h-40 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 text-xs text-zinc-400">
              {latest.log || "…"}
            </pre>
          )}

          {latest.incidents.length === 0 && latest.status === "completed" && (
            <p className="text-sm text-emerald-400">All quiet — no new failures in this window. ✅</p>
          )}

          <div className="space-y-2">
            {latest.incidents.map((incident, index) => (
              <IncidentCard key={index} incident={incident} slug={slug} />
            ))}
          </div>
        </div>
      )}

      {data && data.runs.length > 1 && (
        <>
          <h2 className="mb-2 text-sm font-medium uppercase text-zinc-500">Earlier passes</h2>
          <div className="space-y-2">
            {data.runs.slice(1).map((r) => (
              <div key={r.id} className="card flex items-center gap-3 p-3 text-sm">
                <span className="text-zinc-400">{r.trigger}</span>
                <span className="text-zinc-500">{formatDate(r.created_at)}</span>
                <span className="ml-auto text-zinc-500">{r.incidents.length} incidents</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
