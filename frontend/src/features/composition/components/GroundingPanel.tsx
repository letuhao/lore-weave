// LOOM Composition (M8 + T3.4) — grounding preview (view). Shows the packed
// context + the C3a grounding_available signal + warnings. T3.4: the addressable
// items (present / canon / lore) render as per-line rows the author can PIN
// (force-keep) or EXCLUDE (drop); the non-addressable blocks stay opaque.
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useGrounding } from '../hooks/useWork';
import { useGroundingPins } from '../hooks/useGroundingPins';
import { useMentionHeatmap } from '../hooks/useMentionHeatmap';
import type { GroundingItem, GroundingItemType } from '../types';

const BLOCK_ORDER = ['canon', 'present', 'threads', 'beat', 'recent', 'memory', 'lore', 'guide'];
const ADDRESSABLE = ['present', 'canon', 'lore'];
// The grounding preview renders only these three item groups; 'reference' items
// (also addressable, T3.6) have their own ReferencesPanel, so they're not grouped here.
type GroundingGroup = 'present' | 'canon' | 'lore';
const ITEM_GROUPS: GroundingGroup[] = ['present', 'canon', 'lore'];
const GROUP_LABEL: Record<GroundingGroup, string> = {
  present: 'Cast in scene', canon: 'Canon rules', lore: 'Lore',
};

