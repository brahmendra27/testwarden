import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

interface Health {
  health: { grade: string; score: number; drivers: string[] };
  actions: { priority: string; title: string; detail: string; link: string | null }[];
}
interface Alerts {
  alerts: { kind: string; severity: string; message: string; tests?: unknown[] }[];
}

const GRADE_COLOR: Record<string, string> = {
  A: "text-emerald-400", B: "text-emerald-300", C: "text-amber-400",
  D: "text-orange-400", F: "text-red-400", "—": "text-zinc-500",
};
const PRI_STYLE: Record<string, string> = {
  high: "border-red-400/30 bg-red-500/[0.06]",
  medium: "border-amber-400/30 bg-amber-500/[0.06]",
  low: "border-white/10 bg-white/[0.03]",
};

export function HealthPanel() {
  const { slug = "" } = useParams();
  const { data } = useQuery({
    queryKey: ["health", slug],
    queryFn: async (): Promise<Health> => {
      const r = await fetch(`/api/v1/projects/${slug}/health`);
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    },
  });
  const { data: alertData } = useQuery({
    queryKey: ["alerts", slug],
    queryFn: async (): Promise<Alerts> => {
      const r = await fetch(`/api/v1/projects/${slug}/alerts`);
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    },
  });

  if (!data) return null;
  const grade = data.health.grade;

  return (
    <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Grade */}
      <div className="card flex flex-col items-center justify-center p-5 text-center">
        <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">Health grade</div>
        <div className={`text-6xl font-bold ${GRADE_COLOR[grade] ?? "text-zinc-300"}`}
             style={{ fontFamily: "Plus Jakarta Sans" }}>
          {grade}
        </div>
        <div className="mt-1 text-xs text-zinc-500">{data.health.score}/100</div>
        <ul className="mt-3 space-y-1 text-xs text-zinc-400">
          {data.health.drivers.map((d, i) => <li key={i}>{d}</li>)}
        </ul>
      </div>

      {/* What should I do today */}
      <div className="card p-5 lg:col-span-2">
        <h2 className="mb-3 text-sm font-semibold text-zinc-300">What should I do today?</h2>
        <div className="space-y-2">
          {data.actions.map((a, i) => {
            const body = (
              <div className={`rounded-lg border p-3 ${PRI_STYLE[a.priority] ?? PRI_STYLE.low}`}>
                <div className="flex items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                    a.priority === "high" ? "bg-red-500/15 text-red-400"
                      : a.priority === "medium" ? "bg-amber-500/15 text-amber-400"
                      : "bg-white/10 text-zinc-400"}`}>
                    {a.priority}
                  </span>
                  <span className="text-sm font-medium text-zinc-200">{a.title}</span>
                </div>
                <p className="mt-1 text-xs text-zinc-400">{a.detail}</p>
              </div>
            );
            return a.link ? (
              <Link key={i} to={`/p/${slug}${a.link}`} className="block transition hover:opacity-90">{body}</Link>
            ) : <div key={i}>{body}</div>;
          })}
        </div>
        {alertData && alertData.alerts.length > 0 && (
          <div className="mt-4">
            <h3 className="mb-2 text-xs font-medium uppercase text-zinc-500">Regression alerts</h3>
            <div className="space-y-1.5">
              {alertData.alerts.map((al, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <span className={al.severity === "high" ? "text-red-400" : "text-amber-400"}>▲</span>
                  <span className="text-zinc-300">{al.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
