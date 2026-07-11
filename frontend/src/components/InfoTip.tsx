const GLOSSARY: Record<string, string> = {
  "flake score":
    "How often a test flip-flops between pass and fail without the code changing. Higher = less trustworthy. Above ~30% we flag it as flaky.",
  flaky:
    "A test that sometimes passes and sometimes fails on the same code — usually a timing or race issue, not a real bug.",
  quarantine:
    "Temporarily mark a flaky test so it keeps running but stops failing the build, while the fix agent works on it.",
  xfail:
    "'Expected to fail' — a quarantined test runs but its failure doesn't break CI. If it passes, that's a good sign it may be healed.",
  incident:
    "A group of test failures that share the same root cause. Fix the cause once instead of triaging each failure.",
  fingerprint:
    "A signature computed from the error type and stack trace, used to group failures that are really the same problem.",
  verdict:
    "A merge recommendation that ignores known-flaky failures and only blocks on genuinely new failures.",
};

export function InfoTip({ term, children }: { term: string; children?: React.ReactNode }) {
  const text = GLOSSARY[term.toLowerCase()] ?? "";
  return (
    <span className="group relative inline-flex items-center gap-1">
      {children ?? term}
      <span className="cursor-help select-none rounded-full border border-white/20 px-1 text-[10px] leading-none text-zinc-500">
        ?
      </span>
      <span className="pointer-events-none absolute bottom-full left-0 z-30 mb-1 hidden w-64 rounded-lg border border-white/10 bg-black/95 p-2 text-xs font-normal leading-5 text-zinc-300 shadow-xl group-hover:block">
        {text}
      </span>
    </span>
  );
}
