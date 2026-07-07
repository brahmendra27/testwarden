import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

interface ApiTestJob {
  id: number;
  spec_url: string;
  base_url: string;
  status: "queued" | "running" | "completed" | "failed";
  model: string;
  log: string;
  code: string | null;
  summary: string | null;
  run_id: number | null;
  error: string | null;
}

interface ApiAgentState {
  available: boolean;
  job: ApiTestJob | null;
}

export function ApiAgentPage() {
  const { slug = "" } = useParams();
  const queryClient = useQueryClient();
  const [specUrl, setSpecUrl] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [showCode, setShowCode] = useState(false);

  const { data: state } = useQuery({
    queryKey: ["api-agent", slug],
    queryFn: async (): Promise<ApiAgentState> => {
      const response = await fetch(`/api/v1/projects/${slug}/api-agent`);
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
      const response = await fetch(`/api/v1/projects/${slug}/api-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec_url: specUrl, base_url: baseUrl }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `${response.status}`);
      return body;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["api-agent", slug] }),
  });

  const job = state?.job;
  const active = job?.status === "queued" || job?.status === "running";

  return (
    <div className="max-w-4xl">
      <h1 className="grad-text mb-2 text-3xl font-bold">API test agent</h1>
      <p className="mb-6 text-sm text-zinc-500">
        Point the agent at an OpenAPI spec. It generates a pytest + httpx suite with
        RestAssured-style assertions, verifies it against the live API, and reports the results
        here as a normal run.
      </p>

      <div className="card mb-6 p-5">
        <div className="mb-3 grid gap-3 md:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-xs font-medium uppercase text-zinc-500">
              OpenAPI spec URL
            </span>
            <input
              value={specUrl}
              onChange={(event) => setSpecUrl(event.target.value)}
              placeholder="http://localhost:8787/openapi.json"
              className="field w-full"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium uppercase text-zinc-500">
              API base URL
            </span>
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="http://localhost:8787"
              className="field w-full"
            />
          </label>
        </div>
        <button
          onClick={() => start.mutate()}
          className="btn-grad"
          disabled={!specUrl || !baseUrl || active}
        >
          🤖 {active ? "Agent running…" : "Generate & run API tests"}
        </button>
        {!state?.available && state && (
          <p className="mt-2 text-xs text-zinc-500">
            Requires <code className="rounded bg-white/10 px-1">ANTHROPIC_API_KEY</code> on the
            backend server.
          </p>
        )}
        {start.isError && (
          <p className="mt-2 text-xs text-red-400">{String(start.error.message)}</p>
        )}
      </div>

      {job && (
        <div className="card space-y-4 p-5">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-sm font-semibold text-zinc-200">Job #{job.id}</h2>
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
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
            <span className="truncate text-xs text-zinc-500">{job.spec_url}</span>
            {job.run_id && (
              <Link to={`/p/${slug}/runs/${job.run_id}`} className="btn-grad ml-auto">
                View run #{job.run_id} →
              </Link>
            )}
          </div>

          <pre className="max-h-56 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 text-xs leading-5 text-zinc-400">
            {job.log || "…"}
          </pre>

          {job.summary && (
            <div>
              <h3 className="mb-1 text-xs font-medium uppercase text-zinc-500">Agent summary</h3>
              <p className="whitespace-pre-wrap text-sm text-zinc-300">{job.summary}</p>
            </div>
          )}
          {job.error && <p className="text-sm text-red-400">{job.error}</p>}

          {job.code && (
            <div>
              <button
                onClick={() => setShowCode(!showCode)}
                className="mb-2 text-xs text-sky-400 hover:underline"
              >
                {showCode ? "hide" : "show"} generated suite
              </button>
              {showCode && (
                <pre className="max-h-96 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 text-xs leading-5 text-zinc-300">
                  {job.code}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
