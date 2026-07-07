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
        <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
        <XAxis dataKey="label" stroke="#71717a" fontSize={11} tickLine={false} />
        <YAxis
          stroke="#71717a"
          fontSize={11}
          tickLine={false}
          tickFormatter={(value: number) => formatDuration(value)}
        />
        <Tooltip
          contentStyle={{ background: "#0a0a0a", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 8 }}
          labelStyle={{ color: "#a1a1aa" }}
          formatter={(value) => [formatDuration(Number(value)), "duration"]}
        />
        <Line
          type="monotone"
          dataKey="duration_ms"
          stroke="#4d76ff"
          strokeWidth={2}
          dot={{ r: 2.5, fill: "#4d76ff" }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
