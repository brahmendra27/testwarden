import { Link } from "react-router-dom";
import { TOKEN_COLORS, TOKEN_LABELS } from "./status";

export interface SquareEntry {
  token: string;
  label: string;
  href?: string;
}

/** Row of small squares, oldest → newest (per-test history). */
export function HistorySquares({ entries, size = 14 }: { entries: SquareEntry[]; size?: number }) {
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map((entry, index) => {
        const square = (
          <span
            key={index}
            title={`${entry.label} — ${TOKEN_LABELS[entry.token] ?? entry.token}`}
            className="inline-block rounded-sm hover:ring-2 hover:ring-zinc-400"
            style={{
              width: size,
              height: size,
              backgroundColor: TOKEN_COLORS[entry.token] ?? "#52525b",
            }}
          />
        );
        return entry.href ? (
          <Link key={index} to={entry.href}>
            {square}
          </Link>
        ) : (
          square
        );
      })}
    </div>
  );
}
