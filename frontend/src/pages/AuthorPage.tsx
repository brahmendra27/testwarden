import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

interface AuthorJob {
  id: number;
  description: string;
  url: string;
  status: "queued" | "running" | "completed" | "failed";
  log: string;
  code: string | null;
  file_path: string | null;
  verified: boolean;
  branch: string | null;
  pr_url: string | null;
  summary: string | null;
  error: string | null;
}

interface AuthorState {
  available: boolean;
  job: AuthorJob | null;
}

const EXAMPLES = [
  "A user can sign in with valid credentials and reaches the catalog",
  "Searching for a product filters the list to just that item",
  "Adding an item to the cart increases the cart count",
];

export function AuthorPage() {
  const { slug = "" } = useParams();
  const queryClient = useQueryClient();
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [showCode, setShowCode] = useState(true);

  const { data: state } = useQuery({
    queryKey: ["author", slug],
    queryFn: async (): Promise<AuthorState> => {
      const response = await fetch(`/api/v1/projects/${slug}/author`);
      if (!response.ok) throw new Error(`${response.status}`);
      return response.json();
    },
    refetchInterval: (query) => {
      const status = query.state.data?.job?.status;
      return status === "queued" || status === "running" ? 2500 : false;
    },
  });

  const start = useMutation({
    mutationFn: async () => {
      const response = await fetch(`/api/v1/projects/${slug}/author`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description, url }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `${response.status}`);
      return body;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["author", slug] }),
  });

  const job = state?.job;
  const active = job?.status === "queued" || job?.status === "running";

  return (
    <div className="max-w-4xl">
      <h1 className="grad-text mb-2 text-3xl font-bold">Write a test in plain English</h1>
      <p className="mb-6 text-sm text-zinc-500">
        Describe what you want to test and give the page URL. The agent opens your app in a real
        browser, finds the right elements, writes a Playwright test, runs it to prove it passes,
        and (if the project has a repo) opens a pull request. No code required.
      </p>

      <div className="card mb-6 p-5">
        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-medium uppercase text-zinc-500">
            What should the test check?
          </span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. A user can log in and see their dashboard"
            rows={2}
            className="field w-full resize-y"
          />
        </label>
        <div className="mb-3 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => setDescription(ex)}
              className="rounded-full border border-white/10 px-3 py-1 text-xs text-zinc-400 hover:bg-white/5"
            >
              {ex}
            </button>
          ))}
        </div>
        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-medium uppercase text-zinc-500">Page URL</span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://staging.your-app.com/login"
            className="field w-full"
          />
        </label>
        <button
          onClick={() => start.mutate()}
          disabled={!description || !url || active}
          className="btn-grad"
        >
          ✍️ {active ? "Agent working…" : "Write my test"}
        </button>
        {!state?.available && state && (
          <p className="mt-2 text-xs text-zinc-500">
            Requires <code className="rounded bg-white/10 px-1">ANTHROPIC_API_KEY</code> on the backend.
          </p>
        )}
        {start.isError && <p className="mt-2 text-xs text-red-400">{String(start.error.message)}</p>}
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
            {job.verified && (
              <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-400">
                ✓ verified green
              </span>
            )}
            <span className="truncate text-xs text-zinc-500">{job.description}</span>
            {job.pr_url && (
              <a href={job.pr_url} target="_blank" rel="noreferrer" className="btn-grad ml-auto">
                View pull request →
              </a>
            )}
          </div>

          <pre className="max-h-56 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 text-xs leading-5 text-zinc-400">
            {job.log || "…"}
          </pre>

          {job.summary && <p className="text-sm text-zinc-300">{job.summary}</p>}
          {job.error && <p className="text-sm text-red-400">{job.error}</p>}

          {job.code && (
            <div>
              <button
                onClick={() => setShowCode(!showCode)}
                className="mb-2 text-xs text-sky-400 hover:underline"
              >
                {showCode ? "hide" : "show"} generated test
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

      {!job && (
        <p className="text-xs text-zinc-600">
          New here? The <Link to={`/p/${slug}/api-agent`} className="text-sky-400 hover:underline">API test agent</Link>{" "}
          does the same for REST endpoints from an OpenAPI spec.
        </p>
      )}
    </div>
  );
}