export function GroundingPanel({ projectId, bookId, chapterId, sceneId, token, heatmapEnabled, onToggleHeatmap }: {
  projectId: string; bookId: string; chapterId: string; sceneId: string; token: string | null;
  heatmapEnabled?: boolean; onToggleHeatmap?: () => void;
}) {
  const { t } = useTranslation('composition');
  const grounding = useGrounding(projectId, sceneId, '', token, !!sceneId);
  const pins = useGroundingPins(projectId, sceneId, token);
  // M7 — the cast-density bar list shares the chapter-windowed heatmap (same cache as
  // the editor's in-prose tint), keyed by bookId + the active scene's chapter.
  const heatmap = useMentionHeatmap(bookId, chapterId, token);

  if (!sceneId) return <div className="p-3 text-sm text-neutral-500">{t('needScene', { defaultValue: 'Pick a scene' })}</div>;
  if (grounding.isLoading) return <div className="p-3 text-sm text-neutral-500">{t('loadingGrounding', { defaultValue: 'Loading grounding…' })}</div>;
  const g = grounding.data;
  if (!g) return <div className="p-3 text-sm text-neutral-500">{t('noGrounding', { defaultValue: 'No grounding.' })}</div>;

  const items = g.grounding_items ?? [];
  const hasItems = items.length > 0;
  // When items are present, the addressable blocks render as rows (don't double up);
  // otherwise (legacy/derivative pack) fall back to showing every block opaque.
  const blockKeys = BLOCK_ORDER.filter((b) => g.blocks[b] && !(hasItems && ADDRESSABLE.includes(b)));
  const nonC3aWarnings = g.warnings.filter((w) => !w.startsWith('grounding_unavailable'));

  return (
    <div className="flex flex-col gap-2 p-3 text-sm" data-testid="composition-grounding">
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2 w-2 rounded-full ${g.grounding_available ? 'bg-emerald-500' : 'bg-amber-500'}`} />
        <span data-testid="composition-grounding-signal" data-available={g.grounding_available} className="text-xs text-neutral-500">
          {g.grounding_available ? t('grounded', { defaultValue: 'Grounded' }) : t('groundingThin', { defaultValue: 'Grounding thin / unavailable' })}
          {` · ${g.token_count} ${t('tokens', { defaultValue: 'tokens' })}`}
        </span>
      </div>
      {!g.grounding_available && (
        <div data-testid="composition-grounding-empty-hint" className="rounded bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          {t('groundingEmptyHint', { defaultValue: 'No knowledge graph yet — run a knowledge extraction on this book once to ground the co-writer. After that, publishing chapters keeps the canon up to date automatically.' })}
        </div>
      )}
      {nonC3aWarnings.length > 0 && (
        <div data-testid="composition-grounding-warning" className="rounded bg-amber-50 p-1.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">{nonC3aWarnings.join(' · ')}</div>
      )}

      {/* T5.2 — mention heatmap: top cast by mention frequency + an in-prose tint toggle. */}
      {(heatmap.data?.length ?? 0) > 0 && (
        <div data-testid="composition-heatmap">
          <div className="flex items-center justify-between px-1 py-0.5">
            <span className="text-xs font-medium uppercase tracking-wide text-neutral-500">
              {t('heatmap.title', { defaultValue: 'Mention heatmap' })}
            </span>
            {onToggleHeatmap && (
              <button
                type="button" data-testid="heatmap-prose-toggle" aria-pressed={!!heatmapEnabled}
                onClick={onToggleHeatmap}
                className={`rounded px-2 py-0.5 text-[11px] ${heatmapEnabled ? 'bg-primary text-primary-foreground' : 'text-neutral-500 hover:text-neutral-700'}`}
              >
                {t('heatmap.inProse', { defaultValue: 'In prose' })}
              </button>
            )}
          </div>
          <ul className="flex flex-col gap-0.5">
            {heatmap.data!.map((h) => {
              const max = heatmap.data![0]?.mention_count || 1;
              const pct = Math.max(4, Math.round((h.mention_count / max) * 100));
              return (
                <li key={h.id} data-testid={`heatmap-row-${h.id}`} className="flex items-center gap-2 px-1 text-xs">
                  <span className="w-24 shrink-0 truncate" title={h.name}>{h.name}</span>
                  <span className="h-2 flex-1 overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
                    <span className={`block h-full rounded-full heat-band-${h.band}`} style={{ width: `${pct}%` }} />
                  </span>
                  <span className="w-8 shrink-0 text-right tabular-nums text-neutral-500">{h.mention_count}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* T3.4 — addressable items, grouped by type, each pin/exclude-able. */}
      {hasItems && ITEM_GROUPS.map((type) => {
        const rows = items.filter((it) => it.type === type);
        if (!rows.length) return null;
        return (
          <div key={type} data-testid={`grounding-items-${type}`}>
            <div className="px-1 py-0.5 text-xs font-medium uppercase tracking-wide text-neutral-500">
              {t(`groundingPins.${type}`, { defaultValue: GROUP_LABEL[type] })}
            </div>
            <ul className="flex flex-col gap-0.5">
              {rows.map((it) => <GroundingItemRow key={`${it.type}-${it.id}`} item={it} t={t} onAction={pins.setAction} />)}
            </ul>
          </div>
        );
      })}

      {blockKeys.map((b) => (
        <details key={b} data-testid={`composition-grounding-block-${b}`} className="rounded border border-neutral-200 dark:border-neutral-700">
          <summary className="cursor-pointer px-2 py-1 text-xs font-medium uppercase tracking-wide text-neutral-500">{b}</summary>
          <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap px-2 py-1 text-xs text-neutral-700 dark:text-neutral-300">{g.blocks[b]}</pre>
        </details>
      ))}
    </div>
  );
}

function GroundingItemRow({ item, t, onAction }: {
  item: GroundingItem;
  t: TFunction;
  onAction: (item: GroundingItem, action: 'pin' | 'exclude' | 'none') => void;
}) {
  return (
    <li
      data-testid={`grounding-item-${item.type}-${item.id}`}
      className={`flex items-center justify-between gap-2 rounded border px-2 py-1 text-xs ${item.excluded ? 'border-neutral-100 opacity-50 dark:border-neutral-800' : 'border-neutral-200 dark:border-neutral-700'}`}
    >
      <span className={`truncate ${item.excluded ? 'line-through' : ''}`}>{item.label}</span>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button" data-testid={`grounding-pin-${item.id}`} aria-pressed={item.pinned}
          className={item.pinned ? 'text-primary' : 'text-neutral-400 hover:text-neutral-600'}
          title={item.pinned ? t('groundingPins.unpin', { defaultValue: 'Unpin' }) : t('groundingPins.pin', { defaultValue: 'Pin — always keep this' })}
          onClick={() => onAction(item, item.pinned ? 'none' : 'pin')}
        >📌</button>
        <button
          type="button" data-testid={`grounding-exclude-${item.id}`} aria-pressed={item.excluded}
          className={item.excluded ? 'text-destructive' : 'text-neutral-400 hover:text-neutral-600'}
          title={item.excluded ? t('groundingPins.restore', { defaultValue: 'Restore' }) : t('groundingPins.exclude', { defaultValue: 'Exclude — drop from grounding' })}
          onClick={() => onAction(item, item.excluded ? 'none' : 'exclude')}
        >🚫</button>
      </div>
    </li>
  );
}
