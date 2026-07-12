import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useProjects } from "../api/hooks";
import { NewProject } from "../components/NewProject";
import { Sparkline } from "../components/Sparkline";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate } from "../components/status";

const CAPABILITIES = [
  {
    icon: "🩹",
    title: "SelfHeal",
    body: "Diagnoses a failing test and opens a pull request that fixes it — verified green before you ever look.",
  },
  {
    icon: "✍️",
    title: "Write a test in English",
    body: "Describe what to check. The agent drives your real app, writes the Playwright test, and proves it passes.",
  },
  {
    icon: "🔬",
    title: "Reproducer",
    body: "Deterministically reproduces a flake under controlled network, timing and CPU chaos — no more “can’t repro”.",
  },
  {
    icon: "🛡️",
    title: "Quarantine & heal",
    body: "Chronic flakes get quarantined so CI stays green, then healed in the background. A merge verdict ignores the noise.",
  },
];

function PipInstall() {
  const cmd = "pip install pytest-flakelens";
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard?.writeText(cmd).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1400);
          },
          () => {},
        );
      }}
      className="group inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3.5 py-2 font-mono text-sm text-zinc-300 transition hover:border-blue-400/40 hover:text-white"
      title="Copy to clipboard"
    >
      <span className="text-zinc-500 group-hover:text-blue-300">$</span>
      {cmd}
      <span className="ml-1 text-xs text-zinc-500">{copied ? "copied ✓" : "copy"}</span>
    </button>
  );
}

type Health = {
  grade: string;
  score: number;
  pass_rate: number | null;
  flaky: number;
  incidents?: number;
};

function StatChips({ slug }: { slug: string }) {
  const { data } = useQuery({
    queryKey: ["health", slug],
    queryFn: async (): Promise<Health> => {
      const r = await fetch(`/api/v1/projects/${slug}/health`);
      if (!r.ok) throw new Error("health unavailable");
      const body = await r.json();
      return body.health; // endpoint returns { health, actions }
    },
    staleTime: 60_000,
    retry: false,
  });
  if (!data || data.grade === "—") return null;
  const chips = [
    { label: "health grade", value: data.grade },
    ...(data.pass_rate != null
      ? [{ label: "pass rate", value: `${Math.round(data.pass_rate * 100)}%` }]
      : []),
    { label: "flaky caught", value: String(data.flaky) },
    ...(data.incidents != null
      ? [{ label: "incidents clustered", value: String(data.incidents) }]
      : []),
  ];
  return (
    <div className="mt-6 flex flex-wrap items-center gap-2">
      {chips.map((c) => (
        <span
          key={c.label}
          className="inline-flex items-baseline gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-zinc-400"
        >
          <span className="font-semibold text-zinc-100">{c.value}</span>
          {c.label}
        </span>
      ))}
      <span className="text-xs text-zinc-600">· live from the demo project</span>
    </div>
  );
}

function Hero({ demoSlug }: { demoSlug?: string }) {
  return (
    <section className="card relative overflow-hidden p-8 sm:p-10">
      {/* soft accent glow inside the panel */}
      <div
        className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full opacity-40 blur-3xl"
        style={{ background: "radial-gradient(circle, rgba(77,118,255,0.5), transparent 60%)" }}
      />
      <div className="relative grid items-center gap-10 xl:grid-cols-[1.1fr_1fr]">
        <div className="max-w-2xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-zinc-300">
            <span className="glow-dot" /> Self-hosted · open source · AI-native
          </span>
          <h1
            className="mt-5 text-4xl font-extrabold leading-[1.1] tracking-tight sm:text-5xl"
            style={{ fontFamily: "Plus Jakarta Sans" }}
          >
            <span className="text-zinc-100">Every tool tells you a test is flaky.</span>
            <br />
            <span className="grad-text">FlakeLens fixes it.</span>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-zinc-400">
            Test observability with AI agents that <span className="text-zinc-200">write new tests from
            plain English</span> and <span className="text-zinc-200">fix flaky ones with a pull request</span>.
            Ingests Playwright, pytest, or JUnit from any framework — then closes the loop:
            reproduce → self-heal → quarantine → verify.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            {demoSlug && (
              <Link to={`/p/${demoSlug}/overview`} className="btn-grad inline-flex items-center gap-2">
                Explore the demo project
                <span aria-hidden>→</span>
              </Link>
            )}
            <PipInstall />
            <a
              href="https://github.com/brahmendra27/testwarden"
              target="_blank"
              rel="noreferrer"
              className="text-sm text-zinc-400 underline-offset-4 hover:text-zinc-200 hover:underline"
            >
              View on GitHub
            </a>
          </div>
          {demoSlug && <StatChips slug={demoSlug} />}
        </div>
        <div className="hidden xl:block">
          <div className="overflow-hidden rounded-xl border border-white/10 shadow-[0_0_40px_rgba(61,106,254,0.15)]">
            <img
              src="/flakelens-demo.gif"
              alt="FlakeLens dashboard walkthrough"
              className="block w-full"
              loading="lazy"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function Capabilities() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {CAPABILITIES.map((c) => (
        <div key={c.title} className="card card-hover p-5">
          <div className="mb-2.5 text-2xl">{c.icon}</div>
          <div className="mb-1.5 font-semibold text-zinc-100" style={{ fontFamily: "Plus Jakarta Sans" }}>
            {c.title}
          </div>
          <p className="text-sm leading-relaxed text-zinc-400">{c.body}</p>
        </div>
      ))}
    </div>
  );
}

export function ProjectsPage() {
  const { data: projects, isLoading, error } = useProjects();

  // Projects with runs are the interesting ones — lead with them, and point the
  // demo CTA at the richest one so "Explore" never lands on an empty overview.
  const ordered = projects
    ? [...projects].sort((a, b) => Number(!!b.last_run) - Number(!!a.last_run))
    : projects;
  const demoSlug = ordered?.find((p) => p.last_run)?.slug ?? ordered?.[0]?.slug;

  return (
    <div className="mx-auto max-w-6xl space-y-10">
      <Hero demoSlug={demoSlug} />

      <div>
        <h2
          className="mb-4 text-xs font-semibold uppercase tracking-widest text-zinc-500"
          style={{ fontFamily: "Plus Jakarta Sans" }}
        >
          What makes it different
        </h2>
        <Capabilities />
      </div>

      <div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <h2 className="grad-text text-2xl font-bold">Your projects</h2>
          <NewProject />
        </div>

        {isLoading && <p className="text-zinc-500">Loading projects…</p>}
        {error && <p className="text-red-400">Failed to load projects: {String(error)}</p>}

        {!isLoading && !error && !projects?.length && (
          <div className="card p-8 text-center text-zinc-500">
            <p className="text-lg text-zinc-300">No projects yet.</p>
            <p className="mt-2 text-sm">
              Seed demo data with{" "}
              <code className="rounded bg-white/10 px-1.5 py-0.5">python -m flakelens.seed</code> or point
              the pytest reporter at this server to see your first run appear.
            </p>
          </div>
        )}

        {!!ordered?.length && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {ordered.map((project) => {
              const lastRun = project.last_run;
              const passRate =
                lastRun && lastRun.total ? Math.round((lastRun.passed / lastRun.total) * 100) : null;
              return (
                <Link key={project.id} to={`/p/${project.slug}/overview`} className="card card-hover p-5">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-lg font-medium text-zinc-100">{project.name}</span>
                    {lastRun && (
                      <StatusBadge
                        status={lastRun.failed + lastRun.error_count > 0 ? "failed" : "passed"}
                      />
                    )}
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
        )}
      </div>
    </div>
  );
}
