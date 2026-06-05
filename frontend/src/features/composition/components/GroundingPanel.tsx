// LOOM Composition (M8) — grounding preview (view). Shows the packed context
// blocks + the C3a grounding_available signal + warnings.
import { useTranslation } from 'react-i18next';
import { useGrounding } from '../hooks/useWork';

const BLOCK_ORDER = ['canon', 'present', 'threads', 'beat', 'recent', 'memory', 'lore', 'guide'];

export function GroundingPanel({ projectId, sceneId, token }: { projectId: string; sceneId: string; token: string | null }) {
  const { t } = useTranslation('composition');
  const grounding = useGrounding(projectId, sceneId, '', token, !!sceneId);

  if (!sceneId) return <div className="p-3 text-sm text-neutral-500">{t('needScene', { defaultValue: 'Pick a scene' })}</div>;
  if (grounding.isLoading) return <div className="p-3 text-sm text-neutral-500">{t('loadingGrounding', { defaultValue: 'Loading grounding…' })}</div>;
  const g = grounding.data;
  if (!g) return <div className="p-3 text-sm text-neutral-500">{t('noGrounding', { defaultValue: 'No grounding.' })}</div>;

  return (
    <div className="flex flex-col gap-2 p-3 text-sm" data-testid="composition-grounding">
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2 w-2 rounded-full ${g.grounding_available ? 'bg-emerald-500' : 'bg-amber-500'}`} />
        <span
          data-testid="composition-grounding-signal"
          data-available={g.grounding_available}
          className="text-xs text-neutral-500"
        >
          {g.grounding_available
            ? t('grounded', { defaultValue: 'Grounded' })
            : t('groundingThin', { defaultValue: 'Grounding thin / unavailable' })}
          {` · ${g.token_count} ${t('tokens', { defaultValue: 'tokens' })}`}
        </span>
      </div>
      {/* When the project has no knowledge graph, the raw C3a warning is
          developer-ese — show the author an ACTIONABLE hint instead: run a
          knowledge extraction once to bootstrap canon, after which publishing
          auto-updates it. (The auto-drain reuses the project's extraction model,
          so a never-extracted project can't auto-ground — surface that, don't
          silently ship thin.) */}
      {!g.grounding_available && (
        <div
          data-testid="composition-grounding-empty-hint"
          className="rounded bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        >
          {t('groundingEmptyHint', {
            defaultValue:
              'No knowledge graph yet — run a knowledge extraction on this book once to ground the co-writer. After that, publishing chapters keeps the canon up to date automatically.',
          })}
        </div>
      )}
      {/* Remaining (non-C3a) warnings — over-budget, dropped L4, etc. */}
      {g.warnings.filter((w) => !w.startsWith('grounding_unavailable')).length > 0 && (
        <div
          data-testid="composition-grounding-warning"
          className="rounded bg-amber-50 p-1.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        >
          {g.warnings.filter((w) => !w.startsWith('grounding_unavailable')).join(' · ')}
        </div>
      )}
      {BLOCK_ORDER.filter((b) => g.blocks[b]).map((b) => (
        <details key={b} data-testid={`composition-grounding-block-${b}`} className="rounded border border-neutral-200 dark:border-neutral-700">
          <summary className="cursor-pointer px-2 py-1 text-xs font-medium uppercase tracking-wide text-neutral-500">{b}</summary>
          <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap px-2 py-1 text-xs text-neutral-700 dark:text-neutral-300">{g.blocks[b]}</pre>
        </details>
      ))}
    </div>
  );
}
