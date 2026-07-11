import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

interface Probe {
  label: string;
  fail_rate: number;
}

interface ReproJob {
  id: number;
  status: "queued" | "running" | "completed" | "failed";
  outcome: string | null;
  log: string;
  recipe: Record<string, unknown> | null;
  recipe_label: string | null;
  fail_rate: number | null;
  baseline_fail_rate: number | null;
  probes: Probe[];
  error: string | null;
}

interface ReproState {
  available: boolean;
  job: ReproJob | null;
}

function Bar({ label, rate, highlight }: { label: string; rate: number; highlight?: boolean }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-52 shrink-0 truncate text-zinc-400" title={label}>
        {label}
      </span>
      <div className="h-2 flex-1 overflow-hidden rounded bg-white/5">
        <div
          className={`h-full rounded ${highlight ? "bg-red-400" : "bg-blue-400/70"}`}
          style={{ width: `${Math.round(rate * 100)}%` }}
        />
      </div>
      <span className="w-10 shrink-0 text-right text-zinc-400">{Math.round(rate * 100)}%</span>
    </div>
  );
}

export function Reproducer({ caseId }: { caseId: number }) {
  const queryClient = useQueryClient();
  const { data: state } = useQuery({
    queryKey: ["reproducer", caseId],
    queryFn: async (): Promise<ReproState> => {
      const response = await fetch(`/api/v1/tests/${caseId}/reproducer`);
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
      const response = await fetch(`/api/v1/tests/${caseId}/reproducer`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `${response.status}`);
      return body;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reproducer", caseId] }),
  });

  const job = state?.job;
  const active = job?.status === "queued" || job?.status === "running";
  const reproduced = job?.outcome === "reproduced";

  return (
    <div className="card mb-6 border-red-400/20 p-5">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-base">🎯</span>
        <h2 className="text-sm font-semibold text-red-200">Reproducer</h2>
        {job && (
          <span
            className={`ml-auto rounded px-2 py-0.5 text-xs font-medium ${
              reproduced
                ? "bg-red-500/15 text-red-300"
                : job.status === "completed"
                  ? "bg-zinc-500/15 text-zinc-400"
                  : job.status === "failed"
                    ? "bg-red-500/15 text-red-400"
                    : "bg-sky-500/15 text-sky-400"
            }`}
          >
            {active && <span className="glow-dot mr-1.5 align-middle" />}
            {active ? job.status : job.outcome ?? job.status}
          </span>
        )}
      </div>

      {!job && (
        <>
          <p className="mb-3 text-sm text-zinc-400">
            Hunt the race. The Reproducer runs this test under controlled chaos — network latency,
            CPU throttling, timing jitter, mobile viewport — to find the minimal condition that
            makes a "sometimes red" test fail <strong>every time</strong>. That turns a guess into a
            diagnosis, and lets SelfHeal verify a fix under the real failure condition.
          </p>
          <button onClick={() => start.mutate()} className="btn-grad" disabled={!state}>
            🎯 Reproduce this flake
          </button>
        </>
      )}

      {job && (
        <div className="space-y-4">
          {reproduced && (
            <div className="rounded-lg border border-red-400/30 bg-red-500/10 p-3">
              <div className="text-xs font-medium uppercase text-red-300">Deterministic trigger found</div>
              <div className="mt-1 font-mono text-sm text-red-200">{job.recipe_label}</div>
              <div className="mt-2 text-xs text-zinc-400">
                Fails <strong className="text-red-300">{Math.round((job.fail_rate ?? 0) * 100)}%</strong> under
                this condition, vs {Math.round((job.baseline_fail_rate ?? 0) * 100)}% normally. SelfHeal will
                now verify any fix under this exact condition.
              </div>
            </div>
          )}
          {job.status === "completed" && !reproduced && (
            <p className="text-sm text-zinc-400">
              No deterministic trigger found in the searched space — this looks like true
              nondeterminism (infra, resource contention) rather than an app race.{" "}
              {job.recipe_label}
            </p>
          )}
          {job.error && <p className="text-sm text-red-400">{job.error}</p>}

          {job.probes.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-medium uppercase text-zinc-500">Probe results</div>
              <div className="space-y-1.5">
                {job.probes.map((probe, index) => (
                  <Bar
                    key={index}
                    label={probe.label}
                    rate={probe.fail_rate}
                    highlight={reproduced && probe.fail_rate >= 0.6 && probe.label !== "baseline"}
                  />
                ))}
              </div>
            </div>
          )}

          {active && (
            <pre className="max-h-40 overflow-auto rounded-lg border border-white/10 bg-black/60 p-3 text-xs text-zinc-400">
              {job.log || "…"}
            </pre>
          )}

          {!active && (
            <button onClick={() => start.mutate()} className="text-xs text-sky-400 hover:underline">
              run again
            </button>
          )}
        </div>
      )}
      {start.isError && <p className="mt-2 text-xs text-red-400">{String(start.error.message)}</p>}
    </div>
  );
}
