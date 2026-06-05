// LOOM Composition (V1 slice 5) — the eval-gate dashboard (view).
//
// Shows the per-mode correction rates that REPLACE the saturating auto-judge as
// the quality signal (spec §6). Within one Work the author is fixed, so the
// auto-vs-cowrite columns are a within-author A/B: lower edit/regenerate/reject
// + higher accept in `auto` = the diverge→converge reranker earns its latency.
// Cold-start safe: rates show "—" until generations accumulate.
import { useTranslation } from 'react-i18next';
import { useCorrectionStats } from '../hooks/useCorrectionStats';
import type { ModeCorrectionStats } from '../types';

const pct = (r: number | null) => (r == null ? '—' : `${Math.round(r * 100)}%`);
const num = (r: number | null) => (r == null ? '—' : r.toFixed(1));

export function QualityPanel({ projectId, token }: { projectId: string; token: string | null }) {
  const { t } = useTranslation('composition');
  const stats = useCorrectionStats(projectId, token);

  if (stats.isLoading) return <Hint>{t('loadingStats', { defaultValue: 'Loading quality…' })}</Hint>;
  if (stats.isError || !stats.data) return <Hint>{t('statsUnavailable', { defaultValue: 'Quality stats unavailable.' })}</Hint>;

  const byMode = stats.data.by_mode;
  const auto = byMode.find((m) => m.mode === 'auto');
  const cowrite = byMode.find((m) => m.mode === 'cowrite');
  const cols: (ModeCorrectionStats | undefined)[] = [auto, cowrite];
  const totalGens = byMode.reduce((s, m) => s + m.generations, 0);

  // metric rows: [label, accessor, goodDirection]
  const rows: [string, (m: ModeCorrectionStats) => string, string][] = [
    [t('statGenerations', { defaultValue: 'Generations' }), (m) => String(m.generations), ''],
    [t('statAcceptRate', { defaultValue: 'Accept as-is' }), (m) => pct(m.accept_rate), '↑'],
    [t('statEditRate', { defaultValue: 'Edited' }), (m) => pct(m.edit_rate), '↓'],
    [t('statPickRate', { defaultValue: 'Picked other' }), (m) => pct(m.pick_different_rate), '↓'],
    [t('statRegenRate', { defaultValue: 'Regenerated' }), (m) => pct(m.regenerate_rate), '↓'],
    [t('statRejectRate', { defaultValue: 'Rejected' }), (m) => pct(m.reject_rate), '↓'],
    [t('statEditSize', { defaultValue: 'Avg edit (blocks)' }), (m) => num(m.avg_edit_magnitude), '↓'],
  ];

  return (
    <div data-testid="composition-quality" className="flex flex-col gap-2 p-3 text-sm">
      <p className="text-xs text-neutral-500">
        {t('statsIntro', { defaultValue: 'Your corrections are the quality signal. Lower edit/regenerate/reject (and higher accept) in Diverge means the K-option reranker is earning its time.' })}
      </p>
      {totalGens === 0 ? (
        <div data-testid="composition-quality-coldstart" className="rounded bg-neutral-50 p-2 text-xs text-neutral-500 dark:bg-neutral-800/50">
          {t('statsColdStart', { defaultValue: 'No generations yet — compose a few scenes and your accept/edit/regenerate rates will appear here.' })}
        </div>
      ) : (
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="text-neutral-500">
              <th className="py-1 text-left font-medium" />
              <th className="py-1 text-right font-medium">{t('statDiverge', { defaultValue: 'Diverge (K)' })}</th>
              <th className="py-1 text-right font-medium">{t('statStream', { defaultValue: 'Stream' })}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, get, dir]) => (
              <tr key={label} className="border-t border-neutral-100 dark:border-neutral-800">
                <td className="py-1 text-left text-neutral-600 dark:text-neutral-300">
                  {label}{dir && <span className="ml-1 text-[10px] text-neutral-400">{dir}</span>}
                </td>
                {cols.map((m, i) => (
                  <td key={i} className="py-1 text-right tabular-nums" data-testid={`stat-${m?.mode}`}>
                    {m ? get(m) : '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <div className="p-4 text-sm text-neutral-500">{children}</div>;
}
