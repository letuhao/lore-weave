import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { useEntityKinds } from '@/features/glossary/hooks/useEntityKinds';
import { useGlossaryEntities } from '@/features/glossary/hooks/useGlossaryEntities';
import { useEntityDetail } from '@/features/glossary/hooks/useEntityDetail';
import { glossaryApi } from '@/features/glossary/api';
import { CreateEntityModal } from '@/features/glossary/components/CreateEntityModal';
import { GlossaryEntityCard } from '@/features/glossary/components/GlossaryEntityCard';
import { GlossaryFiltersBar } from '@/features/glossary/components/GlossaryFiltersBar';
import { EntityDetailPanel } from '@/features/glossary/components/EntityDetailPanel';
import type { EntityKind } from '@/features/glossary/types';

/**
 * SP-2: Full entity list + filters + detail panel + create flow.
 */
export function GlossaryPage() {
  const { bookId = '' } = useParams();
  const { accessToken } = useAuth();

  const { kinds, isLoading: kindsLoading } = useEntityKinds();
  const {
    entities,
    total,
    isLoading,
    isLoadingMore,
    error,
    filters,
    hasMore,
    setFilters,
    loadMore,
    removeEntity,
    refresh,
  } = useGlossaryEntities(bookId);

  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  const {
    entity: detailEntity,
    isLoading: detailLoading,
    isSaving,
    patch,
    refetch: refetchDetail,
  } = useEntityDetail(bookId, selectedEntityId);

  async function handleKindSelect(kind: EntityKind) {
    if (!accessToken) return;
    setIsCreating(true);
    setCreateError('');
    try {
      const created = await glossaryApi.createEntity(bookId, kind.kind_id, accessToken);
      setIsCreateOpen(false);
      refresh();
      setSelectedEntityId(created.entity_id);
    } catch (e: unknown) {
      setCreateError((e as Error).message || 'Failed to create entity');
    } finally {
      setIsCreating(false);
    }
  }

  async function handleDelete(entityId: string) {
    if (!accessToken) return;
    try {
      await glossaryApi.deleteEntity(bookId, entityId, accessToken);
      removeEntity(entityId);
      if (selectedEntityId === entityId) setSelectedEntityId(null);
    } catch {
      // ignore — card already closed optimistically
    }
  }

  async function handleSetInactive(entityId: string) {
    if (!accessToken) return;
    try {
      await glossaryApi.patchEntity(bookId, entityId, { status: 'inactive' }, accessToken);
      refresh();
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* ── Toolbar ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Glossary</h1>
          <p className="text-xs text-muted-foreground">
            {total} {total === 1 ? 'entity' : 'entities'}
          </p>
        </div>
        <button
          onClick={() => { setIsCreateOpen(true); setCreateError(''); }}
          className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-muted"
        >
          + New Entity
        </button>
      </div>

      {/* ── Filters ──────────────────────────────────────────────────────────── */}
      {!kindsLoading && (
        <GlossaryFiltersBar filters={filters} kinds={kinds} onChange={setFilters} />
      )}

      {/* ── Error ────────────────────────────────────────────────────────────── */}
      {error && (
        <p className="rounded border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {/* ── Entity list ──────────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded border bg-muted" />
          ))}
        </div>
      ) : entities.length === 0 ? (
        <div className="rounded border p-8 text-center text-sm text-muted-foreground">
          No entities yet. Click <strong>+ New Entity</strong> to create your first.
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {entities.map((entity) => (
              <GlossaryEntityCard
                key={entity.entity_id}
                entity={entity}
                isSelected={selectedEntityId === entity.entity_id}
                onClick={() => setSelectedEntityId(entity.entity_id)}
                onDelete={() => handleDelete(entity.entity_id)}
                onSetInactive={() => handleSetInactive(entity.entity_id)}
              />
            ))}
          </div>

          {hasMore && (
            <div className="flex justify-center pt-2">
              <button
                onClick={loadMore}
                disabled={isLoadingMore}
                className="rounded border px-4 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                {isLoadingMore ? 'Loading…' : `Load more (${total - entities.length} remaining)`}
              </button>
            </div>
          )}
        </>
      )}

      {/* ── Create entity modal ───────────────────────────────────────────────── */}
      {isCreateOpen && (
        <CreateEntityModal
          kinds={kinds}
          onSelect={handleKindSelect}
          onClose={() => setIsCreateOpen(false)}
          isCreating={isCreating}
          createError={createError}
        />
      )}

      {/* ── Entity detail panel ───────────────────────────────────────────────── */}
      {selectedEntityId && (
        <EntityDetailPanel
          entity={detailEntity}
          bookId={bookId}
          token={accessToken ?? ''}
          isLoading={detailLoading}
          isSaving={isSaving}
          onClose={() => setSelectedEntityId(null)}
          onPatch={patch}
          onRefresh={refetchDetail}
        />
      )}
    </div>
  );
}
