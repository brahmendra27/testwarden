import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

interface AnalysisPayload {
  id: number;
  model: string;
  content: string;
  created_at: string | null;
  cached: boolean;
}

interface AnalysisState {
  available: boolean;
  analysis: AnalysisPayload | null;
}

function AnalysisBody({ content }: { content: string }) {
  return (
    <div className="space-y-1 text-sm leading-6 text-zinc-300">
      {content.split("\n").map((line, index) => {
        if (line.startsWith("## ")) {
          return (
            <h4 key={index} className="grad-text pt-2 text-sm font-bold">
              {line.slice(3)}
            </h4>
          );
        }
        if (line.trim() === "") return <div key={index} className="h-1" />;
        return <p key={index}>{line}</p>;
      })}
    </div>
  );
}

export function AiAnalysis({ resultId }: { resultId: number }) {
  const queryClient = useQueryClient();
  const { data: state } = useQuery({
    queryKey: ["analysis", resultId],
    queryFn: async (): Promise<AnalysisState> => {
      const response = await fetch(`/api/v1/results/${resultId}/analysis`);
      if (!response.ok) throw new Error(`${response.status}`);
      return response.json();
    },
  });

  const analyze = useMutation({
    mutationFn: async (): Promise<AnalysisPayload> => {
      const response = await fetch(`/api/v1/results/${resultId}/analyze`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `${response.status}`);
      return body;
    },
    onSuccess: (analysis) => {
      queryClient.setQueryData(["analysis", resultId], {
        available: true,
        analysis,
      } satisfies AnalysisState);
    },
  });

  const analysis = state?.analysis;

  return (
    <div className="rounded-xl border border-blue-400/25 bg-blue-500/[0.06] p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-base">✨</span>
        <h3 className="text-sm font-semibold text-blue-200">AI failure analysis</h3>
        {analysis && (
          <span className="ml-auto text-xs text-zinc-500">
            {analysis.model}
            {analysis.cached ? " · cached" : ""}
          </span>
        )}
      </div>

      {analyze.isPending ? (
        <div className="space-y-2 py-2">
          <div className="shimmer-line h-3 w-3/4 rounded bg-white/10" />
          <div className="shimmer-line h-3 w-full rounded bg-white/10" />
          <div className="shimmer-line h-3 w-2/3 rounded bg-white/10" />
          <p className="pt-1 text-xs text-zinc-500">Claude is reading the failure…</p>
        </div>
      ) : analysis ? (
        <>
          <AnalysisBody content={analysis.content} />
          <button
            onClick={() => analyze.mutate()}
            className="mt-3 text-xs text-sky-400 hover:underline"
          >
            re-analyze
          </button>
        </>
      ) : (
        <>
          <p className="mb-3 text-sm text-zinc-400">
            Let Claude read the stack trace, retry history and flake stats, then classify the
            root cause and suggest a fix.
          </p>
          <button onClick={() => analyze.mutate()} className="btn-grad" disabled={!state}>
            ✨ Analyze with AI
          </button>
          {!state?.available && state && (
            <p className="mt-2 text-xs text-zinc-500">
              Requires <code className="rounded bg-white/10 px-1">ANTHROPIC_API_KEY</code> on the
              backend server.
            </p>
          )}
        </>
      )}
      {analyze.isError && (
        <p className="mt-2 text-xs text-red-400">{String(analyze.error.message)}</p>
      )}
    </div>
  );
}
