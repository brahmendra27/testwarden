import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useBranches, useCompare, useRuns } from "../api/hooks";
import type { CompareItem } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate } from "../components/status";

const BUCKETS: { key: string; label: string; tone: string }[] = [
  { key: "newly_failing", label: "Newly failing", tone: "text-red-400" },
  { key: "fixed", label: "Fixed", tone: "text-emerald-400" },
  { key: "newly_flaky", label: "Newly flaky", tone: "text-amber-400" },
  { key: "still_failing", label: "Still failing", tone: "text-rose-400" },
  { key: "new", label: "New tests", tone: "text-sky-400" },
  { key: "removed", label: "Removed", tone: "text-zinc-400" },
];

function RunSelect({
  label,
  value,
  onChange,
  runs,
}: {
  label: string;
  value: number | null;
  onChange: (id: number) => void;
  runs: { id: number; branch: string | null; started_at: string | null }[];
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-zinc-400">
      {label}
      <select
        value={value ?? ""}
        onChange={(event) => onChange(Number(event.target.value))}
        className="field"
      >
        <option value="" disabled>
          select run
        </option>
        {runs.map((run) => (
          <option key={run.id} value={run.id}>
            #{run.id} · {run.branch ?? "?"} · {formatDate(run.started_at)}
          </option>
        ))}
      </select>
    </label>
  );
}

function BranchSelect({ label, value, onChange, branches }: {
  label: string; value: string; onChange: (b: string) => void; branches: string[];
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-zinc-400">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="field">
        <option value="" disabled>select branch</option>
        {branches.map((b) => <option key={b} value={b}>{b}</option>)}
      </select>
    </label>
  );
}

export function ComparePage() {
  const { slug = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [mode, setMode] = useState<"runs" | "branches">("runs");
  const { data: runs } = useRuns(slug);
  const { data: branches } = useBranches(slug);
  const [baseBranch, setBaseBranch] = useState("");
  const [headBranch, setHeadBranch] = useState("");
  const base = params.get("base") ? Number(params.get("base")) : null;
  const head = params.get("head") ? Number(params.get("head")) : null;
  const { data: runComparison, isLoading: runLoading } = useCompare(base, head);
  const { data: branchComparison, isLoading: branchLoading } = useQuery({
    queryKey: ["compare-branches", slug, baseBranch, headBranch],
    queryFn: async () => {
      const r = await fetch(`/api/v1/projects/${slug}/compare-branches?base=${encodeURIComponent(baseBranch)}&head=${encodeURIComponent(headBranch)}`);
      if (!r.ok) throw new Error((await r.json()).detail ?? `${r.status}`);
      return r.json();
    },
    enabled: mode === "branches" && !!baseBranch && !!headBranch,
    retry: false,
  });
  const [activeBucket, setActiveBucket] = useState("newly_failing");

  const setParam = (key: "base" | "head") => (id: number) => {
    params.set(key, String(id));
    setParams(params, { replace: true });
  };

  const comparison = mode === "runs" ? runComparison : branchComparison;
  const isLoading = mode === "runs" ? runLoading : branchLoading;
  const ready = mode === "runs" ? base != null && head != null : !!baseBranch && !!headBranch;
  const items: CompareItem[] = comparison?.buckets[activeBucket] ?? [];

  return (
    <div>
      <h1 className="grad-text mb-4 text-3xl font-bold">Compare</h1>
      <div className="mb-4 flex gap-2">
        {(["runs", "branches"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)}
            className={`rounded-full px-3 py-1 text-sm capitalize transition ${
              mode === m ? "border border-blue-400/40 bg-blue-500/15 text-blue-200"
                : "border border-white/10 text-zinc-400 hover:bg-white/5"}`}>
            {m}
          </button>
        ))}
      </div>
      <div className="mb-6 flex flex-wrap items-center gap-6">
        {mode === "runs" ? (
          <>
            <RunSelect label="Base" value={base} onChange={setParam("base")} runs={runs ?? []} />
            <span className="text-zinc-600">→</span>
            <RunSelect label="Head" value={head} onChange={setParam("head")} runs={runs ?? []} />
          </>
        ) : (
          <>
            <BranchSelect label="Base" value={baseBranch} onChange={setBaseBranch} branches={branches ?? []} />
            <span className="text-zinc-600">→</span>
            <BranchSelect label="Head" value={headBranch} onChange={setHeadBranch} branches={branches ?? []} />
          </>
        )}
      </div>
      {!ready ? (
        <p className="text-zinc-500">Pick two {mode === "runs" ? "runs" : "branches"} to compare.</p>
      ) : isLoading ? (
        <p className="text-zinc-500">Comparing…</p>
      ) : comparison ? (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-6">
            {BUCKETS.map((bucket) => (
              <button
                key={bucket.key}
                onClick={() => setActiveBucket(bucket.key)}
                className={`rounded-xl border px-4 py-3 text-left transition ${
                  activeBucket === bucket.key
                    ? "border-blue-400/50 bg-blue-500/10 shadow-[0_0_20px_rgba(61,106,254,0.25)]"
                    : "border-white/10 bg-white/[0.04] hover:border-blue-400/30"
                }`}
              >
                <div className={`text-xl font-semibold ${bucket.tone}`}>
                  {comparison.counts[bucket.key] ?? 0}
                </div>
                <div className="text-xs text-zinc-500">{bucket.label}</div>
              </button>
            ))}
          </div>
          {items.length === 0 ? (
            <p className="text-zinc-500">Nothing in this bucket.</p>
          ) : (
            <div className="card overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-white/5 text-left text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="px-4 py-2">Test</th>
                    <th className="px-4 py-2">Base</th>
                    <th className="px-4 py-2">Head</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.test_case_id} className="border-t border-white/5 hover:bg-white/5">
                      <td className="px-4 py-2">
                        <Link to={`/p/${slug}/tests/${item.test_case_id}`} className="font-mono text-xs text-zinc-300 hover:text-sky-400">
                          {item.node_id}
                        </Link>
                        {item.error_message && (
                          <div className="mt-0.5 line-clamp-1 text-xs text-red-400/80">{item.error_message}</div>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        {item.base_status ? <StatusBadge status={item.base_status} /> : <span className="text-zinc-600">—</span>}
                      </td>
                      <td className="px-4 py-2">
                        {item.head_status ? (
                          <StatusBadge status={item.head_status} flaky={item.head_flaky_in_run} />
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
