import { Link } from "react-router-dom";
import { useProjects } from "../api/hooks";
import { Sparkline } from "../components/Sparkline";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate } from "../components/status";

export function ProjectsPage() {
  const { data: projects, isLoading, error } = useProjects();
  if (isLoading) return <p className="text-zinc-500">Loading projects…</p>;
  if (error) return <p className="text-red-400">Failed to load projects: {String(error)}</p>;
  if (!projects?.length)
    return (
      <div className="mt-20 text-center text-zinc-500">
        <p className="text-lg">No projects yet.</p>
        <p className="mt-2 text-sm">
          Seed demo data with <code className="rounded bg-zinc-900 px-1.5 py-0.5">python -m testwarden.seed</code>{" "}
          or point the pytest reporter at this server.
        </p>
      </div>
    );
  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold text-zinc-100">Projects</h1>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {projects.map((project) => {
          const lastRun = project.last_run;
          const passRate =
            lastRun && lastRun.total ? Math.round((lastRun.passed / lastRun.total) * 100) : null;
          return (
            <Link
              key={project.id}
              to={`/p/${project.slug}/runs`}
              className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 transition hover:border-zinc-600"
            >
              <div className="mb-3 flex items-center justify-between">
                <span className="text-lg font-medium text-zinc-100">{project.name}</span>
                {lastRun && <StatusBadge status={lastRun.failed + lastRun.error_count > 0 ? "failed" : "passed"} />}
              </div>
              <Sparkline values={project.sparkline.map((point) => point.pass_rate)} />
              <div className="mt-3 flex items-center gap-4 text-sm text-zinc-400">
                <span>{passRate != null ? `${passRate}% pass` : "no runs"}</span>
                {project.flaky_count > 0 && (
                  <span className="text-amber-400">{project.flaky_count} flaky</span>
                )}
                <span className="ml-auto text-zinc-500">
                  {lastRun ? formatDate(lastRun.started_at) : ""}
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
