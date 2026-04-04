import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Plus, Search, Filter, Trash2, Settings2, Layers } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { type GlossaryEntitySummary, type EntityKind, type FilterState, defaultFilters } from '@/features/glossary/types';
import { Skeleton } from '@/components/shared/Skeleton';
import { EmptyState, ConfirmDialog } from '@/components/shared';
import { cn } from '@/lib/utils';
import { KindEditor } from './KindEditor';
import { GenreGroupsPanel } from '@/features/glossary/components/GenreGroupsPanel';
import { EntityEditorModal } from '@/components/entity-editor';

type GlossaryView = 'entities' | 'kinds' | 'genres';

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-amber-400/15 text-amber-400',
  active: 'bg-green-500/15 text-green-500',
  inactive: 'bg-muted text-muted-foreground',
};

function KindBadge({ kind }: { kind: GlossaryEntitySummary['kind'] }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
      style={{ backgroundColor: kind.color + '18', color: kind.color }}
    >
      <span>{kind.icon}</span>
      {kind.name}
    </span>
  );
}

export function GlossaryTab({ bookId }: { bookId: string }) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [filterOpen, setFilterOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<GlossaryEntitySummary | null>(null);
  const [createKindOpen, setCreateKindOpen] = useState(false);
  const [view, setView] = useState<GlossaryView>('entities');
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  const { data: entityData, isLoading: entitiesLoading, error: entitiesError } = useQuery({
    queryKey: ['glossary-entities', bookId, filters],
    queryFn: () => glossaryApi.listEntities(bookId, { ...filters, limit: 100, offset: 0 }, accessToken!),
    enabled: !!accessToken,
  });

  const { data: kinds = [] } = useQuery({
    queryKey: ['glossary-kinds'],
    queryFn: () => glossaryApi.getKinds(accessToken!),
    enabled: !!accessToken,
    staleTime: 10 * 60 * 1000, // kinds rarely change
  });

  const entities = entityData?.items ?? [];
  const total = entityData?.total ?? 0;
  const loading = entitiesLoading;
  const error = entitiesError ? (entitiesError as Error).message : '';

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['glossary-entities', bookId] });

  const visibleKinds = useMemo(
    () => kinds.filter((k) => !k.is_hidden).sort((a, b) => a.sort_order - b.sort_order),
    [kinds],
  );

  const handleCreate = async (kindId: string) => {
    if (!accessToken) return;
    try {
      await glossaryApi.createEntity(bookId, kindId, accessToken);
      toast.success('Entity created');
      setCreateKindOpen(false);
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleDelete = async () => {
    if (!accessToken || !deleteTarget) return;
    try {
      await glossaryApi.deleteEntity(bookId, deleteTarget.entity_id, accessToken);
      toast.success('Entity deleted');
      setDeleteTarget(null);
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const activeFilterCount = (filters.kindCodes.length > 0 ? 1 : 0) + (filters.status !== 'all' ? 1 : 0);

  if (view === 'kinds') {
    return <KindEditor onClose={() => setView('entities')} />;
  }
  if (view === 'genres') {
    return <GenreGroupsPanel bookId={bookId} kinds={kinds} onClose={() => setView('entities')} />;
  }

  if (loading && entities.length === 0) {
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return <div className="p-6 text-sm text-destructive">{error}</div>;
  }

  return (
    <div className="space-y-4 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Glossary & Lore</h3>
          <p className="text-xs text-muted-foreground">
            {total} entit{total !== 1 ? 'ies' : 'y'}
            {visibleKinds.length > 0 && ` · ${visibleKinds.length} kind${visibleKinds.length !== 1 ? 's' : ''}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setView('genres')}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Layers className="h-3.5 w-3.5" />
            Genres
          </button>
          <button
            onClick={() => setView('kinds')}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Settings2 className="h-3.5 w-3.5" />
            Kinds
          </button>
          <div className="relative">
            <button
              onClick={() => setCreateKindOpen(!createKindOpen)}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" />
              New Entity
            </button>
            {createKindOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setCreateKindOpen(false)} />
                <div className="absolute right-0 top-full z-50 mt-1 w-48 rounded-md border bg-card shadow-lg">
                  {visibleKinds.map((k) => (
                    <button
                      key={k.kind_id}
                      onClick={() => void handleCreate(k.kind_id)}
                      className="flex w-full items-center gap-2 px-3 py-2 text-xs hover:bg-secondary transition-colors first:rounded-t-md last:rounded-b-md"
                    >
                      <span>{k.icon}</span>
                      <span>{k.name}</span>
                    </button>
                  ))}
                  {visibleKinds.length === 0 && (
                    <p className="px-3 py-2 text-xs text-muted-foreground">No kinds available</p>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Search + Filter bar */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={filters.searchQuery}
            onChange={(e) => setFilters((f) => ({ ...f, searchQuery: e.target.value }))}
            placeholder="Search entities..."
            className="w-full rounded-md border bg-background pl-9 pr-3 py-1.5 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <button
          onClick={() => setFilterOpen(!filterOpen)}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
            activeFilterCount > 0
              ? 'border-primary/40 text-primary hover:bg-primary/10'
              : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
          )}
        >
          <Filter className="h-3.5 w-3.5" />
          {activeFilterCount > 0 ? `${activeFilterCount} filter${activeFilterCount > 1 ? 's' : ''}` : 'Filter'}
        </button>
      </div>

      {/* Filter panel */}
      {filterOpen && (
        <div className="rounded-lg border bg-card p-3 space-y-3">
          <div className="space-y-1.5">
            <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Kind</span>
            <div className="flex flex-wrap gap-1.5">
              {visibleKinds.map((k) => {
                const active = filters.kindCodes.includes(k.code);
                return (
                  <button
                    key={k.kind_id}
                    onClick={() => setFilters((f) => ({
                      ...f,
                      kindCodes: active ? f.kindCodes.filter((c) => c !== k.code) : [...f.kindCodes, k.code],
                    }))}
                    className={cn(
                      'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium border transition-colors',
                      active ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <span>{k.icon}</span> {k.name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="space-y-1.5">
            <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Status</span>
            <div className="flex gap-1.5">
              {(['all', 'draft', 'active', 'inactive'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setFilters((f) => ({ ...f, status: s }))}
                  className={cn(
                    'rounded-full px-2.5 py-1 text-[11px] font-medium border transition-colors',
                    filters.status === s ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:text-foreground',
                  )}
                >
                  {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>
          </div>
          {activeFilterCount > 0 && (
            <button
              onClick={() => setFilters(defaultFilters)}
              className="text-[10px] text-primary hover:underline"
            >
              Clear all filters
            </button>
          )}
        </div>
      )}

      {/* Entity list */}
      {entities.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="No entities yet"
          description="Create your first glossary entity — characters, places, items, and more."
        />
      ) : (
        <div className="rounded-lg border divide-y">
          {entities.map((e) => (
            <div
              key={e.entity_id}
              onClick={() => setSelectedEntityId(e.entity_id)}
              className={cn(
                'flex items-center gap-3 px-4 py-3 hover:bg-card/50 transition-colors group cursor-pointer',
                selectedEntityId === e.entity_id && 'bg-primary/5 border-l-2 border-l-primary',
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">
                    {e.display_name || 'Untitled'}
                  </span>
                  <KindBadge kind={e.kind} />
                  <span className={cn('rounded-full px-1.5 py-0.5 text-[9px] font-medium', STATUS_COLORS[e.status])}>
                    {e.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-0.5 text-[10px] text-muted-foreground">
                  {e.chapter_link_count > 0 && <span>{e.chapter_link_count} chapter{e.chapter_link_count !== 1 ? 's' : ''}</span>}
                  {e.translation_count > 0 && <span>{e.translation_count} translation{e.translation_count !== 1 ? 's' : ''}</span>}
                  {e.evidence_count > 0 && <span>{e.evidence_count} evidence{e.evidence_count !== 1 ? 's' : ''}</span>}
                  {e.tags.length > 0 && <span>{e.tags.join(', ')}</span>}
                </div>
              </div>
              <button
                onClick={() => setDeleteTarget(e)}
                className="opacity-0 group-hover:opacity-100 rounded p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                title="Delete"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title="Delete entity?"
        description={`"${deleteTarget?.display_name || 'Untitled'}" will be moved to the recycle bin.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => void handleDelete()}
      />

      {/* Entity Editor Modal */}
      {selectedEntityId && (
        <EntityEditorModal
          bookId={bookId}
          entityId={selectedEntityId}
          onClose={() => setSelectedEntityId(null)}
          onSaved={() => invalidate()}
          onDelete={() => {
            setDeleteTarget(entities.find((e) => e.entity_id === selectedEntityId) ?? null);
          }}
        />
      )}
    </div>
  );
}
