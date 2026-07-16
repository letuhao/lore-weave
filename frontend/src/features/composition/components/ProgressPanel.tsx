// LOOM Composition (T4.2) — writing-progress stats panel (server-SSOT).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useProgress, useSetDailyGoal } from '../hooks/useProgress';
import type { ProgressPoint } from '../types';

type Props = {
  bookId: string;
  projectId: string;
  token: string | null;
};

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border bg-card px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

export function ProgressPanel({ bookId, projectId, token }: Props) {
  const { t } = useTranslation('composition');
  const { data, isLoading, isError } = useProgress(projectId, token);
  const setGoal = useSetDailyGoal(bookId, token);
  const [window, setWindow] = useState<7 | 30>(7);
  const [goalDraft, setGoalDraft] = useState<string>('');

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">{t('progressPanel.loading')}</div>;
  if (isError || !data) return <div className="p-4 text-sm text-muted-foreground">{t('progressPanel.error')}</div>;

  const goal = data.daily_goal;
  const pct = goal ? Math.min(100, Math.round((data.today_words / goal) * 100)) : null;
  const series: ProgressPoint[] = data.sparkline.slice(-window);
  const chartData = series.map((p) => ({ ...p, label: p.date.slice(5) /* MM-DD */ }));

  const saveGoal = () => {
    const n = Math.max(0, Math.floor(Number(goalDraft) || 0));
    setGoal.mutate(
      { projectId, goal: n },
      { onSuccess: () => setGoalDraft('') },
    );
  };

  return (
    <div data-testid="progress-panel" className="flex flex-col gap-3 p-3">
      <div className="grid grid-cols-3 gap-2">
        <Stat
          label={t('progressPanel.today')}
          value={data.today_words.toLocaleString()}
          hint={goal ? t('progressPanel.ofGoal', { goal: goal.toLocaleString(), pct }) : t('progressPanel.noGoal')}
        />
        <Stat
          label={t('progressPanel.streak')}
          value={data.current_streak > 0 ? `🔥 ${data.current_streak}` : '—'}
          hint={t('progressPanel.streakDays', { count: data.current_streak })}
        />
        <Stat label={t('progressPanel.bookTotal')} value={data.book_total.toLocaleString()} />
      </div>

      {/* daily-goal progress bar (only when a goal is set) */}
      {goal != null && (
        <div className="rounded-lg border bg-card px-3 py-2">
          <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>{t('progressPanel.dailyGoal')}</span>
            <span className="tabular-nums">{data.today_words.toLocaleString()} / {goal.toLocaleString()}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              data-testid="progress-goal-bar"
              className={`h-full rounded-full ${pct! >= 100 ? 'bg-success' : 'bg-primary'}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* sparkline + 7/30 toggle */}
      <div className="rounded-lg border bg-card px-2 py-2">
        <div className="mb-1 flex items-center justify-between px-1">
          <span className="text-[11px] font-semibold text-muted-foreground">{t('progressPanel.sparkTitle')}</span>
          <div className="flex gap-1 text-[11px]">
            {([7, 30] as const).map((w) => (
              <button
                key={w}
                data-testid={`progress-window-${w}`}
                onClick={() => setWindow(w)}
                className={`rounded px-2 py-0.5 ${window === w ? 'bg-muted font-medium' : 'text-muted-foreground'}`}
              >
                {t('progressPanel.lastDays', { count: w })}
              </button>
            ))}
          </div>
        </div>
        <div style={{ height: 96 }}>
          <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
            <BarChart data={chartData} barGap={0}>
              <XAxis dataKey="label" tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              {/* hidden Y axis establishes the scale the goal ReferenceLine maps onto */}
              <YAxis hide domain={[0, (max: number) => Math.max(max, goal ?? 0)]} />
              {goal != null && <ReferenceLine y={goal} stroke="var(--primary)" strokeDasharray="3 3" />}
              <Tooltip
                contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 6, fontSize: 11, color: 'hsl(var(--foreground))' }}
                wrapperStyle={{ outline: 'none' }}
                cursor={{ fill: 'hsl(var(--muted) / 0.15)' }}
                formatter={(v) => [Number(v ?? 0).toLocaleString(), t('progressPanel.words')]}
              />
              <Bar dataKey="words" fill="var(--primary)" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* editable daily goal */}
      <div className="flex items-center gap-2">
        <input
          type="number"
          min={0}
          inputMode="numeric"
          data-testid="progress-goal-input"
          value={goalDraft}
          onChange={(e) => setGoalDraft(e.target.value)}
          placeholder={goal != null ? String(goal) : t('progressPanel.goalPlaceholder')}
          className="w-28 rounded border bg-background px-2 py-1 text-sm"
        />
        <button
          data-testid="progress-goal-save"
          onClick={saveGoal}
          disabled={setGoal.isPending || goalDraft === ''}
          className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground disabled:opacity-50"
        >
          {t('progressPanel.setGoal')}
        </button>
        {goal != null && (
          <span className="text-[11px] text-muted-foreground">{t('progressPanel.goalHint')}</span>
        )}
      </div>

      {/* SET-1 — show the effective goal's SOURCE tier. A legacy (shared-settings) goal is flagged so
          the user knows setting it now makes it their OWN per-user goal (BE-P2 tenancy fix). */}
      {data.daily_goal_source === 'work_legacy' && (
        <p data-testid="progress-goal-legacy" className="text-[11px] text-amber-600 dark:text-amber-400">
          {t('progressPanel.goalLegacy', { defaultValue: "This goal came from the book's shared settings — setting it makes it yours." })}
        </p>
      )}
    </div>
  );
}
