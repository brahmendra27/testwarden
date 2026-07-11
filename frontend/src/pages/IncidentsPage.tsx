import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

interface Incident {
  count: number;
  node_ids: string[];
  error_type: string | null;
  error_message: string | null;
  worst_case_id: number | null;
}

export function IncidentsPage() {
  const { slug = "" } = useParams();
  const { data } = useQuery({
    queryKey: ["incidents", slug],
    queryFn: async (): Promise<{ incidents: Incident[] }> => {
      const r = await fetch(`/api/v1/projects/${slug}/incidents`);
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    },
  });

  return (
    <div className="max-w-4xl">
      <h1 className="grad-text mb-2 text-3xl font-bold">Incidents</h1>
      <p className="mb-6 text-sm text-zinc-500">
        Failures from the last 7 days grouped by root cause. One incident can span many tests —
        so you fix the cause once instead of triaging each failure separately.
      </p>
      {data && data.incidents.length === 0 && (
        <div className="card p-8 text-center text-sm text-zinc-500">No failures this week. ✅</div>
      )}
      <div className="space-y-3">
        {data?.incidents.map((inc, i) => (
          <div key={i} className="card p-4">
            <div className="mb-2 flex flex-wrap items-center gap-3">
              <span className="rounded bg-red-500/15 px-2 py-0.5 text-sm font-semibold text-red-400">
                {inc.count} failure{inc.count > 1 ? "s" : ""}
              </span>
              {inc.node_ids.length > 1 && (
                <span className="text-xs text-zinc-400">across {inc.node_ids.length} tests</span>
              )}
              {inc.worst_case_id && (
                <Link to={`/p/${slug}/tests/${inc.worst_case_id}`} className="btn-grad ml-auto text-xs">
                  Investigate →
                </Link>
              )}
            </div>
            {inc.error_message && (
              <p className="mb-2 text-sm text-red-400/80">
                {inc.error_type}: {inc.error_message}
              </p>
            )}
            <div className="flex flex-wrap gap-1.5">
              {inc.node_ids.slice(0, 8).map((n) => (
                <span key={n} className="rounded bg-white/5 px-2 py-0.5 font-mono text-xs text-zinc-400">
                  {n}
                </span>
              ))}
              {inc.node_ids.length > 8 && (
                <span className="text-xs text-zinc-500">+{inc.node_ids.length - 8} more</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
