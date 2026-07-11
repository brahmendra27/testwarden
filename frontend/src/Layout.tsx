import { NavLink, Outlet, useParams } from "react-router-dom";

function SideLink({ to, label, end }: { to: string; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `block rounded-lg px-3 py-2 text-sm transition ${
          isActive
            ? "border border-blue-400/30 bg-blue-500/10 text-white shadow-[0_0_16px_rgba(61,106,254,0.2)]"
            : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export function Layout() {
  const { slug } = useParams();
  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-white/10 bg-white/[0.02] p-4 backdrop-blur-sm">
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <span className="glow-dot" />
          <span className="grad-text text-lg font-bold tracking-tight" style={{ fontFamily: "Plus Jakarta Sans" }}>
            FlakeLens
          </span>
        </div>
        <nav className="space-y-1">
          <SideLink to="/" label="Projects" end />
          {slug && (
            <>
              <div className="mt-4 px-3 pb-1 text-xs font-medium uppercase tracking-wide text-zinc-600">
                {slug}
              </div>
              <SideLink to={`/p/${slug}/overview`} label="Overview" />
              <SideLink to={`/p/${slug}/runs`} label="Runs" />
              <SideLink to={`/p/${slug}/flaky`} label="Flaky tests" />
              <SideLink to={`/p/${slug}/quarantine`} label="Quarantine" />
              <SideLink to={`/p/${slug}/compare`} label="Compare runs" />
              <SideLink to={`/p/${slug}/api-agent`} label="API test agent" />
              <SideLink to={`/p/${slug}/crew`} label="Maintenance crew" />
            </>
          )}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}
