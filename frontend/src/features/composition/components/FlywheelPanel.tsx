// LOOM Composition (T4.1) — the canon-growth flywheel (render + light glue).
// After a publish→extraction completes, shows "+N entities/relations/events" the
// run ADDED to canon, with named highlights. Each stat deep-links to its view
// (Cast/Timeline/Relations) and each entity chip focuses that entity in Cast.
// Advisory: a neutral empty state until the first extraction completes.
import { useTranslation } from 'react-i18next';
import { useFlywheel } from '../hooks/useFlywheel';
import type { FlywheelItemWire } from '@/features/knowledge/api';

type Props = {
  projectId: string | undefined;
  token: string | null;
  /** focus an entity by name in the Cast tab (in-page deep-link) */
  onOpenCast: (name?: string) => void;
  onOpenTimeline: () => void;
  onOpenRelations: () => void;
};

const KIND_OPEN: Record<FlywheelItemWire['kind'], 'cast' | 'timeline' | 'relations'> = {
  entity: 'cast',
  event: 'timeline',
  relation: 'relations',
};

export function FlywheelPanel({ projectId, token, onOpenCast, onOpenTimeline, onOpenRelations }: Props) {
  const { t } = useTranslation('composition');
  const { data, isLoading, isError } = useFlywheel(projectId, token);

  if (isLoading) {
    return <div data-testid="flywheel-loading" className="p-3 text-xs text-neutral-500">{t('flywheelPanel.loading', { defaultValue: 'Loading…' })}</div>;
  }
  const total = data ? data.entities_added + data.relations_added + data.events_added : 0;
  if (isError || !data || !data.has_delta || total === 0) {
    return (
      <div data-testid="flywheel-empty" className="p-3 text-xs text-neutral-500">
        {t('flywheelPanel.empty', { defaultValue: 'Publish a chapter to grow your canon — new entities, relations and events will show up here.' })}
      </div>
    );
  }

  const openFor = (item: FlywheelItemWire) => {
    const target = KIND_OPEN[item.kind];
    if (target === 'cast') onOpenCast(item.name);
    else if (target === 'timeline') onOpenTimeline();
    else onOpenRelations();
  };

  const Stat = ({ n, label, onClick, testid }: { n: number; label: string; onClick: () => void; testid: string }) => (
    <button
      type="button"
      data-testid={testid}
      onClick={onClick}
      disabled={n === 0}
      className="flex flex-1 flex-col items-center rounded-md border border-emerald-300/40 bg-emerald-50/40 px-2 py-1.5 hover:bg-emerald-100/60 disabled:opacity-40 dark:border-emerald-400/20 dark:bg-emerald-400/5"
    >
      <span className="text-lg font-semibold text-emerald-700 dark:text-emerald-300">+{n}</span>
      <span className="text-[11px] text-neutral-600 dark:text-neutral-400">{label}</span>
    </button>
  );

  return (
    <div data-testid="flywheel-panel" className="space-y-3 p-3">
      <p className="text-xs text-neutral-500">{t('flywheelPanel.subtitle', { defaultValue: 'Your latest publish grew the canon:' })}</p>
      <div className="flex gap-2">
        <Stat testid="flywheel-stat-entities" n={data.entities_added} label={t('flywheelPanel.entities', { defaultValue: 'entities' })} onClick={() => onOpenCast()} />
        <Stat testid="flywheel-stat-relations" n={data.relations_added} label={t('flywheelPanel.relations', { defaultValue: 'relations' })} onClick={onOpenRelations} />
        <Stat testid="flywheel-stat-events" n={data.events_added} label={t('flywheelPanel.events', { defaultValue: 'events' })} onClick={onOpenTimeline} />
      </div>
      {data.new_items.length > 0 && (
        <div>
          <p className="mb-1 text-[11px] font-medium text-neutral-500">{t('flywheelPanel.highlights', { defaultValue: 'New highlights' })}</p>
          <div className="flex flex-wrap gap-1.5">
            {data.new_items.map((item) => (
              <button
                key={`${item.kind}-${item.id}`}
                type="button"
                data-testid={`flywheel-chip-${item.id}`}
                onClick={() => openFor(item)}
                title={t(`flywheelPanel.kind.${item.kind}`, { defaultValue: item.kind })}
                className="max-w-full truncate rounded-full border bg-white px-2 py-0.5 text-[11px] hover:bg-neutral-100 dark:bg-neutral-900 dark:hover:bg-neutral-800"
              >
                {item.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
