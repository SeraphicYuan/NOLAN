// figures/Chart.tsx — Tier-2: real data charts, themed from --ra-* tokens.
//
// For actual numbers (trends / distributions / comparisons) where ProportionBar is
// too coarse. Wraps Recharts (SVG). Supply data + series; colors default from theme.
//
// IMPORTANT: import this DIRECTLY (`import { Chart } from "../figures/Chart"`), NOT
// from the figures barrel — keeps Recharts out of articles that don't chart anything.
import { useEffect, useRef, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { readPalette, type ThemePalette } from "./_theme";
import { figureText as tx, figureTokens as T } from "./primitives";

export type ChartSeries = { key: string; label?: string; color?: string };

export function Chart({
  type = "line",
  data,
  xKey,
  series,
  height = 280,
  stacked = false,
  caption,
}: {
  type?: "line" | "bar" | "area";
  data: Record<string, string | number>[];
  xKey: string;
  series: ChartSeries[];
  height?: number;
  stacked?: boolean;
  caption?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [p, setP] = useState<ThemePalette | null>(null);
  useEffect(() => {
    if (host.current) setP(readPalette(host.current));
  }, []);

  const axisColor = p?.muted ?? "#6b6860";
  const gridColor = p?.border ?? "#e3e1da";
  const fontBody = p?.fontBody ?? "system-ui, sans-serif";
  const color = (s: ChartSeries, i: number) => s.color ?? p?.series[i % (p?.series.length || 1)] ?? "#3257d6";
  const axisProps = { stroke: axisColor, tick: { fill: axisColor, fontSize: 12 }, tickLine: false } as const;
  const tooltipStyle = {
    background: p?.bg ?? "#fff",
    border: `1px solid ${p?.borderStrong ?? "#cfccc1"}`,
    borderRadius: 8,
    color: p?.text ?? "#222",
    fontSize: 13,
  };

  return (
    <figure ref={host} style={{ margin: 0, width: "100%", fontFamily: fontBody }}>
      <ResponsiveContainer width="100%" height={height}>
        {type === "bar" ? (
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={gridColor} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} />
            <YAxis {...axisProps} width={44} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: p?.accentSoft ?? "#eee", opacity: 0.5 }} />
            {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12, color: axisColor }} />}
            {series.map((s, i) => (
              <Bar key={s.key} dataKey={s.key} name={s.label ?? s.key} fill={color(s, i)} stackId={stacked ? "a" : undefined} radius={[3, 3, 0, 0]} isAnimationActive={false} />
            ))}
          </BarChart>
        ) : type === "area" ? (
          <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={gridColor} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} />
            <YAxis {...axisProps} width={44} />
            <Tooltip contentStyle={tooltipStyle} />
            {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12, color: axisColor }} />}
            {series.map((s, i) => (
              <Area key={s.key} type="monotone" dataKey={s.key} name={s.label ?? s.key} stroke={color(s, i)} fill={color(s, i)} fillOpacity={0.18} stackId={stacked ? "a" : undefined} isAnimationActive={false} />
            ))}
          </AreaChart>
        ) : (
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={gridColor} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} />
            <YAxis {...axisProps} width={44} />
            <Tooltip contentStyle={tooltipStyle} />
            {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12, color: axisColor }} />}
            {series.map((s, i) => (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.label ?? s.key} stroke={color(s, i)} strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
            ))}
          </LineChart>
        )}
      </ResponsiveContainer>
      {caption && (
        <figcaption style={{ marginTop: "var(--ra-space-2, .5rem)", fontSize: tx("xs"), color: T.faint, fontFamily: T.label }}>
          {caption}
        </figcaption>
      )}
    </figure>
  );
}
