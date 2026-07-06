import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDuration } from "./status";

export interface TrendPoint {
  label: string;
  duration_ms: number;
  status: string;
}

export function TrendChart({ points }: { points: TrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={points} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
        <XAxis dataKey="label" stroke="#71717a" fontSize={11} tickLine={false} />
        <YAxis
          stroke="#71717a"
          fontSize={11}
          tickLine={false}
          tickFormatter={(value: number) => formatDuration(value)}
        />
        <Tooltip
          contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
          labelStyle={{ color: "#a1a1aa" }}
          formatter={(value) => [formatDuration(Number(value)), "duration"]}
        />
        <Line
          type="monotone"
          dataKey="duration_ms"
          stroke="#38bdf8"
          strokeWidth={2}
          dot={{ r: 2.5, fill: "#38bdf8" }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
