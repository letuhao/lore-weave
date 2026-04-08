import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Eye, EyeOff, RefreshCw } from 'lucide-react';
import type { EntityNameEntry } from '@/features/glossary/types';

type EntityWithCount = EntityNameEntry & { count: number };

type Props = {
  entities: EntityWithCount[];
  glossaryEnabled: boolean;
  onToggleEnabled: () => void;
  onRefresh: () => void;
  onEntityClick: (entity: EntityNameEntry) => void;
};

export function GlossaryPanel({ entities, glossaryEnabled, onToggleEnabled, onRefresh, onEntityClick }: Props) {
  const { t } = useTranslation('glossaryEditor');
  const [filter, setFilter] = useState('');

  // Group by kind
  const grouped = useMemo(() => {
    const q = filter.toLowerCase();
    const filtered = entities.filter((e) => !q || e.display_name.toLowerCase().includes(q));
    const groups = new Map<string, EntityWithCount[]>();
    for (const e of filtered) {
      const key = e.kind_code || 'other';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(e);
    }
    return groups;
  }, [entities, filter]);

  const totalCount = entities.reduce((sum, e) => sum + e.count, 0);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b">
        <div className="flex items-center gap-1.5">
          <span className="text-[13px] font-semibold">{t('entities')}</span>
          {totalCount > 0 && (
            <span className="text-[10px] px-1.5 py-px rounded-full bg-[var(--primary-muted)] text-[var(--primary)]">
              {totalCount}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          <button
            onClick={onToggleEnabled}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title={glossaryEnabled ? t('hideHighlights') : t('showHighlights')}
          >
            {glossaryEnabled ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={onRefresh}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title={t('refresh')}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="px-3.5 py-2 border-b">
        <div className="flex items-center gap-1.5 bg-secondary rounded px-2 py-1.5">
          <Search className="h-3 w-3 text-muted-foreground flex-shrink-0" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-transparent border-none outline-none text-[11px] text-foreground w-full"
            placeholder={t('filterEntities')}
          />
        </div>
      </div>

      {/* Entity list grouped by kind */}
      <div className="flex-1 overflow-y-auto">
        {entities.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">{t('noEntities')}</div>
        ) : (
          Array.from(grouped.entries()).map(([kindCode, items]) => {
            const first = items[0];
            return (
              <div key={kindCode}>
                <div
                  className="px-3.5 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1"
                  style={{ color: first.kind_color || 'var(--muted-foreground)' }}
                >
                  <span
                    className="h-2 w-2 rounded-full flex-shrink-0"
                    style={{ background: first.kind_color || 'var(--muted-foreground)' }}
                  />
                  {first.kind_name || kindCode} ({items.length})
                </div>
                <div className="px-2 pb-1">
                  {items.map((entity) => (
                    <div
                      key={entity.entity_id}
                      onClick={() => onEntityClick(entity)}
                      className="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-[var(--card-hover)] transition-colors"
                    >
                      <span className="text-xs flex-1 truncate">{entity.display_name}</span>
                      {entity.count > 0 && (
                        <span className="text-[9px] text-muted-foreground font-mono">
                          ×{entity.count}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
