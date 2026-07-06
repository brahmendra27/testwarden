import { useNavigate } from "react-router-dom";
import type { StripEntry } from "../api/types";
import { TOKEN_COLORS, TOKEN_LABELS } from "./status";

/** One colored segment per test in execution order — the signature visualization. */
export function RunStrip({
  entries,
  slug,
  height = 14,
}: {
  entries: StripEntry[];
  slug: string;
  height?: number;
}) {
  const navigate = useNavigate();
  if (!entries.length) return <div className="h-3 rounded bg-zinc-800" />;
  return (
    <svg
      width="100%"
      height={height}
      preserveAspectRatio="none"
      viewBox={`0 0 ${entries.length} 10`}
      className="block rounded"
    >
      {entries.map(([caseId, token, nodeId], index) => (
        <rect
          key={index}
          x={index}
          y={0}
          width={1}
          height={10}
          fill={TOKEN_COLORS[token] ?? "#52525b"}
          className="cursor-pointer hover:opacity-70"
          onClick={(event) => {
            event.stopPropagation();
            navigate(`/p/${slug}/tests/${caseId}`);
          }}
        >
          <title>{`${nodeId} — ${TOKEN_LABELS[token] ?? token}`}</title>
        </rect>
      ))}
    </svg>
  );
}
