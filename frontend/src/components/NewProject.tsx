import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

interface CreatedProject {
  slug: string;
  name: string;
  api_key: string;
}

function Snippet({ created }: { created: CreatedProject }) {
  const ini = `[pytest]
testwarden_url = http://localhost:8787
; add to your suite's pytest.ini / pyproject`;
  const shell = `pip install -e <path-to-testwarden>/packages/pytest-testwarden
$env:TESTWARDEN_API_KEY = "${created.api_key}"
pytest`;
  return (
    <div className="space-y-3 text-left">
      <div>
        <p className="mb-1 text-xs font-medium uppercase text-zinc-500">
          Your ingestion API key — shown only once, store it now
        </p>
        <div className="flex items-center gap-2">
          <code className="flex-1 overflow-x-auto rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
            {created.api_key}
          </code>
          <button
            onClick={() => navigator.clipboard.writeText(created.api_key)}
            className="btn-grad shrink-0"
          >
            Copy
          </button>
        </div>
      </div>
      <div>
        <p className="mb-1 text-xs font-medium uppercase text-zinc-500">1 · pytest.ini</p>
        <pre className="rounded-lg border border-white/10 bg-black/60 p-3 text-xs text-zinc-300">{ini}</pre>
      </div>
      <div>
        <p className="mb-1 text-xs font-medium uppercase text-zinc-500">2 · install reporter & run</p>
        <pre className="rounded-lg border border-white/10 bg-black/60 p-3 text-xs text-zinc-300">{shell}</pre>
      </div>
      <p className="text-xs text-zinc-500">
        Every pytest run now appears under <strong>{created.name}</strong>. Add{" "}
        <code className="rounded bg-white/10 px-1">--screenshot only-on-failure --tracing retain-on-failure --reruns 2</code>{" "}
        for Playwright artifacts and flaky detection.
      </p>
    </div>
  );
}

export function NewProject() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");

  const create = useMutation({
    mutationFn: async (): Promise<CreatedProject> => {
      const response = await fetch("/api/v1/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, repo_url: repoUrl || null }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `${response.status}`);
      return body;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  });

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn-grad">
        + New project
      </button>
    );
  }

  return (
    <div className="card w-full max-w-2xl p-5">
      {create.data ? (
        <Snippet created={create.data} />
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-48 flex-1">
            <span className="mb-1 block text-xs font-medium uppercase text-zinc-500">Project name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="My Web App"
              className="field w-full"
              autoFocus
            />
          </label>
          <label className="min-w-48 flex-1">
            <span className="mb-1 block text-xs font-medium uppercase text-zinc-500">
              Repo URL (optional, for auto-fix)
            </span>
            <input
              value={repoUrl}
              onChange={(event) => setRepoUrl(event.target.value)}
              placeholder="https://github.com/you/repo or local path"
              className="field w-full"
            />
          </label>
          <button onClick={() => create.mutate()} disabled={!name || create.isPending} className="btn-grad">
            Create
          </button>
          <button onClick={() => setOpen(false)} className="px-2 py-2 text-sm text-zinc-500 hover:text-zinc-300">
            cancel
          </button>
        </div>
      )}
      {create.isError && <p className="mt-2 text-xs text-red-400">{String(create.error.message)}</p>}
    </div>
  );
}
