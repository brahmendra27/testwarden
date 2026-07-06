import { NavLink, Outlet, useParams } from "react-router-dom";

function SideLink({ to, label, end }: { to: string; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `block rounded-md px-3 py-2 text-sm ${
          isActive ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
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
      <aside className="w-56 shrink-0 border-r border-zinc-800 p-4">
        <div className="mb-6 flex items-center gap-2 px-2">
          <span className="text-xl">🛡️</span>
          <span className="text-lg font-semibold tracking-tight text-zinc-100">TestWarden</span>
        </div>
        <nav className="space-y-1">
          <SideLink to="/" label="Projects" end />
          {slug && (
            <>
              <div className="mt-4 px-3 pb-1 text-xs font-medium uppercase tracking-wide text-zinc-600">
                {slug}
              </div>
              <SideLink to={`/p/${slug}/runs`} label="Runs" />
              <SideLink to={`/p/${slug}/flaky`} label="Flaky tests" />
              <SideLink to={`/p/${slug}/compare`} label="Compare runs" />
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
