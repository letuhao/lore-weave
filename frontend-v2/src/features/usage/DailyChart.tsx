import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { DailyBreakdown } from './types';

type Props = {
  data: DailyBreakdown[];
};

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function shortDay(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', { weekday: 'short' });
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

export function DailyChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="border-b px-4 py-3">
          <span className="text-sm font-semibold">Daily Token Usage</span>
        </div>
        <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">
          No data for this period
        </div>
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    label: shortDay(d.date),
    fullDate: formatDate(d.date),
  }));

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <span className="text-sm font-semibold">Daily Token Usage</span>
        <div className="flex gap-3 text-[10px]">
          <span className="flex items-center gap-1 text-muted-foreground">
            <span className="inline-block h-[3px] w-2 rounded-sm bg-green-500" />
            Input
          </span>
          <span className="flex items-center gap-1 text-muted-foreground">
            <span className="inline-block h-[3px] w-2 rounded-sm bg-primary" />
            Output
          </span>
        </div>
      </div>
      <div className="px-4 py-5" style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} barGap={0}>
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
              axisLine={false}
              tickLine={false}
              tickFormatter={formatTokens}
              width={45}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--card)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                fontSize: 11,
              }}
              labelFormatter={(_, payload) => payload[0]?.payload?.fullDate ?? ''}
              formatter={(value, name) => [formatTokens(Number(value ?? 0)), name === 'input_tokens' ? 'Input' : 'Output']}
            />
            <Bar dataKey="input_tokens" stackId="a" fill="#3dba6a" radius={[0, 0, 0, 0]} />
            <Bar dataKey="output_tokens" stackId="a" fill="var(--primary)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
