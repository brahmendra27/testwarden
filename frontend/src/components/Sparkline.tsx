/** Tiny pass-rate sparkline used on project cards. */
export function Sparkline({ values }: { values: (number | null)[] }) {
  const points = values.filter((value): value is number => value != null);
  if (points.length < 2) return <div className="h-8" />;
  const width = 160;
  const height = 32;
  const step = width / (points.length - 1);
  const path = points
    .map((value, index) => `${index === 0 ? "M" : "L"}${index * step},${height - value * (height - 4) - 2}`)
    .join(" ");
  const last = points[points.length - 1];
  return (
    <svg width={width} height={height} className="block">
      <path d={path} fill="none" stroke={last >= 0.98 ? "#10b981" : last >= 0.9 ? "#f59e0b" : "#ef4444"} strokeWidth={2} />
    </svg>
  );
}
