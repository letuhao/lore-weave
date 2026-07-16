// LOOM Composition (T2.1) — Cast & Codex: the book's cast (characters / places /
// factions) as a docked codex, grouped by kind, searchable, each row showing its
// spoiler-safe current story-state. Reads the knowledge graph via the gateway
// (reuses features/knowledge). Render-only; logic in useCast.
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Entity, EntityStatusEntry } from '../../knowledge/api';
import { useCast, useKnowledgeProjectId, type CastRow } from '../hooks/useCast';
import { CastEntityRow } from './CastEntityRow';

// s7-4 — group order mirrors the authorable kind set (organization is the
// canonical group kind; the legacy `faction` misnomer is retired). Unknown
// kinds (event_ref/preference/extraction-emitted) sort after, then alpha.
const KIND_ORDER = ['character', 'location', 'organization', 'concept', 'item'];

// Pure (exported for tests): join entities↔status, then group by kind in a stable
// order (known kinds first, then alpha), rows alpha within a group.
export function groupCast(
  entities: Entity[],
  statuses: Record<string, EntityStatusEntry>,
): { kind: string; rows: CastRow[] }[] {
  const byKind = new Map<string, CastRow[]>();
  for (const e of entities) {
    const row: CastRow = { ...e, state: statuses[e.id] };
    const arr = byKind.get(e.kind);
    if (arr) arr.push(row); else byKind.set(e.kind, [row]);
  }
  const rank = (k: string) => { const i = KIND_ORDER.indexOf(k); return i < 0 ? KIND_ORDER.length : i; };
  return [...byKind.keys()]
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .map((kind) => ({ kind, rows: byKind.get(kind)!.sort((a, b) => a.name.localeCompare(b.name)) }));
}

export function CastCodexPanel({
  bookId, chapterId, token, onViewArc, search: searchProp, onSearchChange,
  onRename, onEdit, onArchive, onNewEntity,
}: {
  bookId: string;
  chapterId: string;
  token: string | null;
  /** T2.4: launch the Character Arc tab for this entity (set by CompositionPanel). */
  onViewArc?: (entityId: string) => void;
  /** T2.5: optionally control the search from the parent (World Map click → prefill
   *  this place's name). Omitted → the panel keeps its own internal search state. */
  search?: string;
  onSearchChange?: (v: string) => void;
  // s7-4 — ADDITIVE edit affordances (forwarded to each row) + a "+ New" toolbar
  // button. Omitted by the legacy mount → read-only codex, exactly as before.
  onRename?: (args: { entityId: string; name: string; version: number }) => void;
  onEdit?: (row: CastRow) => void;
  onArchive?: (row: CastRow) => void;
  onNewEntity?: () => void;
}) {
  const { t } = useTranslation('composition');
  const projectQ = useKnowledgeProjectId(bookId, token);
  const projectId = projectQ.data;
  const [localSearch, setLocalSearch] = useState('');
  const search = searchProp ?? localSearch;
  const setSearch = onSearchChange ?? setLocalSearch;
  const { entities, statuses } = useCast(projectId, token, { search, beforeChapterId: chapterId });

  const groups = useMemo(
    () => groupCast(entities.data ?? [], statuses.data?.statuses ?? {}),
    [entities.data, statuses.data],
  );
  const windowUnknown = statuses.data?.window_available === false;

  return (
    <div className="flex h-full flex-col" data-testid="composition-cast">
      <div className="flex flex-shrink-0 items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="text-muted-foreground">{t('codex.title', { defaultValue: 'Cast & Codex' })}</span>
        <input
          data-testid="cast-search"
          aria-label={t('codex.search', { defaultValue: 'Search cast' })}
          placeholder={t('codex.search', { defaultValue: 'Search…' })}
          className="ml-auto w-32 rounded border bg-background px-1.5 py-0.5"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {onNewEntity && (
          <button
            type="button"
            data-testid="cast-new-entity"
            className="shrink-0 rounded border px-1.5 py-0.5 text-[11px] hover:bg-accent/50"
            onClick={onNewEntity}
          >
            + {t('codex.newEntity', { defaultValue: 'New' })}
          </button>
        )}
      </div>

      {windowUnknown && (
        <div data-testid="cast-window-hint" className="border-b bg-amber-50 px-3 py-1 text-[10px] text-amber-700 dark:bg-amber-950/40 dark:text-amber-400">
          {t('codex.windowUnknown', { defaultValue: 'Reading position unknown — state may be incomplete.' })}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {projectQ.isLoading || entities.isLoading ? (
          <Hint>{t('codex.loading', { defaultValue: 'Loading cast…' })}</Hint>
        ) : !projectId ? (
          <Hint>{t('codex.noProject', { defaultValue: 'No knowledge graph yet — extract this book to populate the codex.' })}</Hint>
        ) : groups.length === 0 ? (
          <Hint>
            {search.trim().length >= 2
              ? t('codex.noMatch', { defaultValue: 'No cast members match your search.' })
              : t('codex.empty', { defaultValue: 'No extracted entities yet — publish/extract to populate the codex.' })}
          </Hint>
        ) : (
          <div className="flex flex-col gap-3">
            {groups.map((g) => (
              <div key={g.kind}>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {t(`codex.kind_${g.kind}`, { defaultValue: g.kind })} ({g.rows.length})
                </div>
                <div className="flex flex-col gap-1">
                  {g.rows.map((row) => (
                    <CastEntityRow
                      key={row.id}
                      row={row}
                      bookId={bookId}
                      chapterId={chapterId}
                      token={token}
                      onViewArc={onViewArc}
                      onRename={onRename}
                      onEdit={onEdit}
                      onArchive={onArchive}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const Hint = ({ children }: { children: React.ReactNode }) => (
  <div className="p-2 text-xs text-muted-foreground">{children}</div>
);
