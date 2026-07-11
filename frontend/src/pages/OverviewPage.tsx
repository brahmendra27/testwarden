import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { StatusBadge } from "../components/StatusBadge";
import { HealthPanel } from "../components/HealthPanel";
import { formatDuration } from "../components/status";

interface Overview {
  project: { slug: string; name: string };
  kpis: {
    pass_rate: number | null;
    pass_rate_prev: number | null;
    flaky_count: number;
    last_duration_ms: number;
    prev_duration_ms: number;
    total_tests: number;
    last_run_id: number | null;
    last_failed: number;
  };
  series: {
    run_id: number;
    pass_rate: number | null;
    duration_ms: number;
    failed: number;
    flaky: number;
  }[];
  most_failing: {
    test_case_id: number;
    node_id: string;
    failures: number;
    window_runs: number;
    last_status: string | null;
    is_flaky: boolean;
  }[];
  slowest: { test_case_id: number; node_id: string; avg_duration_ms: number; p95_duration_ms: number }[];
}

function useOverview(slug: string) {
  return useQuery({
    queryKey: ["overview", slug],
    queryFn: async (): Promise<Overview> => {
      const response = await fetch(`/api/v1/projects/${slug}/overview`);
      if (!response.ok) throw new Error(`${response.status}`);
      return response.json();
    },
  });
}

function Delta({ current, previous, invert }: { current: number | null; previous: number | null; invert?: boolean }) {
  if (current == null || previous == null || previous === 0) return null;
  const change = current - previous;
  if (Math.abs(change) < 0.0001) return <span className="text-xs text-zinc-500">— steady</span>;
  const good = invert ? change < 0 : change > 0;
  return (
    <span className={`text-xs ${good ? "text-emerald-400" : "text-red-400"}`}>
      {change > 0 ? "▲" : "▼"} {Math.abs(change * 100).toFixed(1)}% vs prev
    </span>
  );
}

function Kpi({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="card card-hover p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-1 text-3xl font-bold text-white" style={{ fontFamily: "Plus Jakarta Sans" }}>
        {value}
      </div>
      <div className="mt-1 h-4">{sub}</div>
    </div>
  );
}

const tooltipStyle = {
  background: "#0a0a0a",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: 8,
} as const;

export function OverviewPage() {
  const { slug = "" } = useParams();
  const { data, isLoading, error } = useOverview(slug);
  if (isLoading) return <p className="text-zinc-500">Loading overview…</p>;
  if (error || !data) return <p className="text-red-400">Failed to load overview.</p>;
  const { kpis, series } = data;

  return (
    <div>
      <div className="mb-1 flex items-center gap-3">
        <h1 className="grad-text text-3xl font-bold">{data.project.name}</h1>
        <span className="glow-dot" />
      </div>
      <p className="mb-6 text-sm text-zinc-500">Suite health over the last {series.length} runs</p>

      <HealthPanel />

      <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Kpi
          label="Pass rate"
          value={kpis.pass_rate != null ? `${(kpis.pass_rate * 100).toFixed(1)}%` : "—"}
          sub={<Delta current={kpis.pass_rate} previous={kpis.pass_rate_prev} />}
        />
        <Kpi
          label="Flaky tests"
          value={<span className={kpis.flaky_count ? "text-amber-400" : undefined}>{kpis.flaky_count}</span>}
          sub={
            kpis.flaky_count > 0 && (
              <Link to={`/p/${slug}/flaky`} className="text-xs text-sky-400 hover:underline">
                view all →
              </Link>
            )
          }
        />
        <Kpi
          label="Last run"
          value={
            <span className={kpis.last_failed ? "text-red-400" : "text-emerald-400"}>
              {kpis.last_failed ? `${kpis.last_failed} failing` : "green"}
            </span>
          }
          sub={
            kpis.last_run_id && (
              <Link to={`/p/${slug}/runs/${kpis.last_run_id}`} className="text-xs text-sky-400 hover:underline">
                run #{kpis.last_run_id} →
              </Link>
            )
          }
        />
        <Kpi label="Tests" value={kpis.total_tests} sub={<span className="text-xs text-zinc-500">in latest run</span>} />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card p-5">
          <h2 className="mb-3 text-sm font-semibold text-zinc-300">Pass rate</h2>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={series} margin={{ top: 5, right: 5, bottom: 0, left: -10 }}>
              <defs>
                <linearGradient id="passGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4d76ff" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="#4d76ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
              <XAxis dataKey="run_id" stroke="#71717a" fontSize={11} tickLine={false} tickFormatter={(v) => `#${v}`} />
              <YAxis
                domain={[(min: number) => Math.max(0, min - 0.05), 1]}
                stroke="#71717a"
                fontSize={11}
                tickLine={false}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                labelFormatter={(v) => `Run #${v}`}
                formatter={(value) => [`${(Number(value) * 100).toFixed(1)}%`, "pass rate"]}
              />
              <Area
                type="monotone"
                dataKey="pass_rate"
                stroke="#4d76ff"
                strokeWidth={2}
                fill="url(#passGrad)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-5">
          <h2 className="mb-3 text-sm font-semibold text-zinc-300">Run duration</h2>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={series} margin={{ top: 5, right: 5, bottom: 0, left: -10 }}>
              <defs>
                <linearGradient id="durGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
              <XAxis dataKey="run_id" stroke="#71717a" fontSize={11} tickLine={false} tickFormatter={(v) => `#${v}`} />
              <YAxis stroke="#71717a" fontSize={11} tickLine={false} tickFormatter={(v: number) => formatDuration(v)} />
              <Tooltip
                contentStyle={tooltipStyle}
                labelFormatter={(v) => `Run #${v}`}
                formatter={(value) => [formatDuration(Number(value)), "duration"]}
              />
              <Area
                type="monotone"
                dataKey="duration_ms"
                stroke="#a78bfa"
                strokeWidth={2}
                fill="url(#durGrad)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card p-5">
          <h2 className="mb-3 text-sm font-semibold text-zinc-300">Most failing (last {series.length} runs)</h2>
          {data.most_failing.length === 0 ? (
            <p className="text-sm text-zinc-500">No failures in this window. 🎉</p>
          ) : (
            <div className="space-y-2">
              {data.most_failing.map((item) => (
                <Link
                  key={item.test_case_id}
                  to={`/p/${slug}/tests/${item.test_case_id}`}
                  className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2 transition hover:border-blue-400/30"
                >
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-zinc-300">{item.node_id}</span>
                  {item.is_flaky && <StatusBadge status="flaky" />}
                  <span className="text-xs text-red-400">
                    {item.failures}/{item.window_runs} runs
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
        <div className="card p-5">
          <h2 className="mb-3 text-sm font-semibold text-zinc-300">Slowest tests</h2>
          <div className="space-y-2">
            {data.slowest.map((item) => (
              <Link
                key={item.test_case_id}
                to={`/p/${slug}/tests/${item.test_case_id}`}
                className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2 transition hover:border-blue-400/30"
              >
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-zinc-300">{item.node_id}</span>
                <span className="text-xs text-zinc-400">avg {formatDuration(item.avg_duration_ms)}</span>
                <span className="text-xs text-zinc-500">p95 {formatDuration(item.p95_duration_ms)}</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
